//! Retained winit 0.30 host. Native objects never leave their owning thread.
//! This layer translates OS input and presents pixels; document semantics live in the renderer.
use crate::document::{Clipboard, ImeState, Input, MAX_PIXELS};
use crate::runtime::{lock, FileDialogRequest, Observed, Session, WindowInfo, WindowOp};
use crate::{Error, Result};
use serde_json::json;
use softbuffer::{Context, Surface};
use std::cell::RefCell;
use std::collections::BTreeMap;
use std::num::NonZeroU32;
use std::rc::Rc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, OnceLock};
use std::thread::{self, ThreadId};
use winit::application::ApplicationHandler;
use winit::dpi::{LogicalPosition, LogicalSize, PhysicalPosition, PhysicalSize};
use winit::event::{ElementState, Ime, MouseButton, MouseScrollDelta, WindowEvent};
use winit::event_loop::{ActiveEventLoop, ControlFlow, EventLoop};
use winit::keyboard::{Key, ModifiersState, NamedKey, PhysicalKey};
use winit::platform::run_on_demand::EventLoopExtRunOnDemand;
use winit::window::{CursorIcon, ImePurpose, Window, WindowId};

thread_local! { static LOOP: RefCell<Option<EventLoop<()>>> = const { RefCell::new(None) }; }
static NATIVE_OWNER: OnceLock<Mutex<Option<ThreadId>>> = OnceLock::new();
static INITIALIZATION_FAILED: AtomicBool = AtomicBool::new(false);

pub fn run(session: Arc<Session>) -> Result<()> {
    if INITIALIZATION_FAILED.load(Ordering::Acquire) {
        return Err(Error::native(
            "native initialization previously failed; restart_required",
        ));
    }
    {
        let mut owner = lock(NATIVE_OWNER.get_or_init(|| Mutex::new(None)));
        if let Some(id) = *owner {
            if id != thread::current().id() {
                return Err(Error::thread(
                    "the process native event loop belongs to another thread; restart_required",
                ));
            }
        } else {
            *owner = Some(thread::current().id());
        }
    }
    LOOP.with(|cell| {
        let mut storage = cell.try_borrow_mut().map_err(|_| Error::state("nested native run is not supported"))?;
        if storage.is_none() {
            let mut builder = EventLoop::<()>::with_user_event();
            #[cfg(target_os = "windows")]
            {
                use winit::platform::windows::EventLoopBuilderExtWindows;
                builder.with_any_thread(session.allow_any_thread);
                // Menu commands of app windows reach the desktop services adapter (0.7 F0703).
                builder.with_msg_hook(crate::services::windows_msg_hook);
            }
            #[cfg(target_os = "linux")]
            {
                winit::platform::x11::EventLoopBuilderExtX11::with_any_thread(&mut builder, session.allow_any_thread);
                winit::platform::wayland::EventLoopBuilderExtWayland::with_any_thread(&mut builder, session.allow_any_thread);
            }
            match builder.build() {
                Ok(event_loop) => *storage = Some(event_loop),
                Err(error) => {
                    INITIALIZATION_FAILED.store(true, Ordering::Release);
                    return Err(Error::native(format!("native startup failed: {error}; fix desktop access and start a fresh process")));
                }
            }
        }
        let event_loop = storage.as_mut().ok_or_else(|| Error::native("missing native event loop"))?;
        *lock(&session.proxy) = Some(event_loop.create_proxy());
        let clipboard = Rc::new(RefCell::new(arboard::Clipboard::new().map_err(|e| e.to_string())));
        *lock(&session.clipboard) = Some(clipboard.borrow().as_ref().map(|_| ()).map_err(Clone::clone));
        let mut app = Desktop { session, windows: BTreeMap::new(), started: false, resumed: false, clipboard, used_startup_token: false };
        let result = event_loop.run_app_on_demand(&mut app).map_err(|e| Error::native(format!("native event loop: {e}")));
        app.windows.clear();
        if result.is_err() { INITIALIZATION_FAILED.store(true, Ordering::Release); }
        result
    })
}

type SharedClipboard = Rc<RefCell<std::result::Result<arboard::Clipboard, String>>>;
struct NativeClipboard(SharedClipboard);
impl Clipboard for NativeClipboard {
    fn read_text(&mut self) -> std::result::Result<Option<String>, String> {
        let mut shared = self
            .0
            .try_borrow_mut()
            .map_err(|_| "clipboard is busy".to_owned())?;
        let clipboard = shared.as_mut().map_err(|e| e.clone())?;
        match clipboard.get_text() {
            Ok(text) if text.len() <= 16 * 1024 * 1024 => Ok(Some(text)),
            Ok(_) => Err("clipboard text exceeds 16 MiB".into()),
            Err(arboard::Error::ContentNotAvailable) => Ok(None),
            Err(error) => Err(format!("system clipboard read: {error}")),
        }
    }
    fn write_text(&mut self, text: &str) -> std::result::Result<(), String> {
        if text.len() > 16 * 1024 * 1024 {
            return Err("clipboard text exceeds 16 MiB".into());
        }
        let mut shared = self
            .0
            .try_borrow_mut()
            .map_err(|_| "clipboard is busy".to_owned())?;
        shared
            .as_mut()
            .map_err(|e| e.clone())?
            .set_text(text.to_owned())
            .map_err(|e| format!("system clipboard write: {e}"))
    }
    fn write_html(&mut self, html: &str, alt_text: &str) -> std::result::Result<(), String> {
        let mut shared = self
            .0
            .try_borrow_mut()
            .map_err(|_| "clipboard is busy".to_owned())?;
        shared
            .as_mut()
            .map_err(|e| e.clone())?
            .set_html(html.to_owned(), Some(alt_text.to_owned()))
            .map_err(|e| format!("system clipboard write: {e}"))
    }
    fn read_html(&mut self) -> std::result::Result<Option<String>, String> {
        let mut shared = self
            .0
            .try_borrow_mut()
            .map_err(|_| "clipboard is busy".to_owned())?;
        let clipboard = shared.as_mut().map_err(|e| e.clone())?;
        match clipboard.get().html() {
            Ok(html) => Ok(Some(html)),
            Err(arboard::Error::ContentNotAvailable) => Ok(None),
            Err(error) => Err(format!("system clipboard read: {error}")),
        }
    }
}

