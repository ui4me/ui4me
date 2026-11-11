//! 1.0 F1104: protocol and C ABI boundary fuzzing for the session runtime, plus the regression
//! tests that pin every fixed finding. The harnesses are `#[ignore]`d and deterministic:
//!
//!     UI4ME_FUZZ_SECS=300 UI4ME_FUZZ_SEED=1 nice cargo test -p ui4me-core --lib --release \
//!         fuzz_gate::harness -- --ignored --nocapture --test-threads=1
//!
//! `UI4ME_FUZZ_SEED` (default 1), `UI4ME_FUZZ_ITERS` (default 20000 commands / 300 ABI runs),
//! `UI4ME_FUZZ_SECS` (wall budget, 0 = iterations only), `UI4ME_FUZZ_TIMEOUT_MS` (no-progress
//! watchdog, default 30000). A panic, a hang, an unregistered error code or a poisoned runtime is a
//! finding; the last command is printed and the harness fails. No dependencies: xorshift PRNG.
use super::*;
use crate::runtime::lock;
use crate::tests::SERIAL;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, AtomicUsize};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

struct Rng(u64);
impl Rng {
    fn new(seed: u64) -> Self {
        Rng(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15) | 1)
    }
    fn next(&mut self) -> u64 {
        let mut x = self.0;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.0 = x;
        x
    }
    fn below(&mut self, n: usize) -> usize {
        if n == 0 {
            0
        } else {
            (self.next() % n as u64) as usize
        }
    }
    fn chance(&mut self, percent: u64) -> bool {
        self.next() % 100 < percent
    }
    fn pick<'a, T>(&mut self, items: &'a [T]) -> &'a T {
        &items[self.below(items.len())]
    }
}

fn env_u64(name: &str, default: u64) -> u64 {
    std::env::var(name)
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
}

const STRINGS: &[&str] = &[
    "",
    "a",
    "root",
    "p1",
    "b1",
    "in1",
    "ta1",
    "ce",
    "sel",
    "pop",
    "dlg",
    "list",
    "missing",
    "x y",
    "<b>bold</b>",
    "<div id=n1>x</div>",
    "<script>alert(1)</script>",
    "<input id=nx>",
    "beforeend",
    "afterbegin",
    "beforebegin",
    "afterend",
    "start",
    "end",
    "click",
    "keydown",
    "Enter",
    "color",
    "red",
    "display:none",
    "p{color:red}",
    "@import url(http://127.0.0.1:9/a.css);",
    "\u{0}",
    "\u{202e}",
    "𝒜👨‍👩‍👧",
    "node:1:1",
    "node:0:0",
    "node:4294967295:4294967295",
    "A4",
    "letter landscape",
    "smooth",
    "instant",
    "light",
    "dark",
    "maximize",
    "minimize",
    "restore",
    "fullscreen",
    "close",
    "title",
    "{}",
    "[]",
    "null",
    "-1",
    "1e400",
];

/// Operation catalogue: every `Command` variant and its field types, read from the protocol
/// source so the harness cannot drift from the real command set.
fn catalogue() -> Vec<(String, Vec<(String, String)>)> {
    let src = include_str!("protocol.rs");
    let start = src.find("pub enum Command {").expect("Command enum");
    let body = &src[start..];
    let mut out = Vec::new();
    let mut lines = body.lines().skip(1);
    let mut current: Option<(String, Vec<(String, String)>)> = None;
    for line in lines.by_ref() {
        if line == "}" {
            break;
        }
        let t = line.trim();
        if t.starts_with("///") || t.starts_with("#[") || t.is_empty() {
            continue;
        }
        // `    Name {` / `    Name,`
        if line.starts_with("    ") && !line.starts_with("     ") {
            if let Some(c) = current.take() {
                out.push(c);
            }
            let name: String = t.chars().take_while(|c| c.is_alphanumeric()).collect();
            if !name.is_empty() && name.chars().next().unwrap().is_uppercase() {
                current = Some((snake(&name), Vec::new()));
            }
            continue;
        }
        if let Some((_, fields)) = current.as_mut() {
            if let Some((n, ty)) = t.split_once(':') {
                if !n.contains(' ') {
                    fields.push((n.to_owned(), ty.trim().trim_end_matches(',').to_owned()));
                }
            }
        }
    }
    if let Some(c) = current.take() {
        out.push(c);
    }
    out
}

