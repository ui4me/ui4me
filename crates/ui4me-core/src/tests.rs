//! Native runtime and lifecycle contract tests.
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
            (5, Some("resized")) => {
                // Reentry must not deadlock on the native size update lock.
                session.command(json!({"op":"stats"})).map_err(|_| ())?;
            }
            (6, Some("started")) => {
                let result = runtime::destroy(id);
                lock(&capture.events)
                    .push(json!({"type":"destroy_attempt","code":result.err().map(|e|e.code)}));
                session.stop().map_err(|_| ())?;
            }
            (6, Some("stopped")) => {
                let result = runtime::destroy(id);
                lock(&capture.events)
                    .push(json!({"type":"destroy_attempt","code":result.err().map(|e|e.code)}));
            }
            (7, Some("completion")) => {
                session.stop().map_err(|_| ())?;
            }
            (8, Some("started")) => {
                // Exercise the actual inner ABI guard while an outer run and its
                // callback remain on the stack. No panic crosses extern C.
                let status = guard(|| panic!("test-only reentrant ABI panic"));
                lock(&capture.events).push(json!({"type":"panic_status","code":status}));
                let result = runtime::destroy(id);
                lock(&capture.events).push(json!({"type":"destroy_attempt","code":result.err().map(|e|e.code)}));
            }
            (8, Some("stopped")) => {
                let result = runtime::destroy(id);
                lock(&capture.events)
                    .push(json!({"type":"destroy_attempt","code":result.err().map(|e|e.code)}));
            }
            (10, Some("input")) => {
                let window = event["window"].as_u64().ok_or(())?;
                session.command(json!({"op":"replace_children_html","window":window,"element":"content","html":"<input id='editor' value='replacement'>"})).map_err(|_|())?;
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
    let window = h.session.window_info(id).unwrap();
    assert_eq!(
        (window.width, window.height, window.resize_revision),
        (640, 480, 0)
    );
}

#[test]
fn snapshot_round_trips_png_dimensions_and_rgb_pixels() {
    let h = Harness::new(0);
    let id = h
        .session
        .command(json!({"op":"open","html":"<body style=\"background-color:blue\"></body>","width":160,"height":120}))
        .unwrap()["window"]
        .as_u64()
        .unwrap();
    let path = std::env::temp_dir().join(format!(
        "ui4me-snapshot-{}-{}.png",
        std::process::id(),
        h.session.id
    ));
    let result = h
        .session
        .command(json!({"op":"snapshot","window":id,"path":path}))
        .unwrap();
    assert_eq!(result["native_capture"], false);
    assert_eq!(
        (result["width"].as_u64(), result["height"].as_u64()),
        (Some(160), Some(120))
    );
    let file = std::fs::File::open(&path).unwrap();
    let decoder = png::Decoder::new(std::io::BufReader::new(file));
    let mut reader = decoder.read_info().unwrap();
    let mut pixels = vec![0; reader.output_buffer_size().unwrap()];
    let info = reader.next_frame(&mut pixels).unwrap();
    assert_eq!((info.width, info.height), (160, 120));
    assert_eq!(info.color_type, png::ColorType::Rgb);
    assert_eq!(info.bit_depth, png::BitDepth::Eight);
    assert!(pixels[..info.buffer_size()]
        .as_chunks::<3>()
        .0
        .iter()
        .all(|pixel| *pixel == [0, 0, 255]));
    drop(reader);
    std::fs::remove_file(path).unwrap();
}

