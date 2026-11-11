//! Session ownership. The process registry stores only thread-safe control data.
//! DOM, rendering, windows and timers live in OWNER on their creating thread.
#[cfg(any(feature = "native", test))]
use crate::document::Input;
use crate::document::{Document, MAX_PIXELS};
use crate::protocol::{self, Backend, Command, Config};
use crate::{Error, Result};
use serde_json::{json, Value};
use std::cell::RefCell;
use std::collections::{BTreeMap, VecDeque};
use std::ffi::{c_char, c_void, CString};
use std::fs::File;
use std::io::{BufWriter, Read};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::{Arc, Condvar, Mutex, MutexGuard, OnceLock};
use std::thread::{self, ThreadId};
use std::time::{Duration, Instant};

pub type Callback = extern "C" fn(u64, *const c_char, *mut c_void) -> i32;
static NEXT_ID: AtomicU64 = AtomicU64::new(1);
static ACTIVE: OnceLock<Mutex<Option<Arc<Session>>>> = OnceLock::new();
thread_local! { static OWNER: RefCell<Option<OwnerSession>> = const { RefCell::new(None) }; }
const MAX_POSTS: usize = 512;
const MAX_COMPLETIONS: usize = 128;

pub fn lock<T>(m: &Mutex<T>) -> MutexGuard<'_, T> {
    m.lock().unwrap_or_else(|e| e.into_inner())
}
fn active() -> &'static Mutex<Option<Arc<Session>>> {
    ACTIVE.get_or_init(|| Mutex::new(None))
}
fn next_id() -> Result<u64> {
    NEXT_ID
        .try_update(Ordering::Relaxed, Ordering::Relaxed, |v| v.checked_add(1))
        .map_err(|_| Error::limit("identifier space exhausted"))
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Phase {
    Ready,
    Running,
    Stopping,
    Stopped,
}
#[derive(Clone, Debug)]
pub struct WindowInfo {
    pub title: String,
    pub width: u32,
    pub height: u32,
    pub pixel_width: u32,
    pub pixel_height: u32,
    pub scale: f64,
    pub closing: bool,
    pub dirty: bool,
    pub resize_revision: u64,
    /// The application asked to hide the window (`window_action hide`).
    pub hidden: bool,
}
/// A native window operation queued on the owner and applied by the event loop.
#[derive(Clone, Debug, PartialEq)]
pub enum WindowOp {
    Show,
    Hide,
    Focus,
    Minimize,
    Maximize,
    Restore,
    Fullscreen(bool),
    Constraints {
        min: Option<(u32, u32)>,
        max: Option<(u32, u32)>,
        resizable: bool,
    },
    Icon(Option<(Vec<u8>, u32, u32)>),
}
/// Minimum size, maximum size and resizability (logical px).
type Constraints = (Option<(u32, u32)>, Option<(u32, u32)>, bool);
/// Window state as last observed from the platform (`None`: the platform does not report it).
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Observed {
    pub visible: Option<bool>,
    pub focused: Option<bool>,
    pub minimized: Option<bool>,
    pub maximized: Option<bool>,
    pub fullscreen: Option<bool>,
    pub monitor: Option<String>,
}
struct WindowState {
    info: WindowInfo,
    document: Document,
    last_error: Option<(i32, String)>,
    ops: VecDeque<WindowOp>,
    observed: Observed,
    constraints: Constraints,
}
struct Timer {
    due: Instant,
    interval: Duration,
    repeat: bool,
}
struct OwnerSession {
    id: u64,
    windows: BTreeMap<u64, WindowState>,
    timers: BTreeMap<u64, Timer>,
    had_window: bool,
}
#[derive(Default)]
pub struct Stats {
    pub posted: u64,
    pub executed: u64,
    pub cancelled: u64,
    pub callbacks: u64,
    pub loop_turns: u64,
    pub wait_requests: u64,
    pub completions_delivered: u64,
    pub completions_cancelled: u64,
}
pub struct Control {
    pub phase: Phase,
    pub stop: bool,
    wake_generation: u64,
    posts: VecDeque<u64>,
    // false = reserved; true = published and waiting for owner delivery.
    completions: BTreeMap<u64, bool>,
    ready_completions: VecDeque<u64>,
    pub failure: Option<Error>,
    pub stats: Stats,
}
pub struct Session {
    pub id: u64,
    pub owner: ThreadId,
    pub native: bool,
    pub app_id: String,
    // Retained in portable configuration even when only headless is compiled.
    #[cfg_attr(not(feature = "native"), allow(dead_code))]
    pub allow_any_thread: bool,
    callback: Option<Callback>,
    user: usize,
    pub control: Mutex<Control>,
    changed: Condvar,
    run_active: AtomicBool,
    callback_depth: AtomicUsize,
    #[cfg(feature = "native")]
    pub proxy: Mutex<Option<winit::event_loop::EventLoopProxy<()>>>,
    /// Platform of the native backend once running (`wayland`, `x11`, `windows`), else `headless`.
    pub platform: Mutex<&'static str>,
    /// Monitors as last enumerated by the native event loop.
    pub monitors: Mutex<Vec<Value>>,
}
struct RunLease<'a>(&'a Session);
impl Drop for RunLease<'_> {
    fn drop(&mut self) {
        self.0.run_active.store(false, Ordering::Release);
    }
}
struct CallbackLease<'a>(&'a Session);
impl Drop for CallbackLease<'_> {
    fn drop(&mut self) {
        self.0.callback_depth.fetch_sub(1, Ordering::AcqRel);
    }
}

