//! These tests are authored for local/CI execution; the reconstruction was not executed.
use super::*;
use crate::runtime::{lock, Session};
use std::sync::{Arc, Mutex, MutexGuard};

static SERIAL: Mutex<()> = Mutex::new(());
struct Capture {
    mode: u8,
    events: Mutex<Vec<Value>>,
}

extern "C" fn callback(id: u64, text: *const c_char, user: *mut c_void) -> i32 {
    // No panic may cross an extern C callback, including in test code.
    catch_unwind(AssertUnwindSafe(|| {
        let capture = unsafe { &*(user as *const Capture) };
        let event: Value =
            serde_json::from_slice(unsafe { CStr::from_ptr(text) }.to_bytes()).map_err(|_| ())?;
        lock(&capture.events).push(event.clone());
        let session = runtime::get(id).map_err(|_| ())?;
        match (capture.mode, event["type"].as_str()) {
            (0, Some("started")) => {
                session.stop().map_err(|_| ())?;
            }
            (1, Some("started")) => return Ok(-1),
            (2, Some("started")) => {
                session.post(42).map_err(|_| ())?;
            }
            (2, Some("post")) => {
                session.command(json!({"op":"stats"})).map_err(|_| ())?;
                session.stop().map_err(|_| ())?;
            }
            (3, Some("started")) => {
                session
                    .command(json!({"op":"timer","token":7,"milliseconds":1,"repeat":true}))
                    .map_err(|_| ())?;
            }
            (3, Some("timer")) => {
                session
                    .command(json!({"op":"cancel_timer","token":7}))
                    .map_err(|_| ())?;
                session.stop().map_err(|_| ())?;
            }
            (4, Some("close_requested")) => {
                session.stop().map_err(|_| ())?;
                return Ok(1);
            }
            _ => {}
        }
        Ok::<i32, ()>(0)
    }))
    .ok()
    .and_then(|r| r.ok())
    .unwrap_or(-1)
}

struct Harness {
    _serial: MutexGuard<'static, ()>,
    session: Arc<Session>,
    capture: Box<Capture>,
}
impl Harness {
    fn new(mode: u8) -> Self {
        let serial = lock(&SERIAL);
        let mut capture = Box::new(Capture {
            mode,
            events: Mutex::new(Vec::new()),
        });
        let user = (&mut *capture as *mut Capture).cast();
        let id = runtime::create(json!({"backend":"headless"}), Some(callback), user).unwrap();
        Self {
            _serial: serial,
            session: runtime::get(id).unwrap(),
            capture,
        }
    }
    fn events(&self) -> Vec<Value> {
        lock(&self.capture.events).clone()
    }
}
impl Drop for Harness {
    fn drop(&mut self) {
        let _ = runtime::destroy(self.session.id);
    }
}

#[test]
fn session_is_terminal_and_destroyed_ids_are_stale() {
    let h = Harness::new(0);
    h.session.run().unwrap();
    assert!(h.session.run().is_err());
    assert_eq!(h.events().first().unwrap()["type"], "started");
    assert_eq!(h.events().last().unwrap()["type"], "stopped");
    runtime::destroy(h.session.id).unwrap();
    assert_eq!(runtime::get(h.session.id).err().unwrap().code, 4);
    let next = runtime::create(json!({"backend":"headless"}), None, ptr::null_mut()).unwrap();
    assert_ne!(h.session.id, next);
    runtime::destroy(next).unwrap();
}

#[test]
fn concurrent_session_is_rejected() {
    let _h = Harness::new(0);
    assert_eq!(
        runtime::create(json!({"backend":"headless"}), None, ptr::null_mut())
            .unwrap_err()
            .code,
        2
    );
}

#[test]
fn invalid_resize_does_not_partially_change_window() {
    let h = Harness::new(0);
    let id = h
        .session
        .command(json!({"op":"open","html":"<p>Hello</p>","width":640,"height":480}))
        .unwrap()["window"]
        .as_u64()
        .unwrap();
    assert!(h
        .session
        .command(json!({"op":"resize","window":id,"width":800,"height":1}))
        .is_err());
    let state = lock(&h.session.state);
    let window = &state.windows[&id];
    assert_eq!(
        (window.width, window.height, window.resize_revision),
        (640, 480, 0)
    );
}

#[test]
fn callback_failure_returns_after_cleanup() {
    let h = Harness::new(1);
    let window = h
        .session
        .command(json!({"op":"open","html":"<p>Hello</p>"}))
        .unwrap()["window"]
        .as_u64()
        .unwrap();
    assert_eq!(h.session.run().unwrap_err().code, 7);
    assert!(h
        .events()
        .iter()
        .any(|e| e["type"] == "closed" && e["window"] == window));
    assert_eq!(
        h.session.command(json!({"op":"stats"})).unwrap()["windows"],
        0
    );
}

#[test]
fn post_queue_is_bounded_and_prestop_settles_every_post() {
    let h = Harness::new(0);
    for token in 0..512 {
        h.session.post(token).unwrap();
    }
    assert_eq!(h.session.post(513).unwrap_err().code, 5);
    h.session.stop().unwrap();
    h.session.run().unwrap();
    let stats = h.session.command(json!({"op":"stats"})).unwrap();
    assert_eq!(stats["posted"], 512);
    assert_eq!(stats["cancelled"], 512);
    assert_eq!(stats["executed"], 0);
}

#[test]
fn post_callback_can_reenter_commands_without_deadlock() {
    let h = Harness::new(2);
    h.session.run().unwrap();
    assert!(h
        .events()
        .iter()
        .any(|e| e["type"] == "post" && e["token"] == 42));
    assert_eq!(
        h.session.command(json!({"op":"stats"})).unwrap()["executed"],
        1
    );
}

#[test]
fn repeating_timer_can_cancel_itself() {
    let h = Harness::new(3);
    h.session.run().unwrap();
    assert_eq!(
        h.events().iter().filter(|e| e["type"] == "timer").count(),
        1
    );
}

#[test]
fn cross_thread_mutation_is_rejected_but_stop_is_safe() {
    let h = Harness::new(0);
    let session = h.session.clone();
    let (code, stop) = std::thread::spawn(move || {
        (
            session.command(json!({"op":"stats"})).unwrap_err().code,
            session.stop().is_ok(),
        )
    })
    .join()
    .unwrap();
    assert_eq!(code, 3);
    assert!(stop);
    h.session.run().unwrap();
}

#[test]
fn forced_stop_overrides_close_veto() {
    let h = Harness::new(4);
    let id = h
        .session
        .command(json!({"op":"open","html":"<button id='ok'>OK</button>"}))
        .unwrap()["window"]
        .as_u64()
        .unwrap();
    h.session
        .command(json!({"op":"close","window":id}))
        .unwrap();
    h.session.run().unwrap();
    assert!(h.events().iter().any(|e| e["type"] == "close_requested"));
    assert!(h.events().iter().any(|e| e["type"] == "closed"));
}

#[test]
fn multiple_windows_close_before_terminal_event() {
    let h = Harness::new(5);
    for _ in 0..2 {
        let id = h
            .session
            .command(json!({"op":"open","html":"<p>Hello</p>"}))
            .unwrap()["window"]
            .as_u64()
            .unwrap();
        h.session
            .command(json!({"op":"close","window":id}))
            .unwrap();
    }
    h.session.run().unwrap();
    assert_eq!(
        h.events().iter().filter(|e| e["type"] == "closed").count(),
        2
    );
    assert_eq!(h.events().last().unwrap()["type"], "stopped");
}
