//! Retained winit 0.30 host. Native objects never leave their owning thread.
//! This layer translates OS input and presents pixels; document semantics live in the renderer.
use crate::document::{Clipboard, ImeState, Input, MAX_PIXELS};
use crate::runtime::{lock, Observed, Session, WindowInfo, WindowOp};
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
        let mut app = Desktop { session, windows: BTreeMap::new(), started: false, resumed: false, clipboard };
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
}

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
    last_cursor: CursorIcon,
}
struct Desktop {
    session: Arc<Session>,
    windows: BTreeMap<u64, NativeWindow>,
    started: bool,
    resumed: bool,
    clipboard: SharedClipboard,
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
        let context = Context::new(window.clone())
            .map_err(|e| Error::native(format!("create software context: {e}")))?;
        let surface = Surface::new(&context, window.clone())
            .map_err(|e| Error::native(format!("create software surface: {e}")))?;
        let size = window.inner_size();
        self.session
            .update_geometry(id, size.width, size.height, window.scale_factor())?;
        self.session
            .install_clipboard(id, Box::new(NativeClipboard(self.clipboard.clone())))?;
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
                last_cursor: CursorIcon::Default,
            },
        );
        // Paint before reveal. Some backends do not send redraw while a window is hidden.
        // An initial render has no last-good frame to retain. Return its error
        // through run instead of leaving an invisible, unfinishable window.
        self.draw(id)?;
        Ok(())
    }
    fn close(&mut self, id: u64) {
        self.windows.remove(&id);
        self.session.closed(id);
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
                if let Some(native) = self.windows.get_mut(&id) {
                    for op in ops {
                        apply_op(native, op, current.hidden);
                    }
                }
                self.observe(id);
            }
            self.update_input_state(id);
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
        let Some(native) = self.windows.get(&id) else {
            return;
        };
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
                if let Some(native) = self.windows.get_mut(&id) {
                    native.cursor = PhysicalPosition::new(-1.0, -1.0);
                }
                self.send_input(id, Input::PointerLeft);
            }
            WindowEvent::MouseInput { state, button, .. } => {
                self.pointer_button(id, state == ElementState::Pressed, button)
            }
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
                    if let Some(native) = self.windows.get_mut(&id) {
                        native.modifiers = ModifiersState::empty();
                        native.composing = false;
                    }
                }
                self.send_input(id, Input::Focus(focused));
                self.observe(id);
            }
            WindowEvent::Ime(Ime::Preedit(text, cursor)) => {
                if let Some(native) = self.windows.get_mut(&id) {
                    native.composing = !text.is_empty();
                }
                self.send_input(id, Input::ImePreedit { text, cursor });
            }
            WindowEvent::Ime(Ime::Commit(text)) => {
                if let Some(native) = self.windows.get_mut(&id) {
                    native.composing = false;
                }
                self.send_input(id, Input::ImeCommit(text));
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
        WindowOp::Icon(icon) => {
            let icon = icon.and_then(|(rgba, width, height)| {
                winit::window::Icon::from_rgba(rgba, width, height).ok()
            });
            w.set_window_icon(icon);
        }
    }
}