pub fn get(id: u64) -> Result<Arc<Session>> {
    lock(active())
        .as_ref()
        .filter(|s| s.id == id)
        .cloned()
        .ok_or_else(|| Error::stale("unknown or destroyed session"))
}
pub fn create(value: Value, callback: Option<Callback>, user: *mut c_void) -> Result<u64> {
    if crate::POISONED.load(Ordering::Acquire) {
        return Err(Error::poison("runtime is poisoned; start a fresh process"));
    }
    let config = Config::parse(value)?;
    #[cfg(not(feature = "native"))]
    if config.backend == Backend::Native {
        return Err(Error::native(
            "this build does not include the native backend",
        ));
    }
    let mut registry = lock(active());
    if registry.is_some() {
        return Err(Error::state(
            "another session exists; destroy it before creating a new one",
        ));
    }
    let id = next_id()?;
    OWNER.with(|cell| {
        let mut slot = cell
            .try_borrow_mut()
            .map_err(|_| Error::state("owner state is currently borrowed"))?;
        if slot.is_some() {
            return Err(Error::state("owner state from an earlier session remains"));
        }
        *slot = Some(OwnerSession {
            id,
            windows: BTreeMap::new(),
            timers: BTreeMap::new(),
            had_window: false,
        });
        Ok(())
    })?;
    *registry = Some(Arc::new(Session {
        id,
        owner: thread::current().id(),
        native: config.backend == Backend::Native,
        app_id: config.app_id,
        allow_any_thread: config.allow_any_thread,
        callback,
        user: user as usize,
        control: Mutex::new(Control {
            phase: Phase::Ready,
            stop: false,
            wake_generation: 0,
            posts: VecDeque::new(),
            completions: BTreeMap::new(),
            ready_completions: VecDeque::new(),
            failure: None,
            stats: Stats::default(),
        }),
        changed: Condvar::new(),
        run_active: AtomicBool::new(false),
        callback_depth: AtomicUsize::new(0),
        #[cfg(feature = "native")]
        proxy: Mutex::new(None),
        platform: Mutex::new("headless"),
        monitors: Mutex::new(Vec::new()),
    }));
    Ok(id)
}

/// Why `op` cannot be honoured on `platform` (the compositor or OS forbids or ignores it).
pub fn unsupported(platform: &str, op: &WindowOp) -> Option<&'static str> {
    match (platform, op) {
        ("wayland", WindowOp::Focus) => {
            Some("Wayland compositors activate a window only with a user-provided activation token")
        }
        ("wayland", WindowOp::Hide) | ("wayland", WindowOp::Show) => {
            Some("Wayland has no client-side show/hide of a toplevel; close or minimize instead")
        }
        ("wayland", WindowOp::Icon(_)) => {
            Some("Wayland takes the icon from the desktop entry named by app_id")
        }
        _ => None,
    }
}