fn snake(name: &str) -> String {
    let mut s = String::new();
    for (i, c) in name.chars().enumerate() {
        if c.is_uppercase() {
            if i > 0 {
                s.push('_');
            }
            s.extend(c.to_lowercase());
        } else {
            s.push(c);
        }
    }
    s
}

fn any_json(rng: &mut Rng, depth: usize) -> Value {
    match rng.below(if depth > 2 { 6 } else { 9 }) {
        0 => Value::Null,
        1 => json!(rng.chance(50)),
        2 => json!(rng.next() % 100),
        3 => json!(*rng.pick(&[-1i64, 0, i64::MAX, i64::MIN, 4_294_967_296])),
        4 => json!(*rng.pick(&[0.5f64, -0.0, 1e300, 1e-300])),
        5 => json!(rng.pick(STRINGS)),
        6 => Value::Array(
            (0..rng.below(4))
                .map(|_| any_json(rng, depth + 1))
                .collect(),
        ),
        _ => {
            let mut m = serde_json::Map::new();
            for _ in 0..rng.below(4) {
                m.insert(rng.pick(STRINGS).to_string(), any_json(rng, depth + 1));
            }
            Value::Object(m)
        }
    }
}

fn typed_json(rng: &mut Rng, ty: &str, windows: &[u64], scratch: &std::path::Path) -> Value {
    if rng.chance(4) {
        return any_json(rng, 0); // wrongly typed on purpose
    }
    let ty = ty.trim();
    if let Some(inner) = ty.strip_prefix("Option<").and_then(|t| t.strip_suffix('>')) {
        return if rng.chance(30) {
            Value::Null
        } else {
            typed_json(rng, inner, windows, scratch)
        };
    }
    if ty.starts_with("Vec<") {
        let inner = ty.trim_start_matches("Vec<").trim_end_matches('>');
        return Value::Array(
            (0..rng.below(5))
                .map(|_| typed_json(rng, inner, windows, scratch))
                .collect(),
        );
    }
    match ty {
        "u64" => json!(if rng.chance(60) && !windows.is_empty() {
            *rng.pick(windows)
        } else {
            *rng.pick(&[0u64, 1, 2, 7, 42, u64::MAX, 1 << 40])
        }),
        "u32" | "u16" | "u8" | "usize" | "i32" | "i64" | "isize" => {
            json!(*rng.pick(&[
                0i64,
                1,
                2,
                3,
                10,
                100,
                240,
                480,
                4096,
                4097,
                -1,
                65_536,
                1 << 33
            ]))
        }
        "f64" | "f32" => json!(*rng.pick(&[0.0f64, 1.0, -1.0, 0.5, 100.0, 1e9, 1e300, 3.5])),
        "bool" => json!(rng.chance(50)),
        "PathBuf" => json!(scratch
            .join(*rng.pick(&["a.html", "b.pdf", "c.png", "missing/x", "", "d"]))
            .to_string_lossy()
            .into_owned()),
        "String" => json!(rng.pick(STRINGS)),
        _ => any_json(rng, 0),
    }
}

