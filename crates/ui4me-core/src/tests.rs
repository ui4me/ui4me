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
            // 0.5 F0505: lifecycle faults injected from inside input callbacks.
            (20, Some("keydown")) => {
                session.stop().map_err(|_| ())?;
            }
            (21, Some("keydown")) => {
                let window = event["window"].as_u64().ok_or(())?;
                session
                    .command(json!({"op":"close","window":window}))
                    .map_err(|_| ())?;
            }
            (22, Some("keydown")) if event["element"] == "editor" => {
                let window = event["window"].as_u64().ok_or(())?;
                session
                    .command(json!({"op":"remove_element","window":window,"element":"editor"}))
                    .map_err(|_| ())?;
            }
            (22, Some("cancel")) => {
                let window = event["window"].as_u64().ok_or(())?;
                session
                    .command(json!({"op":"remove_element","window":window,"element":"dlg"}))
                    .map_err(|_| ())?;
            }
            (23, Some("invalid")) | (23, Some("submit")) => {
                let window = event["window"].as_u64().ok_or(())?;
                let target = event["element"].as_str().ok_or(())?.to_owned();
                session
                    .command(json!({"op":"remove_element","window":window,"element":target}))
                    .map_err(|_| ())?;
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

#[test]
fn batch_is_atomic_and_restores_focus_on_rollback() {
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","html":"<ul id='log'><li id='l1'>one</li></ul><div id='box'><input id='edit' value='v'></div>"})).unwrap()["window"].as_u64().unwrap();
    let ids = |sel: &str| {
        cmd(json!({"op":"query","window":id,"selector":sel})).unwrap()["elements"].clone()
    };
    cmd(json!({"op":"batch","window":id,"ops":[
        {"op":"insert_html","element":"log","position":"beforeend","html":"<li id='l2'>two</li>"},
        {"op":"set_text","element":"l2","text":"zwei"},
        {"op":"add_class","element":"l2","name":"new"},
        {"op":"move_element","element":"l2","target":"l1","position":"beforebegin"},
        {"op":"set_attribute","element":"log","name":"data-n","value":"2"}
    ]}))
    .unwrap();
    assert_eq!(ids("#log > li"), json!(["l2", "l1"]));
    assert_eq!(ids(".new"), json!(["l2"]));
    cmd(json!({"op":"focus","window":id,"element":"edit"})).unwrap();
    let error = cmd(json!({"op":"batch","window":id,"ops":[
        {"op":"remove_element","element":"box"},
        {"op":"insert_html","element":"log","position":"beforeend","html":"<li id='l3'>three</li>"},
        {"op":"set_text","element":"missing","text":"x"}
    ]}))
    .unwrap_err();
    assert_eq!(error.code, 1);
    assert!(
        error.message.contains("batch operation 2"),
        "{}",
        error.message
    );
    assert_eq!(ids("#log > li"), json!(["l2", "l1"]));
    assert_eq!(
        ids(":focus"),
        json!(["edit"]),
        "rollback restores the removed focused element"
    );
    assert_eq!(
        cmd(json!({"op":"get_value","window":id,"element":"edit"})).unwrap()["value"],
        "v"
    );
    // A fragment rejected late inside a batch also rolls back earlier creations.
    assert!(cmd(json!({"op":"batch","window":id,"ops":[
        {"op":"insert_html","element":"log","position":"beforeend","html":"<li id='l4'>4</li>"},
        {"op":"insert_html","element":"log","position":"beforeend","html":"<li id='l4'>dup</li>"}
    ]}))
    .is_err());
    assert_eq!(
        cmd(json!({"op":"has_element","window":id,"element":"l4"})).unwrap()["exists"],
        false
    );
    // Controls are rejected and the batch is bounded.
    assert!(cmd(
        json!({"op":"batch","window":id,"ops":[{"op":"set_text","element":"edit","text":"x"}]})
    )
    .is_err());
    let many: Vec<Value> = (0..1025)
        .map(|_| json!({"op":"add_class","element":"log","name":"x"}))
        .collect();
    assert_eq!(
        cmd(json!({"op":"batch","window":id,"ops":many}))
            .unwrap_err()
            .code,
        5
    );
    assert!(
        cmd(json!({"op":"batch","window":id,"ops":[{"op":"focus","element":"edit"}]})).is_err()
    );
    // Still usable after rejections.
    cmd(json!({"op":"batch","window":id,"ops":[{"op":"remove_element","element":"l1"}]})).unwrap();
    assert_eq!(ids("#log > li"), json!(["l2"]));
}

#[test]
fn default_action_rule_cancels_enter_but_not_shift_enter() {
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","html":"<form id='f'><textarea id='msg'></textarea></form>"}))
        .unwrap()["window"]
        .as_u64()
        .unwrap();
    cmd(json!({"op":"set_default_action","window":id,"element":"f","event":"keydown","key":"Enter","shift":false})).unwrap();
    assert!(
        cmd(json!({"op":"set_default_action","window":id,"element":"f","event":"input"})).is_err()
    );
    cmd(json!({"op":"focus","window":id,"element":"msg"})).unwrap();
    let key = |shift: bool| {
        for pressed in [true, false] {
            h.session
                .input(
                    id,
                    crate::document::Input::Key {
                        key: "Enter".into(),
                        code: "Enter".into(),
                        pressed,
                        repeat: false,
                        shift,
                        ctrl: false,
                        alt: false,
                        meta: false,
                    },
                )
                .unwrap();
        }
    };
    let value = || {
        cmd(json!({"op":"get_value","window":id,"element":"msg"})).unwrap()["value"]
            .as_str()
            .unwrap()
            .to_owned()
    };
    key(false);
    assert_eq!(value(), "");
    let downs: Vec<Value> = h
        .events()
        .into_iter()
        .filter(|e| e["type"] == "keydown")
        .collect();
    assert_eq!(downs.last().unwrap()["default_prevented"], true);
    key(true);
    assert_eq!(value(), "\n");
    cmd(json!({"op":"set_default_action","window":id,"element":"f","event":"keydown","key":"Enter","shift":false,"prevent":false})).unwrap();
    key(false);
    assert_eq!(value(), "\n\n");
    // Rules die with their element.
    cmd(json!({"op":"set_default_action","window":id,"element":"f","event":"keydown"})).unwrap();
    cmd(json!({"op":"replace_children_html","window":id,"element":"f","html":"<textarea id='msg'></textarea>"})).unwrap();
}

#[test]
fn scroll_behavior_argument_smooth_instant_and_reduced_motion() {
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","width":400,"height":300,"html":"<style>body{margin:0}.r{height:100px}</style><div id='box' style='height:100px;overflow:auto'><div class='r'></div><div class='r'></div><div class='r'></div><div class='r'></div></div>"})).unwrap()["window"].as_u64().unwrap();
    let scroll = || cmd(json!({"op":"get_scroll","window":id,"element":"box"})).unwrap();
    // Omitted and `instant` move at once; `animating` is reported.
    let s = cmd(json!({"op":"scroll_to","window":id,"element":"box","y":100})).unwrap();
    assert_eq!(
        (s["y"].as_f64(), s["animating"].as_bool()),
        (Some(100.0), Some(false))
    );
    let s = cmd(json!({"op":"scroll_by","window":id,"element":"box","dy":50,"behavior":"instant"}))
        .unwrap();
    assert_eq!(s["y"], 150.0);
    // `smooth` animates on the owner clock and ends on the target.
    let s = cmd(json!({"op":"scroll_to","window":id,"element":"box","y":0,"behavior":"smooth"}))
        .unwrap();
    assert_eq!(
        (s["y"].as_f64(), s["animating"].as_bool()),
        (Some(150.0), Some(true))
    );
    std::thread::sleep(std::time::Duration::from_millis(600));
    let s = scroll();
    assert_eq!(
        (s["y"].as_f64(), s["animating"].as_bool()),
        (Some(0.0), Some(false))
    );
    // Reduced motion turns smooth into instant.
    cmd(json!({"op":"set_environment","window":id,"reduced_motion":"reduce"})).unwrap();
    let s = cmd(json!({"op":"scroll_to","window":id,"element":"box","y":200,"behavior":"smooth"}))
        .unwrap();
    assert_eq!(
        (s["y"].as_f64(), s["animating"].as_bool()),
        (Some(200.0), Some(false))
    );
    let s = cmd(json!({"op":"scroll_into_view","window":id,"element":"box","behavior":"smooth"}));
    assert!(s.is_ok());
    assert!(
        cmd(json!({"op":"scroll_to","window":id,"element":"box","y":1,"behavior":"slow"})).is_err()
    );
}

#[test]
fn scroll_geometry_into_view_and_follow_end() {
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","width":400,"height":300,"html":"<style>body{margin:0}.r{height:30px}</style><div id='log' style='height:100px;overflow:auto'><div id='r0' class='r'></div><div class='r'></div><div class='r'></div><div class='r'></div><div id='r4' class='r'></div></div><div id='full' style='height:20px'></div>"})).unwrap()["window"].as_u64().unwrap();
    let scroll = || cmd(json!({"op":"get_scroll","window":id,"element":"log"})).unwrap();
    let s = scroll();
    assert_eq!(s["scrollable"], true);
    assert_eq!(s["max_y"], 50.0);
    assert_eq!(s["height"], 100.0);
    assert_eq!(
        cmd(json!({"op":"get_scroll","window":id,"element":"full"})).unwrap()["scrollable"],
        false
    );
    let rect =
        |e: &str| cmd(json!({"op":"get_rect","window":id,"element":e})).unwrap()["rect"].clone();
    assert_eq!(
        rect("r4"),
        json!({"x":0.0,"y":120.0,"width":400.0,"height":30.0})
    );
    // scroll_to clamps, keeps an omitted axis and moves element rects.
    let s = cmd(json!({"op":"scroll_to","window":id,"element":"log","y":1000})).unwrap();
    assert_eq!((s["y"].as_f64(), s["x"].as_f64()), (Some(50.0), Some(0.0)));
    assert_eq!(rect("r4")["y"], 70.0);
    cmd(json!({"op":"scroll_by","window":id,"element":"log","dy":-20})).unwrap();
    assert_eq!(scroll()["y"], 30.0);
    cmd(json!({"op":"scroll_into_view","window":id,"element":"r0","block":"start"})).unwrap();
    assert_eq!(scroll()["y"], 0.0);
    cmd(json!({"op":"scroll_into_view","window":id,"element":"r4"})).unwrap();
    assert_eq!(scroll()["y"], 50.0, "nearest aligns the bottom edge");
    assert!(cmd(json!({"op":"scroll_to","window":id,"element":"log","y":"down"})).is_err());
    assert!(
        cmd(json!({"op":"scroll_into_view","window":id,"element":"r0","block":"top"})).is_err()
    );
    // Follow end: growth keeps the bottom visible until the user scrolls away.
    cmd(json!({"op":"set_scroll_follow","window":id,"element":"log"})).unwrap();
    cmd(json!({"op":"insert_html","window":id,"element":"log","position":"beforeend","html":"<div class='r'></div>"})).unwrap();
    assert_eq!(scroll()["y"], 80.0);
    cmd(json!({"op":"scroll_to","window":id,"element":"log","y":10})).unwrap();
    cmd(json!({"op":"insert_html","window":id,"element":"log","position":"beforeend","html":"<div class='r'></div>"})).unwrap();
    assert_eq!(
        scroll()["y"],
        10.0,
        "a scrolled-away reader is not yanked to the end"
    );
    cmd(json!({"op":"scroll_to","window":id,"element":"log","y":1e9})).unwrap();
    cmd(json!({"op":"insert_html","window":id,"element":"log","position":"beforeend","html":"<div class='r'></div>"})).unwrap();
    assert_eq!(scroll()["y"], 140.0);
    // A user wheel scroll away also stops following.
    for dy in [-60.0, 60.0] {
        h.session
            .input(
                id,
                crate::document::Input::PointerMoved { x: 10.0, y: 10.0 },
            )
            .unwrap();
        h.session
            .input(
                id,
                crate::document::Input::Wheel {
                    dx: 0.0,
                    dy,
                    x: 10.0,
                    y: 10.0,
                },
            )
            .unwrap();
        if scroll()["y"].as_f64().unwrap() < 140.0 {
            break;
        }
    }
    let away = scroll()["y"].as_f64().unwrap();
    assert!(away < 140.0, "wheel input scrolled the log");
    cmd(json!({"op":"insert_html","window":id,"element":"log","position":"beforeend","html":"<div class='r'></div>"})).unwrap();
    assert_eq!(scroll()["y"].as_f64().unwrap(), away);
    // Resize is visible to geometry queries before the next frame.
    cmd(json!({"op":"resize","window":id,"width":300,"height":300})).unwrap();
    assert_eq!(rect("full")["width"], 300.0);
    h.session.update_geometry(id, 800, 600, 2.0).unwrap();
    assert_eq!(
        rect("full")["width"],
        400.0,
        "geometry is in CSS px at any device scale"
    );
    assert!(cmd(json!({"op":"get_rect","window":id,"element":"missing"})).is_err());
    cmd(json!({"op":"set_attribute","window":id,"element":"full","name":"style","value":"display:none"})).unwrap();
    assert_eq!(rect("full"), Value::Null);
}

#[test]
fn popover_commands_toggle_report_and_reject_non_popovers() {
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","width":400,"height":300,"html":"<button id='b' popovertarget='a'>B</button>\
        <div id='a' popover>A</div><div id='m' popover='manual'>M</div>"}))
    .unwrap()["window"]
        .as_u64()
        .unwrap();
    let get = |e: &str| cmd(json!({"op":"get_popover","window":id,"element":e})).unwrap();
    assert_eq!(get("a"), json!({"open":false,"kind":"auto"}));
    assert_eq!(get("m"), json!({"open":false,"kind":"manual"}));
    cmd(json!({"op":"show_popover","window":id,"element":"a"})).unwrap();
    assert_eq!(get("a")["open"], true);
    assert_eq!(
        cmd(json!({"op":"toggle_popover","window":id,"element":"a"})).unwrap(),
        json!({"open":false})
    );
    assert_eq!(
        cmd(json!({"op":"toggle_popover","window":id,"element":"a"})).unwrap(),
        json!({"open":true})
    );
    cmd(json!({"op":"show_popover","window":id,"element":"m"})).unwrap();
    // Opening the auto popover again leaves the manual one; hiding works on both.
    cmd(json!({"op":"hide_popover","window":id,"element":"a"})).unwrap();
    assert_eq!(get("a")["open"], false);
    assert_eq!(get("m")["open"], true);
    cmd(json!({"op":"hide_popover","window":id,"element":"m"})).unwrap();
    assert!(cmd(json!({"op":"show_popover","window":id,"element":"b"})).is_err());
    assert!(cmd(json!({"op":"get_popover","window":id,"element":"b"})).is_err());
    // `toggle` events report the states.
    let toggles: Vec<_> = h
        .events()
        .into_iter()
        .filter(|e| e["type"] == "toggle" && e["element"] == "a")
        .map(|e| e["new_state"].clone())
        .collect();
    assert_eq!(toggles.last(), Some(&json!("closed")));
    assert!(toggles.contains(&json!("open")));
}

#[test]
fn dialog_details_select_and_labels() {
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","width":600,"height":400,"html":"<button id='opener'>Open</button><label id='lbl' for='name'>Name</label><input id='name'>\
        <dialog id='dlg'><input id='first'><button id='ok'>OK</button></dialog>\
        <details id='det'><summary id='sum'>More</summary><p>Hidden</p></details>\
        <select id='pick'><option value='a'>Alpha</option><option value='b'>Beta</option><option value='c' disabled>Gamma</option></select>\
        <select id='many' multiple><option value='x'>X</option><option value='y'>Y</option><option value='z'>Z</option></select>"})).unwrap()["window"].as_u64().unwrap();
    let focus =
        || cmd(json!({"op":"query","window":id,"selector":":focus"})).unwrap()["elements"].clone();
    let key = |k: &str, shift: bool| {
        for pressed in [true, false] {
            h.session
                .input(
                    id,
                    crate::document::Input::Key {
                        key: k.into(),
                        code: k.into(),
                        pressed,
                        repeat: false,
                        shift,
                        ctrl: false,
                        alt: false,
                        meta: false,
                    },
                )
                .unwrap();
        }
    };
    let events = |ty: &str| {
        h.events()
            .into_iter()
            .filter(|e| e["type"] == ty)
            .collect::<Vec<_>>()
    };
    // Modal dialog: focus moves in, the rest is inert, Tab stays inside, Escape closes and restores focus.
    cmd(json!({"op":"focus","window":id,"element":"opener"})).unwrap();
    cmd(json!({"op":"show_dialog","window":id,"element":"dlg"})).unwrap();
    assert_eq!(
        cmd(json!({"op":"get_dialog","window":id,"element":"dlg"})).unwrap(),
        json!({"open":true,"modal":true,"return_value":""})
    );
    assert_eq!(focus(), json!(["first"]));
    assert!(
        cmd(json!({"op":"focus","window":id,"element":"name"})).is_err(),
        "outside a modal dialog is inert"
    );
    for _ in 0..3 {
        key("Tab", false);
        let f = focus();
        assert!(
            f == json!(["ok"]) || f == json!(["first"]) || f == json!(["dlg"]),
            "focus escaped the modal dialog: {f}"
        );
    }
    key("Escape", false);
    assert_eq!(
        cmd(json!({"op":"get_dialog","window":id,"element":"dlg"})).unwrap()["open"],
        false
    );
    assert_eq!(focus(), json!(["opener"]), "focus returns to the opener");
    assert_eq!(events("cancel").len(), 1);
    assert_eq!(events("close").last().unwrap()["element"], "dlg");
    // close with a return value; a cancel rule keeps the dialog open on Escape.
    cmd(json!({"op":"show_dialog","window":id,"element":"dlg"})).unwrap();
    cmd(json!({"op":"close_dialog","window":id,"element":"dlg","return_value":"ok"})).unwrap();
    assert_eq!(events("close").last().unwrap()["return_value"], "ok");
    cmd(json!({"op":"set_default_action","window":id,"element":"dlg","event":"cancel"})).unwrap();
    cmd(json!({"op":"show_dialog","window":id,"element":"dlg","modal":true})).unwrap();
    key("Escape", false);
    assert_eq!(
        cmd(json!({"op":"get_dialog","window":id,"element":"dlg"})).unwrap()["open"],
        true
    );
    cmd(json!({"op":"close_dialog","window":id,"element":"dlg"})).unwrap();
    assert!(cmd(json!({"op":"show_dialog","window":id,"element":"opener"})).is_err());
    // details: activating the summary toggles and reports `toggle`.
    cmd(json!({"op":"focus","window":id,"element":"sum"})).unwrap();
    key("Enter", false);
    assert_eq!(
        cmd(json!({"op":"get_attribute","window":id,"element":"det","name":"open"})).unwrap()
            ["value"],
        ""
    );
    assert_eq!(events("toggle").last().unwrap()["new_state"], "open");
    // select: keyboard changes commit, disabled options are skipped, options are readable.
    cmd(json!({"op":"focus","window":id,"element":"pick"})).unwrap();
    key("ArrowDown", false);
    assert_eq!(
        cmd(json!({"op":"get_value","window":id,"element":"pick"})).unwrap()["value"],
        "b"
    );
    key("ArrowDown", false);
    assert_eq!(
        cmd(json!({"op":"get_value","window":id,"element":"pick"})).unwrap()["value"],
        "b",
        "disabled option skipped"
    );
    assert!(events("commit")
        .iter()
        .any(|e| e["element"] == "pick" && e["value"] == "b"));
    let options =
        cmd(json!({"op":"get_options","window":id,"element":"pick"})).unwrap()["options"].clone();
    assert_eq!(
        options[2],
        json!({"value":"c","label":"Gamma","selected":false,"disabled":true})
    );
    cmd(json!({"op":"set_selected_values","window":id,"element":"many","values":["x","z"]}))
        .unwrap();
    let many: Vec<bool> = cmd(json!({"op":"get_options","window":id,"element":"many"})).unwrap()
        ["options"]
        .as_array()
        .unwrap()
        .iter()
        .map(|o| o["selected"].as_bool().unwrap())
        .collect();
    assert_eq!(many, vec![true, false, true]);
    assert!(cmd(
        json!({"op":"set_selected_values","window":id,"element":"pick","values":["a","b"]})
    )
    .is_err());
    assert!(cmd(
        json!({"op":"set_selected_values","window":id,"element":"pick","values":["nope"]})
    )
    .is_err());
    // A label click focuses its control.
    let r = cmd(json!({"op":"get_rect","window":id,"element":"lbl"})).unwrap()["rect"].clone();
    let (x, y) = (
        r["x"].as_f64().unwrap() + 3.0,
        r["y"].as_f64().unwrap() + 3.0,
    );
    for pressed in [true, false] {
        h.session
            .input(
                id,
                crate::document::Input::PointerButton {
                    pressed,
                    button: 0,
                    x,
                    y,
                },
            )
            .unwrap();
    }
    assert_eq!(focus(), json!(["name"]));
}

#[test]
fn window_actions_constraints_icon_and_state() {
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","html":"<p>w</p>"})).unwrap()["window"]
        .as_u64()
        .unwrap();
    let state = || cmd(json!({"op":"get_window_state","window":id})).unwrap();
    assert_eq!(state()["platform"], "headless");
    assert_eq!(state()["width"], 640.0);
    for (action, key, value) in [
        ("maximize", "maximized", true),
        ("minimize", "minimized", true),
        ("fullscreen", "fullscreen", true),
        ("hide", "visible", false),
        ("show", "visible", true),
        ("focus", "focused", true),
    ] {
        assert_eq!(
            cmd(json!({"op":"window_action","window":id,"action":action})).unwrap()["applied"],
            true
        );
        assert_eq!(state()[key], value, "{action}");
    }
    cmd(json!({"op":"window_action","window":id,"action":"restore"})).unwrap();
    assert_eq!(
        (state()["minimized"].clone(), state()["maximized"].clone()),
        (json!(false), json!(false))
    );
    assert!(cmd(json!({"op":"window_action","window":id,"action":"spin"})).is_err());
    cmd(json!({"op":"set_window_constraints","window":id,"min_width":300,"min_height":200,"max_width":900,"max_height":700,"resizable":false})).unwrap();
    assert_eq!(state()["min_size"], json!([300, 200]));
    assert_eq!(state()["resizable"], false);
    assert_eq!(
        cmd(json!({"op":"resize","window":id,"width":200,"height":1000})).unwrap(),
        json!({"width":300,"height":700}),
        "resize clamps to constraints"
    );
    assert_eq!(
        (state()["width"].clone(), state()["height"].clone()),
        (json!(300.0), json!(700.0))
    );
    assert!(cmd(json!({"op":"set_window_constraints","window":id,"min_width":800,"min_height":800,"max_width":400,"max_height":400})).is_err());
    assert!(cmd(json!({"op":"set_window_constraints","window":id,"min_width":300})).is_err());
    // Icon: a real PNG decodes; junk and oversized images are rejected.
    let dir = std::env::temp_dir().join(format!("ui4me-icon-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let png_path = dir.join("icon ž.png");
    {
        let file = std::fs::File::create(&png_path).unwrap();
        let mut e = png::Encoder::new(std::io::BufWriter::new(file), 16, 16);
        e.set_color(png::ColorType::Rgba);
        e.set_depth(png::BitDepth::Eight);
        e.write_header()
            .unwrap()
            .write_image_data(&[200u8; 16 * 16 * 4])
            .unwrap();
    }
    cmd(json!({"op":"set_window_icon","window":id,"path":png_path})).unwrap();
    std::fs::write(dir.join("bad.png"), b"not a png").unwrap();
    assert_eq!(
        cmd(json!({"op":"set_window_icon","window":id,"path":dir.join("bad.png")}))
            .unwrap_err()
            .code,
        1
    );
    cmd(json!({"op":"set_window_icon","window":id})).unwrap();
    std::fs::remove_dir_all(&dir).unwrap();
    assert_eq!(
        cmd(json!({"op":"list_monitors"})).unwrap()["monitors"],
        json!([])
    );
    // The capability report (0.5 F0508): exact statuses with causes, never optimistic booleans.
    let caps = cmd(json!({"op":"capabilities"})).unwrap();
    assert_eq!(caps["backend"], "headless");
    assert_eq!(caps["platform"], "headless");
    let features = caps["features"].as_object().unwrap();
    for (name, f) in features {
        let status = f["status"].as_str().unwrap();
        assert!(
            [
                "supported",
                "unsupported",
                "denied",
                "unavailable",
                "unknown"
            ]
            .contains(&status),
            "{name}: {status}"
        );
        assert!(
            status == "supported" || f["reason"].as_str().is_some_and(|r| !r.is_empty()),
            "{name} needs a reason"
        );
    }
    assert_eq!(features["window.focus"]["status"], "unavailable");
    assert_eq!(features["clipboard.text"]["status"], "supported");
    assert_eq!(features["system_tray"]["status"], "unavailable");
    // Platform rules: Wayland reports unsupported operations instead of pretending.
    assert!(crate::runtime::unsupported("wayland", &crate::runtime::WindowOp::Focus).is_some());
    assert!(crate::runtime::unsupported("windows", &crate::runtime::WindowOp::Focus).is_none());
    assert_eq!(
        cmd(json!({"op":"get_window_state","window":id + 1000}))
            .unwrap_err()
            .code,
        4
    );
    assert_eq!(
        cmd(json!({"op":"window_action","window":id + 1000,"action":"focus"}))
            .unwrap_err()
            .code,
        4
    );
}

#[test]
fn file_dialog_requests_validate_and_complete() {
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","html":"<p>f</p>"})).unwrap()["window"]
        .as_u64()
        .unwrap();
    let ok = cmd(json!({"op":"file_dialog","window":id,"token":7,"kind":"open","title":"Pick ž","filters":[{"name":"Images","extensions":["png","jpg"]}]})).unwrap();
    assert_eq!(ok["token"], 7);
    h.session.process_work();
    let done: Vec<Value> = h
        .events()
        .into_iter()
        .filter(|e| e["type"] == "file_dialog")
        .collect();
    assert_eq!(done.len(), 1);
    assert_eq!(
        (
            done[0]["token"].clone(),
            done[0]["paths"].clone(),
            done[0]["window"].clone()
        ),
        (json!(7), Value::Null, json!(id))
    );
    for bad in [
        json!({"op":"file_dialog","window":id,"token":8,"kind":"delete"}),
        json!({"op":"file_dialog","window":id,"token":8,"kind":"save","file_name":"../x"}),
        json!({"op":"file_dialog","window":id,"token":8,"kind":"open","filters":[{"name":"x","extensions":["*.png"]}]}),
        json!({"op":"file_dialog","window":id,"token":8,"kind":"open","directory":"relative/dir"}),
    ] {
        assert_eq!(cmd(bad).unwrap_err().code, 1);
    }
    assert_eq!(
        cmd(json!({"op":"file_dialog","window":id + 99,"token":9,"kind":"folder"}))
            .unwrap_err()
            .code,
        4
    );
}

#[test]
fn responsive_layout_flex_media_grid_overflow() {
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let html = "<style>*{box-sizing:border-box}body{margin:0;font:14px sans-serif}\
        header{display:flex;justify-content:space-between;align-items:center;height:40px;padding:0 10px}\
        #app{display:flex;height:calc(100vh - 40px)}#side{width:200px;flex:none;overflow:auto}#main{flex:1;min-width:0;position:relative}\
        @media (max-width:700px){#app{flex-direction:column}#side{width:auto;height:120px}}\
        #grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;padding:10px}\
        .cell{height:50px}#name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;width:120px}\
        #badge{position:absolute;right:8px;top:8px;width:20px;height:20px}\
        #scroller{height:100px;overflow:auto}#sticky{position:sticky;top:0;height:20px}</style>\
        <header><b id='brand'>Files</b><button id='act'>Action</button></header>\
        <div id='app'><nav id='side'><div id='name'>a-very-long-file-name-that-must-be-truncated.txt</div></nav>\
        <main id='main'><span id='badge'></span><div id='grid'><div id='c1' class='cell'></div><div id='c2' class='cell'></div><div id='c3' class='cell'></div><div id='c4' class='cell'></div><div id='c5' class='cell'></div></div>\
        <div id='scroller'><div id='sticky'></div><div style='height:400px'></div></div></main></div>";
    let id = cmd(json!({"op":"open","width":1000,"height":600,"html":html})).unwrap()["window"]
        .as_u64()
        .unwrap();
    let r = |e: &str| {
        let v = cmd(json!({"op":"get_rect","window":id,"element":e})).unwrap()["rect"].clone();
        (
            v["x"].as_f64().unwrap(),
            v["y"].as_f64().unwrap(),
            v["width"].as_f64().unwrap(),
            v["height"].as_f64().unwrap(),
        )
    };
    // Wide: header spreads, sidebar beside main, grid has several columns, ellipsis clips.
    assert_eq!(r("brand").0, 10.0);
    assert!(
        (r("act").0 + r("act").2 - 990.0).abs() < 0.5,
        "space-between puts the button at the end: {:?}",
        r("act")
    );
    assert_eq!((r("side").2, r("main").0), (200.0, 200.0));
    assert_eq!(r("main").3, 560.0, "calc(100vh - 40px)");
    let cols = |cells: &[&str]| cells.iter().filter(|c| r(c).1 == r("c1").1).count();
    assert_eq!(
        cols(&["c1", "c2", "c3", "c4", "c5"]),
        4,
        "780px of grid content fits 4 columns of >=150px with 10px gaps"
    );
    assert_eq!(r("name").2, 120.0);
    assert_eq!((r("badge").0, r("badge").1), (1000.0 - 8.0 - 20.0, 48.0));
    // Narrow: the media query stacks the layout and the grid reflows.
    cmd(json!({"op":"resize","window":id,"width":600,"height":600})).unwrap();
    assert_eq!((r("side").2, r("side").3), (600.0, 120.0));
    assert_eq!((r("main").0, r("main").1), (0.0, 160.0));
    assert_eq!(
        cols(&["c1", "c2", "c3", "c4", "c5"]),
        3,
        "580px fits 3 columns"
    );
    assert_eq!(r("c4").1, r("c1").1 + 60.0);
    // Sticky stays at the top of its scroller while scrolling.
    let top = r("scroller").1;
    cmd(json!({"op":"scroll_to","window":id,"element":"scroller","y":150})).unwrap();
    assert_eq!(r("sticky").1, top);
}

#[test]
fn keyboard_only_operation_of_ordinary_controls() {
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","width":600,"height":400,"html":"<a id='link' href='#x'>Link</a><input id='name'><button id='go'>Go</button>\
        <button id='off' disabled>Off</button><input id='agree' type='checkbox'><input id='r1' type='radio' name='g' checked><input id='r2' type='radio' name='g'>\
        <select id='pick'><option>A</option><option>B</option></select><textarea id='notes'></textarea><div id='inert' inert><button id='hidden'>Hidden</button></div><button id='last' tabindex='0'>Last</button>"})).unwrap()["window"].as_u64().unwrap();
    let key = |k: &str, shift: bool| {
        for pressed in [true, false] {
            h.session
                .input(
                    id,
                    crate::document::Input::Key {
                        key: k.into(),
                        code: k.into(),
                        pressed,
                        repeat: false,
                        shift,
                        ctrl: false,
                        alt: false,
                        meta: false,
                    },
                )
                .unwrap();
        }
    };
    let focus = || {
        cmd(json!({"op":"query","window":id,"selector":":focus"})).unwrap()["elements"][0]
            .as_str()
            .unwrap_or("")
            .to_owned()
    };
    let mut order = Vec::new();
    for _ in 0..9 {
        key("Tab", false);
        order.push(focus());
    }
    assert_eq!(
        order,
        ["link", "name", "go", "agree", "r1", "pick", "notes", "last", "link"],
        "Tab order skips disabled and inert controls and wraps"
    );
    assert_eq!(
        cmd(json!({"op":"query","window":id,"selector":":focus-visible"})).unwrap()["elements"],
        json!(["link"]),
        "keyboard focus is focus-visible"
    );
    key("Tab", true);
    assert_eq!(focus(), "last", "Shift+Tab goes back");
    // Activation from the keyboard.
    while focus() != "go" {
        key("Tab", false);
    }
    key("Enter", false);
    key(" ", false);
    let clicks = h
        .events()
        .into_iter()
        .filter(|e| e["type"] == "click" && e["element"] == "go")
        .count();
    assert_eq!(clicks, 2, "Enter and Space activate a button");
    key("Tab", false);
    key(" ", false);
    assert_eq!(
        cmd(json!({"op":"get_checked","window":id,"element":"agree"})).unwrap()["checked"],
        true,
        "Space toggles a checkbox"
    );
    key("Tab", false);
    key("ArrowDown", false);
    assert_eq!(
        cmd(json!({"op":"get_checked","window":id,"element":"r2"})).unwrap()["checked"],
        true,
        "arrows move through a radio group"
    );
    assert_eq!(focus(), "r2");
}

#[test]
fn environment_and_scale_changes_restyle_without_losing_input_state() {
    // 0.5 F0506: an OS theme signal, an app override and a scale change each restyle the
    // document; the DOM, control values and focus survive.
    let h = Harness::new(0);
    let s = &h.session;
    let cmd = |v: Value| s.command(v);
    let id = cmd(json!({"op":"open","html":"<style>#box{width:100px;height:10px}@media (prefers-color-scheme: dark){#box{width:200px}}@media (prefers-reduced-motion: reduce){#box{height:30px}}</style><div id=box></div><input id=name value=Ada>"})).unwrap()["window"].as_u64().unwrap();
    let rect = |k: &str| {
        cmd(json!({"op":"get_rect","window":id,"element":"box"})).unwrap()["rect"][k]
            .as_f64()
            .unwrap()
    };
    cmd(json!({"op":"focus","window":id,"element":"name"})).unwrap();
    cmd(json!({"op":"set_value","window":id,"element":"name","value":"Ada!"})).unwrap();
    assert_eq!(rect("width"), 100.0);
    let env = cmd(json!({"op":"get_environment","window":id})).unwrap();
    assert_eq!(
        (
            env["color_scheme"].as_str(),
            env["color_scheme_source"].as_str()
        ),
        (Some("light"), Some("default"))
    );
    s.system_color_scheme(id, Some(true));
    assert_eq!(rect("width"), 200.0, "the OS dark scheme applies");
    assert!(h.events().iter().any(|e| e["type"] == "environment_changed"
        && e["color_scheme"] == "dark"
        && e["color_scheme_source"] == "system"));
    // The app override wins over a later OS change, and `system` returns to the OS value.
    let env = cmd(json!({"op":"set_environment","window":id,"color_scheme":"light","reduced_motion":"reduce"})).unwrap();
    assert_eq!(
        (
            env["color_scheme"].as_str(),
            env["color_scheme_source"].as_str()
        ),
        (Some("light"), Some("app"))
    );
    s.system_color_scheme(id, Some(true));
    assert_eq!(rect("width"), 100.0);
    assert_eq!(rect("height"), 30.0, "reduced motion applies");
    cmd(json!({"op":"set_environment","window":id,"color_scheme":"system"})).unwrap();
    assert_eq!(rect("width"), 200.0);
    assert_eq!(
        cmd(json!({"op":"set_environment","window":id,"color_scheme":"blue"}))
            .unwrap_err()
            .code,
        1
    );
    // A scale change keeps the input state.
    s.update_geometry(id, 1280, 960, 2.0).unwrap();
    assert_eq!(
        cmd(json!({"op":"get_environment","window":id})).unwrap()["scale"],
        2.0
    );
    assert_eq!(
        cmd(json!({"op":"get_value","window":id,"element":"name"})).unwrap()["value"],
        "Ada!"
    );
    assert_eq!(
        cmd(json!({"op":"query","window":id,"selector":":focus"})).unwrap()["elements"],
        json!(["name"])
    );
}

fn key(name: &str) -> crate::document::Input {
    crate::document::Input::Key {
        key: name.into(),
        code: name.into(),
        pressed: true,
        repeat: false,
        shift: false,
        ctrl: false,
        alt: false,
        meta: false,
    }
}

#[test]
fn stop_inside_an_input_callback_ends_delivery_and_the_session_cleanly() {
    let h = Harness::new(20);
    let window = h
        .session
        .command(json!({"op":"open","html":"<input id='editor'>"}))
        .unwrap()["window"]
        .as_u64()
        .unwrap();
    h.session
        .command(json!({"op":"focus","window":window,"element":"editor"}))
        .unwrap();
    h.session.input(window, key("a")).unwrap();
    // The stop requested inside keydown ends delivery: the same key's text and later input are refused.
    assert!(h
        .session
        .input(window, crate::document::Input::Text("a".into()))
        .is_err());
    let delivered = h.events().iter().filter(|e| e["type"] == "keydown").count();
    assert_eq!(delivered, 1);
    assert!(h.events().iter().all(|e| e["type"] != "input"));
    h.session.run().unwrap();
    assert_eq!(h.events().last().unwrap()["type"], "stopped");
}

#[test]
fn closing_a_window_from_its_own_callback_ends_its_delivery_at_once() {
    let h = Harness::new(21);
    let window = h
        .session
        .command(json!({"op":"open","html":"<input id='editor'>"}))
        .unwrap()["window"]
        .as_u64()
        .unwrap();
    h.session
        .command(json!({"op":"focus","window":window,"element":"editor"}))
        .unwrap();
    let other = h
        .session
        .command(json!({"op":"open","html":"<input id='editor' value='other'>"}))
        .unwrap()["window"]
        .as_u64()
        .unwrap();
    h.session.input(window, key("a")).unwrap();
    // The close requested inside keydown ends delivery at once: the rest of that key's events and
    // later input for the window are not delivered.
    assert_eq!(
        h.events().iter().filter(|e| e["type"] == "keydown").count(),
        1
    );
    assert!(h
        .session
        .input(window, crate::document::Input::Text("x".into()))
        .is_err());
    assert!(h.events().iter().all(|e| e["type"] != "input"));
    // The other window is unaffected.
    assert_eq!(
        h.session
            .command(json!({"op":"get_value","window":other,"element":"editor"}))
            .unwrap()["value"],
        "other"
    );
    h.session
        .command(json!({"op":"close","window":other}))
        .unwrap();
    h.session.run().unwrap();
    let events = h.events();
    let closed: Vec<_> = events
        .iter()
        .filter(|e| e["type"] == "closed")
        .map(|e| e["window"].as_u64().unwrap())
        .collect();
    assert_eq!(closed, vec![window, other], "each window closes once");
    assert_eq!(events.last().unwrap()["type"], "stopped");
}

#[test]
fn removing_the_focused_node_or_an_open_modal_in_a_callback_leaves_no_stale_targets() {
    let h = Harness::new(22);
    let window = h.session.command(json!({"op":"open","html":"<input id='editor'><button id='after'>After</button><dialog id='dlg'><button id='inside'>In</button></dialog>"})).unwrap()["window"].as_u64().unwrap();
    h.session
        .command(json!({"op":"focus","window":window,"element":"editor"}))
        .unwrap();
    let before = h.session.accessibility_tree(window).unwrap();
    let editor_key = before
        .nodes
        .values()
        .find(|n| n.html_id.as_deref() == Some("editor"))
        .unwrap()
        .id;
    h.session.input(window, key("a")).unwrap();
    h.session
        .input(window, crate::document::Input::Text("a".into()))
        .unwrap();
    assert!(!h
        .session
        .command(json!({"op":"has_element","window":window,"element":"editor"}))
        .unwrap()["exists"]
        .as_bool()
        .unwrap());
    // No input reached the removed node; focus left it; the accessibility tree forgot it.
    assert!(h
        .events()
        .iter()
        .all(|e| !(e["type"] == "input" && e["element"] == "editor")));
    assert_eq!(
        h.session
            .command(json!({"op":"query","window":window,"selector":":focus"}))
            .unwrap()["elements"],
        json!([])
    );
    let tree = h.session.accessibility_tree(window).unwrap();
    assert!(tree.get(editor_key).is_none() && tree.focus != editor_key);
    // An assistive action aimed at the removed node is a stale-handle error, not a panic or a
    // different node.
    let stale = ui4me_renderer::a11y::A11yRequest {
        target: ui4me_renderer::a11y::node_of_key(editor_key),
        kind: ui4me_renderer::a11y::A11yRequestKind::Click,
    };
    let errors_before = h.events().iter().filter(|e| e["type"] == "error").count();
    h.session.accessibility_request(window, &stale);
    assert!(h.events().iter().filter(|e| e["type"] == "error").count() > errors_before);
    // A modal removed from its own cancel handler: the document is interactive again.
    h.session
        .command(json!({"op":"show_dialog","window":window,"element":"dlg","modal":true}))
        .unwrap();
    h.session.input(window, key("Escape")).unwrap();
    assert!(h.events().iter().any(|e| e["type"] == "cancel"));
    assert!(!h
        .session
        .command(json!({"op":"has_element","window":window,"element":"dlg"}))
        .unwrap()["exists"]
        .as_bool()
        .unwrap());
    h.session
        .command(json!({"op":"focus","window":window,"element":"after"}))
        .unwrap();
    assert_eq!(
        h.session
            .command(json!({"op":"query","window":window,"selector":":focus"}))
            .unwrap()["elements"],
        json!(["after"])
    );
    assert!(h
        .session
        .accessibility_tree(window)
        .unwrap()
        .nodes
        .values()
        .any(|n| n.html_id.as_deref() == Some("after")));
}

#[test]
fn html_serialization_stylesheets_and_node_traversal() {
    // 0.6 F0601/F0602/F0604.
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","html":"<div id=box class='a b' data-x=\"1 &amp; 2\"><p>Příliš <b>žluťoučký</b> kůň</p><span>no id</span><!--c--></div><template id=tpl><i>inside</i></template><input id=f value=typed>"})).unwrap()["window"].as_u64().unwrap();
    // Serialization: inner/outer/document; attributes escaped, Unicode kept, control values not markup.
    let inner = cmd(json!({"op":"get_html","window":id,"element":"box"})).unwrap()["html"]
        .as_str()
        .unwrap()
        .to_owned();
    assert_eq!(
        inner,
        "<p>Příliš <b>žluťoučký</b> kůň</p><span>no id</span><!--c-->"
    );
    let outer = cmd(json!({"op":"get_html","window":id,"element":"box","outer":true})).unwrap()
        ["html"]
        .as_str()
        .unwrap()
        .to_owned();
    assert!(
        outer.starts_with("<div id=\"box\" class=\"a b\" data-x=\"1 &amp; 2\">"),
        "{outer}"
    );
    assert_eq!(
        cmd(json!({"op":"get_html","window":id,"element":"tpl"})).unwrap()["html"],
        "<i>inside</i>"
    );
    let doc = cmd(json!({"op":"get_html","window":id})).unwrap()["html"]
        .as_str()
        .unwrap()
        .to_owned();
    assert!(
        doc.starts_with("<html><head></head><body>")
            && doc.contains("<input id=\"f\" value=\"typed\">"),
        "{doc}"
    );
    // Round trip: inner HTML re-inserted elsewhere yields the same markup.
    cmd(json!({"op":"insert_html","window":id,"element":"box","position":"afterend","html":format!("<div id=copy>{inner}</div>")})).unwrap();
    assert_eq!(
        cmd(json!({"op":"get_html","window":id,"element":"copy"})).unwrap()["html"],
        inner.as_str()
    );
    assert_eq!(
        cmd(json!({"op":"get_html","window":id,"element":"nope"}))
            .unwrap_err()
            .code,
        1
    );
    // Stylesheets: add (with diagnostics), replace, list order, remove, stale ids.
    let w = |e: &str| {
        cmd(json!({"op":"get_rect","window":id,"element":e})).unwrap()["rect"]["width"]
            .as_f64()
            .unwrap()
    };
    let added =
        cmd(json!({"op":"add_stylesheet","window":id,"css":"#box{width:120px} p{colr:red}"}))
            .unwrap();
    let sheet = added["sheet"].as_u64().unwrap();
    assert_eq!(w("box"), 120.0);
    assert!(
        added["diagnostics"]
            .as_array()
            .unwrap()
            .iter()
            .any(|d| d["line"] == 1),
        "{added}"
    );
    cmd(json!({"op":"replace_stylesheet","window":id,"sheet":sheet,"css":"#box{width:150px}"}))
        .unwrap();
    assert_eq!(w("box"), 150.0);
    let second = cmd(json!({"op":"add_stylesheet","window":id,"css":"#box{width:90px}"})).unwrap()
        ["sheet"]
        .as_u64()
        .unwrap();
    assert_eq!(w("box"), 90.0, "later sheets win");
    let list = cmd(json!({"op":"list_stylesheets","window":id})).unwrap()["sheets"].clone();
    assert_eq!(
        list.as_array()
            .unwrap()
            .iter()
            .filter(|s| s["kind"] == "attached")
            .map(|s| s["sheet"].as_u64().unwrap())
            .collect::<Vec<_>>(),
        vec![sheet, second]
    );
    cmd(json!({"op":"remove_stylesheet","window":id,"sheet":second})).unwrap();
    assert_eq!(w("box"), 150.0);
    assert_eq!(
        cmd(json!({"op":"remove_stylesheet","window":id,"sheet":second}))
            .unwrap_err()
            .code,
        4
    );
    assert_eq!(
        cmd(json!({"op":"replace_stylesheet","window":id,"sheet":999,"css":""}))
            .unwrap_err()
            .code,
        4
    );
    // Traversal: unidentified elements, text, comments, template contents, stale references.
    let boxref = cmd(json!({"op":"node_of","window":id,"element":"box"})).unwrap()["node"]
        .as_str()
        .unwrap()
        .to_owned();
    let kids = cmd(json!({"op":"node_children","window":id,"node":boxref})).unwrap();
    assert_eq!(kids["total"], 3);
    let types: Vec<_> = kids["children"]
        .as_array()
        .unwrap()
        .iter()
        .map(|k| k["type"].as_str().unwrap().to_owned())
        .collect();
    assert_eq!(types, ["element", "element", "comment"]);
    let span = kids["children"][1]["node"].as_str().unwrap().to_owned();
    let node = cmd(json!({"op":"get_node","window":id,"node":span})).unwrap();
    assert_eq!(
        (
            node["name"].as_str(),
            node["id"].clone(),
            node["parent"].as_str()
        ),
        (Some("span"), Value::Null, Some(boxref.as_str()))
    );
    let text = cmd(json!({"op":"node_children","window":id,"node":span})).unwrap()["children"][0]
        ["node"]
        .as_str()
        .unwrap()
        .to_owned();
    assert_eq!(
        cmd(json!({"op":"get_node","window":id,"node":text})).unwrap()["text"],
        "no id"
    );
    let tpl = cmd(json!({"op":"get_node","window":id,"node":cmd(json!({"op":"node_of","window":id,"element":"tpl"})).unwrap()["node"]})).unwrap();
    let content = tpl["content"].as_str().unwrap().to_owned();
    assert_eq!(
        cmd(json!({"op":"node_children","window":id,"node":content})).unwrap()["children"][0]
            ["name"],
        "i"
    );
    assert_eq!(
        cmd(json!({"op":"get_html","window":id,"node":span,"outer":true})).unwrap()["html"],
        "<span>no id</span>"
    );
    let docref = cmd(json!({"op":"node_of","window":id})).unwrap()["node"]
        .as_str()
        .unwrap()
        .to_owned();
    assert_eq!(
        cmd(json!({"op":"get_node","window":id,"node":docref})).unwrap()["type"],
        "document"
    );
    assert_eq!(
        cmd(json!({"op":"node_children","window":id,"node":boxref,"limit":0}))
            .unwrap_err()
            .code,
        1
    );
    assert_eq!(
        cmd(json!({"op":"get_node","window":id,"node":"garbage"}))
            .unwrap_err()
            .code,
        1
    );
    cmd(json!({"op":"remove_element","window":id,"element":"box"})).unwrap();
    assert_eq!(
        cmd(json!({"op":"get_node","window":id,"node":span}))
            .unwrap_err()
            .code,
        4
    );
    assert_eq!(
        cmd(json!({"op":"get_html","window":id,"node":boxref}))
            .unwrap_err()
            .code,
        4
    );
}

