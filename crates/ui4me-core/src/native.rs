//! Desktop adapter. All OS objects stay on the first native owner thread.
//! The model and callback contract live separately so foreign reentry never borrows this adapter.
use crate::document::{Kind, MAX_PIXELS};
use crate::runtime::{lock, Session, WindowModel};
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
use winit::dpi::{LogicalSize, PhysicalPosition, PhysicalSize};
use winit::event::{ElementState, MouseButton, MouseScrollDelta, WindowEvent};
use winit::event_loop::{ActiveEventLoop, ControlFlow, EventLoop};
use winit::keyboard::{Key, NamedKey};
use winit::platform::run_on_demand::EventLoopExtRunOnDemand;
use winit::window::{Window, WindowId};

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
        let mut app = Desktop { session, windows: BTreeMap::new(), started:false, resumed:false };
        let result = event_loop.run_app_on_demand(&mut app).map_err(|e| Error::native(format!("native event loop: {e}")));
        // No Window survives between run_app_on_demand invocations.
        app.windows.clear();
        if result.is_err() { INITIALIZATION_FAILED.store(true, Ordering::Release); }
        result
    })
}

struct NativeWindow {
    // Field order matters: surface -> context -> final window handle.
    surface: Surface<Rc<Window>, Rc<Window>>,
    _context: Context<Rc<Window>>,
    window: Rc<Window>,
    title: String,
    resize_revision: u64,
    last_reported_size: Option<PhysicalSize<u32>>,
    cursor: PhysicalPosition<f64>,
    pressed: Option<usize>,
}

struct Desktop {
    session: Arc<Session>,
    windows: BTreeMap<u64, NativeWindow>,
    started: bool,
    resumed: bool,
}

pub(crate) fn new_size(last: &mut Option<PhysicalSize<u32>>, size: PhysicalSize<u32>) -> bool {
    if *last == Some(size) {
        return false;
    }
    *last = Some(size);
    true
}

pub(crate) fn report_resize(session: &Session, id: u64, size: PhysicalSize<u32>) {
    let exists = {
        let mut state = lock(&session.state);
        if let Some(model) = state.windows.get_mut(&id) {
            model.pixel_width = size.width;
            model.pixel_height = size.height;
            model.dirty = true;
            true
        } else {
            false
        }
    };
    if exists {
        session.emit(json!({"type":"resized","window":id,"width":size.width,"height":size.height,"units":"physical_pixels"}));
    }
}

impl Desktop {
    fn create_window(
        &mut self,
        event_loop: &ActiveEventLoop,
        id: u64,
        model: &WindowModel,
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
        {
            let mut state = lock(&self.session.state);
            if let Some(w) = state.windows.get_mut(&id) {
                w.pixel_width = size.width;
                w.pixel_height = size.height;
                w.scale = window.scale_factor();
                w.dirty = true;
            }
        }
        self.windows.insert(
            id,
            NativeWindow {
                surface,
                _context: context,
                window: window.clone(),
                title: model.title.clone(),
                resize_revision: model.resize_revision,
                last_reported_size: None,
                cursor: PhysicalPosition::new(-1.0, -1.0),
                pressed: None,
            },
        );
        window.set_visible(true);
        window.request_redraw();
        Ok(())
    }

    fn close(&mut self, id: u64) {
        // The surface and OS window are dropped before the `closed` callback.
        self.windows.remove(&id);
        self.session.closed(id);
    }

