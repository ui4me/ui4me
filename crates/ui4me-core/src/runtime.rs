use crate::document::Document;
use crate::{Error, Result};
use serde_json::{json, Value};
use std::collections::{BTreeMap, VecDeque};
use std::ffi::{c_char, c_void, CString};
use std::fs::File;
use std::io::BufWriter;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Condvar, Mutex, MutexGuard, OnceLock};
use std::thread::{self, ThreadId};
use std::time::{Duration, Instant};

pub type Callback = extern "C" fn(u64, *const c_char, *mut c_void) -> i32;
static NEXT_ID: AtomicU64 = AtomicU64::new(1);
static ACTIVE: OnceLock<Mutex<Option<Arc<Session>>>> = OnceLock::new();

pub fn lock<T>(m: &Mutex<T>) -> MutexGuard<'_, T> { m.lock().unwrap_or_else(|e| e.into_inner()) }
fn active() -> &'static Mutex<Option<Arc<Session>>> { ACTIVE.get_or_init(|| Mutex::new(None)) }
fn next_id() -> Result<u64> {
    NEXT_ID.fetch_update(Ordering::Relaxed, Ordering::Relaxed, |v| v.checked_add(1))
        .map_err(|_| Error::limit("identifier space exhausted"))
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Phase { Ready, Running, Stopped }

#[derive(Clone)]
pub struct WindowModel {
    pub document: Document,
    pub title: String,
    pub width: u32,
    pub height: u32,
    pub pixel_width: u32,
    pub pixel_height: u32,
    pub scale: f64,
    pub closing: bool,
    pub dirty: bool,
    pub resize_revision: u64,
}
pub struct Timer { pub due: Instant, pub interval: Duration, pub repeat: bool }
#[derive(Default)]
pub struct Stats {
    pub posted: u64, pub executed: u64, pub cancelled: u64,
    pub callbacks: u64, pub loop_turns: u64, pub wait_requests: u64,
}
pub struct State {
    pub phase: Phase,
    pub stop: bool,
    pub windows: BTreeMap<u64, WindowModel>,
    pub had_window: bool,
    pub posts: VecDeque<u64>,
    pub timers: BTreeMap<u64, Timer>,
    pub failure: Option<Error>,
    pub stats: Stats,
}
pub struct Session {
    pub id: u64,
    pub owner: ThreadId,
    pub native: bool,
    pub app_id: String,
    callback: Option<Callback>,
    user: usize,
    pub state: Mutex<State>,
    changed: Condvar,
    #[cfg(feature = "native")]
    pub proxy: Mutex<Option<winit::event_loop::EventLoopProxy<()>>>,
}

pub fn get(id: u64) -> Result<Arc<Session>> {
    lock(active()).as_ref().filter(|s| s.id == id).cloned().ok_or_else(|| Error::stale("unknown or destroyed session"))
}
pub fn create(config: Value, callback: Option<Callback>, user: *mut c_void) -> Result<u64> {
    if crate::POISONED.load(Ordering::Acquire) { return Err(Error::poison("runtime is poisoned; start a fresh process")); }
    let map = config.as_object().ok_or_else(|| Error::arg("configuration must be a JSON object"))?;
    for key in map.keys() { if key != "backend" && key != "app_id" { return Err(Error::arg(format!("unknown configuration field: {key}"))); } }
    let backend = config.get("backend").map(|v| v.as_str().ok_or_else(|| Error::arg("backend must be a string"))).transpose()?.unwrap_or("native");
    if !matches!(backend, "native" | "headless") { return Err(Error::arg("backend must be native or headless")); }
    let app_id = config.get("app_id").map(|v| v.as_str().ok_or_else(|| Error::arg("app_id must be a string"))).transpose()?.unwrap_or("org.ui4me.app").to_owned();
    if app_id.is_empty() || app_id.len() > 128 || !app_id.chars().all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '-' | '_')) {
        return Err(Error::arg("app_id must be 1..128 ASCII letters, digits, dot, hyphen or underscore"));
    }
    #[cfg(not(feature = "native"))]
    if backend == "native" { return Err(Error::native("this build does not include the native backend")); }
    let mut active = lock(active());
    if active.is_some() { return Err(Error::state("another session exists; destroy it before creating a new one")); }
    let id = next_id()?;
    *active = Some(Arc::new(Session {
        id, owner: thread::current().id(), native: backend == "native", app_id, callback, user: user as usize,
        state: Mutex::new(State { phase: Phase::Ready, stop: false, windows: BTreeMap::new(), had_window: false, posts: VecDeque::new(), timers: BTreeMap::new(), failure: None, stats: Stats::default() }),
        changed: Condvar::new(),
        #[cfg(feature = "native")]
        proxy: Mutex::new(None),
    }));
    Ok(id)
}