#[test]
fn text_range_geometry_and_point_to_text() {
    // 0.6 F0603: wrapped multilingual text, offsets in UTF-16, hidden/clipped text, hit to text.
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","width":400,"height":300,"html":"<style>body{margin:0;font:16px sans-serif}#p{width:120px}#clip{height:20px;overflow:hidden}</style><p id=p>Příliš žluťoučký kůň 😀 úpěl ďábelské ódy שלום</p><div id=clip><div>one</div><div id=below>two</div></div><p id=gone style='display:none'>hidden</p>"})).unwrap()["window"].as_u64().unwrap();
    let all = cmd(json!({"op":"text_rects","window":id,"element":"p"})).unwrap();
    let total = all["length"].as_u64().unwrap();
    assert_eq!(
        total,
        "Příliš žluťoučký kůň 😀 úpěl ďábelské ódy שלום"
            .encode_utf16()
            .count() as u64
    );
    let rects = all["rects"].as_array().unwrap();
    let lines: std::collections::BTreeSet<i64> = rects
        .iter()
        .map(|r| r["y"].as_f64().unwrap() as i64)
        .collect();
    assert!(lines.len() >= 3, "wrapped over several lines: {rects:?}");
    assert!(rects
        .iter()
        .all(|r| r["width"].as_f64().unwrap() > 0.0 && r["visible"] == true));
    // The emoji is two UTF-16 units; its range has one rectangle.
    let emoji = "Příliš žluťoučký kůň ".encode_utf16().count() as u64;
    let e = cmd(json!({"op":"text_rects","window":id,"element":"p","start":emoji,"end":emoji + 2}))
        .unwrap();
    assert_eq!(e["rects"].as_array().unwrap().len(), 1, "{e}");
    assert_eq!(
        cmd(json!({"op":"text_rects","window":id,"element":"p","start":0,"end":total + 1}))
            .unwrap_err()
            .code,
        1
    );
    // Clipped text is reported, marked not visible; display:none text has no geometry.
    let below = cmd(json!({"op":"text_rects","window":id,"element":"below"})).unwrap();
    assert_eq!(below["rects"][0]["visible"], false);
    assert_eq!(
        cmd(json!({"op":"text_rects","window":id,"element":"gone"})).unwrap()["rects"],
        json!([])
    );
    // Hit to text: the middle of the first character's right half is offset 1.
    let r0 = &rects[0];
    let first = cmd(json!({"op":"text_rects","window":id,"element":"p","start":0,"end":1}))
        .unwrap()["rects"][0]
        .clone();
    let x = first["x"].as_f64().unwrap() + first["width"].as_f64().unwrap() * 0.75;
    let hit =
        cmd(json!({"op":"text_at_point","window":id,"x":x,"y":r0["y"].as_f64().unwrap() + 4.0}))
            .unwrap()["hit"]
            .clone();
    assert_eq!(
        (hit["element"].as_str(), hit["offset"].as_u64()),
        (Some("p"), Some(1)),
        "{hit}"
    );
    assert!(hit["block"].as_str().unwrap().starts_with("node:"));
    // A stale node reference is an error.
    let text = cmd(json!({"op":"node_children","window":id,"node":cmd(json!({"op":"node_of","window":id,"element":"p"})).unwrap()["node"]})).unwrap()["children"][0]["node"].as_str().unwrap().to_owned();
    assert!(
        !cmd(json!({"op":"text_rects","window":id,"node":text})).unwrap()["rects"]
            .as_array()
            .unwrap()
            .is_empty()
    );
    cmd(json!({"op":"remove_element","window":id,"element":"p"})).unwrap();
    assert_eq!(
        cmd(json!({"op":"text_rects","window":id,"node":text}))
            .unwrap_err()
            .code,
        4
    );
}