/// The primary touch contact: (id, start CSS px, last CSS px, scrolling).
type PrimaryTouch = (u64, (f64, f64), (f64, f64), bool);

struct NativeWindow {
    // Drop order: surface, context, final window handle.
    surface: Surface<Rc<Window>, Rc<Window>>,
    _context: Context<Rc<Window>>,
    window: Rc<Window>,
    title: String,
    resize_revision: u64,
    last_reported_size: Option<PhysicalSize<u32>>,
    cursor: PhysicalPosition<f64>,
    modifiers: ModifiersState,
    composing: bool,
    visible: bool,
    shown_pending: bool,
    last_ime: Option<ImeState>,
    /// The document's IME reset counter last applied to the platform.
    ime_resets: u64,
    /// After a platform IME reset: late preedit/commit events of the dropped composition are
    /// discarded until this instant or the next key press (0.5 F0501, no double commit).
    ime_quiet_until: Option<std::time::Instant>,
    /// The platform emptied its preedit; unless a commit follows in the same batch (Windows and
    /// text-input-v3 send an empty preedit before every commit) the composition was canceled.
    preedit_cleared: bool,
    /// Pointer grab in force (`none`, `confined`, `locked`) and cursor visibility (0.7 F0709).
    pointer_grab: &'static str,
    /// The primary touch: (id, start CSS px, last CSS px, scrolling) (0.8 F0802).
    touch: Option<PrimaryTouch>,
    cursor_visible: bool,
    last_cursor: CursorIcon,
    a11y: Accessibility,
}
/// Per-window screen-reader bridge. AccessKit calls the handlers on its own thread (AT-SPI) or
/// from the window procedure (UIA); they only record the request and wake the owner, which
/// builds the tree and executes actions on the next loop turn.
struct Accessibility {
    adapter: accesskit_winit::Adapter,
    shared: Arc<A11yShared>,
    previous: Option<ui4me_renderer::a11y::A11yTree>,
    dirty: bool,
}
#[derive(Default)]
struct A11yShared {
    active: AtomicBool,
    needs_full: AtomicBool,
    actions: Mutex<std::collections::VecDeque<ui4me_renderer::a11y::accesskit::ActionRequest>>,
}
struct Activation(Arc<A11yShared>, Arc<Session>);
impl ui4me_renderer::a11y::accesskit::ActivationHandler for Activation {
    fn request_initial_tree(&mut self) -> Option<ui4me_renderer::a11y::accesskit::TreeUpdate> {
        self.0.active.store(true, Ordering::Release);
        self.0.needs_full.store(true, Ordering::Release);
        self.1.wake();
        None
    }
}
struct Actions(Arc<A11yShared>, Arc<Session>);
impl ui4me_renderer::a11y::accesskit::ActionHandler for Actions {
    fn do_action(&mut self, request: ui4me_renderer::a11y::accesskit::ActionRequest) {
        let mut queue = lock(&self.0.actions);
        if queue.len() < 64 {
            queue.push_back(request);
        }
        drop(queue);
        self.1.wake();
    }
}
struct Deactivation(Arc<A11yShared>);
impl ui4me_renderer::a11y::accesskit::DeactivationHandler for Deactivation {
    fn deactivate_accessibility(&mut self) {
        self.0.active.store(false, Ordering::Release);
    }
}
struct Desktop {
    session: Arc<Session>,
    windows: BTreeMap<u64, NativeWindow>,
    started: bool,
    resumed: bool,
    clipboard: SharedClipboard,
    /// The launcher's activation token was given to the first window (0.7 F0708).
    #[allow(dead_code)]
    used_startup_token: bool,
}

