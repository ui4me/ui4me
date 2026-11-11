//! ui4me ABI 1. Foreign callers must obey the pointer and callback lifetime contract.
mod diagnostics;
mod document;
#[cfg(test)]
mod fuzz_gate;
mod instance;
#[cfg(feature = "native")]
mod native;
mod print;
mod protocol;
mod runtime;
pub(crate) mod services;
#[cfg(test)]
mod tests;

use serde_json::{json, Value};
use std::cell::RefCell;
use std::ffi::{c_char, c_void, CStr, CString};
use std::panic::{catch_unwind, AssertUnwindSafe};
use std::ptr;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::OnceLock;

static POISONED: AtomicBool = AtomicBool::new(false);
pub type Result<T> = std::result::Result<T, Error>;

#[derive(Clone, Debug)]
pub struct Error {
    pub code: i32,
    pub message: String,
}
impl Error {
    fn new(code: i32, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }
    pub(crate) fn arg(message: impl Into<String>) -> Self {
        Self::new(1, message)
    }
    pub(crate) fn state(message: impl Into<String>) -> Self {
        Self::new(2, message)
    }
    pub(crate) fn thread(message: impl Into<String>) -> Self {
        Self::new(3, message)
    }
    pub(crate) fn stale(message: impl Into<String>) -> Self {
        Self::new(4, message)
    }
    pub(crate) fn limit(message: impl Into<String>) -> Self {
        Self::new(5, message)
    }
    pub(crate) fn native(message: impl Into<String>) -> Self {
        Self::new(6, message)
    }
    pub(crate) fn callback(message: impl Into<String>) -> Self {
        Self::new(7, message)
    }
    pub(crate) fn poison(message: impl Into<String>) -> Self {
        Self::new(8, message)
    }
    pub(crate) fn io(message: impl Into<String>) -> Self {
        Self::new(9, message)
    }
}
impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.message)
    }
}
impl std::error::Error for Error {}

thread_local! {
    static LAST_ERROR: RefCell<CString> = RefCell::new(CString::new("").expect("empty CString"));
    static OUTPUT: RefCell<CString> = RefCell::new(CString::new("{}").expect("JSON CString"));
}

fn guard(action: impl FnOnce() -> Result<()>) -> i32 {
    let result = catch_unwind(AssertUnwindSafe(action));
    let error = match result {
        Ok(Ok(())) => {
            LAST_ERROR.with(|v| *v.borrow_mut() = CString::default());
            return 0;
        }
        Ok(Err(error)) => error,
        Err(_) => {
            POISONED.store(true, Ordering::Release);
            // Recover mutex poison only to settle data and refuse further sessions.
            runtime::poison_active();
            Error::poison("Rust panic contained; restart the process before using ui4me again")
        }
    };
    let text = json!({"code":error.code,"message":error.message}).to_string();
    LAST_ERROR.with(|v| *v.borrow_mut() = CString::new(text).unwrap_or_default());
    error.code
}

/// # Safety
/// The pointer must refer to a readable, NUL-terminated UTF-8 string for the duration of this call.
unsafe fn parse(pointer: *const c_char) -> Result<Value> {
    if pointer.is_null() {
        return Err(Error::arg("null JSON pointer"));
    }
    let bytes = unsafe { CStr::from_ptr(pointer) }.to_bytes();
    if bytes.len() > 2 * 1024 * 1024 {
        return Err(Error::limit("JSON exceeds 2 MiB"));
    }
    serde_json::from_slice(bytes).map_err(|e| Error::arg(format!("invalid JSON: {e}")))
}

#[no_mangle]
pub extern "C" fn ui4me_abi_version() -> u32 {
    1
}

#[no_mangle]
pub extern "C" fn ui4me_build_info() -> *const c_char {
    static INFO: OnceLock<CString> = OnceLock::new();
    INFO.get_or_init(|| {
        CString::new(
            json!({
                "product":"ui4me", "version":env!("CARGO_PKG_VERSION"), "abi":1,
                "source_id":env!("UI4ME_SOURCE_ID"), "git_revision":env!("UI4ME_GIT_REVISION"),
                "target":env!("UI4ME_BUILD_TARGET"), "renderer":"foundation", "profile":"ui4me-foundation-0.2",
                "capabilities":["html","css","text","flex","controls","local-assets","multi-window","reserved-completions"],
                "native_compiled":cfg!(feature="native")
            })
            .to_string(),
        )
        .expect("JSON escapes NUL")
    })
    .as_ptr()
}

#[no_mangle]
pub extern "C" fn ui4me_last_error() -> *const c_char {
    LAST_ERROR.with(|v| v.borrow().as_ptr())
}

/// # Safety
/// config is a valid UTF-8 C string; out is writable. callback and user stay valid until destroy.
#[no_mangle]
pub unsafe extern "C" fn ui4me_session_create(
    config: *const c_char,
    callback: Option<runtime::Callback>,
    user: *mut c_void,
    out: *mut u64,
) -> i32 {
    guard(|| {
        if out.is_null() {
            return Err(Error::arg("out_session is null"));
        }
        unsafe {
            *out = 0;
        }
        let id = runtime::create(unsafe { parse(config)? }, callback, user)?;
        unsafe {
            *out = id;
        }
        Ok(())
    })
}

/// # Safety
/// command is a valid UTF-8 C string; out is writable. Output is borrowed and must be copied immediately.
#[no_mangle]
pub unsafe extern "C" fn ui4me_session_command(
    session: u64,
    command: *const c_char,
    out: *mut *const c_char,
) -> i32 {
    guard(|| {
        if out.is_null() {
            return Err(Error::arg("out_json is null"));
        }
        unsafe {
            *out = ptr::null();
        }
        let result = runtime::get(session)?.command(unsafe { parse(command)? })?;
        let text =
            CString::new(result.to_string()).map_err(|_| Error::arg("invalid response string"))?;
        OUTPUT.with(|v| {
            *v.borrow_mut() = text;
            unsafe {
                *out = v.borrow().as_ptr();
            }
        });
        Ok(())
    })
}

#[no_mangle]
pub extern "C" fn ui4me_session_run(session: u64) -> i32 {
    guard(|| runtime::get(session)?.run())
}
#[no_mangle]
pub extern "C" fn ui4me_session_post(session: u64, token: u64) -> i32 {
    guard(|| runtime::get(session)?.post(token))
}
#[no_mangle]
pub extern "C" fn ui4me_session_stop(session: u64) -> i32 {
    guard(|| runtime::get(session)?.stop())
}
#[no_mangle]
pub extern "C" fn ui4me_session_destroy(session: u64) -> i32 {
    guard(|| runtime::destroy(session))
}

/// Publish a previously reserved completion ticket from any thread.
#[no_mangle]
pub extern "C" fn ui4me_session_complete(session: u64, token: u64) -> i32 {
    guard(|| runtime::get(session)?.complete(token))
}