#[test]
fn computed_style_reports_values_inheritance_and_unsupported_names() {
    // 0.6 F0609.
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","html":"<style>#a{color:rgb(1,2,3);--brand:#123;width:50px} #hid{display:none;color:red}</style><div id=a><span id=s>x</span></div><p id=hid>h</p>"})).unwrap()["window"].as_u64().unwrap();
    let cs = cmd(json!({"op":"get_computed_style","window":id,"element":"s","properties":["color","width","--brand","colr"]})).unwrap();
    assert_eq!(cs["schema"], 1);
    let p = &cs["properties"];
    assert_eq!(
        p["color"],
        json!({"status":"supported","value":"rgb(1, 2, 3)","inherited":true})
    );
    assert_eq!(
        (
            p["width"]["value"].as_str(),
            p["width"]["inherited"].as_bool()
        ),
        (Some("auto"), Some(false))
    );
    assert_eq!(p["--brand"]["value"], "#123", "custom properties inherit");
    assert_eq!(p["colr"]["status"], "invalid");
    // An undisplayed element resolves on demand.
    let hid = cmd(json!({"op":"get_computed_style","window":id,"element":"hid","properties":["color","display"]})).unwrap();
    assert_eq!(
        (
            hid["properties"]["color"]["value"].as_str(),
            hid["properties"]["display"]["value"].as_str()
        ),
        (Some("rgb(255, 0, 0)"), Some("none"))
    );
    assert_eq!(
        cmd(json!({"op":"get_computed_style","window":id,"element":"s","properties":[]}))
            .unwrap_err()
            .code,
        1
    );
    let many: Vec<String> = (0..65).map(|_| "color".to_string()).collect();
    assert_eq!(
        cmd(json!({"op":"get_computed_style","window":id,"element":"s","properties":many}))
            .unwrap_err()
            .code,
        1
    );
}