impl Session {
    pub fn assert_owner(&self) -> Result<()> {
        if self.owner == thread::current().id() {
            Ok(())
        } else {
            Err(Error::thread("operation requires the session owner thread"))
        }
    }
    fn with_owner<R>(&self, action: impl FnOnce(&mut OwnerSession) -> Result<R>) -> Result<R> {
        self.assert_owner()?;
        OWNER.with(|cell| {
            let mut slot = cell
                .try_borrow_mut()
                .map_err(|_| Error::state("document operation reentered an active engine pass"))?;
            let owner = slot
                .as_mut()
                .filter(|o| o.id == self.id)
                .ok_or_else(|| Error::stale("owner session was destroyed"))?;
            action(owner)
        })
    }
    #[cfg(test)]
    pub(crate) fn exercise_owner_borrow<R>(&self, action: impl FnOnce() -> R) -> Result<R> {
        self.with_owner(|_| Ok(action()))
    }
    fn with_window<R>(
        &self,
        id: u64,
        action: impl FnOnce(&mut WindowState) -> Result<R>,
    ) -> Result<R> {
        self.with_owner(|o| {
            action(
                o.windows
                    .get_mut(&id)
                    .ok_or_else(|| Error::stale("unknown or closed window"))?,
            )
        })
    }
    fn require_active(&self) -> Result<()> {
        let state = lock(&self.control);
        if state.stop || matches!(state.phase, Phase::Stopping | Phase::Stopped) {
            Err(Error::state("session is stopping or stopped"))
        } else {
            Ok(())
        }
    }
    pub fn wake(&self) {
        // Synchronize predicate changes with Condvar waiting; a decode completing
        // between polling and waiting must not lose its wakeup.
        {
            let mut control = lock(&self.control);
            control.wake_generation = control.wake_generation.wrapping_add(1);
        }
        self.changed.notify_all();
        #[cfg(feature = "native")]
        if let Some(proxy) = lock(&self.proxy).as_ref() {
            let _ = proxy.send_event(());
        }
    }
    pub fn stop(&self) -> Result<()> {
        let mut state = lock(&self.control);
        state.stop = true;
        if state.phase == Phase::Running {
            state.phase = Phase::Stopping;
        }
        drop(state);
        self.wake();
        Ok(())
    }
    pub fn post(&self, token: u64) -> Result<()> {
        let mut state = lock(&self.control);
        if state.stop || state.phase == Phase::Stopped {
            return Err(Error::state("session is stopping or stopped"));
        }
        if state.posts.len() >= MAX_POSTS {
            return Err(Error::limit("deferred queue is full (512)"));
        }
        state.posts.push_back(token);
        state.stats.posted += 1;
        drop(state);
        self.wake();
        Ok(())
    }
    /// Cross-thread publication uses capacity reserved on the owner before starting work.
    pub fn complete(&self, token: u64) -> Result<()> {
        let mut state = lock(&self.control);
        if state.stop || state.phase == Phase::Stopped {
            return Err(Error::state("session is stopping or stopped"));
        }
        let ready = state
            .completions
            .get_mut(&token)
            .ok_or_else(|| Error::stale("completion ticket is unknown or retired"))?;
        if *ready {
            return Err(Error::stale("completion ticket was already published"));
        }
        *ready = true;
        state.ready_completions.push_back(token);
        drop(state);
        self.wake();
        Ok(())
    }
    pub fn fail(&self, error: Error) {
        let mut state = lock(&self.control);
        if state.failure.is_none() {
            state.failure = Some(error);
        }
        state.stop = true;
        if state.phase == Phase::Running {
            state.phase = Phase::Stopping;
        }
        drop(state);
        self.wake();
    }
    /// No engine borrow or control lock is held while foreign code executes.
    pub fn emit(&self, event: Value) -> i32 {
        if self.assert_owner().is_err() {
            self.fail(Error::thread("callback attempted off owner thread"));
            return -1;
        }
        // An Arc may outlive registry retirement (for example in a producer).
        // Registry retirement is also the callback-root lifetime boundary.
        if get(self.id).is_err() {
            return -1;
        }
        let Some(callback) = self.callback else {
            return 0;
        };
        let Ok(text) = CString::new(event.to_string()) else {
            self.fail(Error::arg("event serialization contains NUL"));
            return -1;
        };
        self.callback_depth.fetch_add(1, Ordering::AcqRel);
        let _lease = CallbackLease(self);
        lock(&self.control).stats.callbacks += 1;
        let result = callback(self.id, text.as_ptr(), self.user as *mut c_void);
        if result < 0 {
            self.fail(Error::callback(
                "binding callback failed; inspect the binding exception",
            ));
        }
        result
    }
    fn emit_document_events(&self, window: u64, events: Vec<Value>) {
        for mut event in events {
            if self.should_stop() || self.window_info(window).is_none() {
                break;
            }
            if !self
                .with_window(window, |w| Ok(w.document.event_is_current(&event)))
                .unwrap_or(false)
            {
                continue;
            }
            if let Some(object) = event.as_object_mut() {
                object.remove("_target");
                object.remove("_element");
                object.insert("window".into(), json!(window));
            }
            self.emit(event);
        }
    }
    pub fn should_stop(&self) -> bool {
        lock(&self.control).stop
    }
    pub fn window_ids(&self) -> Vec<u64> {
        self.with_owner(|o| Ok(o.windows.keys().copied().collect()))
            .unwrap_or_default()
    }
    /// Native window operations queued since the last call (owner/event loop).
    pub fn take_window_ops(&self, id: u64) -> Vec<WindowOp> {
        self.with_window(id, |w| Ok(w.ops.drain(..).collect()))
            .unwrap_or_default()
    }
    /// Record platform-observed window state; emits `window_state` when it changed.
    pub fn observe_window(&self, id: u64, observed: Observed) {
        let changed = self
            .with_window(id, |w| {
                let changed = w.observed != observed;
                w.observed = observed.clone();
                Ok(changed)
            })
            .unwrap_or(false);
        if changed {
            let mut event = observed_json(&observed);
            event["type"] = json!("window_state");
            event["window"] = json!(id);
            self.emit(event);
        }
    }
    pub fn window_info(&self, id: u64) -> Option<WindowInfo> {
        self.with_window(id, |w| Ok(w.info.clone())).ok()
    }
    pub fn close_requested(&self, id: u64) -> bool {
        if self.window_info(id).is_none() {
            return false;
        }
        let veto = self.emit(json!({"type":"close_requested","window":id})) == 1;
        let exists = self
            .with_window(id, |w| {
                w.info.closing = false;
                Ok(())
            })
            .is_ok();
        exists && (!veto || self.should_stop())
    }
    /// Native surface/window must be dropped before this notification.
    pub fn closed(&self, id: u64) {
        let removed = self
            .with_owner(|o| Ok(o.windows.remove(&id)))
            .ok()
            .flatten();
        let existed = removed.is_some();
        drop(removed); // Retire document resources before callbacks.
        if existed {
            self.emit(json!({"type":"closed","window":id}));
        }
        if self
            .with_owner(|o| Ok(o.had_window && o.windows.is_empty()))
            .unwrap_or(false)
        {
            let _ = self.stop();
        }
    }
    #[cfg(feature = "native")]
    pub fn update_geometry(&self, id: u64, width: u32, height: u32, scale: f64) -> Result<()> {
        if !scale.is_finite() || scale <= 0.0 {
            return Err(Error::arg("scale must be finite and positive"));
        }
        self.with_window(id, |w| {
            w.info.pixel_width = width;
            w.info.pixel_height = height;
            w.info.scale = scale;
            w.info.dirty = true;
            w.document.set_viewport(width, height, scale)?;
            Ok(())
        })
    }
    #[cfg(any(feature = "native", test))]
    pub fn input(&self, id: u64, input: Input) -> Result<()> {
        self.require_active()?;
        let events = self.with_window(id, |w| {
            let events = w.document.handle_input(input)?;
            w.info.dirty |= w.document.needs_repaint();
            Ok(events)
        })?;
        self.emit_document_events(id, events);
        self.wake();
        Ok(())
    }
    pub fn render(&self, id: u64) -> Result<Vec<u32>> {
        self.with_window(id, |w| {
            let i = &w.info;
            if (i.pixel_width as usize).saturating_mul(i.pixel_height as usize) > MAX_PIXELS {
                return Err(Error::limit("window exceeds the 16,777,216 pixel budget"));
            }
            let pixels = w.document.render(i.pixel_width, i.pixel_height, i.scale)?;
            w.info.dirty = false;
            w.last_error = None;
            Ok(pixels)
        })
    }
    pub fn report_document_error(&self, id: u64, error: Error) {
        let key = (error.code, error.message.clone());
        let fresh = self
            .with_window(id, |w| {
                // Do not continuously redraw a failing revision. A later edit/resource/resize retries.
                w.info.dirty = false;
                if w.last_error.as_ref() == Some(&key) {
                    return Ok(false);
                }
                w.last_error = Some(key);
                Ok(true)
            })
            .unwrap_or(false);
        if fresh {
            self.emit(
                json!({"type":"error","window":id,"code":error.code,"message":error.message}),
            );
        }
    }
    #[cfg(feature = "native")]
    pub fn ime_request(&self, id: u64) -> Option<crate::document::ImeState> {
        self.with_window(id, |w| Ok(w.document.ime_request().cloned()))
            .ok()
            .flatten()
    }
    #[cfg(feature = "native")]
    pub fn cursor(&self, id: u64) -> String {
        self.with_window(id, |w| Ok(w.document.cursor().to_owned()))
            .unwrap_or_else(|_| "default".into())
    }
    #[cfg(feature = "native")]
    pub fn install_clipboard(
        &self,
        id: u64,
        clipboard: Box<dyn crate::document::Clipboard>,
    ) -> Result<()> {
        self.with_window(id, |w| {
            w.document.set_clipboard(clipboard);
            Ok(())
        })
    }
    pub fn process_work(&self) {
        lock(&self.control).stats.loop_turns += 1;
        // Reserved completions make progress even when the ordinary post queue is saturated.
        for _ in 0..16 {
            let token = {
                let mut state = lock(&self.control);
                if state.stop {
                    None
                } else {
                    let token = state.ready_completions.pop_front();
                    if let Some(token) = token {
                        state.completions.remove(&token);
                        state.stats.completions_delivered += 1;
                    }
                    token
                }
            };
            let Some(token) = token else { break };
            self.emit(json!({"type":"completion","token":token}));
        }
        for _ in 0..64 {
            let token = {
                let mut state = lock(&self.control);
                if state.stop {
                    None
                } else {
                    let token = state.posts.pop_front();
                    if token.is_some() {
                        state.stats.executed += 1;
                    }
                    token
                }
            };
            let Some(token) = token else { break };
            self.emit(json!({"type":"post","token":token}));
        }
        let now = Instant::now();
        let due = self
            .with_owner(|o| {
                Ok(o.timers
                    .iter()
                    .filter(|(_, t)| t.due <= now)
                    .map(|(id, _)| *id)
                    .collect::<Vec<_>>())
            })
            .unwrap_or_default();
        for token in due {
            if self.should_stop() {
                break;
            }
            let fire = self
                .with_owner(|o| {
                    let Some(timer) = o.timers.get_mut(&token) else {
                        return Ok(false);
                    };
                    if timer.due > now {
                        return Ok(false);
                    }
                    if timer.repeat {
                        timer.due = now + timer.interval;
                    } else {
                        o.timers.remove(&token);
                    }
                    Ok(true)
                })
                .unwrap_or(false);
            if fire {
                self.emit(json!({"type":"timer","token":token}));
            }
        }
        if !self.should_stop() {
            for id in self.window_ids() {
                let result = self.with_window(id, |w| {
                    if w.document.poll_resources()? {
                        w.info.dirty = true;
                    }
                    Ok(w.document.drain_events())
                });
                match result {
                    Ok(events) => self.emit_document_events(id, events),
                    Err(error) => self.report_document_error(id, error),
                }
                if self.should_stop() {
                    break;
                }
            }
        }
    }
    pub fn deadline(&self) -> Option<Instant> {
        self.with_owner(|o| {
            let mut deadline = o.timers.values().map(|t| t.due).min();
            if let Some(delay) = o
                .windows
                .values()
                .filter_map(|w| w.document.next_wake_in())
                .min()
            {
                let wake = Instant::now() + delay;
                deadline = Some(deadline.map_or(wake, |d| d.min(wake)));
            }
            Ok(deadline)
        })
        .ok()
        .flatten()
    }
    #[cfg(feature = "native")]
    pub fn has_work(&self) -> bool {
        {
            let state = lock(&self.control);
            if state.stop || !state.posts.is_empty() || !state.ready_completions.is_empty() {
                return true;
            }
        }
        self.with_owner(|o| Ok(o.windows.values().any(|w| w.info.closing)))
            .unwrap_or(false)
    }
    #[cfg(feature = "native")]
    pub fn note_wait(&self) {
        lock(&self.control).stats.wait_requests += 1;
    }
    pub fn finish(&self) -> Result<()> {
        self.assert_owner()?;
        {
            let mut state = lock(&self.control);
            state.stop = true;
            state.phase = Phase::Stopping;
            let n = state.posts.len() as u64;
            state.stats.cancelled += n;
            state.posts.clear();
            let n = state.completions.len() as u64;
            state.stats.completions_cancelled += n;
            state.completions.clear();
            state.ready_completions.clear();
        }
        self.with_owner(|o| {
            o.timers.clear();
            Ok(())
        })?;
        for id in self.window_ids() {
            self.closed(id);
        }
        lock(&self.control).phase = Phase::Stopped;
        self.emit(json!({"type":"stopped"}));
        #[cfg(feature = "native")]
        {
            *lock(&self.proxy) = None;
        }
        if let Some(error) = lock(&self.control).failure.clone() {
            Err(error)
        } else {
            Ok(())
        }
    }
    pub fn run(self: &Arc<Self>) -> Result<()> {
        self.assert_owner()?;
        {
            let mut state = lock(&self.control);
            if state.phase != Phase::Ready {
                return Err(Error::state(
                    "a session can run only once; create a fresh session",
                ));
            }
            if self.run_active.swap(true, Ordering::AcqRel) {
                return Err(Error::state("nested run is not supported"));
            }
            state.phase = Phase::Running;
        }
        let _run_lease = RunLease(self);
        if !self.should_stop() {
            if self.native {
                #[cfg(feature = "native")]
                if let Err(error) = crate::native::run(self.clone()) {
                    self.fail(error);
                }
                #[cfg(not(feature = "native"))]
                self.fail(Error::native("native backend is not compiled"));
            } else {
                self.emit(json!({"type":"started","backend":"headless","app_id":self.app_id}));
                while !self.should_stop() {
                    let observed_wake = lock(&self.control).wake_generation;
                    self.process_work();
                    for id in self.window_ids() {
                        if self.should_stop() {
                            break;
                        }
                        if self.window_info(id).is_some_and(|w| w.closing)
                            && self.close_requested(id)
                        {
                            self.closed(id);
                        }
                    }
                    let deadline = self.deadline();
                    let mut state = lock(&self.control);
                    if state.stop
                        || !state.posts.is_empty()
                        || !state.ready_completions.is_empty()
                        || state.wake_generation != observed_wake
                    {
                        continue;
                    }
                    state.stats.wait_requests += 1;
                    if let Some(deadline) = deadline {
                        let timeout = deadline.saturating_duration_since(Instant::now());
                        let _guard = self
                            .changed
                            .wait_timeout(state, timeout)
                            .unwrap_or_else(|e| e.into_inner());
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
        let command = Command::parse(value)?;
        if matches!(command, Command::Stats) {
            return self.stats();
        }
        self.require_active()?;
        let result = match command {
            Command::Open {
                html,
                title,
                width,
                height,
                base_path,
            } => self.open_document(html, base_path, title, width, height)?,
            Command::OpenFile {
                path,
                title,
                width,
                height,
            } => {
                protocol::validate_size(width, height)?;
                protocol::validate_title(&title)?;
                let path = std::fs::canonicalize(path)
                    .map_err(|e| Error::io(format!("open_file: {e}")))?;
                let file = File::open(&path).map_err(|e| Error::io(format!("open_file: {e}")))?;
                let mut html = String::new();
                file.take(1024 * 1024 + 1)
                    .read_to_string(&mut html)
                    .map_err(|e| Error::io(format!("open_file UTF-8: {e}")))?;
                if html.len() > 1024 * 1024 {
                    return Err(Error::limit("HTML exceeds 1 MiB"));
                }
                self.open_document(
                    html,
                    path.parent().map(Path::to_owned),
                    title,
                    width,
                    height,
                )?
            }
            Command::SetText {
                window,
                element,
                text,
            } => self.mutate(window, |d| d.set_text(&element, &text))?,
            Command::GetValue { window, element } => self.with_window(window, |w| {
                Ok(json!({"value":w.document.get_value(&element)?}))
            })?,
            Command::SetValue {
                window,
                element,
                value,
            } => self.mutate(window, |d| d.set_value(&element, &value))?,
            Command::GetChecked { window, element } => self.with_window(window, |w| {
                Ok(json!({"checked":w.document.get_checked(&element)?}))
            })?,
            Command::SetChecked {
                window,
                element,
                checked,
            } => self.mutate(window, |d| d.set_checked(&element, checked))?,
            Command::SetAttribute {
                window,
                element,
                name,
                value,
            } => self.mutate(window, |d| d.set_attribute(&element, &name, Some(&value)))?,
            Command::RemoveAttribute {
                window,
                element,
                name,
            } => self.mutate(window, |d| d.set_attribute(&element, &name, None))?,
            Command::AddClass {
                window,
                element,
                name,
            } => self.mutate(window, |d| d.add_class(&element, &name))?,
            Command::RemoveClass {
                window,
                element,
                name,
            } => self.mutate(window, |d| d.remove_class(&element, &name))?,
            Command::Focus { window, element } => self.mutate(window, |d| d.focus(&element))?,
            Command::ReplaceChildrenHtml {
                window,
                element,
                html,
            } => self.mutate(window, |d| d.replace_children_html(&element, &html))?,
            Command::InsertHtml {
                window,
                element,
                position,
                html,
            } => self.mutate(window, |d| d.insert_html(&element, &position, &html))?,
            Command::RemoveElement { window, element } => {
                self.mutate(window, |d| d.remove_element(&element))?
            }
            Command::MoveElement {
                window,
                element,
                target,
                position,
            } => self.mutate(window, |d| d.move_element(&element, &target, &position))?,
            Command::GetText { window, element } => self.with_window(window, |w| {
                Ok(json!({"text": w.document.get_text(&element)?}))
            })?,
            Command::GetAttribute {
                window,
                element,
                name,
            } => self.with_window(window, |w| {
                Ok(json!({"value": w.document.get_attribute(&element, &name)?}))
            })?,
            Command::GetAttributes { window, element } => self.with_window(window, |w| {
                let attrs: serde_json::Map<String, Value> = w
                    .document
                    .get_attributes(&element)?
                    .into_iter()
                    .map(|(k, v)| (k, Value::String(v)))
                    .collect();
                Ok(json!({"attributes": attrs}))
            })?,
            Command::HasElement { window, element } => self.with_window(window, |w| {
                Ok(json!({"exists": w.document.has_element(&element)}))
            })?,
            Command::Query {
                window,
                selector,
                limit,
            } => self.with_window(window, |w| {
                let (ids, count) = w.document.query_ids(&selector, limit.min(16_384))?;
                Ok(json!({"elements": ids, "count": count}))
            })?,
            Command::Batch { window, ops } => {
                use crate::protocol::BatchOp as B;
                use ui4me_renderer::DomOp as D;
                let ops: Vec<D> = ops
                    .into_iter()
                    .map(|op| {
                        Ok(match op {
                        B::AppendText { element, text } => D::AppendText { element, text },
                        B::TrimChildren {
                            element,
                            keep,
                            from,
                        } => D::TrimChildren {
                            element,
                            keep,
                            from_start: protocol::trim_from_start(&from)?,
                        },
                        B::SetText { element, text } => D::SetText { element, text },
                        B::SetAttribute {
                            element,
                            name,
                            value,
                        } => D::SetAttribute {
                            element,
                            name,
                            value: Some(value),
                        },
                        B::RemoveAttribute { element, name } => D::SetAttribute {
                            element,
                            name,
                            value: None,
                        },
                        B::AddClass { element, name } => D::AddClass { element, name },
                        B::RemoveClass { element, name } => D::RemoveClass { element, name },
                        B::InsertHtml {
                            element,
                            position,
                            html,
                        } => D::InsertHtml {
                            element,
                            position,
                            html,
                        },
                        B::ReplaceChildrenHtml { element, html } => {
                            D::ReplaceChildrenHtml { element, html }
                        }
                        B::RemoveElement { element } => D::RemoveElement { element },
                        B::MoveElement {
                            element,
                            target,
                            position,
                        } => D::MoveElement {
                            element,
                            target,
                            position,
                        },
                        })
                    })
                    .collect::<Result<_>>()?;
                self.mutate(window, |d| d.apply_batch(&ops))?
            }
            Command::SetDefaultAction {
                window,
                element,
                event,
                key,
                shift,
                ctrl,
                alt,
                meta,
                prevent,
            } => self.mutate(window, |d| {
                d.set_default_action(
                    ui4me_renderer::DefaultActionRule {
                        element,
                        event,
                        key,
                        shift,
                        ctrl,
                        alt,
                        meta,
                    },
                    prevent,
                )
            })?,
            Command::GetScroll { window, element } => {
                self.query(window, |d| d.scroll_state(element.as_deref()).map(scroll_json))?
            }
            Command::ScrollTo {
                window,
                element,
                x,
                y,
            } => self.query(window, |d| {
                d.scroll_to(element.as_deref(), x, y).map(scroll_json)
            })?,
            Command::ScrollBy {
                window,
                element,
                dx,
                dy,
            } => self.query(window, |d| {
                d.scroll_by(element.as_deref(), dx, dy).map(scroll_json)
            })?,
            Command::ScrollIntoView {
                window,
                element,
                block,
                inline,
            } => self.query(window, |d| {
                d.scroll_into_view(&element, &block, &inline)
                    .map(|()| json!({}))
            })?,
            Command::GetRect { window, element } => self.query(window, |d| {
                d.element_rect(&element).map(|r| {
                    json!({"rect": r.map(|r| json!({"x":r.x,"y":r.y,"width":r.width,"height":r.height}))})
                })
            })?,
            Command::SetScrollFollow {
                window,
                element,
                follow,
            } => self.mutate(window, |d| d.set_scroll_follow(element.as_deref(), follow))?,
            Command::GetSelection { window } => self.query(window, |d| {
                d.selection_text().map(|text| json!({"text": text}))
            })?,
            Command::ClearSelection { window } => self.query(window, |d| {
                d.clear_selection();
                Ok(json!({}))
            })?,
            Command::SelectText { window, element } => self.query(window, |d| {
                d.select_text(element.as_deref()).map(|()| json!({}))
            })?,
            Command::CopySelection { window } => self.query(window, |d| {
                d.copy_selection().map(|text| json!({"text": text}))
            })?,
            Command::GetClipboardText { window } => self.query(window, |d| {
                d.clipboard_text().map(|text| json!({"text": text}))
            })?,
            Command::SetClipboardText { window, text } => self.query(window, |d| {
                d.set_clipboard_text(&text).map(|()| json!({}))
            })?,
            Command::AppendText {
                window,
                element,
                text,
            } => self.mutate(window, |d| d.append_text(&element, &text))?,
            Command::TrimChildren {
                window,
                element,
                keep,
                from,
            } => {
                let from_start = protocol::trim_from_start(&from)?;
                self.mutate(window, |d| d.trim_children(&element, keep, from_start))?
            }
            Command::ShowDialog {
                window,
                element,
                modal,
            } => self.query(window, |d| {
                d.show_dialog(&element, modal).map(|()| json!({}))
            })?,
            Command::CloseDialog {
                window,
                element,
                return_value,
            } => self.query(window, |d| {
                d.close_dialog(&element, return_value.as_deref())
                    .map(|()| json!({}))
            })?,
            Command::GetDialog { window, element } => self.with_window(window, |w| {
                let (open, modal, return_value) = w.document.dialog_state(&element)?;
                Ok(json!({"open":open,"modal":modal,"return_value":return_value}))
            })?,
            Command::GetOptions { window, element } => self.with_window(window, |w| {
                let options: Vec<Value> = w
                    .document
                    .select_options(&element)?
                    .into_iter()
                    .map(|(value, label, selected, disabled)| {
                        json!({"value":value,"label":label,"selected":selected,"disabled":disabled})
                    })
                    .collect();
                Ok(json!({"options": options}))
            })?,
            Command::SetSelectedValues {
                window,
                element,
                values,
            } => self.mutate(window, |d| d.set_selected_values(&element, &values))?,
            Command::WindowAction { window, action } => {
                let op = match action.as_str() {
                    "show" => WindowOp::Show,
                    "hide" => WindowOp::Hide,
                    "focus" => WindowOp::Focus,
                    "minimize" => WindowOp::Minimize,
                    "maximize" => WindowOp::Maximize,
                    "restore" => WindowOp::Restore,
                    "fullscreen" => WindowOp::Fullscreen(true),
                    "exit_fullscreen" => WindowOp::Fullscreen(false),
                    _ => return Err(Error::arg(
                        "action must be show, hide, focus, minimize, maximize, restore, fullscreen or exit_fullscreen",
                    )),
                };
                self.queue_window_op(window, op)?
            }
            Command::SetWindowConstraints {
                window,
                min_width,
                min_height,
                max_width,
                max_height,
                resizable,
            } => {
                let pair = |w: Option<u32>, h: Option<u32>| -> Result<Option<(u32, u32)>> {
                    match (w, h) {
                        (None, None) => Ok(None),
                        (Some(w), Some(h)) => {
                            protocol::validate_size(w, h)?;
                            Ok(Some((w, h)))
                        }
                        _ => Err(Error::arg("give both width and height of a size constraint")),
                    }
                };
                let min = pair(min_width, min_height)?;
                let max = pair(max_width, max_height)?;
                if let (Some(a), Some(b)) = (min, max) {
                    if a.0 > b.0 || a.1 > b.1 {
                        return Err(Error::arg("minimum size exceeds maximum size"));
                    }
                }
                self.queue_window_op(
                    window,
                    WindowOp::Constraints {
                        min,
                        max,
                        resizable,
                    },
                )?
            }
            Command::SetWindowIcon { window, path } => {
                let icon = match path {
                    Some(path) => Some(read_icon(&path)?),
                    None => None,
                };
                self.queue_window_op(window, WindowOp::Icon(icon))?
            }
            Command::GetWindowState { window } => self.with_window(window, |w| {
                let mut v = observed_json(&w.observed);
                let i = &w.info;
                v["width"] = json!(i.pixel_width as f64 / i.scale);
                v["height"] = json!(i.pixel_height as f64 / i.scale);
                v["pixel_width"] = json!(i.pixel_width);
                v["pixel_height"] = json!(i.pixel_height);
                v["scale"] = json!(i.scale);
                v["min_size"] = json!(w.constraints.0);
                v["max_size"] = json!(w.constraints.1);
                v["resizable"] = json!(w.constraints.2);
                v["platform"] = json!(*lock(&self.platform));
                Ok(v)
            })?,
            Command::ListMonitors => json!({"monitors": lock(&self.monitors).clone(), "platform": *lock(&self.platform)}),
            Command::Diagnostics { window } => self.with_window(window, |w| {
                let mut diagnostics = w.document.diagnostics();
                if let Some((code, message)) = &w.last_error {
                    diagnostics.push(json!({"code":code,"message":message,"stage":"render"}));
                }
                Ok(json!({"diagnostics":diagnostics}))
            })?,
            Command::Close { window } => self.with_window(window, |w| {
                w.info.closing = true;
                Ok(json!({}))
            })?,
            Command::SetTitle { window, title } => {
                protocol::validate_title(&title)?;
                self.with_window(window, |w| {
                    w.info.title = title;
                    Ok(json!({}))
                })?
            }
            Command::Resize {
                window,
                width,
                height,
            } => {
                protocol::validate_size(width, height)?;
                self.with_window(window, |w| {
                    let revision = w
                        .info
                        .resize_revision
                        .checked_add(1)
                        .ok_or_else(|| Error::limit("resize revision exhausted"))?;
                    // Size constraints apply to programmatic resizes too (on Wayland the
                    // compositor treats them only as hints for the user's own resizing).
                    let (min, max, _) = w.constraints;
                    let (lo, hi) = (min.unwrap_or((160, 120)), max.unwrap_or((4096, 4096)));
                    let width = width.clamp(lo.0, hi.0);
                    let height = height.clamp(lo.1, hi.1);
                    w.info.width = width;
                    w.info.height = height;
                    w.info.resize_revision = revision;
                    w.info.dirty = true;
                    if !self.native {
                        w.info.pixel_width = width;
                        w.info.pixel_height = height;
                        w.document.set_viewport(width, height, w.info.scale)?;
                    }
                    Ok(json!({"width": width, "height": height}))
                })?
            }
            Command::Snapshot { window, path } => self.snapshot(window, &path)?,
            Command::Timer {
                token,
                milliseconds,
                repeat,
            } => {
                if !(1..=86_400_000).contains(&milliseconds) {
                    return Err(Error::arg(
                        "timer interval must be 1..86400000 milliseconds",
                    ));
                }
                self.with_owner(|o| {
                    if o.timers.len() >= 128 && !o.timers.contains_key(&token) {
                        return Err(Error::limit("at most 128 timers"));
                    }
                    let interval = Duration::from_millis(milliseconds);
                    o.timers.insert(
                        token,
                        Timer {
                            due: Instant::now() + interval,
                            interval,
                            repeat,
                        },
                    );
                    Ok(json!({"token":token}))
                })?
            }
            Command::CancelTimer { token } => {
                self.with_owner(|o| Ok(json!({"cancelled":o.timers.remove(&token).is_some()})))?
            }
            Command::ReserveCompletion { token } => {
                let mut state = lock(&self.control);
                if state.stop {
                    return Err(Error::state("session is stopping"));
                }
                if state.completions.contains_key(&token) {
                    return Err(Error::arg("completion token is already reserved"));
                }
                if state.completions.len() >= MAX_COMPLETIONS {
                    return Err(Error::limit("completion capacity is full (128)"));
                }
                state.completions.insert(token, false);
                json!({"token":token})
            }
            Command::CancelCompletion { token } => {
                let mut state = lock(&self.control);
                let cancelled = state.completions.remove(&token).is_some();
                state.ready_completions.retain(|t| *t != token);
                if cancelled {
                    state.stats.completions_cancelled += 1;
                }
                json!({"cancelled":cancelled})
            }
            Command::Stats => unreachable!(),
        };
        self.wake();
        Ok(result)
    }
    fn open_document(
        &self,
        html: String,
        base: Option<PathBuf>,
        title: String,
        width: u32,
        height: u32,
    ) -> Result<Value> {
        protocol::validate_title(&title)?;
        protocol::validate_size(width, height)?;
        self.with_owner(|o| {
            if o.windows.len() >= 32 {
                Err(Error::limit("at most 32 windows"))
            } else {
                Ok(())
            }
        })?;
        if html.len() > 1024 * 1024 {
            return Err(Error::limit("HTML exceeds 1 MiB"));
        }
        let base = base
            .map(|p| {
                let p =
                    std::fs::canonicalize(p).map_err(|e| Error::io(format!("asset base: {e}")))?;
                if !p.is_dir() {
                    return Err(Error::arg("base_path must name a directory"));
                }
                Ok(p)
            })
            .transpose()?;
        let mut document = Document::parse_with_source(&html, base.as_deref(), width, height)?;
        let weak = Arc::downgrade(&get(self.id)?);
        document.set_waker(Arc::new(move || {
            if let Some(session) = weak.upgrade() {
                session.wake();
            }
        }));
        // Stop may have been requested while a large document was parsing.
        self.require_active()?;
        let id = next_id()?;
        self.with_owner(|o| {
            o.windows.insert(
                id,
                WindowState {
                    document,
                    last_error: None,
                    ops: VecDeque::new(),
                    observed: Observed {
                        visible: Some(!self.native),
                        focused: Some(!self.native),
                        minimized: Some(false),
                        maximized: Some(false),
                        fullscreen: Some(false),
                        monitor: None,
                    },
                    constraints: (None, None, true),
                    info: WindowInfo {
                        title,
                        width,
                        height,
                        pixel_width: width,
                        pixel_height: height,
                        scale: 1.0,
                        closing: false,
                        dirty: true,
                        resize_revision: 0,
                        hidden: false,
                    },
                },
            );
            o.had_window = true;
            Ok(())
        })?;
        Ok(json!({"window":id}))
    }
    /// A document operation that returns a value and may queue events (scroll queries flush
    /// layout; scroll writes dispatch `scroll`).
    fn query(
        &self,
        id: u64,
        action: impl FnOnce(&mut Document) -> std::result::Result<Value, ui4me_renderer::Error>,
    ) -> Result<Value> {
        let (value, events) = self.with_window(id, |w| {
            let value = action(&mut w.document)?;
            w.info.dirty |= w.document.needs_repaint();
            Ok((value, w.document.drain_events()))
        })?;
        self.emit_document_events(id, events);
        Ok(value)
    }
    fn queue_window_op(&self, id: u64, op: WindowOp) -> Result<Value> {
        let platform = *lock(&self.platform);
        if let Some(reason) = unsupported(platform, &op) {
            // Still validated against the window, so a stale ID is an error, not "unsupported".
            self.with_window(id, |_| Ok(()))?;
            return Ok(json!({"applied": false, "unsupported": reason, "platform": platform}));
        }
        let native = self.native;
        self.with_window(id, |w| {
            if w.ops.len() >= 32 {
                return Err(Error::limit("too many pending window operations"));
            }
            if let WindowOp::Constraints {
                min,
                max,
                resizable,
                ..
            } = &op
            {
                w.constraints = (*min, *max, *resizable);
            }
            match &op {
                WindowOp::Hide => w.info.hidden = true,
                WindowOp::Show => w.info.hidden = false,
                _ => {}
            }
            if native {
                w.ops.push_back(op);
                w.info.dirty = true;
            } else {
                // Headless: a deterministic model of the requested state.
                let o = &mut w.observed;
                match op {
                    WindowOp::Show => o.visible = Some(true),
                    WindowOp::Hide => o.visible = Some(false),
                    WindowOp::Focus => o.focused = Some(true),
                    WindowOp::Minimize => o.minimized = Some(true),
                    WindowOp::Maximize => o.maximized = Some(true),
                    WindowOp::Restore => {
                        o.minimized = Some(false);
                        o.maximized = Some(false);
                    }
                    WindowOp::Fullscreen(f) => o.fullscreen = Some(f),
                    WindowOp::Constraints { .. } | WindowOp::Icon(_) => {}
                }
            }
            Ok(())
        })?;
        self.wake();
        Ok(json!({"applied": true, "platform": platform}))
    }
    fn mutate(
        &self,
        id: u64,
        action: impl FnOnce(&mut Document) -> std::result::Result<(), ui4me_renderer::Error>,
    ) -> Result<Value> {
        let events = self.with_window(id, |w| {
            action(&mut w.document)?;
            w.info.dirty = true;
            Ok(w.document.drain_events())
        })?;
        self.emit_document_events(id, events);
        Ok(json!({}))
    }
    fn snapshot(&self, id: u64, path: &Path) -> Result<Value> {
        let info = self
            .window_info(id)
            .ok_or_else(|| Error::stale("unknown or closed window"))?;
        let pixels = self.render(id)?;
        // All document borrows and control locks are released before filesystem I/O.
        let file = File::create(path).map_err(|e| Error::io(format!("snapshot: {e}")))?;
        let mut encoder =
            png::Encoder::new(BufWriter::new(file), info.pixel_width, info.pixel_height);
        encoder.set_color(png::ColorType::Rgb);
        encoder.set_depth(png::BitDepth::Eight);
        let mut writer = encoder
            .write_header()
            .map_err(|e| Error::io(e.to_string()))?;
        let bytes: Vec<u8> = pixels
            .iter()
            .flat_map(|p| {
                [
                    ((p >> 16) & 255) as u8,
                    ((p >> 8) & 255) as u8,
                    (p & 255) as u8,
                ]
            })
            .collect();
        writer
            .write_image_data(&bytes)
            .map_err(|e| Error::io(e.to_string()))?;
        writer.finish().map_err(|e| Error::io(e.to_string()))?;
        Ok(
            json!({"path":path,"width":info.pixel_width,"height":info.pixel_height,"native_capture":false}),
        )
    }
    fn stats(&self) -> Result<Value> {
        let (windows, timers) = self.with_owner(|o| Ok((o.windows.len(), o.timers.len())))?;
        let s = lock(&self.control);
        Ok(
            json!({"phase":format!("{:?}",s.phase).to_ascii_lowercase(),"windows":windows,"timers":timers,"pending_posts":s.posts.len(),"reserved_completions":s.completions.len(),"pending_completions":s.ready_completions.len(),"posted":s.stats.posted,"executed":s.stats.executed,"cancelled":s.stats.cancelled,"callbacks":s.stats.callbacks,"loop_turns":s.stats.loop_turns,"wait_requests":s.stats.wait_requests,"completions_delivered":s.stats.completions_delivered,"completions_cancelled":s.stats.completions_cancelled,"run_active":self.run_active.load(Ordering::Acquire),"callback_depth":self.callback_depth.load(Ordering::Acquire)}),
        )
    }
}

pub fn destroy(id: u64) -> Result<()> {
    let session = get(id)?;
    session.assert_owner()?;
    if session.run_active.load(Ordering::Acquire)
        || session.callback_depth.load(Ordering::Acquire) != 0
    {
        return Err(Error::state(
            "stop and return from run and callbacks before destroy",
        ));
    }
    {
        let mut state = lock(&session.control);
        state.stop = true;
        state.phase = Phase::Stopped;
        let count = state.posts.len() as u64;
        state.stats.cancelled += count;
        state.posts.clear();
        let count = state.completions.len() as u64;
        state.stats.completions_cancelled += count;
        state.completions.clear();
        state.ready_completions.clear();
    }
    let retired = OWNER.with(|cell| {
        let mut slot = cell
            .try_borrow_mut()
            .map_err(|_| Error::state("owner state is currently borrowed"))?;
        if slot.as_ref().is_some_and(|o| o.id == id) {
            Ok(slot.take())
        } else {
            Err(Error::stale("owner session was destroyed"))
        }
    })?;
    drop(retired);
    let mut registry = lock(active());
    if registry.as_ref().is_some_and(|s| s.id == id) {
        *registry = None;
    }
    Ok(())
}

pub fn poison_active() {
    if let Some(session) = lock(active()).clone() {
        // Poisoning never grants permission to destroy while run/callback leases exist.
        session.fail(Error::poison(
            "native panic contained; destroy after run returns and restart process",
        ));
        if !session.run_active.load(Ordering::Acquire) {
            lock(&session.control).phase = Phase::Stopped;
        }
    }
}
fn scroll_json(s: ui4me_renderer::ScrollState) -> Value {
    json!({"x":s.x,"y":s.y,"min_x":s.min_x,"min_y":s.min_y,"max_x":s.max_x,"max_y":s.max_y,
        "width":s.width,"height":s.height,"scrollable":s.scrollable})
}
fn observed_json(o: &Observed) -> Value {
    json!({"visible":o.visible,"focused":o.focused,"minimized":o.minimized,
        "maximized":o.maximized,"fullscreen":o.fullscreen,"monitor":o.monitor})
}
/// Read a PNG window icon (at most 1 MiB and 256×256) as RGBA8.
fn read_icon(path: &Path) -> Result<(Vec<u8>, u32, u32)> {
    let meta = std::fs::metadata(path).map_err(|e| Error::io(format!("icon: {e}")))?;
    if meta.len() > 1024 * 1024 {
        return Err(Error::limit("icon file exceeds 1 MiB"));
    }
    let file = std::fs::File::open(path).map_err(|e| Error::io(format!("icon: {e}")))?;
    let mut decoder = png::Decoder::new(std::io::BufReader::new(file));
    decoder.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut reader = decoder
        .read_info()
        .map_err(|e| Error::arg(format!("icon is not a readable PNG: {e}")))?;
    let (w, h) = (reader.info().width, reader.info().height);
    if w == 0 || h == 0 || w > 256 || h > 256 {
        return Err(Error::arg("icon must be 1..256 pixels on each side"));
    }
    let mut buf = vec![
        0;
        reader
            .output_buffer_size()
            .ok_or_else(|| Error::limit("icon too large"))?
    ];
    let frame = reader
        .next_frame(&mut buf)
        .map_err(|e| Error::arg(format!("icon decode: {e}")))?;
    let data = &buf[..frame.buffer_size()];
    let rgba: Vec<u8> = match frame.color_type {
        png::ColorType::Rgba => data.to_vec(),
        png::ColorType::Rgb => data
            .chunks(3)
            .flat_map(|p| [p[0], p[1], p[2], 255])
            .collect(),
        png::ColorType::GrayscaleAlpha => data
            .chunks(2)
            .flat_map(|p| [p[0], p[0], p[0], p[1]])
            .collect(),
        png::ColorType::Grayscale => data.iter().flat_map(|&g| [g, g, g, 255]).collect(),
        png::ColorType::Indexed => return Err(Error::arg("indexed icon was not expanded")),
    };
    Ok((rgba, w, h))
}