#[cfg(feature = "native")]
#[test]
fn applied_native_resize_is_reported_once_in_physical_pixels() {
    use winit::dpi::PhysicalSize;
    let h = Harness::new(5);
    let id = h
        .session
        .command(json!({"op":"open","html":"<p>Hello</p>"}))
        .unwrap()["window"]
        .as_u64()
        .unwrap();
    let mut last = None;
    let applied = PhysicalSize::new(1720, 1560);
    assert!(crate::native::new_size(&mut last, applied));
    crate::native::report_resize(&h.session, id, applied);
    // A later duplicate window-system event should not emit another callback.
    assert!(!crate::native::new_size(&mut last, applied));
    assert!(crate::native::new_size(
        &mut last,
        PhysicalSize::new(1800, 1600)
    ));
    let info = h.session.window_info(id).unwrap();
    assert_eq!((info.pixel_width, info.pixel_height), (1720, 1560));
    let events = h.events();
    assert_eq!(events.len(), 1);
    assert_eq!(events[0]["type"], "resized");
    assert_eq!(events[0]["window"], id);
    assert_eq!(events[0]["width"], 1720);
    assert_eq!(events[0]["height"], 1560);
    assert_eq!(events[0]["units"], "physical_pixels");
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

#[test]
fn destroy_is_rejected_in_started_and_stopped_callbacks() {
    let h = Harness::new(6);
    h.session.run().unwrap();
    let attempts: Vec<_> = h
        .events()
        .into_iter()
        .filter(|e| e["type"] == "destroy_attempt")
        .collect();
    assert_eq!(attempts.len(), 2);
    assert!(attempts.iter().all(|e| e["code"] == 2));
    assert_eq!(
        h.session.command(json!({"op":"stats"})).unwrap()["run_active"],
        false
    );
    runtime::destroy(h.session.id).unwrap();
}

#[test]
fn reentrant_abi_panic_does_not_permit_early_destroy() {
    struct ResetPoison;
    impl Drop for ResetPoison {
        fn drop(&mut self) {
            POISONED.store(false, Ordering::Release);
        }
    }
    let h = Harness::new(8);
    let _reset = ResetPoison;
    assert_eq!(h.session.run().unwrap_err().code, 8);
    assert!(POISONED.load(Ordering::Acquire));
    assert!(h
        .events()
        .iter()
        .any(|e| e["type"] == "panic_status" && e["code"] == 8));
    assert_eq!(
        runtime::create(json!({"backend":"headless"}), None, ptr::null_mut())
            .unwrap_err()
            .code,
        8
    );
    let attempts: Vec<_> = h
        .events()
        .into_iter()
        .filter(|e| e["type"] == "destroy_attempt")
        .collect();
    assert_eq!(attempts.len(), 2);
    assert!(attempts.iter().all(|e| e["code"] == 2));
    assert_eq!(
        h.session.command(json!({"op":"stats"})).unwrap()["windows"],
        0
    );
    runtime::destroy(h.session.id).unwrap();
}

#[test]
fn reserved_completion_survives_full_ordinary_post_queue() {
    let h = Harness::new(7);
    h.session
        .command(json!({"op":"reserve_completion","token":900}))
        .unwrap();
    for token in 0..512 {
        h.session.post(token).unwrap();
    }
    let worker = h.session.clone();
    std::thread::spawn(move || worker.complete(900))
        .join()
        .unwrap()
        .unwrap();
    assert_eq!(h.session.complete(900).unwrap_err().code, 4);
    h.session.run().unwrap();
    assert_eq!(
        h.events()
            .iter()
            .filter(|e| e["type"] == "completion" && e["token"] == 900)
            .count(),
        1
    );
    let stats = h.session.command(json!({"op":"stats"})).unwrap();
    assert_eq!(stats["completions_delivered"], 1);
    assert_eq!(stats["cancelled"], 512);
    assert_eq!(stats["reserved_completions"], 0);
}

#[test]
fn completion_reservations_are_bounded_and_cancelable() {
    let h = Harness::new(0);
    for token in 0..128 {
        h.session
            .command(json!({"op":"reserve_completion","token":token}))
            .unwrap();
    }
    assert_eq!(
        h.session
            .command(json!({"op":"reserve_completion","token":999}))
            .unwrap_err()
            .code,
        5
    );
    h.session.complete(7).unwrap();
    assert_eq!(
        h.session
            .command(json!({"op":"cancel_completion","token":7}))
            .unwrap()["cancelled"],
        true
    );
    assert_eq!(h.session.complete(7).unwrap_err().code, 4);
    h.session
        .command(json!({"op":"reserve_completion","token":999}))
        .unwrap();
    h.session.stop().unwrap();
    h.session.run().unwrap();
    let stats = h.session.command(json!({"op":"stats"})).unwrap();
    assert_eq!(stats["reserved_completions"], 0);
    assert_eq!(stats["completions_cancelled"], 129);
}

#[test]
fn protocol_rejects_unknown_and_wrongly_typed_fields_without_mutation() {
    let h = Harness::new(0);
    assert!(h
        .session
        .command(json!({"op":"open","html":"<p>hello</p>","with":200}))
        .is_err());
    assert!(h
        .session
        .command(json!({"op":"open","html":"<p>hello</p>","width":"200"}))
        .is_err());
    assert!(h
        .session
        .command(json!({"op":"timer","token":1,"milliseconds":1,"repeat":"false"}))
        .is_err());
    let stats = h.session.command(json!({"op":"stats"})).unwrap();
    assert_eq!(stats["windows"], 0);
    assert_eq!(stats["timers"], 0);
}

#[test]
fn structured_document_commands_preserve_literal_text_and_controls() {
    let h = Harness::new(0);
    let id=h.session.command(json!({"op":"open","html":"<main id='content'><p id='status'>Ready</p><input id='name' value='Adam'><input id='enabled' type='checkbox'></main>"})).unwrap()["window"].as_u64().unwrap();
    h.session
        .command(json!({"op":"set_value","window":id,"element":"name","value":"Příliš žluťoučký"}))
        .unwrap();
    assert_eq!(
        h.session
            .command(json!({"op":"get_value","window":id,"element":"name"}))
            .unwrap()["value"],
        "Příliš žluťoučký"
    );
    h.session
        .command(json!({"op":"set_checked","window":id,"element":"enabled","checked":true}))
        .unwrap();
    assert_eq!(
        h.session
            .command(json!({"op":"get_checked","window":id,"element":"enabled"}))
            .unwrap()["checked"],
        true
    );
    h.session
        .command(json!({"op":"set_text","window":id,"element":"status","text":"<b>literal</b>"}))
        .unwrap();
    assert_eq!(
        h.session
            .command(json!({"op":"get_value","window":id,"element":"status"}))
            .unwrap()["value"],
        "<b>literal</b>"
    );
    assert!(h.session.command(json!({"op":"replace_children_html","window":id,"element":"status","html":"<script>bad()</script>"})).is_err());
    assert_eq!(
        h.session
            .command(json!({"op":"get_value","window":id,"element":"name"}))
            .unwrap()["value"],
        "Příliš žluťoučký"
    );
}

#[test]
fn stop_does_not_wait_for_a_document_operation() {
    let h = Harness::new(0);
    let worker = h.session.clone();
    let (start_tx, start_rx) = std::sync::mpsc::channel();
    let (done_tx, done_rx) = std::sync::mpsc::channel();
    let thread = std::thread::spawn(move || {
        start_rx.recv().unwrap();
        let result = worker.stop();
        done_tx.send(result).unwrap();
    });
    let completed = h
        .session
        .exercise_owner_borrow(|| {
            start_tx.send(()).unwrap();
            done_rx.recv_timeout(std::time::Duration::from_secs(2))
        })
        .unwrap();
    thread.join().unwrap();
    completed
        .expect("stop must not wait for the owner document borrow")
        .unwrap();
    h.session.run().unwrap();
}

#[test]
fn reentrant_replacement_retires_remaining_events_for_the_old_node() {
    let h = Harness::new(10);
    let window=h.session.command(json!({"op":"open","html":"<div id='content'><input id='editor' value='before'></div>"})).unwrap()["window"].as_u64().unwrap();
    h.session
        .command(json!({"op":"focus","window":window,"element":"editor"}))
        .unwrap();
    h.session
        .input(window, crate::document::Input::Text("x".into()))
        .unwrap();
    assert_eq!(
        h.session
            .command(json!({"op":"get_value","window":window,"element":"editor"}))
            .unwrap()["value"],
        "replacement"
    );
    let events = h.events();
    assert_eq!(events.iter().filter(|e| e["type"] == "input").count(), 1);
    assert_eq!(events.iter().filter(|e| e["type"] == "change").count(), 0);
    assert!(events.iter().all(|e| e.get("_target").is_none()));
}

#[test]
fn dom_mutation_commands_insert_remove_move_and_read() {
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","html":"<main id='list'><p id='b' class='x y' data-k='v'>B</p></main><aside id='side'><input id='edit' value='keep'></aside>"})).unwrap()["window"].as_u64().unwrap();
    let ids = |sel: &str| {
        cmd(json!({"op":"query","window":id,"selector":sel})).unwrap()["elements"].clone()
    };
    for (pos, html) in [
        ("afterbegin", "<p id='a'>A</p>"),
        ("beforeend", "<p id='d'>D</p>"),
        ("beforebegin", "<p id='a0'>Z</p>"),
        ("afterend", "<p id='c'>C</p>"),
    ] {
        let target = if pos.ends_with("begin") && pos.starts_with("before") {
            "a"
        } else if pos == "afterend" {
            "b"
        } else {
            "list"
        };
        cmd(json!({"op":"insert_html","window":id,"element":target,"position":pos,"html":html}))
            .unwrap();
    }
    assert_eq!(ids("main > p"), json!(["a0", "a", "b", "c", "d"]));
    // Rejections are atomic and typed.
    let err = |v: Value| cmd(v).unwrap_err().code;
    assert_eq!(
        err(
            json!({"op":"insert_html","window":id,"element":"list","position":"beforeend","html":"<p id='e'>E</p><p id='b'>dup</p>"})
        ),
        1
    );
    assert_eq!(
        err(
            json!({"op":"insert_html","window":id,"element":"list","position":"beforeend","html":"<script>x()</script>"})
        ),
        1
    );
    assert_eq!(
        err(
            json!({"op":"insert_html","window":id,"element":"list","position":"inside","html":"<p>x</p>"})
        ),
        1
    );
    assert_eq!(
        cmd(json!({"op":"has_element","window":id,"element":"e"})).unwrap()["exists"],
        false
    );
    assert_eq!(
        err(json!({"op":"remove_element","window":id,"element":"missing"})),
        1
    );
    // Reads.
    assert_eq!(
        cmd(json!({"op":"get_text","window":id,"element":"list"})).unwrap()["text"],
        "ZABCD"
    );
    assert_eq!(
        cmd(json!({"op":"get_attribute","window":id,"element":"b","name":"data-k"})).unwrap()
            ["value"],
        "v"
    );
    assert_eq!(
        cmd(json!({"op":"get_attribute","window":id,"element":"b","name":"title"})).unwrap()
            ["value"],
        Value::Null
    );
    assert_eq!(
        cmd(json!({"op":"get_attributes","window":id,"element":"b"})).unwrap()["attributes"],
        json!({"id":"b","class":"x y","data-k":"v"})
    );
    assert_eq!(err(json!({"op":"query","window":id,"selector":"p[["})), 1);
    // Move keeps value, focus and identity; cycles and structural elements are rejected.
    cmd(json!({"op":"set_value","window":id,"element":"edit","value":"typed"})).unwrap();
    cmd(json!({"op":"focus","window":id,"element":"edit"})).unwrap();
    cmd(json!({"op":"move_element","window":id,"element":"side","target":"b","position":"afterbegin"})).unwrap();
    assert_eq!(ids("#b > aside > input"), json!(["edit"]));
    assert_eq!(
        cmd(json!({"op":"get_value","window":id,"element":"edit"})).unwrap()["value"],
        "typed"
    );
    assert_eq!(ids(":focus"), json!(["edit"]));
    assert_eq!(
        err(
            json!({"op":"move_element","window":id,"element":"b","target":"side","position":"beforeend"})
        ),
        1
    );
    cmd(json!({"op":"move_element","window":id,"element":"a","target":"list","position":"afterend"})).unwrap();
    assert_eq!(ids("body > p"), json!(["a"]));
    cmd(json!({"op":"move_element","window":id,"element":"a","target":"a0","position":"afterend"}))
        .unwrap();
    assert_eq!(
        err(
            json!({"op":"move_element","window":id,"element":"list","target":"a","position":"afterend"})
        ),
        1
    );
    let body_id = cmd(json!({"op":"query","window":id,"selector":"body"})).unwrap();
    assert_eq!(body_id["elements"], json!([]));
    assert_eq!(body_id["count"], 1);
    // Remove retires the subtree, its focus and its IDs.
    cmd(json!({"op":"remove_element","window":id,"element":"b"})).unwrap();
    assert_eq!(
        cmd(json!({"op":"has_element","window":id,"element":"edit"})).unwrap()["exists"],
        false
    );
    assert_eq!(ids(":focus"), json!([]));
    assert_eq!(err(json!({"op":"get_text","window":id,"element":"b"})), 1);
    // A replacement element may reuse a removed ID.
    cmd(json!({"op":"insert_html","window":id,"element":"list","position":"beforeend","html":"<p id='b'>B2</p>"})).unwrap();
    assert_eq!(
        cmd(json!({"op":"get_text","window":id,"element":"b"})).unwrap()["text"],
        "B2"
    );
}