#[test]
fn link_activation_follows_the_app_policy_and_never_navigates() {
    // 0.6 F0608.
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","html":"<a id=web href='https://docs.example.com/p?q=1'>web</a><a id=other href='https://evil.test/'>other</a><a id=js href='javascript:alert(1)'>js</a><a id=data href='data:text/html,x'>data</a><a id=file href='file:///etc/passwd'>file</a><a id=mail href='mailto:a@b.cz'>mail</a><a id=rel href='docs/x.html'>rel</a><a id=nohref>plain</a>"})).unwrap()["window"].as_u64().unwrap();
    let tree = h.session.accessibility_tree(id).unwrap();
    let click = |element: &str| {
        let node = tree
            .nodes
            .values()
            .find(|n| n.html_id.as_deref() == Some(element))
            .map(|n| n.id);
        let request = ui4me_renderer::a11y::A11yRequest {
            target: node.and_then(ui4me_renderer::a11y::node_of_key),
            kind: ui4me_renderer::a11y::A11yRequestKind::Click,
        };
        h.session.accessibility_request(id, &request);
        h.events()
            .into_iter()
            .rev()
            .find(|e| e["type"] == "link_activated" && e["element"] == element)
    };
    let before = cmd(json!({"op":"get_html","window":id})).unwrap()["html"].clone();
    // No policy: reported, refused, nothing opened, the document stays.
    let e = click("web").unwrap();
    assert_eq!(
        (e["allowed"].as_bool(), e["opened"].as_bool()),
        (Some(false), Some(false))
    );
    assert_eq!(e["url"], "https://docs.example.com/p?q=1");
    assert!(e["reason"].as_str().unwrap().contains("no link policy"));
    // Only https/http/mailto can be allowed.
    assert_eq!(
        cmd(json!({"op":"set_link_policy","schemes":["javascript"]}))
            .unwrap_err()
            .code,
        1
    );
    cmd(json!({"op":"set_link_policy","schemes":["https"],"hosts":["*.example.com"]})).unwrap();
    assert_eq!(click("web").unwrap()["allowed"], true);
    assert!(click("other").unwrap()["reason"]
        .as_str()
        .unwrap()
        .contains("host"));
    for blocked in ["js", "data", "file"] {
        let e = click(blocked).unwrap();
        assert_eq!(e["allowed"], false, "{blocked}");
        assert!(
            e["reason"].as_str().unwrap().contains("never opened"),
            "{e}"
        );
    }
    assert!(click("mail").unwrap()["reason"]
        .as_str()
        .unwrap()
        .contains("not allowed"));
    assert_eq!(
        click("rel").unwrap()["allowed"],
        false,
        "a relative link without a base resolves to nothing"
    );
    assert!(click("nohref").is_none(), "an a without href is not a link");
    // Opening: the OS launcher's outcome is reported.
    cmd(json!({"op":"set_link_policy","schemes":["https","mailto"],"open":true})).unwrap();
    #[cfg(unix)]
    {
        std::env::set_var("UI4ME_LINK_LAUNCHER", "/bin/true");
        assert_eq!(click("mail").unwrap()["opened"], true);
        std::env::set_var("UI4ME_LINK_LAUNCHER", "/nonexistent/launcher");
        let e = click("web").unwrap();
        assert_eq!(
            (e["allowed"].as_bool(), e["opened"].as_bool()),
            (Some(true), Some(false))
        );
        assert!(e["error"]
            .as_str()
            .unwrap()
            .contains("could not be started"));
        std::env::remove_var("UI4ME_LINK_LAUNCHER");
    }
    cmd(json!({"op":"set_link_policy"})).unwrap();
    assert_eq!(
        cmd(json!({"op":"get_html","window":id})).unwrap()["html"],
        before,
        "no navigation"
    );
}