fn command(
    rng: &mut Rng,
    cat: &[(String, Vec<(String, String)>)],
    windows: &[u64],
    scratch: &std::path::Path,
) -> Value {
    let (op, fields) = rng.pick(cat);
    let mut m = serde_json::Map::new();
    m.insert("op".into(), json!(op));
    for (name, ty) in fields {
        if rng.chance(4) {
            continue; // missing field
        }
        let mut v = if name == "window" && !windows.is_empty() && rng.chance(85) {
            json!(*rng.pick(windows))
        } else {
            typed_json(rng, ty, windows, scratch)
        };
        if name == "html" && rng.chance(60) {
            v = json!(format!(
                "<div id=n{}>{}</div>",
                rng.below(5),
                rng.pick(STRINGS)
            ));
        }
        m.insert(name.clone(), v);
    }
    if rng.chance(3) {
        m.insert(rng.pick(STRINGS).to_string(), any_json(rng, 0)); // unknown field
    }
    if rng.chance(2) {
        return any_json(rng, 0); // not even an object
    }
    Value::Object(m)
}

const BASE_HTML: &str = "<div id=root><p id=p1>Hello <b id=b1>world</b></p><input id=in1 value=x><textarea id=ta1>abc</textarea><div id=ce contenteditable>edit</div><select id=sel><option>1<option>2</select><div id=pop popover>pop</div><dialog id=dlg>d</dialog><ul id=list><li>1<li>2</ul></div>";

fn code_ok(e: &Error) -> bool {
    (1..=9).contains(&e.code) && !e.message.is_empty()
}

