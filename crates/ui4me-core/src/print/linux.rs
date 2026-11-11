//! Native printing on Linux (1.0 F1002): the xdg-desktop-portal Print interface. `PreparePrint`
//! shows the desktop's print dialog (KDE: the Qt dialog, including print to file); `Print` then
//! receives the job's PDF through a file descriptor. Runs on a worker thread; the outcome is one
//! `print` event. The PDF lives in a private temporary file removed after the call.

use super::Page;
use serde_json::json;
use std::collections::HashMap;
use std::sync::mpsc::channel;
use std::time::Duration;
use zbus::blocking::{Connection, Proxy};
use zbus::zvariant::{Fd, OwnedValue, Value};

const PORTAL: &str = "org.freedesktop.portal.Desktop";
const PATH: &str = "/org/freedesktop/portal/desktop";
const IFACE: &str = "org.freedesktop.portal.Print";
/// The user may keep the dialog open this long.
const DIALOG_WAIT: Duration = Duration::from_secs(30 * 60);
const PRINT_WAIT: Duration = Duration::from_secs(10 * 60);

type Response = (u32, HashMap<String, OwnedValue>);

fn request(
    conn: &Connection,
    method: &str,
    token: &str,
    call: impl FnOnce() -> zbus::Result<zbus::Message>,
    wait: Duration,
) -> Result<Response, String> {
    let me = conn
        .unique_name()
        .map(|n| n.as_str().to_owned())
        .unwrap_or_default();
    let path = format!(
        "/org/freedesktop/portal/desktop/request/{}/{token}",
        me.trim_start_matches(':').replace('.', "_")
    );
    let req = Proxy::new(conn, PORTAL, path, "org.freedesktop.portal.Request")
        .map_err(|e| format!("portal request: {e}"))?;
    let mut signals = req
        .receive_signal("Response")
        .map_err(|e| format!("portal request: {e}"))?;
    call().map_err(|e| format!("{method}: {e}"))?;
    let (tx, rx) = channel();
    std::thread::Builder::new()
        .name("ui4me-print-wait".into())
        .spawn(move || {
            let r = signals
                .next()
                .and_then(|m| m.body().deserialize::<Response>().ok());
            let _ = tx.send(r);
        })
        .map_err(|e| e.to_string())?;
    match rx.recv_timeout(wait) {
        Ok(Some(r)) => Ok(r),
        Ok(None) => Err(format!("{method}: no response")),
        Err(_) => Err(format!(
            "{method}: the print dialog did not answer within {} s",
            wait.as_secs()
        )),
    }
}

/// Print `pages`; returns the `print` event body (status, reason).
pub fn print(job: u64, pages: &[Page], title: &str) -> serde_json::Value {
    match run(job, pages, title) {
        Ok(v) => v,
        Err(reason) => json!({"status": "failed", "reason": reason}),
    }
}

fn run(job: u64, pages: &[Page], title: &str) -> Result<serde_json::Value, String> {
    let conn = Connection::session().map_err(|e| format!("session bus: {e}"))?;
    let has = conn
        .call_method(
            Some("org.freedesktop.DBus"),
            "/org/freedesktop/DBus",
            Some("org.freedesktop.DBus"),
            "NameHasOwner",
            &(PORTAL,),
        )
        .ok()
        .and_then(|m| m.body().deserialize::<bool>().ok())
        .unwrap_or(false);
    if !has {
        return Ok(
            json!({"status": "unavailable", "reason": "no xdg-desktop-portal on the session bus"}),
        );
    }
    let pid = std::process::id();
    let t1 = format!("ui4me_print_{pid}_{job}_prepare");
    let mut opts: HashMap<&str, Value<'_>> = HashMap::new();
    opts.insert("handle_token", Value::from(t1.clone()));
    opts.insert("modal", Value::from(true));
    let settings: HashMap<&str, Value<'_>> = HashMap::new();
    let setup: HashMap<&str, Value<'_>> = HashMap::new();
    let (code, results) = request(
        &conn,
        "PreparePrint",
        &t1,
        || {
            conn.call_method(
                Some(PORTAL),
                PATH,
                Some(IFACE),
                "PreparePrint",
                &("", title, settings, setup, opts),
            )
        },
        DIALOG_WAIT,
    )?;
    match code {
        0 => {}
        1 => return Ok(json!({"status": "cancelled"})),
        _ => return Ok(json!({"status": "failed", "reason": "the print dialog failed"})),
    }
    let token: u32 = results
        .get("token")
        .and_then(|v| u32::try_from(v).ok())
        .ok_or("PreparePrint returned no token")?;
    // The PDF, in a private temporary file.
    let dir = std::env::var_os("XDG_RUNTIME_DIR")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(std::env::temp_dir);
    let path = dir.join(format!("ui4me-print-{pid}-{job}.pdf"));
    {
        use std::os::unix::fs::OpenOptionsExt;
        let mut f = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&path)
            .map_err(|e| format!("print file: {e}"))?;
        std::io::Write::write_all(&mut f, &super::pdf(pages, title))
            .map_err(|e| format!("print file: {e}"))?;
    }
    let file = std::fs::File::open(&path).map_err(|e| format!("print file: {e}"));
    let _ = std::fs::remove_file(&path);
    let file = file?;
    let t2 = format!("ui4me_print_{pid}_{job}_print");
    let mut opts: HashMap<&str, Value<'_>> = HashMap::new();
    opts.insert("handle_token", Value::from(t2.clone()));
    opts.insert("token", Value::from(token));
    opts.insert("modal", Value::from(true));
    use std::os::fd::AsFd;
    let fd = Fd::from(file.as_fd());
    let (code, _) = request(
        &conn,
        "Print",
        &t2,
        || {
            conn.call_method(
                Some(PORTAL),
                PATH,
                Some(IFACE),
                "Print",
                &("", title, fd, opts),
            )
        },
        PRINT_WAIT,
    )?;
    Ok(match code {
        0 => json!({"status": "printed"}),
        1 => json!({"status": "cancelled"}),
        _ => json!({"status": "failed", "reason": "the print service failed"}),
    })
}