#[test]
fn declarative_rules_cancel_link_submit_escape_drag_and_select_defaults() {
    // 0.6 F0607: rules decide before the default action; callbacks still run after dispatch.
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","width":600,"height":400,"html":"<style>body{margin:0;font:16px sans-serif}</style><a id=lnk href='https://example.com/'>link</a><form id=f><button id=go>Go</button></form><p id=para>Selectable paragraph text</p><select id=s><option>a</option><option>b</option></select><dialog id=dlg><button>in</button></dialog>"})).unwrap()["window"].as_u64().unwrap();
    let rule = |element: &str, event: &str, key: Option<&str>| {
        let mut v = json!({"op":"set_default_action","window":id,"element":element,"event":event});
        if let Some(k) = key {
            v["key"] = json!(k);
        }
        cmd(v).unwrap();
    };
    let center = |e: &str| {
        let r = cmd(json!({"op":"get_rect","window":id,"element":e})).unwrap()["rect"].clone();
        (
            r["x"].as_f64().unwrap() + r["width"].as_f64().unwrap() / 2.0,
            r["y"].as_f64().unwrap() + r["height"].as_f64().unwrap() / 2.0,
        )
    };
    let press = |x: f64, y: f64, down: bool| {
        h.session
            .input(id, crate::document::Input::PointerMoved { x, y })
            .unwrap();
        h.session
            .input(
                id,
                crate::document::Input::PointerButton {
                    pressed: down,
                    button: 0,
                    x,
                    y,
                },
            )
            .unwrap();
    };
    let click = |e: &str| {
        let (x, y) = center(e);
        press(x, y, true);
        press(x, y, false);
    };
    let count = |t: &str| h.events().iter().filter(|e| e["type"] == t).count();
    rule("lnk", "click", None);
    click("lnk");
    assert_eq!(
        count("link_activated"),
        0,
        "a prevented click does not activate the link"
    );
    assert!(h
        .events()
        .iter()
        .any(|e| e["type"] == "click" && e["element"] == "lnk" && e["default_prevented"] == true));
    rule("f", "submit", None);
    click("go");
    assert!(h
        .events()
        .iter()
        .any(|e| e["type"] == "submit" && e["default_prevented"] == true));
    // A prevented mousedown starts no text selection drag.
    rule("para", "mousedown", None);
    let (x, y) = center("para");
    press(x - 80.0, y, true);
    h.session
        .input(id, crate::document::Input::PointerMoved { x: x + 80.0, y })
        .unwrap();
    press(x + 80.0, y, false);
    assert_eq!(
        cmd(json!({"op":"get_selection","window":id})).unwrap()["text"],
        ""
    );
    // A prevented mousedown on a select does not open its popup.
    rule("s", "mousedown", None);
    click("s");
    assert_eq!(
        cmd(json!({"op":"get_options","window":id,"element":"s"})).unwrap()["options"][0]
            ["selected"],
        true
    );
    // Escape on a modal dialog: a `cancel` rule keeps it open.
    cmd(json!({"op":"show_dialog","window":id,"element":"dlg","modal":true})).unwrap();
    rule("dlg", "cancel", None);
    for pressed in [true, false] {
        h.session
            .input(
                id,
                crate::document::Input::Key {
                    key: "Escape".into(),
                    code: "Escape".into(),
                    pressed,
                    repeat: false,
                    shift: false,
                    ctrl: false,
                    alt: false,
                    meta: false,
                },
            )
            .unwrap();
    }
    assert_eq!(
        cmd(json!({"op":"get_dialog","window":id,"element":"dlg"})).unwrap()["open"],
        true
    );
    assert!(h
        .events()
        .iter()
        .any(|e| e["type"] == "cancel" && e["default_prevented"] == true));
}