fn session_env() -> (std::sync::MutexGuard<'static, ()>, PathBuf) {
    let g = lock(&SERIAL);
    let dir = std::env::temp_dir().join(format!("ui4me-fuzz-core-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("a.html"), "<p id=file>from file</p>").unwrap();
    (g, dir)
}

// ---------------------------------------------------------------------------------------------
// Harness 5: random JSON commands into Session::command
// ---------------------------------------------------------------------------------------------

#[test]
#[ignore = "fuzz harness; see module docs"]
fn harness_protocol() {
    let (_g, scratch) = session_env();
    let seed = env_u64("UI4ME_FUZZ_SEED", 1);
    let iters = env_u64("UI4ME_FUZZ_ITERS", 20_000);
    let secs = env_u64("UI4ME_FUZZ_SECS", 0);
    let timeout = Duration::from_millis(env_u64("UI4ME_FUZZ_TIMEOUT_MS", 30_000));
    let progress = Arc::new(AtomicU64::new(0));
    let last = Arc::new(Mutex::new(String::new()));
    let (p2, l2, scratch2) = (progress.clone(), last.clone(), scratch.clone());
    let worker = std::thread::Builder::new()
        .stack_size(8 << 20)
        .spawn(move || {
            let cat = catalogue();
            assert!(cat.len() > 80, "catalogue parse found {} ops", cat.len());
            eprintln!("protocol fuzz: {} ops", cat.len());
            let mut rng = Rng::new(seed);
            let id = runtime::create(json!({"backend":"headless"}), None, ptr::null_mut()).unwrap();
            let session = runtime::get(id).unwrap();
            let started = Instant::now();
            let (mut n, mut errors, mut oks) = (0u64, 0u64, 0u64);
            let mut codes = [0u64; 10];
            let mut windows: Vec<u64> = Vec::new();
            while (secs == 0 && n < iters) || (secs > 0 && started.elapsed().as_secs() < secs) {
                if windows.is_empty() || n % 500 == 0 {
                    // keep a small pool of open windows
                    if let Ok(v) = session.command(json!({"op":"open","html":BASE_HTML})) {
                        windows.push(v["window"].as_u64().unwrap());
                    }
                    if windows.len() > 6 {
                        windows.remove(0);
                    }
                }
                let cmd = command(&mut rng, &cat, &windows, &scratch2);
                *lock(&l2) = cmd.to_string();
                match session.command(cmd.clone()) {
                    Ok(v) => {
                        oks += 1;
                        if let Some(w) = v.get("window").and_then(Value::as_u64) {
                            if !windows.contains(&w) && cmd["op"] == "open" {
                                windows.push(w);
                            }
                        }
                    }
                    Err(e) => {
                        errors += 1;
                        assert!(code_ok(&e), "unregistered error {e:?} for {cmd}");
                        codes[e.code as usize] += 1;
                    }
                }
                assert!(!POISONED.load(Ordering::Acquire), "runtime poisoned by {cmd}");
                n += 1;
                p2.store(n, Ordering::Relaxed);
                // closed windows leave the pool lazily: a stale id must be rejected, not reused
                if cmd["op"] == "close" || cmd["op"] == "window_action" {
                    windows.retain(|w| {
                        session
                            .command(json!({"op":"get_window_state","window":w}))
                            .is_ok()
                    });
                }
            }
            eprintln!(
                "protocol fuzz: seed {seed}, {n} commands in {:.1}s, {oks} ok, {errors} errors by code {codes:?}",
                started.elapsed().as_secs_f64()
            );
            let _ = runtime::destroy(id);
        })
        .unwrap();
    // watchdog: no progress for `timeout` is a hang
    let mut seen = 0;
    let mut stalled = Instant::now();
    while !worker.is_finished() {
        std::thread::sleep(Duration::from_millis(200));
        let now = progress.load(Ordering::Relaxed);
        if now != seen {
            seen = now;
            stalled = Instant::now();
        } else if stalled.elapsed() > timeout {
            let c = lock(&last).clone();
            let f = scratch.join(format!("protocol-hang-seed{seed}.json"));
            std::fs::write(&f, &c).ok();
            panic!("FINDING hang: command did not return in {timeout:?}: {c} (saved {f:?})");
        }
    }
    if let Err(e) = worker.join() {
        let c = lock(&last).clone();
        let f = scratch.join(format!("protocol-panic-seed{seed}.json"));
        std::fs::write(&f, &c).ok();
        std::panic::resume_unwind(Box::new(format!(
            "FINDING panic with command {c} (saved {f:?}): {:?}",
            e.downcast_ref::<String>()
        )));
    }
}

// ---------------------------------------------------------------------------------------------
// Harness 6: C ABI boundary - random call sequences with hostile callbacks
// ---------------------------------------------------------------------------------------------

struct AbiState {
    rng: Mutex<Rng>,
    events: AtomicUsize,
    violation: Mutex<Option<String>>,
    id: AtomicU64,
    windows: Mutex<Vec<u64>>,
}

fn abi_code_ok(code: i32) -> bool {
    (0..=9).contains(&code)
}

fn call(state: &AbiState, what: &str, code: i32) {
    if !abi_code_ok(code) {
        *lock(&state.violation) = Some(format!("{what} returned unregistered code {code}"));
    }
}

extern "C" fn abi_callback(id: u64, text: *const c_char, user: *mut c_void) -> i32 {
    catch_unwind(AssertUnwindSafe(|| {
        let state = unsafe { &*(user as *const AbiState) };
        let n = state.events.fetch_add(1, Ordering::SeqCst);
        let event: Value = serde_json::from_slice(unsafe { CStr::from_ptr(text) }.to_bytes())
            .unwrap_or(Value::Null);
        if event.is_null() {
            *lock(&state.violation) = Some("callback received invalid JSON".into());
        }
        if n > 150 {
            call(state, "stop", ui4me_session_stop(id));
            return 0;
        }
        let (action, tok) = {
            let mut r = lock(&state.rng);
            (r.below(16), r.next() % 8)
        };
        let window = lock(&state.windows).first().copied().unwrap_or(1);
        if std::env::var_os("UI4ME_FUZZ_TRACE").is_some() {
            eprintln!("  cb event {} #{n} -> action {action}", event["type"]);
        }
        match action {
            0 => call(state, "stop", ui4me_session_stop(id)),
            1 => call(state, "post", ui4me_session_post(id, tok)),
            2 => {
                let cmd = CString::new(
                    json!({"op":"set_text","window":window,"element":"p1","text":"re-entrant"})
                        .to_string(),
                )
                .unwrap();
                let mut out = ptr::null();
                call(state, "command", unsafe {
                    ui4me_session_command(id, cmd.as_ptr(), &mut out)
                });
            }
            3 => call(state, "destroy", ui4me_session_destroy(id)),
            4 => return -1,
            5 => return 1,
            6 => call(state, "run", ui4me_session_run(id)),
            7 => {
                let mut out = 0u64;
                let cfg = CString::new(r#"{"backend":"headless"}"#).unwrap();
                call(state, "create", unsafe {
                    ui4me_session_create(cfg.as_ptr(), None, ptr::null_mut(), &mut out)
                });
            }
            8 => call(state, "complete", ui4me_session_complete(id, tok)),
            9 => {
                // wrong thread: everything but stop/post/complete must be refused with a code
                let h = std::thread::spawn(move || {
                    let cmd = CString::new(r#"{"op":"stats"}"#).unwrap();
                    let mut out = ptr::null();
                    let a = unsafe { ui4me_session_command(id, cmd.as_ptr(), &mut out) };
                    (a, ui4me_session_run(id), ui4me_session_destroy(id))
                });
                match h.join() {
                    Ok((a, b, c)) => {
                        for (w, code) in [
                            ("x-thread command", a),
                            ("x-thread run", b),
                            ("x-thread destroy", c),
                        ] {
                            if code == 0 {
                                *lock(&state.violation) = Some(format!("{w} was accepted"));
                            }
                            call(state, w, code);
                        }
                    }
                    Err(_) => *lock(&state.violation) = Some("cross-thread call panicked".into()),
                }
            }
            10 => {
                let cmd = CString::new(json!({"op":"open","html":"<p id=p1>new</p>"}).to_string())
                    .unwrap();
                let mut out = ptr::null();
                call(state, "open", unsafe {
                    ui4me_session_command(id, cmd.as_ptr(), &mut out)
                });
            }
            11 => {
                let cmd = CString::new(
                    json!({"op":"timer","token":tok,"milliseconds":1,"repeat":false}).to_string(),
                )
                .unwrap();
                let mut out = ptr::null();
                call(state, "timer", unsafe {
                    ui4me_session_command(id, cmd.as_ptr(), &mut out)
                });
            }
            12 => {
                let cmd = CString::new(json!({"op":"close","window":window}).to_string()).unwrap();
                let mut out = ptr::null();
                call(state, "close", unsafe {
                    ui4me_session_command(id, cmd.as_ptr(), &mut out)
                });
            }
            13 => {
                let cmd = CString::new(json!({"op":"reserve_completion","token":tok}).to_string())
                    .unwrap();
                let mut out = ptr::null();
                call(state, "reserve", unsafe {
                    ui4me_session_command(id, cmd.as_ptr(), &mut out)
                });
            }
            _ => {}
        }
        0
    }))
    .unwrap_or(-1)
}

#[test]
#[ignore = "fuzz harness; see module docs"]
fn harness_abi_sequences() {
    let (_g, _scratch) = session_env();
    let seed = env_u64("UI4ME_FUZZ_SEED", 1);
    let iters = env_u64("UI4ME_FUZZ_ITERS", 300);
    let secs = env_u64("UI4ME_FUZZ_SECS", 0);
    let timeout = Duration::from_millis(env_u64("UI4ME_FUZZ_TIMEOUT_MS", 30_000));
    let progress = Arc::new(AtomicU64::new(0));
    let p2 = progress.clone();
    let worker = std::thread::Builder::new()
        .stack_size(8 << 20)
        .spawn(move || {
            let started = Instant::now();
            let mut n = 0u64;
            let mut codes = [0u64; 10];
            while (secs == 0 && n < iters) || (secs > 0 && started.elapsed().as_secs() < secs) {
                let state = Box::new(AbiState {
                    rng: Mutex::new(Rng::new(seed.wrapping_add(n * 7919))),
                    events: AtomicUsize::new(0),
                    violation: Mutex::new(None),
                    id: AtomicU64::new(0),
                    windows: Mutex::new(Vec::new()),
                });
                let user = (&*state as *const AbiState).cast_mut().cast::<c_void>();
                let cfg = CString::new(r#"{"backend":"headless"}"#).unwrap();
                let mut id = 0u64;
                let c = unsafe {
                    ui4me_session_create(cfg.as_ptr(), Some(abi_callback), user, &mut id)
                };
                assert_eq!(c, 0, "create failed in iteration {n}");
                state.id.store(id, Ordering::SeqCst);
                for html in ["<p id=p1>one</p>", "<p id=p1>two</p>"] {
                    let cmd = CString::new(json!({"op":"open","html":html}).to_string()).unwrap();
                    let mut out = ptr::null();
                    if unsafe { ui4me_session_command(id, cmd.as_ptr(), &mut out) } == 0 {
                        let v: Value =
                            serde_json::from_slice(unsafe { CStr::from_ptr(out) }.to_bytes())
                                .unwrap();
                        lock(&state.windows).push(v["window"].as_u64().unwrap());
                    }
                }
                // some sequences stop before run: the posts must settle
                if lock(&state.rng).chance(15) {
                    ui4me_session_stop(id);
                }
                for tok in 0..3 {
                    call(&state, "post", ui4me_session_post(id, tok));
                }
                // An idle headless session waits for input forever (as a real app does): the
                // cross-thread stop is the way out, and it is part of what is being exercised.
                let stopper = std::thread::spawn(move || {
                    std::thread::sleep(Duration::from_millis(150));
                    ui4me_session_stop(id)
                });
                let rc = ui4me_session_run(id);
                assert!(abi_code_ok(stopper.join().unwrap()));
                codes[rc as usize % 10] += 1;
                call(&state, "run", rc);
                // after run: post/stop/complete have defined results, run is terminal, destroy ok
                call(&state, "post-after-stop", ui4me_session_post(id, 1));
                if ui4me_session_post(id, 1) == 0 {
                    *lock(&state.violation) =
                        Some("post accepted after the session stopped".into());
                }
                call(&state, "run-again", ui4me_session_run(id));
                let d = ui4me_session_destroy(id);
                call(&state, "destroy", d);
                if d != 0 {
                    *lock(&state.violation) = Some(format!("destroy after run returned code {d}"));
                }
                if ui4me_session_destroy(id) == 0 {
                    *lock(&state.violation) = Some("double destroy accepted".into());
                }
                // destroyed ids are stale: every call is refused with the stale code
                let cmd = CString::new(r#"{"op":"stats"}"#).unwrap();
                let mut out = ptr::null();
                let stale = unsafe { ui4me_session_command(id, cmd.as_ptr(), &mut out) };
                if stale != 4 {
                    *lock(&state.violation) =
                        Some(format!("destroyed session answered code {stale}"));
                }
                if let Some(v) = lock(&state.violation).take() {
                    panic!(
                        "FINDING ABI iteration {n} (seed {}): {v}",
                        seed.wrapping_add(n * 7919)
                    );
                }
                assert!(
                    !POISONED.load(Ordering::Acquire),
                    "runtime poisoned in iteration {n}"
                );
                n += 1;
                p2.store(n, Ordering::Relaxed);
                drop(state);
            }
            eprintln!(
                "abi fuzz: seed {seed}, {n} sessions in {:.1}s, run() results by code {codes:?}",
                started.elapsed().as_secs_f64()
            );
        })
        .unwrap();
    let mut seen = 0;
    let mut stalled = Instant::now();
    while !worker.is_finished() {
        std::thread::sleep(Duration::from_millis(200));
        let now = progress.load(Ordering::Relaxed);
        if now != seen {
            seen = now;
            stalled = Instant::now();
        } else if stalled.elapsed() > timeout {
            panic!("FINDING hang: an ABI sequence did not finish within {timeout:?} (seed {seed}, iteration {seen})");
        }
    }
    if let Err(e) = worker.join() {
        std::panic::resume_unwind(e);
    }
}

// ---------------------------------------------------------------------------------------------
// Regression tests: expected codes at the C ABI boundary (not ignored)
// ---------------------------------------------------------------------------------------------

fn abi_command(id: u64, v: Value) -> (i32, Option<Value>) {
    let cmd = CString::new(v.to_string()).unwrap();
    let mut out = ptr::null();
    let code = unsafe { ui4me_session_command(id, cmd.as_ptr(), &mut out) };
    let value = (!out.is_null())
        .then(|| serde_json::from_slice(unsafe { CStr::from_ptr(out) }.to_bytes()).unwrap());
    (code, value)
}

fn last_error_code() -> i64 {
    let text = unsafe { CStr::from_ptr(ui4me_last_error()) }
        .to_str()
        .unwrap()
        .to_owned();
    serde_json::from_str::<Value>(&text).map_or(0, |v| v["code"].as_i64().unwrap_or(-1))
}

#[test]
fn abi_rejects_null_invalid_and_stale_arguments_with_codes() {
    let (_g, _s) = session_env();
    let cfg = CString::new(r#"{"backend":"headless"}"#).unwrap();
    // null out pointer, invalid JSON, wrong config types, unknown fields
    assert_eq!(
        unsafe { ui4me_session_create(cfg.as_ptr(), None, ptr::null_mut(), ptr::null_mut()) },
        1
    );
    let mut id = 7u64;
    assert_eq!(
        unsafe { ui4me_session_create(ptr::null(), None, ptr::null_mut(), &mut id) },
        1
    );
    assert_eq!(id, 0, "out_session is zeroed on failure");
    for bad in [
        "{",
        r#"{"backend":5}"#,
        r#"{"backend":"headless","bogus":1}"#,
        r#"{"backend":"headless","app_id":"a b"}"#,
        r#"{"backend":"headless","app_id":""}"#,
    ] {
        let c = CString::new(bad).unwrap();
        let code = unsafe { ui4me_session_create(c.as_ptr(), None, ptr::null_mut(), &mut id) };
        assert_eq!(code, 1, "{bad}");
        assert_eq!(last_error_code(), 1);
    }
    // oversized JSON (> 2 MiB) is a limit error, not an allocation
    let huge = CString::new(format!(
        "{{\"backend\":\"headless\",\"pad\":\"{}\"}}",
        "x".repeat(2 * 1024 * 1024 + 8)
    ))
    .unwrap();
    assert_eq!(
        unsafe { ui4me_session_create(huge.as_ptr(), None, ptr::null_mut(), &mut id) },
        5
    );
    // invalid UTF-8 bytes in a command
    unsafe {
        let mut id = 0u64;
        assert_eq!(
            ui4me_session_create(cfg.as_ptr(), None, ptr::null_mut(), &mut id),
            0
        );
        let bytes = b"{\"op\":\"stats\",\"x\":\"\xff\xfe\"}\0";
        let mut out = ptr::null();
        assert_eq!(
            ui4me_session_command(id, bytes.as_ptr().cast(), &mut out),
            1
        );
        assert_eq!(ui4me_session_command(id, ptr::null(), &mut out), 1);
        assert_eq!(ui4me_session_command(id, cfg.as_ptr(), ptr::null_mut()), 1);
        // not an object / unknown op / missing window
        assert_eq!(abi_command(id, json!([1])).0, 1);
        assert_eq!(abi_command(id, json!({"op":"nope"})).0, 1);
        assert_eq!(
            abi_command(
                id,
                json!({"op":"set_text","window":999,"element":"a","text":"b"})
            )
            .0,
            4
        );
        assert_eq!(ui4me_session_destroy(id), 0);
        // ids: zero, unknown, destroyed, the maximum
        for stale in [0u64, 1, id, u64::MAX] {
            assert_eq!(ui4me_session_run(stale), 4, "run {stale}");
            assert_eq!(ui4me_session_post(stale, 1), 4);
            assert_eq!(ui4me_session_stop(stale), 4);
            assert_eq!(ui4me_session_complete(stale, 1), 4);
            assert_eq!(ui4me_session_destroy(stale), 4);
            assert_eq!(abi_command(stale, json!({"op":"stats"})).0, 4);
        }
    }
}

#[test]
fn abi_wrong_thread_calls_are_refused_and_stop_is_safe() {
    let (_g, _s) = session_env();
    let mut id = 0u64;
    let cfg = CString::new(r#"{"backend":"headless"}"#).unwrap();
    assert_eq!(
        unsafe { ui4me_session_create(cfg.as_ptr(), None, ptr::null_mut(), &mut id) },
        0
    );
    let results = std::thread::spawn(move || {
        let open = abi_command(id, json!({"op":"open","html":"<p>x</p>"})).0;
        let run = ui4me_session_run(id);
        let destroy = ui4me_session_destroy(id);
        (
            open,
            run,
            destroy,
            ui4me_session_stop(id),
            ui4me_session_post(id, 1),
        )
    })
    .join()
    .unwrap();
    assert_eq!(results, (3, 3, 3, 0, 2), "mutation, run and destroy are owner-thread only; stop is not, and a post after stop is refused");
    assert_eq!(
        ui4me_session_run(id),
        0,
        "a stop requested from elsewhere ends the run"
    );
    assert_eq!(ui4me_session_destroy(id), 0);
}

#[test]
fn abi_callback_errors_destroy_and_post_after_stop_have_defined_codes() {
    extern "C" fn cb(id: u64, text: *const c_char, user: *mut c_void) -> i32 {
        let log = unsafe { &*(user as *const Mutex<Vec<(String, i32)>>) };
        let ev: Value = serde_json::from_slice(unsafe { CStr::from_ptr(text) }.to_bytes()).unwrap();
        let ty = ev["type"].as_str().unwrap_or("").to_owned();
        if ty == "started" {
            // destroy during run, run re-entry, a command re-entry, then ask for a callback error
            let d = ui4me_session_destroy(id);
            let r = ui4me_session_run(id);
            lock(log).push(("destroy-in-run".into(), d));
            lock(log).push(("run-in-run".into(), r));
            lock(log).push((
                "command-in-callback".into(),
                abi_command(id, json!({"op":"stats"})).0,
            ));
            lock(log).push(("stop".into(), ui4me_session_stop(id)));
            lock(log).push(("post-after-stop".into(), ui4me_session_post(id, 1)));
            return -1;
        }
        0
    }
    let (_g, _s) = session_env();
    let log: Box<Mutex<Vec<(String, i32)>>> = Box::new(Mutex::new(Vec::new()));
    let user = (&*log as *const Mutex<Vec<(String, i32)>>)
        .cast_mut()
        .cast();
    let mut id = 0u64;
    let cfg = CString::new(r#"{"backend":"headless"}"#).unwrap();
    assert_eq!(
        unsafe { ui4me_session_create(cfg.as_ptr(), Some(cb), user, &mut id) },
        0
    );
    assert_eq!(abi_command(id, json!({"op":"open","html":"<p>x</p>"})).0, 0);
    assert_eq!(
        ui4me_session_run(id),
        7,
        "a failing callback ends run with the callback code"
    );
    let log = lock(&log).clone();
    let get = |k: &str| log.iter().find(|(n, _)| n == k).unwrap().1;
    assert_eq!(
        get("destroy-in-run"),
        2,
        "destroy during run is a state error"
    );
    assert_eq!(get("run-in-run"), 2, "run is not re-entrant");
    assert_eq!(
        get("command-in-callback"),
        0,
        "owner-thread commands from callbacks are allowed"
    );
    assert_eq!(get("post-after-stop"), 2, "post after stop is refused");
    assert_eq!(
        ui4me_session_post(id, 1),
        2,
        "post after the run ended is refused"
    );
    assert_eq!(ui4me_session_destroy(id), 0);
    assert_eq!(
        ui4me_session_post(id, 1),
        4,
        "post on a destroyed session is stale"
    );
}