impl Session {
    pub fn assert_owner(&self) -> Result<()> {
        if self.owner != thread::current().id() { Err(Error::thread("operation requires the session owner thread")) } else { Ok(()) }
    }
    pub fn wake(&self) {
        self.changed.notify_all();
        #[cfg(feature = "native")]
        if let Some(proxy) = lock(&self.proxy).as_ref() { let _ = proxy.send_event(()); }
    }
    pub fn stop(&self) -> Result<()> {
        let mut s = lock(&self.state);
        // stop is idempotent for an existing terminal session.
        s.stop = true;
        drop(s);
        self.wake();
        Ok(())
    }
    pub fn post(&self, token: u64) -> Result<()> {
        let mut s = lock(&self.state);
        if s.stop || s.phase == Phase::Stopped { return Err(Error::state("session is stopping or stopped")); }
        if s.posts.len() >= 512 { return Err(Error::limit("deferred queue is full (512)")); }
        s.posts.push_back(token);
        s.stats.posted += 1;
        drop(s);
        self.wake();
        Ok(())
    }
    pub fn fail(&self, error: Error) {
        let mut s = lock(&self.state);
        if s.failure.is_none() { s.failure = Some(error); }
        s.stop = true;
        drop(s);
        self.wake();
    }
    /// No lock is held when the foreign callback executes. Reentrant commands are supported.
    pub fn emit(&self, event: Value) -> i32 {
        let Some(callback) = self.callback else { return 0; };
        lock(&self.state).stats.callbacks += 1;
        let Ok(text) = CString::new(event.to_string()) else { self.fail(Error::arg("event serialization contains NUL")); return -1; };
        let result = callback(self.id, text.as_ptr(), self.user as *mut c_void);
        if result < 0 { self.fail(Error::callback("binding callback failed; inspect the binding exception")); }
        result
    }
    pub fn should_stop(&self) -> bool { lock(&self.state).stop }
    pub fn close_requested(&self, id: u64) -> bool {
        if !lock(&self.state).windows.contains_key(&id) { return false; }
        let veto = self.emit(json!({"type":"close_requested","window":id})) == 1;
        let mut state = lock(&self.state);
        if let Some(w) = state.windows.get_mut(&id) { w.closing = false; }
        !veto || state.stop
    }
    /// Native resources must already have been dropped before calling this.
    pub fn closed(&self, id: u64) {
        if lock(&self.state).windows.remove(&id).is_some() {
            self.emit(json!({"type":"closed","window":id}));
        }
        let mut state = lock(&self.state);
        if state.had_window && state.windows.is_empty() { state.stop = true; }
    }
    pub fn process_work(&self) {
        lock(&self.state).stats.loop_turns += 1;
        // A bounded batch allows OS input and timers to make progress under producer load.
        for _ in 0..64 {
            let token = { let mut s = lock(&self.state); if s.stop { None } else { let p = s.posts.pop_front(); if p.is_some() { s.stats.executed += 1; } p } };
            let Some(token) = token else { break; };
            self.emit(json!({"type":"post","token":token}));
        }
        let now = Instant::now();
        let due: Vec<u64> = lock(&self.state).timers.iter().filter(|(_, t)| t.due <= now).map(|(id, _)| *id).collect();
        for token in due {
            let fire = {
                let mut s = lock(&self.state);
                if s.stop { false } else if let Some(timer) = s.timers.get_mut(&token) {
                    if timer.due > now { false } else {
                        if timer.repeat { timer.due = now + timer.interval; } else { s.timers.remove(&token); }
                        true
                    }
                } else { false }
            };
            if fire { self.emit(json!({"type":"timer","token":token})); }
        }
    }
    pub fn deadline(&self) -> Option<Instant> { lock(&self.state).timers.values().map(|t| t.due).min() }
    pub fn has_work(&self) -> bool { let s = lock(&self.state); s.stop || !s.posts.is_empty() || s.windows.values().any(|w| w.closing) }
    pub fn finish(&self) -> Result<()> {
        // Called after the native adapter drops surfaces/windows, or after a headless loop.
        let windows = {
            let mut s = lock(&self.state);
            s.stop = true;
            s.stats.cancelled += s.posts.len() as u64;
            s.posts.clear();
            s.timers.clear();
            s.windows.keys().copied().collect::<Vec<_>>()
        };
        for id in windows { self.closed(id); }
        lock(&self.state).phase = Phase::Stopped;
        self.emit(json!({"type":"stopped"}));
        #[cfg(feature = "native")]
        { *lock(&self.proxy) = None; }
        let error = lock(&self.state).failure.clone();
        if let Some(error) = error { Err(error) } else { Ok(()) }
    }
    pub fn run(self: &Arc<Self>) -> Result<()> {
        self.assert_owner()?;
        {
            let mut s = lock(&self.state);
            if s.phase != Phase::Ready { return Err(Error::state("a session can run only once; create a fresh session")); }
            s.phase = Phase::Running;
        }
        if !self.should_stop() {
            if self.native {
                #[cfg(feature = "native")]
                if let Err(error) = crate::native::run(self.clone()) { self.fail(error); }
                #[cfg(not(feature = "native"))]
                self.fail(Error::native("native backend is not compiled"));
            } else {
                self.emit(json!({"type":"started","backend":"headless"}));
                while !self.should_stop() {
                    self.process_work();
                    let closing: Vec<u64> = lock(&self.state).windows.iter().filter(|(_, w)| w.closing).map(|(id, _)| *id).collect();
                    for id in closing { if self.close_requested(id) { self.closed(id); } }
                    let mut state = lock(&self.state);
                    if state.stop || !state.posts.is_empty() || state.windows.values().any(|w| w.closing) { continue; }
                    let deadline = state.timers.values().map(|t| t.due).min();
                    state.stats.wait_requests += 1;
                    if let Some(deadline) = deadline {
                        let timeout = deadline.saturating_duration_since(Instant::now());
                        let _guard = self.changed.wait_timeout(state, timeout).unwrap_or_else(|e| e.into_inner());
                    } else {
                        let _guard = self.changed.wait(state).unwrap_or_else(|e| e.into_inner());
                    }
                }
            }
        }
        self.finish()
    }