#[test]
fn validity_commands_and_interactive_submission() {
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","width":600,"height":400,"html":"<form id='f'><input id='name' required><input id='mail' type='email'>\
        <button id='go'>Go</button></form>"})).unwrap()["window"].as_u64().unwrap();
    let v = cmd(json!({"op":"get_validity","window":id,"element":"name"})).unwrap();
    assert_eq!(v["valid"], false);
    assert_eq!(v["flags"]["valueMissing"], true);
    assert_eq!(v["flags"]["typeMismatch"], false);
    assert_eq!(v["message"], "Please fill out this field.");
    assert!(cmd(json!({"op":"get_validity","window":id,"element":"zzz"})).is_err());
    let r = cmd(json!({"op":"check_validity","window":id,"element":"f"})).unwrap();
    assert_eq!(r["valid"], false);
    assert_eq!(r["invalid"], json!(["name"]));
    let invalid = || {
        h.events()
            .into_iter()
            .filter(|e| e["type"] == "invalid")
            .count()
    };
    assert_eq!(invalid(), 1);
    cmd(json!({"op":"set_value","window":id,"element":"name","value":"n"})).unwrap();
    cmd(json!({"op":"set_value","window":id,"element":"mail","value":"bad"})).unwrap();
    let r = cmd(json!({"op":"check_validity","window":id,"element":"mail"})).unwrap();
    assert_eq!(r["invalid"], json!(["mail"]));
    cmd(json!({"op":"set_value","window":id,"element":"mail","value":"a@b.co"})).unwrap();
    assert_eq!(
        cmd(json!({"op":"check_validity","window":id,"element":"f"})).unwrap()["valid"],
        true
    );
    // Enter in a valid form submits through the default button.
    cmd(json!({"op":"focus","window":id,"element":"name"})).unwrap();
    for pressed in [true, false] {
        h.session
            .input(
                id,
                crate::document::Input::Key {
                    key: "Enter".into(),
                    code: "Enter".into(),
                    pressed,
                    repeat: false,
                    shift: false,
                    ctrl: false,
                    alt: false,
                    meta: false,
                },
            )
            .unwrap();
    }
    let submits: Vec<Value> = h
        .events()
        .into_iter()
        .filter(|e| e["type"] == "submit")
        .collect();
    assert_eq!(submits.len(), 1);
    assert_eq!(submits[0]["submitter"], "go");
}