pub(crate) fn new_size(last: &mut Option<PhysicalSize<u32>>, size: PhysicalSize<u32>) -> bool {
    if *last == Some(size) {
        return false;
    }
    *last = Some(size);
    true
}
pub(crate) fn report_resize(session: &Session, id: u64, size: PhysicalSize<u32>) {
    let Some(info) = session.window_info(id) else {
        return;
    };
    if session
        .update_geometry(id, size.width, size.height, info.scale)
        .is_ok()
    {
        session.emit(json!({"type":"resized","window":id,"width":size.width,"height":size.height,"scale":info.scale,"units":"physical_pixels"}));
    }
}
impl Desktop {
    fn create_window(
        &mut self,
        event_loop: &ActiveEventLoop,
        id: u64,
        model: &WindowInfo,
    ) -> Result<()> {
        let attributes = Window::default_attributes()
            .with_title(model.title.clone())
            .with_inner_size(LogicalSize::new(model.width as f64, model.height as f64))
            .with_min_inner_size(LogicalSize::new(160.0, 120.0))
            .with_max_inner_size(LogicalSize::new(4096.0, 4096.0))
            .with_visible(false);
        #[cfg(target_os = "windows")]
        let attributes = {
            use winit::platform::windows::WindowAttributesExtWindows;
            attributes.with_class_name(self.session.app_id.clone())
        };
        // The launcher's startup activation token (XDG_ACTIVATION_TOKEN / DESKTOP_STARTUP_ID) lets
        // the first window take the focus on Wayland; it is used once (0.7 F0708).
        #[cfg(target_os = "linux")]
        let attributes = {
            use winit::platform::startup_notify::{
                EventLoopExtStartupNotify, WindowAttributesExtStartupNotify,
            };
            match event_loop
                .read_token_from_env()
                .filter(|_| !self.used_startup_token)
            {
                Some(token) => {
                    self.used_startup_token = true;
                    winit::platform::startup_notify::reset_activation_token_env();
                    attributes.with_activation_token(token)
                }
                None => attributes,
            }
        };
        #[cfg(target_os = "linux")]
        let attributes = {
            let attributes = winit::platform::wayland::WindowAttributesExtWayland::with_name(
                attributes,
                self.session.app_id.clone(),
                self.session.app_id.clone(),
            );
            winit::platform::x11::WindowAttributesExtX11::with_name(
                attributes,
                self.session.app_id.clone(),
                self.session.app_id.clone(),
            )
        };
        let window = Rc::new(
            event_loop
                .create_window(attributes)
                .map_err(|e| Error::native(format!("create window: {e}")))?,
        );
        let shared = Arc::new(A11yShared::default());
        let adapter = accesskit_winit::Adapter::with_direct_handlers(
            event_loop,
            &window,
            Activation(shared.clone(), self.session.clone()),
            Actions(shared.clone(), self.session.clone()),
            Deactivation(shared.clone()),
        );
        let a11y = Accessibility {
            adapter,
            shared,
            previous: None,
            dirty: true,
        };
        let context = Context::new(window.clone())
            .map_err(|e| Error::native(format!("create software context: {e}")))?;
        let surface = Surface::new(&context, window.clone())
            .map_err(|e| Error::native(format!("create software surface: {e}")))?;
        let size = window.inner_size();
        self.session
            .update_geometry(id, size.width, size.height, window.scale_factor())?;
        self.session
            .install_clipboard(id, Box::new(NativeClipboard(self.clipboard.clone())))?;
        // The OS colour scheme (Windows, X11 via the desktop portal); `None` on Wayland in winit 0.30.
        self.session
            .system_color_scheme(id, window.theme().map(|t| t == winit::window::Theme::Dark));
        self.windows.insert(
            id,
            NativeWindow {
                surface,
                _context: context,
                window,
                title: model.title.clone(),
                resize_revision: model.resize_revision,
                last_reported_size: None,
                cursor: PhysicalPosition::new(-1.0, -1.0),
                modifiers: ModifiersState::empty(),
                composing: false,
                visible: false,
                shown_pending: false,
                last_ime: None,
                ime_resets: 0,
                ime_quiet_until: None,
                preedit_cleared: false,
                pointer_grab: "none",
                touch: None,
                cursor_visible: true,
                last_cursor: CursorIcon::Default,
                a11y,
            },
        );
        // Paint before reveal. Some backends do not send redraw while a window is hidden.
        // An initial render has no last-good frame to retain. Return its error
        // through run instead of leaving an invisible, unfinishable window.
        self.draw(id)?;
        Ok(())
    }
    fn close(&mut self, id: u64) {
        // A touch in progress is canceled with its window (0.8 F0802).
        if let Some((touch, _, last, _)) = self.windows.remove(&id).and_then(|n| n.touch) {
            self.session.emit(json!({"type":"touch","window":id,"id":touch,"phase":"cancel","x":last.0,"y":last.1,"force":null}));
        }
        self.session.closed(id);
    }
    /// Run an OS file dialog on a worker thread; the owner keeps painting and receives the
    /// result as a `file_dialog` event. On Windows the dialog is owned by (modal to) the window.
    fn spawn_file_dialog(&self, id: u64, request: FileDialogRequest) {
        #[cfg(target_os = "windows")]
        let parent = self.windows.get(&id).and_then(|n| {
            use winit::raw_window_handle::HasWindowHandle;
            n.window
                .window_handle()
                .ok()
                .map(|h| ParentHandle(h.as_raw()))
        });
        let session = self.session.clone();
        let token = request.token;
        let spawned = thread::Builder::new()
            .name("ui4me-file-dialog".into())
            .spawn(move || {
                let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    let mut dialog = rfd::FileDialog::new();
                    if let Some(title) = &request.title {
                        dialog = dialog.set_title(title);
                    }
                    if let Some(directory) = &request.directory {
                        dialog = dialog.set_directory(directory);
                    }
                    if let Some(name) = &request.file_name {
                        dialog = dialog.set_file_name(name);
                    }
                    for (name, extensions) in &request.filters {
                        dialog = dialog.add_filter(name, extensions);
                    }
                    #[cfg(target_os = "windows")]
                    if let Some(parent) = &parent {
                        dialog = dialog.set_parent(parent);
                    }
                    let paths = match request.kind.as_str() {
                        "open" => dialog.pick_file().map(|p| vec![p]),
                        "open_multiple" => dialog.pick_files(),
                        "save" => dialog.save_file().map(|p| vec![p]),
                        _ => dialog.pick_folder().map(|p| vec![p]),
                    };
                    match paths {
                        None => json!({"paths": null}),
                        Some(paths) => {
                            let text: Option<Vec<String>> =
                                paths.iter().map(|p| p.to_str().map(str::to_owned)).collect();
                            match text {
                                Some(text) => json!({"paths": text}),
                                None => json!({"paths": null, "error": "a selected path is not valid UTF-8"}),
                            }
                        }
                    }
                }))
                .unwrap_or_else(|_| json!({"paths": null, "error": "the native file dialog failed"}));
                session.finish_file_dialog(id, token, result);
            });
        if spawned.is_err() {
            self.session.finish_file_dialog(
                id,
                token,
                json!({"paths": null, "error": "cannot start the file dialog thread"}),
            );
        }
    }
    /// Execute queued assistive-technology actions, then send the tree (full on activation,
    /// otherwise the changes) when an assistive technology is attached and a frame was drawn.
    fn update_accessibility(&mut self, id: u64) {
        let Some(native) = self.windows.get_mut(&id) else {
            return;
        };
        let actions: Vec<_> = lock(&native.a11y.shared.actions).drain(..).collect();
        for action in &actions {
            if let Some(request) = ui4me_renderer::a11y::decode_request(action) {
                self.session.accessibility_request(id, &request);
            }
        }
        let Some(native) = self.windows.get_mut(&id) else {
            return;
        };
        let a = &mut native.a11y;
        if !a.shared.active.load(Ordering::Acquire) {
            a.previous = None;
            return;
        }
        let full = a.shared.needs_full.swap(false, Ordering::AcqRel) || a.previous.is_none();
        if !full && !a.dirty && actions.is_empty() {
            return;
        }
        a.dirty = false;
        let tree = match self.session.accessibility_tree(id) {
            Ok(tree) => tree,
            Err(error) => {
                self.session.report_document_error(id, error);
                return;
            }
        };
        let Some(native) = self.windows.get_mut(&id) else {
            return;
        };
        let a = &mut native.a11y;
        let update = match (&a.previous, full) {
            (Some(previous), false) => ui4me_renderer::a11y::diff_update(previous, &tree),
            _ => Some(ui4me_renderer::a11y::full_update(&tree)),
        };
        if let Some(update) = update {
            a.adapter.update_if_active(|| update);
        }
        a.previous = Some(tree);
    }
    /// Report the platform's view of a window (emits `window_state` on change).
    fn observe(&mut self, id: u64) {
        let Some(native) = self.windows.get(&id) else {
            return;
        };
        let w = &native.window;
        let observed = Observed {
            visible: w.is_visible(),
            focused: Some(w.has_focus()),
            minimized: w.is_minimized(),
            maximized: Some(w.is_maximized()),
            fullscreen: Some(w.fullscreen().is_some()),
            monitor: w.current_monitor().and_then(|m| m.name()),
        };
        self.session.observe_window(id, observed);
    }
    fn enumerate(&mut self, event_loop: &ActiveEventLoop) {
        #[cfg(target_os = "linux")]
        let platform =
            if winit::platform::wayland::ActiveEventLoopExtWayland::is_wayland(event_loop) {
                "wayland"
            } else {
                "x11"
            };
        #[cfg(target_os = "windows")]
        let platform = "windows";
        #[cfg(not(any(target_os = "linux", target_os = "windows")))]
        let platform = "other";
        *lock(&self.session.platform) = platform;
        let primary = event_loop.primary_monitor();
        let monitors = event_loop
            .available_monitors()
            .take(16)
            .map(|m| {
                let size = m.size();
                let position = (platform != "wayland").then(|| {
                    let p = m.position();
                    json!([p.x, p.y])
                });
                json!({"name": m.name(), "width": size.width, "height": size.height,
                    "scale": m.scale_factor(), "position": position,
                    "refresh_millihertz": m.refresh_rate_millihertz(),
                    "primary": primary.as_ref() == Some(&m)})
            })
            .collect();
        *lock(&self.session.monitors) = monitors;
    }
    fn synchronize(&mut self, event_loop: &ActiveEventLoop) {
        if !self.resumed || self.session.should_stop() {
            return;
        }
        for id in self.session.window_ids() {
            if self.session.should_stop() {
                break;
            }
            // Fetch each small descriptor immediately before using it. Prior callbacks may
            // have changed or closed later windows; documents are never cloned here.
            let Some(model) = self.session.window_info(id) else {
                continue;
            };
            if model.closing {
                if self.session.close_requested(id) {
                    self.close(id);
                }
                continue;
            }
            if !self.windows.contains_key(&id) {
                if let Err(error) = self.create_window(event_loop, id, &model) {
                    self.session.fail(error);
                    break;
                }
            }
            let Some(current) = self.session.window_info(id) else {
                self.windows.remove(&id);
                continue;
            };
            let mut applied_size = None;
            if let Some(native) = self.windows.get_mut(&id) {
                if native.title != current.title {
                    native.window.set_title(&current.title);
                    native.title = current.title;
                }
                if native.resize_revision != current.resize_revision {
                    applied_size = native.window.request_inner_size(LogicalSize::new(
                        current.width as f64,
                        current.height as f64,
                    ));
                    native.resize_revision = current.resize_revision;
                }
                if current.dirty {
                    native.window.request_redraw();
                }
            }
            if let Some(size) = applied_size {
                self.resized(id, size);
            }
            let ops = self.session.take_window_ops(id);
            if !ops.is_empty() {
                for op in ops {
                    match op {
                        WindowOp::FileDialog(request) => self.spawn_file_dialog(id, request),
                        WindowOp::Menu(menu) => self.apply_menu(id, menu),
                        WindowOp::PointerGrab {
                            mode,
                            cursor_visible,
                        } => self.pointer_grab(id, mode, cursor_visible),
                        WindowOp::ContextMenu { x, y, menu } => self.context_menu(id, x, y, menu),
                        op => {
                            if let Some(native) = self.windows.get_mut(&id) {
                                apply_op(native, op, current.hidden);
                            }
                        }
                    }
                }
                self.observe(id);
            }
            self.update_input_state(id);
            self.update_accessibility(id);
            let shown = self.windows.get_mut(&id).is_some_and(|w| {
                if self.started && w.shown_pending {
                    w.shown_pending = false;
                    true
                } else {
                    false
                }
            });
            if shown {
                self.session.emit(json!({"type":"shown","window":id}));
            }
        }
    }
    fn resized(&mut self, id: u64, size: PhysicalSize<u32>) {
        let Some(native) = self.windows.get_mut(&id) else {
            return;
        };
        if !new_size(&mut native.last_reported_size, size) {
            return;
        }
        report_resize(&self.session, id, size);
    }
    fn draw(&mut self, id: u64) -> Result<()> {
        let Some(native) = self.windows.get_mut(&id) else {
            return Ok(());
        };
        let size = native.window.inner_size();
        let (Some(width), Some(height)) =
            (NonZeroU32::new(size.width), NonZeroU32::new(size.height))
        else {
            return Ok(());
        };
        if (size.width as usize).saturating_mul(size.height as usize) > MAX_PIXELS {
            return Err(Error::limit(
                "native window exceeds the 16,777,216 pixel budget",
            ));
        }
        self.session
            .update_geometry(id, size.width, size.height, native.window.scale_factor())?;
        let pixels = self.session.render(id)?;
        native
            .surface
            .resize(width, height)
            .map_err(|e| Error::native(format!("resize surface: {e}")))?;
        let mut buffer = native
            .surface
            .buffer_mut()
            .map_err(|e| Error::native(format!("map software buffer: {e}")))?;
        if buffer.len() != pixels.len() {
            return Err(Error::native("software buffer size mismatch"));
        }
        buffer.copy_from_slice(&pixels);
        buffer
            .present()
            .map_err(|e| Error::native(format!("present software buffer: {e}")))?;
        native.a11y.dirty = true;
        let hidden = self.session.window_info(id).is_some_and(|i| i.hidden);
        if !native.visible && !hidden {
            native.window.set_visible(true);
            native.visible = true;
            native.shown_pending = true;
        }
        Ok(())
    }
    fn send_input(&mut self, id: u64, input: Input) {
        if self.session.should_stop() || self.session.window_info(id).is_none() {
            return;
        }
        if let Err(error) = self.session.input(id, input) {
            self.session.report_document_error(id, error);
        }
        self.update_input_state(id);
    }
    fn update_input_state(&mut self, id: u64) {
        let Some(native) = self.windows.get_mut(&id) else {
            return;
        };
        let cursor = match self.session.cursor(id).as_str() {
            "text" => CursorIcon::Text,
            "pointer" => CursorIcon::Pointer,
            "crosshair" => CursorIcon::Crosshair,
            "move" => CursorIcon::Move,
            "wait" => CursorIcon::Wait,
            "progress" => CursorIcon::Progress,
            "not-allowed" => CursorIcon::NotAllowed,
            "grab" => CursorIcon::Grab,
            "grabbing" => CursorIcon::Grabbing,
            "ew-resize" | "col-resize" => CursorIcon::EwResize,
            "ns-resize" | "row-resize" => CursorIcon::NsResize,
            _ => CursorIcon::Default,
        };
        if native.last_cursor != cursor {
            native.window.set_cursor(cursor);
            native.last_cursor = cursor;
        }
        let current = self.session.ime_request(id);
        let resets = self.session.ime_reset_count(id);
        if resets != native.ime_resets {
            native.ime_resets = resets;
            // The document ended a composition the platform still shows (a pointer press, an
            // element blur, a host value write): disabling the input method drops its preedit; the
            // request below re-enables it for the control that now has the focus.
            if native.last_ime.is_some() {
                native.window.set_ime_allowed(false);
                native.last_ime = None;
                native.composing = false;
                native.ime_quiet_until =
                    Some(std::time::Instant::now() + std::time::Duration::from_millis(250));
            }
        }
        if current != native.last_ime {
            if let Some(ime) = &current {
                if native.last_ime.as_ref().map(|i| i.password) != Some(ime.password) {
                    native.window.set_ime_purpose(if ime.password {
                        ImePurpose::Password
                    } else {
                        ImePurpose::Normal
                    });
                }
                let (x, y, width, height) = ime.cursor_area;
                native.window.set_ime_cursor_area(
                    LogicalPosition::new(x, y),
                    LogicalSize::new(width.max(1.0), height.max(1.0)),
                );
                if native.last_ime.is_none() {
                    native.window.set_ime_allowed(true);
                }
            } else if native.last_ime.is_some() {
                native.window.set_ime_allowed(false);
            }
            native.last_ime = current;
        }
    }
    fn pointer_button(&mut self, id: u64, pressed: bool, button: MouseButton) {
        let button = match button {
            MouseButton::Left => 0,
            MouseButton::Middle => 1,
            MouseButton::Right => 2,
            _ => return,
        };
        let Some(native) = self.windows.get(&id) else {
            return;
        };
        let scale = native.window.scale_factor();
        let (x, y) = (native.cursor.x / scale, native.cursor.y / scale);
        self.send_input(
            id,
            Input::PointerButton {
                pressed,
                button,
                x,
                y,
            },
        );
    }
    fn keyboard(&mut self, id: u64, event: winit::event::KeyEvent) {
        let Some(native) = self.windows.get_mut(&id) else {
            return;
        };
        if event.state == ElementState::Pressed {
            native.ime_quiet_until = None;
        }
        let m = native.modifiers;
        let composing = native.composing;
        let key = match &event.logical_key {
            Key::Character(value) => value.to_string(),
            Key::Named(NamedKey::Space) => " ".into(),
            Key::Named(value) => format!("{value:?}"),
            Key::Dead(_) => "Dead".into(),
            Key::Unidentified(_) => "Unidentified".into(),
        };
        let code = match event.physical_key {
            PhysicalKey::Code(value) => format!("{value:?}"),
            PhysicalKey::Unidentified(_) => "Unidentified".into(),
        };
        let pressed = event.state == ElementState::Pressed;
        // A window menu accelerator is the menu's command, not a key for the document (0.7 F0703).
        if pressed && !composing {
            if let Some(command) = self.session.menu_accelerator(
                id,
                &key,
                &code,
                m.control_key(),
                m.alt_key(),
                m.shift_key(),
                m.super_key(),
            ) {
                if !event.repeat {
                    (self.session.service_sink())(
                        json!({"type":"menu_command","source":"accelerator","window":id,"command":command}),
                    );
                }
                return;
            }
        }
        self.send_input(
            id,
            Input::Key {
                key,
                code,
                pressed,
                repeat: event.repeat,
                shift: m.shift_key(),
                ctrl: m.control_key(),
                alt: m.alt_key(),
                meta: m.super_key(),
            },
        );
        // Ctrl+Alt permits AltGr characters. Ordinary Ctrl/Meta shortcuts never insert text.
        if pressed
            && !composing
            && !m.super_key()
            && ((!m.control_key() && !m.alt_key()) || (m.control_key() && m.alt_key()))
        {
            if let Some(text) = event.text.as_deref() {
                let text: String = text.chars().filter(|c| !c.is_control()).collect();
                if !text.is_empty() {
                    self.send_input(id, Input::Text(text));
                }
            }
        }
    }
    /// An empty preedit that no commit followed in its batch canceled the composition: end it with
    /// what it now holds (nothing). The document treats this like the IME turning off.
    fn end_canceled_compositions(&mut self) {
        let canceled: Vec<u64> = self
            .windows
            .iter_mut()
            .filter_map(|(id, w)| std::mem::take(&mut w.preedit_cleared).then_some(*id))
            .collect();
        for id in canceled {
            self.send_input(id, Input::ImeDisabled);
        }
    }
    /// Touch (0.8 F0802): every contact is reported as a `touch` event (id, phase, CSS px, force);
    /// the primary contact also drives the page like a finger: a tap is a click at the touch
    /// point, a drag beyond 8 CSS px scrolls (content follows the finger) and never selects text,
    /// a canceled contact does nothing.
    fn touch(&mut self, id: u64, t: winit::event::Touch) {
        use winit::event::TouchPhase;
        let Some(native) = self.windows.get_mut(&id) else {
            return;
        };
        let scale = native.window.scale_factor();
        let (x, y) = (t.location.x / scale, t.location.y / scale);
        let phase = match t.phase {
            TouchPhase::Started => "start",
            TouchPhase::Moved => "move",
            TouchPhase::Ended => "end",
            TouchPhase::Cancelled => "cancel",
        };
        let force = t.force.map(|f| f.normalized());
        let mut inputs: Vec<Input> = Vec::new();
        match (t.phase, native.touch) {
            (TouchPhase::Started, None) => native.touch = Some((t.id, (x, y), (x, y), false)),
            (TouchPhase::Moved, Some((tid, start, last, scrolling))) if tid == t.id => {
                let far = ((x - start.0).powi(2) + (y - start.1).powi(2)).sqrt() >= 8.0;
                if scrolling || far {
                    inputs.push(Input::Wheel {
                        dx: last.0 - x,
                        dy: last.1 - y,
                        x,
                        y,
                    });
                    native.touch = Some((tid, start, (x, y), true));
                } else {
                    native.touch = Some((tid, start, last, false));
                }
            }
            (TouchPhase::Ended, Some((tid, _, _, scrolling))) if tid == t.id => {
                native.touch = None;
                if !scrolling {
                    inputs.push(Input::PointerMoved { x, y });
                    inputs.push(Input::PointerButton {
                        pressed: true,
                        button: 0,
                        x,
                        y,
                    });
                    inputs.push(Input::PointerButton {
                        pressed: false,
                        button: 0,
                        x,
                        y,
                    });
                }
            }
            (TouchPhase::Cancelled, Some((tid, ..))) if tid == t.id => native.touch = None,
            _ => {}
        }
        self.session.emit(
            json!({"type":"touch","window":id,"id":t.id,"phase":phase,"x":x,"y":y,"force":force}),
        );
        for input in inputs {
            self.send_input(id, input);
        }
    }
    /// Confine or lock the pointer and show/hide the cursor (0.7 F0709); the outcome is reported
    /// as a `pointer_grab` event (a platform may refuse a mode).
    fn pointer_grab(&mut self, id: u64, mode: &'static str, cursor_visible: bool) {
        use winit::window::CursorGrabMode;
        let Some(native) = self.windows.get_mut(&id) else {
            return;
        };
        let grab = match mode {
            "confined" => CursorGrabMode::Confined,
            "locked" => CursorGrabMode::Locked,
            _ => CursorGrabMode::None,
        };
        let focused = native.window.has_focus();
        let result = if grab != CursorGrabMode::None && !focused {
            Err("the window does not have the focus".to_string())
        } else {
            native
                .window
                .set_cursor_grab(grab)
                .map_err(|e| e.to_string())
        };
        native
            .window
            .set_cursor_visible(cursor_visible || mode == "none");
        native.cursor_visible = cursor_visible || mode == "none";
        let mut event = json!({"type":"pointer_grab","window":id,"mode":mode,"cursor_visible":native.cursor_visible});
        match result {
            Ok(()) => {
                native.pointer_grab = mode;
                event["applied"] = json!(true);
            }
            Err(e) => {
                native.pointer_grab = "none";
                let _ = native.window.set_cursor_grab(CursorGrabMode::None);
                event["applied"] = json!(false);
                event["reason"] = json!(format!("the platform refused the {mode} pointer: {e}"));
            }
        }
        self.session.emit(event);
    }
    fn raw_handle(&self, id: u64) -> Option<winit::raw_window_handle::RawWindowHandle> {
        use winit::raw_window_handle::HasWindowHandle;
        let native = self.windows.get(&id)?;
        native.window.window_handle().ok().map(|h| h.as_raw())
    }
    /// Apply a native menu bar (0.7 F0703); a refusal is reported as a `menu_status` event.
    fn apply_menu(&mut self, id: u64, menu: Option<Vec<crate::services::MenuItem>>) {
        let handle = self.raw_handle(id);
        let sink = self.session.service_sink();
        let result =
            crate::services::with(&sink, |s| s.set_window_menu(id, handle, menu.as_deref()));
        if let Err(r) = result {
            if menu.is_some() {
                let mut v = r.to_json();
                v["type"] = json!("menu_status");
                v["window"] = json!(id);
                sink(v);
            }
        }
    }
    /// Show a context menu at CSS px of window `id` (0.7 F0703).
    fn context_menu(&mut self, id: u64, x: f64, y: f64, menu: Vec<crate::services::MenuItem>) {
        let handle = self.raw_handle(id);
        let scale = self
            .windows
            .get(&id)
            .map_or(1.0, |w| w.window.scale_factor());
        let sink = self.session.service_sink();
        let result = crate::services::with(&sink, |s| {
            s.show_context_menu(id, handle, x * scale, y * scale, &menu)
        });
        if let Err(r) = result {
            let mut v = r.to_json();
            v["type"] = json!("menu_status");
            v["window"] = json!(id);
            sink(v);
        }
    }
    /// Whether IME text events are the tail of a composition the document already ended and reset.
    fn ime_quiet(&mut self, id: u64) -> bool {
        let Some(native) = self.windows.get_mut(&id) else {
            return true;
        };
        match native.ime_quiet_until {
            Some(until) if std::time::Instant::now() < until => true,
            Some(_) => {
                native.ime_quiet_until = None;
                false
            }
            None => false,
        }
    }
    fn stop_if_requested(&mut self, event_loop: &ActiveEventLoop) -> bool {
        if self.session.should_stop() {
            self.windows.clear();
            event_loop.exit();
            true
        } else {
            false
        }
    }
}
impl ApplicationHandler<()> for Desktop {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        self.resumed = true;
        // The OS colour/contrast preference as the services adapter reads it (0.7 F0701).
        let sink = self.session.service_sink();
        let (dark, contrast) = crate::services::with(&sink, |s| s.system_preferences());
        if dark.is_some() || contrast.is_some() {
            let mut v = json!({"type":"system_preferences"});
            if let Some(d) = dark {
                v["dark"] = json!(d);
            }
            if let Some(c) = contrast {
                v["high_contrast"] = json!(c);
            }
            sink(v);
        }
        self.enumerate(event_loop);
        self.synchronize(event_loop);
        if !self.started && !self.session.should_stop() {
            self.started = true;
            self.session
                .emit(json!({"type":"started","backend":"native","app_id":self.session.app_id}));
        }
        self.synchronize(event_loop);
        self.stop_if_requested(event_loop);
    }
    fn suspended(&mut self, _: &ActiveEventLoop) {
        self.resumed = false;
        for id in self.session.window_ids() {
            let _ = self.session.input(id, Input::Focus(false));
        }
        self.windows.clear();
    }
    fn user_event(&mut self, _: &ActiveEventLoop, _: ()) {}
    fn window_event(
        &mut self,
        event_loop: &ActiveEventLoop,
        window_id: WindowId,
        event: WindowEvent,
    ) {
        if self.stop_if_requested(event_loop) {
            return;
        }
        let id = self
            .windows
            .iter()
            .find(|(_, w)| w.window.id() == window_id)
            .map(|(id, _)| *id);
        let Some(id) = id else { return };
        if let Some(native) = self.windows.get_mut(&id) {
            native.a11y.adapter.process_event(&native.window, &event);
        }
        if !matches!(event, WindowEvent::Ime(_) | WindowEvent::RedrawRequested) {
            self.end_canceled_compositions();
        }
        match event {
            WindowEvent::CloseRequested => {
                if self.session.close_requested(id) {
                    self.close(id);
                }
            }
            WindowEvent::RedrawRequested => {
                if let Err(error) = self.draw(id) {
                    self.session.report_document_error(id, error);
                }
            }
            WindowEvent::Resized(size) => {
                self.resized(id, size);
                self.observe(id);
            }
            WindowEvent::Moved(_) | WindowEvent::Occluded(_) => self.observe(id),
            WindowEvent::DroppedFile(path) => {
                let path = path.to_str().map(str::to_owned);
                // The element under the pointer receives the drop (0.7 F0707).
                let element = self.windows.get(&id).and_then(|w| {
                    let s = w.window.scale_factor();
                    (w.cursor.x >= 0.0)
                        .then(|| self.session.element_at(id, w.cursor.x / s, w.cursor.y / s))
                        .flatten()
                });
                self.session.emit(
                    json!({"type":"file_drop","window":id,"paths":path.map(|p| vec![p]),"element":element}),
                );
            }
            WindowEvent::HoveredFile(_) => {
                self.session.emit(json!({"type":"file_hover","window":id}));
            }
            WindowEvent::HoveredFileCancelled => {
                self.session
                    .emit(json!({"type":"file_hover_cancelled","window":id}));
            }
            WindowEvent::ThemeChanged(theme) => {
                self.session
                    .system_color_scheme(id, Some(theme == winit::window::Theme::Dark));
            }
            WindowEvent::ScaleFactorChanged { scale_factor, .. } => {
                if let Some(native) = self.windows.get(&id) {
                    let size = native.window.inner_size();
                    let _ = self
                        .session
                        .update_geometry(id, size.width, size.height, scale_factor);
                    self.session
                        .emit(json!({"type":"scale_changed","window":id,"scale":scale_factor}));
                }
                self.enumerate(event_loop);
                self.observe(id);
            }
            WindowEvent::CursorMoved { position, .. } => {
                if let Some(native) = self.windows.get_mut(&id) {
                    native.cursor = position;
                    let scale = native.window.scale_factor();
                    self.send_input(
                        id,
                        Input::PointerMoved {
                            x: position.x / scale,
                            y: position.y / scale,
                        },
                    );
                }
            }
            WindowEvent::CursorLeft { .. } => {
                // The last position is kept: when a modal OS window (a file picker) covered the
                // window and closes, a click at the same spot comes without a new move, and it
                // must land where the pointer is (0.6 F0606 journey), not at a sentinel.
                self.send_input(id, Input::PointerLeft);
            }
            WindowEvent::MouseInput { state, button, .. } => {
                self.pointer_button(id, state == ElementState::Pressed, button)
            }
            WindowEvent::Touch(t) => self.touch(id, t),
            WindowEvent::MouseWheel { delta, .. } => {
                if let Some(native) = self.windows.get(&id) {
                    let scale = native.window.scale_factor();
                    let (dx, dy) = match delta {
                        MouseScrollDelta::LineDelta(x, y) => {
                            (-f64::from(x) * 36.0, -f64::from(y) * 36.0)
                        }
                        MouseScrollDelta::PixelDelta(p) => (-p.x / scale, -p.y / scale),
                    };
                    let (x, y) = (native.cursor.x / scale, native.cursor.y / scale);
                    self.send_input(id, Input::Wheel { dx, dy, x, y });
                }
            }
            WindowEvent::ModifiersChanged(modifiers) => {
                let state = modifiers.state();
                if let Some(native) = self.windows.get_mut(&id) {
                    native.modifiers = state;
                }
                self.send_input(
                    id,
                    Input::Modifiers {
                        shift: state.shift_key(),
                        ctrl: state.control_key(),
                        alt: state.alt_key(),
                        meta: state.super_key(),
                    },
                );
            }
            // Focus changes synthesize key presses/releases on Windows and X11.
            // They must not type characters or activate a newly focused control.
            WindowEvent::KeyboardInput {
                event,
                is_synthetic: false,
                ..
            } => self.keyboard(id, event),
            WindowEvent::Focused(focused) => {
                if !focused {
                    let mut released = false;
                    if let Some(native) = self.windows.get_mut(&id) {
                        native.modifiers = ModifiersState::empty();
                        native.composing = false;
                        // A pointer grab never outlives the focus (0.7 F0709).
                        if native.pointer_grab != "none" || !native.cursor_visible {
                            let _ = native
                                .window
                                .set_cursor_grab(winit::window::CursorGrabMode::None);
                            native.window.set_cursor_visible(true);
                            native.pointer_grab = "none";
                            native.cursor_visible = true;
                            released = true;
                        }
                    }
                    if released {
                        self.session.emit(json!({"type":"pointer_grab","window":id,"mode":"none","applied":true,"reason":"the window lost the focus"}));
                    }
                }
                self.send_input(id, Input::Focus(focused));
                self.observe(id);
            }
            WindowEvent::Ime(Ime::Preedit(text, cursor)) => {
                if !self.ime_quiet(id) {
                    if let Some(native) = self.windows.get_mut(&id) {
                        native.preedit_cleared = text.is_empty() && native.composing;
                        native.composing = !text.is_empty();
                    }
                    self.send_input(id, Input::ImePreedit { text, cursor });
                }
            }
            WindowEvent::Ime(Ime::Commit(text)) => {
                if !self.ime_quiet(id) {
                    if let Some(native) = self.windows.get_mut(&id) {
                        native.composing = false;
                        native.preedit_cleared = false;
                    }
                    self.send_input(id, Input::ImeCommit(text));
                }
            }
            WindowEvent::Ime(Ime::Enabled) => self.send_input(id, Input::ImeEnabled),
            WindowEvent::Ime(Ime::Disabled) => {
                if let Some(native) = self.windows.get_mut(&id) {
                    native.composing = false;
                }
                self.send_input(id, Input::ImeDisabled);
            }
            _ => {}
        }
        self.synchronize(event_loop);
        self.stop_if_requested(event_loop);
    }
    fn about_to_wait(&mut self, event_loop: &ActiveEventLoop) {
        self.end_canceled_compositions();
        self.session.process_work();
        self.synchronize(event_loop);
        if self.stop_if_requested(event_loop) {
            return;
        }
        if self.session.has_work() {
            event_loop.set_control_flow(ControlFlow::Poll);
        } else if let Some(deadline) = self.session.deadline() {
            event_loop.set_control_flow(ControlFlow::WaitUntil(deadline));
            self.session.note_wait();
        } else {
            event_loop.set_control_flow(ControlFlow::Wait);
            self.session.note_wait();
        }
    }
    fn exiting(&mut self, _: &ActiveEventLoop) {
        self.windows.clear();
    }
}