    pub fn command(&self, value: Value) -> Result<Value> {
        self.assert_owner()?;
        let op = string(&value, "op")?;
        if op == "stats" {
            let s = lock(&self.state);
            return Ok(json!({"phase":format!("{:?}", s.phase).to_ascii_lowercase(),"windows":s.windows.len(),"pending_posts":s.posts.len(),"timers":s.timers.len(),"posted":s.stats.posted,"executed":s.stats.executed,"cancelled":s.stats.cancelled,"callbacks":s.stats.callbacks,"loop_turns":s.stats.loop_turns,"wait_requests":s.stats.wait_requests}));
        }
        let mut s = lock(&self.state);
        if s.stop || s.phase == Phase::Stopped { return Err(Error::state("session is stopping or stopped")); }
        let result = match op {
            "open" => {
                if s.windows.len() >= 32 { return Err(Error::limit("at most 32 windows")); }
                let document = Document::parse(string(&value, "html")?)?;
                let title = optional_text(&value, "title", "ui4me", 4096)?;
                let width = dimension(&value, "width", 640, 160)?;
                let height = dimension(&value, "height", 480, 120)?;
                let id = next_id()?;
                s.windows.insert(id, WindowModel { document, title, width, height, pixel_width: width, pixel_height: height, scale:1.0, closing:false, dirty:true, resize_revision:0 });
                s.had_window = true;
                json!({"window":id})
            }
            "timer" => {
                let token = number(&value, "token")?;
                let ms = number(&value, "milliseconds")?;
                if !(1..=86_400_000).contains(&ms) { return Err(Error::arg("timer interval must be 1..86400000 milliseconds")); }
                if s.timers.len() >= 128 && !s.timers.contains_key(&token) { return Err(Error::limit("at most 128 timers")); }
                let repeat = value.get("repeat").map(|v| v.as_bool().ok_or_else(|| Error::arg("repeat must be boolean"))).transpose()?.unwrap_or(false);
                let interval = Duration::from_millis(ms);
                s.timers.insert(token, Timer { due:Instant::now() + interval, interval, repeat });
                json!({"token":token})
            }
            "cancel_timer" => json!({"cancelled":s.timers.remove(&number(&value, "token")?).is_some()}),
            "set_text" | "get_value" | "close" | "set_title" | "resize" | "snapshot" => {
                let id = number(&value, "window")?;
                let w = s.windows.get_mut(&id).ok_or_else(|| Error::stale("unknown or closed window"))?;
                match op {
                    "set_text" => { w.document.set_text(string(&value, "element")?, string(&value, "text")?)?; w.dirty = true; json!({}) }
                    "get_value" => json!({"value":w.document.element(string(&value, "element")?)?.text}),
                    "close" => { w.closing = true; json!({}) }
                    "set_title" => { w.title = optional_text(&value, "title", "", 4096)?; w.dirty = true; json!({}) }
                    "resize" => { w.width = dimension(&value, "width", w.width, 160)?; w.height = dimension(&value, "height", w.height, 120)?; w.resize_revision += 1; w.dirty = true; if !self.native { w.pixel_width=w.width; w.pixel_height=w.height; } json!({}) }
                    "snapshot" => {
                        let path = string(&value, "path")?;
                        let pixels = w.document.render(w.pixel_width, w.pixel_height, w.scale)?;
                        let file = File::create(path).map_err(|e| Error::io(format!("snapshot: {e}")))?;
                        let mut encoder = png::Encoder::new(BufWriter::new(file), w.pixel_width, w.pixel_height);
                        encoder.set_color(png::ColorType::Rgb); encoder.set_depth(png::BitDepth::Eight);
                        let mut writer = encoder.write_header().map_err(|e| Error::io(e.to_string()))?;
                        let bytes: Vec<u8> = pixels.iter().flat_map(|p| [((p>>16)&255) as u8, ((p>>8)&255) as u8, (p&255) as u8]).collect();
                        writer.write_image_data(&bytes).map_err(|e| Error::io(e.to_string()))?;
                        json!({"path":path,"width":w.pixel_width,"height":w.pixel_height,"native_capture":false})
                    }
                    _ => unreachable!(),
                }
            }
            _ => return Err(Error::arg(format!("unknown operation: {op}"))),
        };
        drop(s);
        self.wake();
        Ok(result)
    }
}