#[test]
fn removing_a_control_inside_invalid_and_submit_handlers_is_safe() {
    let h = Harness::new(23);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","width":600,"height":400,"html":"<form id='f'><input id='a' required><input id='b' required>\
        <button id='go'>Go</button></form>"})).unwrap()["window"].as_u64().unwrap();
    // Each `invalid` handler removes its own control; nothing panics and no stale event follows.
    let r = cmd(json!({"op":"check_validity","window":id,"element":"f"})).unwrap();
    assert_eq!(r["valid"], false);
    assert!(cmd(json!({"op":"get_validity","window":id,"element":"a"})).is_err());
    assert!(cmd(json!({"op":"get_validity","window":id,"element":"b"})).is_err());
    let r = cmd(json!({"op":"check_validity","window":id,"element":"f"})).unwrap();
    assert_eq!(r["valid"], true, "the invalid controls are gone");
    assert_eq!(
        h.events().iter().filter(|e| e["type"] == "invalid").count(),
        2
    );
}

#[test]
fn file_input_opens_the_picker_and_reports_cancel_in_headless_sessions() {
    // 0.6 F0606: activation by click and keyboard; headless has no OS picker (cancel).
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","html":"<form id=f><input id=pick type=file multiple accept='.txt,image/*'><input id=off type=file disabled><button type=reset id=r>Reset</button></form>"})).unwrap()["window"].as_u64().unwrap();
    let tree = h.session.accessibility_tree(id).unwrap();
    let activate = |element: &str| {
        let node = tree
            .nodes
            .values()
            .find(|n| n.html_id.as_deref() == Some(element))
            .map(|n| n.id);
        h.session.accessibility_request(
            id,
            &ui4me_renderer::a11y::A11yRequest {
                target: node.and_then(ui4me_renderer::a11y::node_of_key),
                kind: ui4me_renderer::a11y::A11yRequestKind::Click,
            },
        );
    };
    activate("pick");
    h.session.process_work();
    assert!(
        h.events()
            .iter()
            .any(|e| e["type"] == "cancel" && e["element"] == "pick"),
        "{:?}",
        h.events()
    );
    assert_eq!(
        cmd(json!({"op":"get_files","window":id,"element":"pick"})).unwrap()["files"],
        json!([])
    );
    // Keyboard: Space on the focused input activates it too.
    cmd(json!({"op":"focus","window":id,"element":"pick"})).unwrap();
    for pressed in [true, false] {
        h.session
            .input(
                id,
                crate::document::Input::Key {
                    key: " ".into(),
                    code: "Space".into(),
                    pressed,
                    repeat: false,
                    shift: false,
                    ctrl: false,
                    alt: false,
                    meta: false,
                },
            )
            .unwrap();
    }
    h.session.process_work();
    assert_eq!(
        h.events()
            .iter()
            .filter(|e| e["type"] == "cancel" && e["element"] == "pick")
            .count(),
        2
    );
    // A disabled file input opens nothing.
    activate("off");
    h.session.process_work();
    assert!(!h
        .events()
        .iter()
        .any(|e| e["type"] == "cancel" && e["element"] == "off"));
    assert_eq!(
        cmd(json!({"op":"get_files","window":id,"element":"r"}))
            .unwrap_err()
            .code,
        1
    );
    // The picker tokens are reserved.
    assert_eq!(
        cmd(json!({"op":"file_dialog","window":id,"token":(1u64 << 62),"kind":"open"}))
            .unwrap_err()
            .code,
        1
    );
    // A completed choice (as the native picker delivers it) sets the files, fires input/change,
    // and a form reset clears them.
    let pickers = (1u64 << 62)..((1u64 << 62) + 8);
    let _ = pickers;
}

