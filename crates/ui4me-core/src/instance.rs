//! Single instance and "open with" delivery (0.7 F0710).
//!
//! An app opts in with `claim_instance {open_files}` at startup. The first instance of an
//! `app_id` (per user) becomes the primary and listens on a private endpoint: a Unix socket in
//! `$XDG_RUNTIME_DIR` (mode 0700, per user) on Linux, a named pipe on Windows. A later instance
//! connects, forwards its paths and is told it is not the primary (it should exit). The primary
//! receives forwarded paths as `open_files` events with `source: "second_instance"`, and its own
//! startup paths as `source: "startup"`. The message is data only — a bounded JSON list of path
//! strings — never a command line or a shell request; nothing installs file associations.

use serde_json::{json, Value};
#[cfg(unix)]
use std::io::Read;
use std::io::Write;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

/// Paths per message / bytes per path / message bytes.
const MAX_PATHS: usize = 256;
const MAX_PATH_BYTES: usize = 4096;
const MAX_MESSAGE: usize = 1024 * 1024 + 4096;

/// Validate paths received from another process or the app.
pub fn validate_paths(paths: &[String]) -> Result<(), String> {
    if paths.len() > MAX_PATHS {
        return Err(format!("at most {MAX_PATHS} paths"));
    }
    if paths
        .iter()
        .any(|p| p.is_empty() || p.len() > MAX_PATH_BYTES || p.contains('\0'))
    {
        return Err(format!(
            "each path is 1..{MAX_PATH_BYTES} bytes without NUL"
        ));
    }
    Ok(())
}

fn decode(bytes: &[u8]) -> Option<Vec<String>> {
    let v: Value = serde_json::from_slice(bytes).ok()?;
    let paths: Vec<String> = v
        .get("open_files")?
        .as_array()?
        .iter()
        .map(|p| p.as_str().map(str::to_owned))
        .collect::<Option<_>>()?;
    validate_paths(&paths).ok()?;
    Some(paths)
}

fn endpoint_name(app_id: &str) -> String {
    // app_id is validated ASCII [A-Za-z0-9._-]{1,128}.
    format!("ui4me-instance-{app_id}")
}

/// The primary's listener; dropping it stops listening and removes the endpoint.
pub struct Listener {
    stop: Arc<AtomicBool>,
    #[cfg(unix)]
    path: std::path::PathBuf,
    #[cfg(windows)]
    name: String,
}

impl Drop for Listener {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
        #[cfg(unix)]
        {
            // Wake the accept loop so its thread ends, then remove the socket file.
            let _ = std::os::unix::net::UnixStream::connect(&self.path);
            let _ = std::fs::remove_file(&self.path);
        }
        #[cfg(windows)]
        {
            // Wake the pending ConnectNamedPipe so the thread sees the stop flag.
            let _ = std::fs::OpenOptions::new().write(true).open(&self.name);
        }
    }
}

/// The outcome of a claim.
pub enum Claim {
    /// This process is the primary: it listens; `deliver` receives forwarded path lists.
    Primary(Listener),
    /// Another instance is the primary and received the paths.
    Forwarded,
}

#[cfg(unix)]
pub fn claim(
    app_id: &str,
    paths: &[String],
    deliver: Arc<dyn Fn(Vec<String>) + Send + Sync>,
) -> Result<Claim, String> {
    use std::os::unix::fs::PermissionsExt;
    use std::os::unix::net::{UnixListener, UnixStream};
    let dir = std::env::var_os("XDG_RUNTIME_DIR")
        .map(std::path::PathBuf::from)
        .ok_or("single instance needs XDG_RUNTIME_DIR (a private per-user directory)")?;
    let meta = std::fs::metadata(&dir).map_err(|e| format!("XDG_RUNTIME_DIR: {e}"))?;
    if meta.permissions().mode() & 0o077 != 0 {
        return Err("XDG_RUNTIME_DIR is accessible to other users".into());
    }
    let path = dir.join(format!("{}.sock", endpoint_name(app_id)));
    let message = serde_json::to_vec(&json!({"open_files": paths})).map_err(|e| e.to_string())?;
    // A primary is running if it accepts a connection.
    if let Ok(mut s) = UnixStream::connect(&path) {
        s.set_write_timeout(Some(std::time::Duration::from_secs(2)))
            .ok();
        s.write_all(&message)
            .map_err(|e| format!("forwarding to the running instance: {e}"))?;
        return Ok(Claim::Forwarded);
    }
    // No primary: remove a stale socket and listen.
    let _ = std::fs::remove_file(&path);
    let listener =
        UnixListener::bind(&path).map_err(|e| format!("listening for other instances: {e}"))?;
    let _ = std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600));
    let stop = Arc::new(AtomicBool::new(false));
    let flag = stop.clone();
    std::thread::Builder::new()
        .name("ui4me-instance".into())
        .spawn(move || {
            for stream in listener.incoming() {
                if flag.load(Ordering::Acquire) {
                    break;
                }
                let Ok(mut s) = stream else { continue };
                s.set_read_timeout(Some(std::time::Duration::from_secs(2)))
                    .ok();
                let mut buf = Vec::new();
                if (&mut s)
                    .take(MAX_MESSAGE as u64)
                    .read_to_end(&mut buf)
                    .is_ok()
                {
                    if let Some(paths) = decode(&buf) {
                        deliver(paths);
                    }
                }
            }
        })
        .map_err(|e| e.to_string())?;
    Ok(Claim::Primary(Listener { stop, path }))
}