fn apply_op(native: &mut NativeWindow, op: WindowOp, hidden: bool) {
    let w = &native.window;
    match op {
        WindowOp::Show => {
            if native.visible || !hidden {
                w.set_visible(true);
                native.visible = true;
            }
        }
        WindowOp::Hide => {
            w.set_visible(false);
            native.visible = false;
        }
        WindowOp::Focus => w.focus_window(),
        WindowOp::Minimize => w.set_minimized(true),
        WindowOp::Maximize => w.set_maximized(true),
        WindowOp::Restore => {
            w.set_minimized(false);
            w.set_maximized(false);
        }
        WindowOp::Fullscreen(on) => {
            w.set_fullscreen(on.then_some(winit::window::Fullscreen::Borderless(None)))
        }
        WindowOp::Constraints {
            min,
            max,
            resizable,
        } => {
            let (min, max) = (min.unwrap_or((160, 120)), max.unwrap_or((4096, 4096)));
            w.set_min_inner_size(Some(LogicalSize::new(min.0 as f64, min.1 as f64)));
            w.set_max_inner_size(Some(LogicalSize::new(max.0 as f64, max.1 as f64)));
            w.set_resizable(resizable);
        }
        WindowOp::FileDialog(_)
        | WindowOp::Menu(_)
        | WindowOp::ContextMenu { .. }
        | WindowOp::PointerGrab { .. } => {}
        WindowOp::Icon(icon) => {
            let icon = icon.and_then(|(rgba, width, height)| {
                winit::window::Icon::from_rgba(rgba, width, height).ok()
            });
            w.set_window_icon(icon);
        }
    }
}