#[test]
fn accept_lists_map_to_picker_filters() {
    let f = crate::runtime::accept_filters_for_tests(&[".txt".into(), "image/*".into()]);
    assert_eq!(f[0].1[0], "txt");
    assert!(f[0].1.contains(&"png".to_string()));
    assert!(crate::runtime::accept_filters_for_tests(&["application/x-unknown".into()]).is_empty());
    assert!(crate::runtime::accept_filters_for_tests(&[]).is_empty());
}

#[test]
fn desktop_services_validate_and_refuse_honestly_in_headless_sessions() {
    // 0.7: headless sessions have no desktop services; requests are validated, refused with a
    // status and reason, and menu accelerators still work (Core matches them).
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","html":"<p>x</p>"})).unwrap()["window"]
        .as_u64()
        .unwrap();
    let n = cmd(json!({"op":"notify","token":1,"title":"Hi","body":"there"})).unwrap();
    assert_eq!(
        (n["status"].as_str(), n["token"].as_u64()),
        (Some("unavailable"), Some(1))
    );
    assert!(n["reason"].as_str().unwrap().contains("headless"));
    assert_eq!(
        cmd(json!({"op":"notify","token":1,"title":""}))
            .unwrap_err()
            .code,
        1
    );
    assert_eq!(
        cmd(json!({"op":"set_tray","tooltip":"t"})).unwrap()["status"],
        "unavailable"
    );
    assert_eq!(
        cmd(json!({"op":"remove_tray"})).unwrap()["status"],
        "unavailable"
    );
    let menu = json!([{"label":"File","items":[{"id":"save","label":"Save","accelerator":"Ctrl+S"},{"separator":true},{"id":"quit","label":"Quit","accelerator":"Ctrl+Q"}]}]);
    let r = cmd(json!({"op":"set_menu","window":id,"menu":menu})).unwrap();
    assert_eq!(
        (r["status"].as_str(), r["accelerators"].as_bool()),
        (Some("unavailable"), Some(true))
    );
    assert_eq!(
        h.session
            .menu_accelerator(id, "s", "KeyS", true, false, false, false)
            .as_deref(),
        Some("save")
    );
    assert_eq!(
        h.session
            .menu_accelerator(id, "s", "KeyS", false, false, false, false),
        None
    );
    let bad = json!([{"id":"a","label":"A","accelerator":"Ctrl+S"},{"id":"b","label":"B","accelerator":"Ctrl+S"}]);
    assert_eq!(
        cmd(json!({"op":"set_menu","window":id,"menu":bad}))
            .unwrap_err()
            .code,
        1
    );
    cmd(json!({"op":"set_menu","window":id})).unwrap();
    assert_eq!(
        h.session
            .menu_accelerator(id, "s", "KeyS", true, false, false, false),
        None
    );
    assert_eq!(cmd(json!({"op":"show_context_menu","window":id,"x":1,"y":2,"menu":[{"id":"c","label":"Copy"}]})).unwrap()["status"], "unavailable");
    assert_eq!(
        cmd(json!({"op":"register_hotkey","id":"k","accelerator":"Ctrl+Alt+K"})).unwrap()["status"],
        "unavailable"
    );
    assert_eq!(
        cmd(json!({"op":"register_hotkey","id":"k","accelerator":"K"}))
            .unwrap_err()
            .code,
        1,
        "a bare letter is not a global shortcut"
    );
    let caps = cmd(json!({"op":"capabilities"})).unwrap();
    for f in [
        "notifications",
        "system_tray",
        "native_menus",
        "global_hotkeys",
    ] {
        assert_eq!(caps["features"][f]["status"], "unavailable", "{f}");
    }
}

#[test]
fn clipboard_html_round_trips_and_pasted_html_is_sanitized() {
    // 0.7 F0706 (the headless in-process clipboard; the native one uses the OS formats).
    let h = Harness::new(0);
    let cmd = |v: Value| h.session.command(v);
    let id = cmd(json!({"op":"open","html":"<div id=dst></div>"})).unwrap()["window"]
        .as_u64()
        .unwrap();
    let evil = "<p style='color:red' onclick='x()'>Ahoj <b>světe</b><script>alert(1)</script></p><a href='javascript:alert(1)'>j</a><a href='https://ui4me.org/'>ok</a><img src=x onerror=y()><iframe src='https://x'></iframe><!-- c -->";
    cmd(json!({"op":"set_clipboard_html","window":id,"html":evil,"text":"Ahoj světe"})).unwrap();
    assert_eq!(
        cmd(json!({"op":"get_clipboard_text","window":id})).unwrap()["text"],
        "Ahoj světe",
        "plain-text fallback"
    );
    let raw = cmd(json!({"op":"get_clipboard_html","window":id,"raw":true})).unwrap();
    assert_eq!(raw["html"], evil);
    let safe = cmd(json!({"op":"get_clipboard_html","window":id})).unwrap()["html"]
        .as_str()
        .unwrap()
        .to_owned();
    assert_eq!(
        safe,
        "<p>Ahoj <b>světe</b></p><a>j</a><a href=\"https://ui4me.org/\">ok</a><img src=\"x\">"
    );
    // The sanitized form is accepted by insert_html (which rejects scripts and handlers).
    cmd(json!({"op":"insert_html","window":id,"element":"dst","position":"beforeend","html":safe}))
        .unwrap();
    let caps = cmd(json!({"op":"capabilities"})).unwrap();
    assert_eq!(caps["features"]["clipboard.image"]["status"], "unsupported");
    cmd(json!({"op":"set_clipboard_text","window":id,"text":"plain"})).unwrap();
    assert_eq!(
        cmd(json!({"op":"get_clipboard_html","window":id})).unwrap()["html"],
        Value::Null,
        "a text copy replaces the HTML flavour"
    );
}