    fn synchronize(&mut self, event_loop: &ActiveEventLoop) {
        if !self.resumed || self.session.should_stop() {
            return;
        }
        let models: Vec<(u64, WindowModel)> = lock(&self.session.state)
            .windows
            .iter()
            .map(|(id, w)| (*id, w.clone()))
            .collect();
        for (id, model) in models {
            if self.session.should_stop() {
                break;
            }
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
            let mut applied_size = None;
            if let Some(native) = self.windows.get_mut(&id) {
                if native.title != model.title {
                    native.window.set_title(&model.title);
                    native.title = model.title;
                }
                if native.resize_revision != model.resize_revision {
                    applied_size = native.window.request_inner_size(LogicalSize::new(
                        model.width as f64,
                        model.height as f64,
                    ));
                    native.resize_revision = model.resize_revision;
                }
                if model.dirty {
                    native.window.request_redraw();
                }
            }
            // Some backends apply the request immediately and do not send a
            // Resized event. Process the actual returned physical size through
            // the same path as an asynchronous window-system notification.
            if let Some(size) = applied_size {
                self.resized(id, size);
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
        let pixels = {
            let mut state = lock(&self.session.state);
            let Some(model) = state.windows.get_mut(&id) else {
                return Ok(());
            };
            model.pixel_width = size.width;
            model.pixel_height = size.height;
            model.scale = native.window.scale_factor();
            let pixels = model
                .document
                .render(size.width, size.height, model.scale)?;
            model.dirty = false;
            pixels
        };
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
            .map_err(|e| Error::native(format!("present software buffer: {e}")))
    }

    fn pointer_button(&mut self, id: u64, pressed: bool) {
        let Some(native) = self.windows.get_mut(&id) else {
            return;
        };
        let mut state = lock(&self.session.state);
        let Some(model) = state.windows.get_mut(&id) else {
            return;
        };
        let scale = model.scale.max(0.5);
        let hit = model.document.hit(
            native.cursor.x / scale,
            native.cursor.y / scale,
            model.pixel_width as f64 / scale,
        );
        let hit = hit.filter(|index| {
            matches!(
                model.document.elements[*index].kind,
                Kind::Input | Kind::Button
            )
        });
        if pressed {
            native.pressed = hit;
            model.document.focus = hit;
            model.dirty = true;
        } else {
            let click = hit
                .filter(|index| {
                    Some(*index) == native.pressed
                        && model.document.elements[*index].kind == Kind::Button
                })
                .map(|index| model.document.elements[index].id.clone());
            native.pressed = None;
            drop(state);
            if let Some(element) = click {
                self.session
                    .emit(json!({"type":"click","window":id,"element":element}));
            }
        }
    }

    fn keyboard(&mut self, id: u64, event: winit::event::KeyEvent) {
        if event.state != ElementState::Pressed {
            return;
        }
        let mut state = lock(&self.session.state);
        let Some(model) = state.windows.get_mut(&id) else {
            return;
        };
        let mut emitted = None;
        match &event.logical_key {
            Key::Named(NamedKey::Tab) => model.document.next_focus(),
            Key::Named(NamedKey::Backspace) => {
                if let Some((element, value)) = model.document.edit(None, true) {
                    emitted =
                        Some(json!({"type":"change","window":id,"element":element,"value":value}));
                }
            }
            Key::Named(NamedKey::Enter) | Key::Named(NamedKey::Space) => {
                let button = model
                    .document
                    .focus
                    .and_then(|i| model.document.elements.get(i))
                    .filter(|e| e.kind == Kind::Button)
                    .map(|e| e.id.clone());
                if let Some(element) = button {
                    emitted = Some(json!({"type":"click","window":id,"element":element}));
                } else if event.logical_key == Key::Named(NamedKey::Space) {
                    if let Some((element, value)) = model.document.edit(Some(" "), false) {
                        emitted = Some(
                            json!({"type":"change","window":id,"element":element,"value":value}),
                        );
                    }
                }
            }
            _ => {
                if let Some((element, value)) = model.document.edit(event.text.as_deref(), false) {
                    emitted =
                        Some(json!({"type":"change","window":id,"element":element,"value":value}));
                }
            }
        }
        model.dirty = true;
        drop(state);
        if let Some(event) = emitted {
            self.session.emit(event);
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
        let Some(id) = id else {
            return;
        };
        match event {
            WindowEvent::CloseRequested => {
                if self.session.close_requested(id) {
                    self.close(id);
                }
            }
            WindowEvent::RedrawRequested => {
                if let Err(error) = self.draw(id) {
                    self.session.fail(error);
                }
            }
            WindowEvent::Resized(size) => {
                self.resized(id, size);
            }
            WindowEvent::ScaleFactorChanged { scale_factor, .. } => {
                if let Some(model) = lock(&self.session.state).windows.get_mut(&id) {
                    model.scale = scale_factor;
                    model.dirty = true;
                }
            }
            WindowEvent::CursorMoved { position, .. } => {
                if let Some(native) = self.windows.get_mut(&id) {
                    native.cursor = position;
                }
            }
            WindowEvent::CursorLeft { .. } => {
                if let Some(native) = self.windows.get_mut(&id) {
                    native.cursor = PhysicalPosition::new(-1.0, -1.0);
                    native.pressed = None;
                }
            }
            WindowEvent::MouseInput {
                state,
                button: MouseButton::Left,
                ..
            } => self.pointer_button(id, state == ElementState::Pressed),
            WindowEvent::MouseWheel { delta, .. } => {
                if let Some(model) = lock(&self.session.state).windows.get_mut(&id) {
                    let delta = match delta {
                        MouseScrollDelta::LineDelta(_, y) => y as f64 * 36.0,
                        MouseScrollDelta::PixelDelta(p) => p.y / model.scale.max(0.5),
                    };
                    let max = (model.document.elements.len() as f64 * 44.0 + 40.0
                        - model.pixel_height as f64 / model.scale.max(0.5))
                    .max(0.0);
                    model.document.scroll = (model.document.scroll - delta).clamp(0.0, max);
                    model.dirty = true;
                }
            }
            WindowEvent::KeyboardInput { event, .. } => self.keyboard(id, event),
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
            lock(&self.session.state).stats.wait_requests += 1;
        } else {
            event_loop.set_control_flow(ControlFlow::Wait);
            lock(&self.session.state).stats.wait_requests += 1;
        }
    }
    fn exiting(&mut self, _: &ActiveEventLoop) {
        self.windows.clear();
    }
}