/// A window handle lent to the dialog thread. The window outlives the dialog's use of it as an
/// owner: Windows disables, not destroys, the owner while the modal dialog runs, and a closed
/// owner only makes the dialog unowned.
#[cfg(target_os = "windows")]
struct ParentHandle(winit::raw_window_handle::RawWindowHandle);
#[cfg(target_os = "windows")]
// SAFETY: an HWND is a process-wide identifier, valid to pass between threads.
unsafe impl Send for ParentHandle {}
#[cfg(target_os = "windows")]
impl winit::raw_window_handle::HasWindowHandle for ParentHandle {
    fn window_handle(
        &self,
    ) -> std::result::Result<
        winit::raw_window_handle::WindowHandle<'_>,
        winit::raw_window_handle::HandleError,
    > {
        // SAFETY: see the type comment; the handle is only used as a dialog owner.
        Ok(unsafe { winit::raw_window_handle::WindowHandle::borrow_raw(self.0) })
    }
}
#[cfg(target_os = "windows")]
impl winit::raw_window_handle::HasDisplayHandle for ParentHandle {
    fn display_handle(
        &self,
    ) -> std::result::Result<
        winit::raw_window_handle::DisplayHandle<'_>,
        winit::raw_window_handle::HandleError,
    > {
        Ok(winit::raw_window_handle::DisplayHandle::windows())
    }
}