#[cfg(windows)]
pub fn claim(
    app_id: &str,
    paths: &[String],
    deliver: Arc<dyn Fn(Vec<String>) + Send + Sync>,
) -> Result<Claim, String> {
    use windows_sys::Win32::Foundation::{CloseHandle, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::Storage::FileSystem::{
        ReadFile, FILE_FLAG_FIRST_PIPE_INSTANCE, PIPE_ACCESS_INBOUND,
    };
    use windows_sys::Win32::System::Pipes::{
        ConnectNamedPipe, CreateNamedPipeW, DisconnectNamedPipe, PIPE_READMODE_BYTE,
        PIPE_REJECT_REMOTE_CLIENTS, PIPE_TYPE_BYTE, PIPE_WAIT,
    };
    let user = std::env::var("USERNAME").unwrap_or_default();
    let user: String = user.chars().filter(|c| c.is_ascii_alphanumeric()).collect();
    let name = format!(r"\\.\pipe\{}-{user}", endpoint_name(app_id));
    let message = serde_json::to_vec(&json!({"open_files": paths})).map_err(|e| e.to_string())?;
    if let Ok(mut f) = std::fs::OpenOptions::new().write(true).open(&name) {
        f.write_all(&message)
            .map_err(|e| format!("forwarding to the running instance: {e}"))?;
        return Ok(Claim::Forwarded);
    }
    let wide: Vec<u16> = name.encode_utf16().chain(std::iter::once(0)).collect();
    let create = |first: bool| unsafe {
        // SAFETY: `wide` is NUL-terminated; the default security descriptor grants the creator
        // (this user) and administrators access; remote clients are rejected.
        CreateNamedPipeW(
            wide.as_ptr(),
            PIPE_ACCESS_INBOUND
                | if first {
                    FILE_FLAG_FIRST_PIPE_INSTANCE
                } else {
                    0
                },
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
            1,
            0,
            MAX_MESSAGE as u32,
            0,
            std::ptr::null(),
        )
    };
    let first = create(true);
    if first == INVALID_HANDLE_VALUE {
        return Err("another instance owns the endpoint but did not accept the paths".into());
    }
    let stop = Arc::new(AtomicBool::new(false));
    let flag = stop.clone();
    let first = first as isize;
    std::thread::Builder::new()
        .name("ui4me-instance".into())
        .spawn(move || {
            let handle = first as windows_sys::Win32::Foundation::HANDLE;
            loop {
                // SAFETY: `handle` is a pipe instance this thread owns.
                let connected = unsafe { ConnectNamedPipe(handle, std::ptr::null_mut()) } != 0
                    || std::io::Error::last_os_error().raw_os_error() == Some(535); // ERROR_PIPE_CONNECTED
                if flag.load(Ordering::Acquire) {
                    unsafe { CloseHandle(handle) };
                    break;
                }
                if connected {
                    let mut buf = vec![0u8; MAX_MESSAGE];
                    let mut total = 0usize;
                    loop {
                        let mut read = 0u32;
                        // SAFETY: reads into the owned buffer within its length.
                        let ok = unsafe {
                            ReadFile(
                                handle,
                                buf[total..].as_mut_ptr().cast(),
                                (buf.len() - total) as u32,
                                &mut read,
                                std::ptr::null_mut(),
                            )
                        } != 0;
                        if !ok || read == 0 {
                            break;
                        }
                        total += read as usize;
                        if total >= buf.len() {
                            break;
                        }
                    }
                    if let Some(paths) = decode(&buf[..total]) {
                        deliver(paths);
                    }
                    unsafe { DisconnectNamedPipe(handle) };
                }
                if flag.load(Ordering::Acquire) {
                    unsafe { CloseHandle(handle) };
                    break;
                }
            }
        })
        .map_err(|e| e.to_string())?;
    Ok(Claim::Primary(Listener { stop, name }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn messages_are_bounded_path_lists_only() {
        assert_eq!(
            decode(r#"{"open_files":["/a/ž b.txt"]}"#.as_bytes()),
            Some(vec!["/a/ž b.txt".into()])
        );
        assert_eq!(decode(br#"{"open_files":["a", 5]}"#), None);
        assert_eq!(decode(br#"{"command":"rm -rf"}"#), None);
        assert_eq!(decode(br#"{"open_files":[""]}"#), None);
        let many: Vec<String> = (0..300).map(|i| format!("/{i}")).collect();
        assert!(validate_paths(&many).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn a_second_claim_forwards_to_the_first() {
        let dir = std::env::temp_dir().join(format!("ui4me-instance-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&dir, std::fs::Permissions::from_mode(0o700)).unwrap();
        // SAFETY of the test: XDG_RUNTIME_DIR is only read by `claim` in this test process.
        std::env::set_var("XDG_RUNTIME_DIR", &dir);
        let got = Arc::new(std::sync::Mutex::new(Vec::new()));
        let sink = got.clone();
        let deliver: Arc<dyn Fn(Vec<String>) + Send + Sync> =
            Arc::new(move |p| sink.lock().unwrap().push(p));
        let primary = claim("org.ui4me.test", &[], deliver.clone()).unwrap();
        assert!(matches!(primary, Claim::Primary(_)));
        assert!(matches!(
            claim("org.ui4me.test", &["/tmp/ü.txt".into()], deliver).unwrap(),
            Claim::Forwarded
        ));
        for _ in 0..50 {
            if !got.lock().unwrap().is_empty() {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(20));
        }
        assert_eq!(*got.lock().unwrap(), vec![vec!["/tmp/ü.txt".to_string()]]);
        drop(primary);
        assert!(
            !dir.join("ui4me-instance-org.ui4me.test.sock").exists(),
            "the endpoint is removed"
        );
        let _ = std::fs::remove_dir_all(&dir);
    }
}