pub fn destroy(id: u64) -> Result<()> {
    let session = get(id)?;
    session.assert_owner()?;
    {
        let mut s = lock(&session.state);
        if s.phase == Phase::Running { return Err(Error::state("stop and return from run before destroy")); }
        s.stats.cancelled += s.posts.len() as u64;
        s.posts.clear(); s.timers.clear(); s.windows.clear(); s.phase = Phase::Stopped; s.stop = true;
    }
    let mut active = lock(active());
    if active.as_ref().is_some_and(|s| s.id == id) { *active = None; }
    Ok(())
}

pub fn poison_active() {
    if let Some(session) = lock(active()).clone() {
        let mut s = lock(&session.state);
        s.failure = Some(Error::poison("native panic contained; destroy session and exit process"));
        s.stop = true; s.phase = Phase::Stopped;
        s.stats.cancelled += s.posts.len() as u64; s.posts.clear(); s.timers.clear(); s.windows.clear();
        drop(s);
        session.wake();
    }
}

fn string<'a>(value: &'a Value, key: &str) -> Result<&'a str> { value.get(key).and_then(Value::as_str).ok_or_else(|| Error::arg(format!("{key} must be a string"))) }
fn number(value: &Value, key: &str) -> Result<u64> { value.get(key).and_then(Value::as_u64).ok_or_else(|| Error::arg(format!("{key} must be an unsigned integer"))) }
fn optional_text(value: &Value, key: &str, default: &str, max: usize) -> Result<String> {
    let text = if value.get(key).is_none() { default } else { string(value,key)? };
    if text.len() > max || text.contains('\0') { return Err(Error::arg(format!("{key} is too long or contains NUL"))); }
    Ok(text.to_owned())
}
fn dimension(value: &Value, key: &str, default: u32, min: u32) -> Result<u32> {
    let v = if value.get(key).is_none() { default as u64 } else { number(value,key)? };
    if v < min as u64 || v > 4096 { return Err(Error::arg(format!("{key} must be {min}..4096 logical pixels"))); }
    Ok(v as u32)
}
