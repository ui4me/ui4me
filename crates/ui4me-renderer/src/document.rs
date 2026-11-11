//! The application-facing document engine. Backend stages never cross this seam.
//! Every method is owner-thread only. Input records events; the host invokes
//! foreign callbacks only after this engine operation releases all its borrows.
use crate::interaction::dispatch::{self, DispatchHost, InteractionRuntime, Invocation};
use crate::interaction::frame::Modifiers;
use crate::interaction::input_queue::{InputItem, drain_input};
use crate::interaction::listeners::{ListenerSpec, Released};
use crate::interaction::scroll::{ScrollApplied, ScrollTargetInfo};
use crate::layout::coordinator::overflow::{ScrollError, ScrollTarget};
use crate::pipeline::resources::{PipelineResources, SharedResources};
use crate::pipeline::state::{DocumentPipeline, PipelineConfig, PipelineState};
use crate::raster::headless::PixelFormat;
use crate::scene::hit_index::{HitOptions, ScrollAxis, ViewportPoint};
use serde_json::{Value, json};
use std::collections::{BTreeSet, VecDeque};
use std::num::NonZeroU32;
use std::path::Path;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Arc, Mutex, MutexGuard};
use std::time::{Duration, Instant};
use ui4me_assets::ResourceManager;
use ui4me_assets::decode::default_decoder;
use ui4me_assets::policy::{ResourcePolicy, ResourcePolicyPatch, RuntimeResourceModes};
use ui4me_document::control_semantics::InputType;
use ui4me_document::document::Document as Model;
use ui4me_document::limits::DomLimits;
use ui4me_engine_types::clipboard::ClipboardData;
use ui4me_engine_types::codes_generated::{Code, Family};
use ui4me_engine_types::diag::DispatchOrigin;
use ui4me_engine_types::ids::{CallbackToken, DocumentId, NodeId, RawId};
use ui4me_engine_types::input::{
    InputKind, InputOrigin, KeyData, PointerData, utf8_to_utf16_offset,
};
use ui4me_engine_types::stage::Stage;
use ui4me_engine_types::status::Status;

pub const MAX_TEXT: usize = 16 * 1024;
pub const MAX_PIXELS: usize = 16_777_216;
const MAX_HTML: usize = 1024 * 1024;
const MAX_NODES: usize = 16_384;
const MAX_DEPTH: usize = 256;
const MAX_EVENTS: usize = 1024;
const BLINK: Duration = Duration::from_millis(500);
static NEXT_DOCUMENT: AtomicU32 = AtomicU32::new(1);
static CLIPBOARD: Mutex<Option<String>> = Mutex::new(None);
pub type Result<T> = std::result::Result<T, Error>;

#[derive(Clone, Debug)]
pub struct Error {
    pub code: i32,
    pub message: String,
}
impl std::fmt::Display for Error {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}
impl std::error::Error for Error {}
impl From<Status> for Error {
    fn from(value: Status) -> Self {
        let code = match value.code {
            Code::SizeLimit | Code::OutOfMemory => 5,
            Code::StaleHandle | Code::WrongDocument => 4,
            Code::DocumentClosed | Code::InvalidState => 2,
            _ => match value.family() {
                Family::Threading => 3,
                Family::Resource => 9,
                Family::Platform | Family::PaintBackend => 6,
                _ => 1,
            },
        };
        Error {
            code,
            message: format!("{}: {}", value.code.name(), value.message),
        }
    }
}
fn arg(message: impl Into<String>) -> Error {
    Error {
        code: 1,
        message: message.into(),
    }
}
fn invalid(message: impl Into<String>) -> Status {
    Status::new(Code::InvalidArgument, Stage::Host).with_message(message)
}
fn limit(message: impl Into<String>) -> Status {
    Status::new(Code::SizeLimit, Stage::Host).with_message(message)
}
fn lock<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(|e| e.into_inner())
}

/// Native hosts install a system clipboard. Headless callers use memory only.
pub trait Clipboard {
    fn read_text(&mut self) -> std::result::Result<Option<String>, String>;
    fn write_text(&mut self, text: &str) -> std::result::Result<(), String>;
}
struct MemoryClipboard;
impl Clipboard for MemoryClipboard {
    fn read_text(&mut self) -> std::result::Result<Option<String>, String> {
        Ok(lock(&CLIPBOARD).clone())
    }
    fn write_text(&mut self, text: &str) -> std::result::Result<(), String> {
        *lock(&CLIPBOARD) = Some(text.to_owned());
        Ok(())
    }
}
#[derive(Clone, Debug, PartialEq)]
pub struct ImeState {
    pub password: bool,
    pub cursor_area: (f64, f64, f64, f64),
}
/// Positions are CSS pixels; preedit cursor positions are UTF-8 byte offsets.
#[derive(Clone, Debug)]
pub enum Input {
    PointerMoved {
        x: f64,
        y: f64,
    },
    PointerButton {
        pressed: bool,
        button: i8,
        x: f64,
        y: f64,
    },
    PointerLeft,
    Wheel {
        dx: f64,
        dy: f64,
        x: f64,
        y: f64,
    },
    Key {
        key: String,
        code: String,
        pressed: bool,
        repeat: bool,
        shift: bool,
        ctrl: bool,
        alt: bool,
        meta: bool,
    },
    Modifiers {
        shift: bool,
        ctrl: bool,
        alt: bool,
        meta: bool,
    },
    Text(String),
    Focus(bool),
    ImePreedit {
        text: String,
        cursor: Option<(usize, usize)>,
    },
    ImeCommit(String),
    ImeEnabled,
    ImeDisabled,
}
struct CaretBlink {
    node: NodeId,
    deadline: Instant,
    visible: bool,
    upstream: bool,
}
/// One canonical document and its owner-local renderer/interaction state.
pub struct Document {
    pipeline: DocumentPipeline,
    interaction: InteractionRuntime,
    resources: SharedResources,
    events: Vec<Value>,
    errors: VecDeque<Value>,
    clipboard: Box<dyn Clipboard>,
    cursor: String,
    ime: Option<ImeState>,
    blink: Option<CaretBlink>,
    started: Instant,
    modifiers: Modifiers,
    pointer_buttons: u16,
    pointer: (f64, f64),
    window_focused: bool,
    repaint: bool,
}
impl std::fmt::Debug for Document {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Document")
            .field("id", &self.id())
            .field("state", &self.pipeline.state())
            .finish_non_exhaustive()
    }
}
impl Document {
    pub fn parse(html: &str) -> Result<Self> {
        Self::parse_with_source(html, None, 640, 480)
    }
    pub fn parse_with_source(
        html: &str,
        base: Option<&Path>,
        width: u32,
        height: u32,
    ) -> Result<Self> {
        check_html(html)?;
        let index = NEXT_DOCUMENT
            .try_update(Ordering::Relaxed, Ordering::Relaxed, |v| v.checked_add(1))
            .map_err(|_| Error {
                code: 5,
                message: "Document identity space exhausted".into(),
            })?;
        let id = DocumentId::from_raw(RawId {
            index: 0,
            generation: NonZeroU32::new(index).expect("nonzero document generation"),
        });
        let base = base
            .map(std::fs::canonicalize)
            .transpose()
            .map_err(|e| Error {
                code: 9,
                message: format!("Cannot resolve asset base: {e}"),
            })?;
        if base.as_ref().is_some_and(|p| !p.is_dir()) {
            return Err(arg("Asset base must be a directory"));
        }
        let url = match &base {
            Some(path) => url::Url::from_directory_path(path)
                .map_err(|_| arg("Asset base must be an absolute directory"))?,
            None => url::Url::parse("about:blank").map_err(|e| arg(e.to_string()))?,
        };
        let limits = DomLimits {
            input_bytes: MAX_HTML as u64,
            nodes: MAX_NODES as u64,
            string_bytes: MAX_HTML as u64,
            serialization_bytes: 4 * MAX_HTML as u64,
            batch_commands: 1024,
            batch_bytes: MAX_HTML as u64,
        };
        let model = Model::create(id, html, url.as_str(), limits)?;
        validate_document(&model, None, None)?;
        let policy = ResourcePolicy {
            decoded_memory_budget: 128 * 1024 * 1024,
            cache_budget: 64 * 1024 * 1024,
            max_decoded_pixels: MAX_PIXELS as u64,
            ..ResourcePolicy::default()
        };
        let mut manager =
            ResourceManager::new(RuntimeResourceModes::default(), policy, default_decoder())?;
        let patch = ResourcePolicyPatch {
            file_roots: base.map(|p| vec![p]),
            ..ResourcePolicyPatch::default()
        };
        manager.create_document(id, url.clone(), None, &patch)?;
        manager.set_local_family_lookup(Some(Arc::new(
            crate::pipeline::font_faces::system_family_exists,
        )));
        let fonts = manager.runtime_font_sources();
        let resources = Arc::new(Mutex::new(manager));
        let config = PipelineConfig {
            viewport_width: f64::from(width),
            viewport_height: f64::from(height),
            scale: 1.0,
            font_files: Vec::new(),
        };
        let mut pipeline = DocumentPipeline::from_document(model, config, fonts)?;
        pipeline.attach_resources(Arc::new(PipelineResources::new(resources.clone(), id, url)))?;
        let mut interaction = InteractionRuntime::with_event_log_capacity(64);
        pipeline.mutate(|d| interaction.attach_document(d))?;
        let root = pipeline.document().document_node();
        for event in [
            "click",
            "input",
            "change",
            "focus",
            "blur",
            "focusin",
            "focusout",
            "keydown",
            "keyup",
            "mousedown",
            "mouseup",
            "mousemove",
            "wheel",
            "scroll",
            "compositionstart",
            "compositionupdate",
            "compositionend",
            "submit",
            "reset",
        ] {
            interaction.add_listener(
                pipeline.document(),
                root,
                ListenerSpec::new(event, CallbackToken::new(1).expect("nonzero")).capture(true),
            )?;
        }
        Ok(Self {
            pipeline,
            interaction,
            resources,
            events: Vec::new(),
            errors: VecDeque::new(),
            clipboard: Box::new(MemoryClipboard),
            cursor: "default".into(),
            ime: None,
            blink: None,
            started: Instant::now(),
            modifiers: Modifiers::default(),
            pointer_buttons: 0,
            pointer: (0.0, 0.0),
            window_focused: true,
            repaint: true,
        })
    }
    fn id(&self) -> DocumentId {
        self.pipeline.document().id()
    }
    fn node(&self, element: &str) -> Result<NodeId> {
        self.pipeline
            .element_by_id(element)
            .ok_or_else(|| arg(format!("Unknown element ID: {element}")))
    }
    pub fn set_waker(&mut self, wake: Arc<dyn Fn() + Send + Sync>) {
        lock(&self.resources).set_wake(Some(wake));
    }
    pub fn set_clipboard(&mut self, clipboard: Box<dyn Clipboard>) {
        self.clipboard = clipboard;
    }
    pub fn cursor(&self) -> &str {
        &self.cursor
    }
    pub fn ime_request(&self) -> Option<&ImeState> {
        self.ime.as_ref().filter(|_| self.window_focused)
    }
    pub fn needs_repaint(&self) -> bool {
        self.repaint || self.pipeline.state() == PipelineState::Dirty
    }
    pub fn drain_events(&mut self) -> Vec<Value> {
        std::mem::take(&mut self.events)
    }
    /// Recheck before each foreign callback: an earlier callback may have removed
    /// this target and created an element with the same public ID.
    pub fn event_is_current(&self, event: &Value) -> bool {
        let decode = |name: &str| -> Option<NodeId> {
            let token = event.get(name)?.as_array()?;
            let index = u32::try_from(token.first()?.as_u64()?).ok()?;
            let generation = NonZeroU32::new(u32::try_from(token.get(1)?.as_u64()?).ok()?)?;
            Some(NodeId::from_raw(RawId { index, generation }))
        };
        let Some(target) = decode("_target") else {
            return false;
        };
        let Some(element) = decode("_element") else {
            return false;
        };
        let d = self.pipeline.document();
        d.arena().contains(target)
            && d.is_connected(target).unwrap_or(false)
            && d.arena().contains(element)
            && d.is_connected(element).unwrap_or(false)
            && d.get_attribute(element, "id").ok().flatten().unwrap_or("")
                == event.get("element").and_then(Value::as_str).unwrap_or("")
    }
    pub fn get_value(&self, element: &str) -> Result<String> {
        let n = self.node(element)?;
        match self.pipeline.document().control_value(n) {
            Some(value) => Ok(value),
            None => Ok(self.pipeline.text_content(n)?),
        }
    }
    pub fn set_text(&mut self, element: &str, text: &str) -> Result<()> {
        check_text(text)?;
        let n = self.node(element)?;
        if crate::interaction::editing::text_kind(self.pipeline.document(), n).is_some() {
            return self.set_value(element, text);
        }
        self.pipeline.set_text_content(n, text)?;
        self.after_mutation(true);
        Ok(())
    }
    pub fn set_value(&mut self, element: &str, value: &str) -> Result<()> {
        check_text(value)?;
        let n = self.node(element)?;
        if !matches!(
            self.pipeline.document().local_name(n)?,
            "input" | "textarea" | "select"
        ) {
            return Err(arg("set_value requires a form control"));
        }
        self.pipeline
            .mutate(|d| crate::interaction::controls::host_set_value(d, n, value))?;
        let value = self
            .pipeline
            .document()
            .control_value(n)
            .unwrap_or_default();
        self.interaction.host_value_written(self.id(), n, &value);
        self.after_mutation(false);
        Ok(())
    }
    pub fn get_checked(&self, element: &str) -> Result<bool> {
        let n = self.node(element)?;
        self.pipeline
            .document()
            .control_state(n)?
            .and_then(|s| s.checkedness)
            .ok_or_else(|| arg("get_checked requires a checkbox or radio"))
    }
    pub fn set_checked(&mut self, element: &str, checked: bool) -> Result<()> {
        let n = self.node(element)?;
        self.get_checked(element)?;
        self.pipeline
            .mutate(|d| crate::interaction::controls::host_set_checked(d, n, checked))?;
        self.after_mutation(false);
        Ok(())
    }
    pub fn set_attribute(&mut self, element: &str, name: &str, value: Option<&str>) -> Result<()> {
        let n = self.node(element)?;
        let name = name.to_ascii_lowercase();
        if name.starts_with("on") || name == "srcdoc" {
            return Err(arg("Script-bearing attributes are unsupported"));
        }
        if name == "type" && self.pipeline.document().input_type(n).is_some() {
            validate_input_type(InputType::parse(value))?;
        }
        if let Some(value) = value {
            check_text(value)?;
            if name == "id" && !value.is_empty() {
                validate_id(value)?;
                if self
                    .pipeline
                    .element_by_id(value)
                    .is_some_and(|other| other != n)
                {
                    return Err(arg("Duplicate public element ID"));
                }
            }
            self.pipeline.set_attribute(n, &name, value)?;
        } else {
            self.pipeline
                .mutate(|d| d.remove_attribute(n, &name).map(|_| ()))?;
        }
        self.after_mutation(false);
        Ok(())
    }
    pub fn add_class(&mut self, element: &str, class: &str) -> Result<()> {
        self.class(element, class, true)
    }
    pub fn remove_class(&mut self, element: &str, class: &str) -> Result<()> {
        self.class(element, class, false)
    }
    fn class(&mut self, element: &str, class: &str, add: bool) -> Result<()> {
        if class.is_empty() || class.chars().any(char::is_whitespace) {
            return Err(arg("A class must be one nonempty token"));
        }
        let n = self.node(element)?;
        let mut classes: Vec<String> = self
            .pipeline
            .document()
            .get_attribute(n, "class")?
            .unwrap_or("")
            .split_whitespace()
            .map(str::to_owned)
            .collect();
        classes.retain(|s| s != class);
        if add {
            classes.push(class.to_owned());
        }
        self.set_attribute(element, "class", Some(&classes.join(" ")))
    }
    pub fn replace_children_html(&mut self, element: &str, html: &str) -> Result<()> {
        check_html(html)?;
        let n = self.node(element)?;
        self.pipeline.mutate(|d| {
            d.set_inner_html_checked(n, html, |d, f| validate_document(d, Some(n), Some(f)))
        })?;
        self.after_mutation(true);
        Ok(())
    }
    fn after_mutation(&mut self, subtree: bool) {
        let id = self.id();
        self.interaction.note_doc(id);
        dispatch::operation(self, |_| {});
        if subtree {
            let d = self.pipeline.document();
            let live = d
                .arena()
                .iter()
                .map(|n| n.id())
                .filter(|&n| d.arena().is_connected(n))
                .collect();
            lock(&self.resources).retain_nodes(id, &live);
        }
        if self
            .blink
            .as_ref()
            .is_some_and(|b| Some(b.node) != self.interaction.focused_element(id))
        {
            self.blink = None;
            self.ime = None;
        }
        self.repaint = true;
    }
    pub fn focus(&mut self, element: &str) -> Result<()> {
        let n = self.node(element)?;
        let id = self.id();
        crate::interaction::focus::focus(self, id, n)?;
        Ok(())
    }
    pub fn render(&mut self, width: u32, height: u32, scale: f64) -> Result<Vec<u32>> {
        if width == 0
            || height == 0
            || (width as usize)
                .checked_mul(height as usize)
                .is_none_or(|n| n > MAX_PIXELS)
        {
            return Err(Error {
                code: 5,
                message: "Framebuffer dimensions exceed pixel budget".into(),
            });
        }
        if !scale.is_finite() || scale <= 0.0 {
            return Err(arg("Scale must be finite and positive"));
        }
        self.poll_resources()?;
        self.pipeline.set_device_viewport(width, height, scale)?;
        let frame = self.pipeline.render_headless()?;
        if frame.pixels.width != width || frame.pixels.height != height {
            return Err(Error {
                code: 6,
                message: format!(
                    "Renderer surface mismatch: {}x{} versus {width}x{height}",
                    frame.pixels.width, frame.pixels.height
                ),
            });
        }
        let mut pixels = Vec::with_capacity(width as usize * height as usize);
        for rgba in frame.pixels.data.as_chunks::<4>().0 {
            let a = u32::from(rgba[3]);
            let channel = |v: u8| match frame.pixels.format {
                PixelFormat::Rgba8Premultiplied => (u32::from(v) + 255 - a).min(255),
                PixelFormat::Rgba8Unpremultiplied => {
                    (u32::from(v) * a + 255 * (255 - a) + 127) / 255
                }
            };
            pixels.push((channel(rgba[0]) << 16) | (channel(rgba[1]) << 8) | channel(rgba[2]));
        }
        frame.recycle();
        self.repaint = false;
        Ok(pixels)
    }
    pub fn has_pending_resources(&self) -> bool {
        lock(&self.resources).pending(self.id()).unwrap_or(0) != 0
    }
    pub fn next_wake_in(&self) -> Option<Duration> {
        let resources = self
            .has_pending_resources()
            .then_some(Duration::from_millis(50));
        let blink = self
            .blink
            .as_ref()
            .filter(|_| self.window_focused)
            .map(|b| b.deadline.saturating_duration_since(Instant::now()));
        match (resources, blink) {
            (Some(a), Some(b)) => Some(a.min(b)),
            (a, b) => a.or(b),
        }
    }
    pub fn poll_resources(&mut self) -> Result<bool> {
        let id = self.id();
        let batches = lock(&self.resources).process_completions();
        let mut changed = false;
        for batch in batches.into_iter().filter(|b| b.document == id) {
            changed |= self.pipeline.apply_resource_batch(&batch)?;
            if batch.font_epoch_changed {
                let faces = lock(&self.resources).document_faces(id)?;
                changed |= self.pipeline.apply_font_faces(faces)?;
            }
        }
        if self.blink.as_ref().is_some_and(|b| {
            !self
                .pipeline
                .document()
                .is_connected(b.node)
                .unwrap_or(false)
        }) {
            self.blink = None;
        }
        if let Some(b) = self.blink.as_mut().filter(|_| self.window_focused)
            && b.deadline <= Instant::now()
        {
            b.deadline = Instant::now() + BLINK;
            b.visible = !b.visible;
            self.pipeline
                .set_caret_state(b.visible, b.upstream, b.node)?;
            changed = true;
        }
        self.repaint |= changed;
        Ok(changed)
    }
    pub fn diagnostics(&self) -> Vec<Value> {
        let mut values: Vec<Value> = self.errors.iter().rev().take(32).cloned().collect();
        let stores = self.pipeline.stores();
        for entry in stores.errors.iter().take(32) {
            let status = &entry.record.status;
            values.push(json!({"code":status.code.name(),"stage":status.stage.name(),"message":status.message}));
        }
        for entry in stores.unsupported.iter().take(32) {
            values.push(json!({"code":entry.code.name(),"stage":entry.key.stage.name(),"feature":entry.key.feature.as_str(),"reason":entry.reason.name()}));
        }
        for e in lock(&self.resources)
            .document_records(self.id())
            .into_iter()
            .rev()
            .take(32)
        {
            if e.outcome != Code::Ok {
                values.push(
                    json!({"code":e.outcome.name(),"stage":"resource","request":e.request.serial}),
                );
            }
        }
        values.truncate(128);
        values
    }
    pub fn handle_input(&mut self, input: Input) -> Result<Vec<Value>> {
        if let Input::Modifiers {
            shift,
            ctrl,
            alt,
            meta,
        } = input
        {
            self.modifiers = Modifiers {
                shift,
                ctrl,
                alt,
                meta,
            };
            return Ok(Vec::new());
        }
        let window_focus = match &input {
            Input::Focus(focused) => Some(*focused),
            _ => None,
        };
        if let Some(focused) = window_focus {
            self.window_focused = focused;
        }
        if window_focus == Some(false) {
            self.modifiers = Modifiers::default();
            self.pointer_buttons = 0;
        }
        let id = self.id();
        self.pipeline.flush()?;
        if let Some(node) = self.interaction.focused_element(id)
            && !self.focus_target_visible(id, node)?
        {
            crate::interaction::focus::blur(self, id, node)?;
        }
        if let Input::Text(text) = &input {
            check_text(text)?;
            if let Some(n) = self.interaction.focused_element(id) {
                let composing = crate::interaction::editing::ime::is_composing(self, id);
                let key = KeyData {
                    text: Some(text.clone()),
                    is_composing: composing,
                    ..KeyData::new("Unidentified", "Unidentified")
                };
                // The platform has already separated committed text from
                // shortcuts. AltGr often arrives with Ctrl+Alt set.
                let m = Modifiers {
                    shift: self.modifiers.shift,
                    ..Modifiers::default()
                };
                dispatch::operation(self, |h| {
                    crate::interaction::editing::keydown(
                        h,
                        id,
                        n,
                        &key,
                        m,
                        DispatchOrigin::Native,
                        None,
                    )
                })?;
            }
            return Ok(self.drain_events());
        }
        let kind = match input {
            Input::PointerMoved { x, y } => {
                finite_point(x, y)?;
                self.pointer = (x, y);
                let mut p = PointerData::mouse(x, y, -1);
                p.buttons = self.pointer_buttons;
                p.pressure = if p.buttons == 0 { 0.0 } else { 0.5 };
                InputKind::PointerMove(p)
            }
            Input::PointerButton {
                pressed,
                button,
                x,
                y,
            } => {
                finite_point(x, y)?;
                self.pointer = (x, y);
                let bit = ui4me_engine_types::input::button_bit(button);
                if pressed {
                    self.pointer_buttons |= bit;
                } else {
                    self.pointer_buttons &= !bit;
                }
                let mut p = PointerData::mouse(x, y, button);
                p.buttons = self.pointer_buttons;
                p.pressure = if p.buttons == 0 { 0.0 } else { 0.5 };
                if pressed {
                    InputKind::PointerDown(p)
                } else {
                    InputKind::PointerUp(p)
                }
            }
            Input::PointerLeft => {
                let mut p = PointerData::mouse(self.pointer.0, self.pointer.1, -1);
                p.buttons = self.pointer_buttons;
                InputKind::PointerLeave(p)
            }
            Input::Wheel { dx, dy, x, y } => {
                finite_point(dx, dy)?;
                finite_point(x, y)?;
                InputKind::Wheel {
                    x,
                    y,
                    delta_x: dx,
                    delta_y: dy,
                }
            }
            Input::Key {
                key,
                code,
                pressed,
                repeat,
                shift,
                ctrl,
                alt,
                meta,
            } => {
                self.modifiers = Modifiers {
                    shift,
                    ctrl,
                    alt,
                    meta,
                };
                let composing = crate::interaction::editing::ime::is_composing(self, id);
                let key = KeyData {
                    repeat,
                    is_composing: composing,
                    ..KeyData::new(key, code)
                };
                if pressed {
                    InputKind::KeyDown(key)
                } else {
                    InputKind::KeyUp(key)
                }
            }
            Input::Focus(focused) => InputKind::WindowFocus { focused },
            Input::ImePreedit { text, cursor } => {
                check_text(&text)?;
                let cursor = cursor.map(|(a, b)| {
                    (
                        utf8_to_utf16_offset(&text, a),
                        utf8_to_utf16_offset(&text, b),
                    )
                });
                InputKind::ImePreedit { text, cursor }
            }
            Input::ImeCommit(text) => {
                check_text(&text)?;
                InputKind::ImeCommit { text }
            }
            Input::ImeEnabled => InputKind::ImeEnabled,
            Input::ImeDisabled => InputKind::ImeDisabled,
            Input::Text(_) | Input::Modifiers { .. } => unreachable!(),
        };
        let mut item = InputItem::new(id, InputOrigin::Native, kind);
        item.modifiers = self.modifiers;
        self.interaction.queue_input(item);
        drain_input(self);
        if let Some(focused) = window_focus
            && let Some(blink) = &self.blink
        {
            self.set_caret_state(id, blink.node, focused, blink.upstream);
        }
        Ok(self.drain_events())
    }
}
impl DispatchHost for Document {
    fn with_runtime(&mut self, f: &mut dyn FnMut(&mut InteractionRuntime)) {
        f(&mut self.interaction);
    }
    fn with_engine(
        &mut self,
        id: DocumentId,
        f: &mut dyn FnMut(&mut InteractionRuntime, &mut Model),
    ) -> std::result::Result<(), Status> {
        if id != self.id() {
            return Err(Status::new(Code::WrongDocument, Stage::Host));
        }
        let interaction = &mut self.interaction;
        self.pipeline.mutate(|document| {
            f(interaction, document);
            Ok(())
        })
    }
    fn invoke(&mut self, inv: &Invocation) -> std::result::Result<(), dispatch::CallbackError> {
        let event = self
            .interaction
            .event(inv.event)
            .map_err(|e| dispatch::CallbackError::new(e.message))?;
        let node = event.target;
        let d = self.pipeline.document();
        let raw = node.raw();
        let path = self
            .interaction
            .event_path(inv.event)
            .map_err(|e| dispatch::CallbackError::new(e.message))?;
        let identified: Vec<(NodeId, String)> = path
            .into_iter()
            .filter_map(|n| {
                d.get_attribute(n, "id")
                    .ok()
                    .flatten()
                    .filter(|id| !id.is_empty())
                    .map(|id| (n, id.to_owned()))
            })
            .collect();
        let (element, element_name) = identified.first().cloned().unwrap_or((node, String::new()));
        let eraw = element.raw();
        let route: Vec<&str> = identified
            .iter()
            .take(if event.init.bubbles { usize::MAX } else { 1 })
            .map(|(_, id)| id.as_str())
            .collect();
        let event_type = if inv.event_type == "change" {
            "commit"
        } else {
            &inv.event_type
        };
        let mut value = json!({"type":event_type,"element":element_name,"path":route,
            "_target":[raw.index,raw.generation.get()],"_element":[eraw.index,eraw.generation.get()]});
        if let Some(control) = d.control_state(node).ok().flatten() {
            if let Some(text) = d.control_value(node) {
                value["value"] = json!(text);
            }
            if let Some(checked) = control.checkedness {
                value["checked"] = json!(checked);
            }
        }
        let data = &event.init.data;
        macro_rules! field {
            ($name:literal,$field:ident) => {
                if let Some(v) = &data.$field {
                    value[$name] = json!(v);
                }
            };
        }
        field!("key", key);
        field!("code", code);
        field!("data", data);
        field!("button", button);
        field!("x", client_x);
        field!("y", client_y);
        field!("delta_x", delta_x);
        field!("delta_y", delta_y);
        field!("repeat", repeat);
        field!("input_type", input_type);
        field!("is_composing", is_composing);
        let m = event.init.modifiers;
        value["shift"] = json!(m.shift);
        value["ctrl"] = json!(m.ctrl);
        value["alt"] = json!(m.alt);
        value["meta"] = json!(m.meta);
        let needed = if inv.event_type == "input" { 2 } else { 1 };
        if self.events.len() + needed > MAX_EVENTS {
            return Err(dispatch::CallbackError::new("Document event queue is full"));
        }
        self.events.push(value.clone());
        // ABI 0.1 called every user edit `change`. Retain it while exposing the
        // canonical `input` and one blur/Enter `commit` event for new callers.
        if inv.event_type == "input" {
            value["type"] = json!("change");
            self.events.push(value);
        }
        Ok(())
    }
    fn record_error(&mut self, _id: DocumentId, status: Status) -> Status {
        if self.errors.len() == 64 {
            self.errors.pop_front();
        }
        self.errors
            .push_back(json!({"code":status.code.name(),"message":status.message.clone()}));
        status
    }
    fn hit_test(
        &mut self,
        _id: DocumentId,
        x: f64,
        y: f64,
    ) -> std::result::Result<Option<NodeId>, Status> {
        let read = self.pipeline.flush()?;
        let hit = read.committed.scene.hit_test(
            ViewportPoint { x, y },
            HitOptions {
                all: true,
                include_scrollbars: false,
            },
        );
        Ok(hit
            .hits
            .iter()
            .map(|h| h.element)
            .find(|&n| !self.pipeline.document().is_inert(n)))
    }
    fn scrollbar_hit(
        &mut self,
        _id: DocumentId,
        x: f64,
        y: f64,
    ) -> std::result::Result<Option<crate::interaction::scroll::ScrollbarHit>, Status> {
        let read = self.pipeline.flush()?;
        let Some(hit) = read.committed.scene.scrollbar_hit(ViewportPoint { x, y }) else {
            return Ok(None);
        };
        let d = self.pipeline.document();
        if d.is_inert(hit.container) {
            return Ok(None);
        }
        Ok(Some(crate::interaction::scroll::ScrollbarHit {
            node: hit.container,
            viewport: d.document_element() == Some(hit.container),
            vertical: hit.axis == ScrollAxis::Vertical,
            local: hit.local,
            track_length: hit.track_length,
            thumb_start: hit.thumb_start,
            thumb_length: hit.thumb_length,
        }))
    }
    fn scrollbar_local(
        &mut self,
        _id: DocumentId,
        node: NodeId,
        vertical: bool,
        x: f64,
        y: f64,
    ) -> std::result::Result<Option<f64>, Status> {
        let read = self.pipeline.flush()?;
        let axis = if vertical {
            ScrollAxis::Vertical
        } else {
            ScrollAxis::Horizontal
        };
        Ok(read
            .committed
            .scene
            .scrollbar_local(node, axis, ViewportPoint { x, y }))
    }
    fn now_ms(&mut self) -> f64 {
        self.started.elapsed().as_secs_f64() * 1000.0
    }
    fn run_deferred_closes(&mut self) {}
    fn outermost_commit(&mut self, _id: DocumentId) {
        self.pipeline.outermost_commit();
    }
    fn release_callbacks(&mut self, _released: &[Released]) {}
    fn request_frame(&mut self, _id: DocumentId) {
        self.repaint = true;
    }
    fn computed_cursor(
        &mut self,
        _id: DocumentId,
        node: NodeId,
    ) -> std::result::Result<String, Status> {
        self.pipeline.flush()?;
        self.pipeline
            .style_bridge()
            .computed_value(self.pipeline.document(), node, "cursor")
    }
    fn set_cursor(&mut self, _id: DocumentId, keyword: &str) {
        self.cursor = keyword.to_owned();
    }
    fn focus_target_visible(
        &mut self,
        _id: DocumentId,
        node: NodeId,
    ) -> std::result::Result<bool, Status> {
        let read = self.pipeline.flush()?;
        let Some(style) = read.committed.style.view(node) else {
            return Ok(false);
        };
        let flow = style.display_flow();
        Ok(!flow.display.is_none()
            && flow.visibility == crate::style::view::groups::Visibility::Visible
            && read
                .committed
                .layout
                .fragments
                .element_border_box(node)
                .is_some())
    }
    fn control_geometry(
        &mut self,
        _id: DocumentId,
        node: NodeId,
    ) -> std::result::Result<Option<crate::interaction::editing::EditGeometry>, Status> {
        let read = self.pipeline.flush()?;
        let tree = &read.committed.layout.fragments;
        let Some((frag, bf)) = tree.box_fragment(node) else {
            return Ok(None);
        };
        let Some(inner) = bf.extras.control_inner.clone() else {
            return Ok(None);
        };
        let origin = tree.document_rect(frag.id).rect.origin;
        let (mut sx, mut sy) = (0.0, 0.0);
        for e in self.pipeline.scroll_chain(node) {
            if e.target != ScrollTarget::Node(node) {
                sx += e.offset.0;
                sy += e.offset.1;
            }
        }
        let scroll = self
            .pipeline
            .scroll_offsets()
            .offset(ScrollTarget::Node(node));
        Ok(Some(crate::interaction::editing::EditGeometry {
            origin: (
                origin.x.to_f64() + inner.viewport.origin.x.to_f64() - sx,
                origin.y.to_f64() + inner.viewport.origin.y.to_f64() - sy,
            ),
            inner: *inner,
            scroll,
        }))
    }
    fn element_content_rect(
        &mut self,
        _id: DocumentId,
        node: NodeId,
    ) -> std::result::Result<Option<(f64, f64, f64, f64)>, Status> {
        let read = self.pipeline.flush()?;
        let tree = &read.committed.layout.fragments;
        let Some((frag, bf)) = tree.box_fragment(node) else {
            return Ok(None);
        };
        let rect = tree.document_rect(frag.id).rect;
        let (mut sx, mut sy) = (0.0, 0.0);
        for e in self.pipeline.scroll_chain(node) {
            if e.target != ScrollTarget::Node(node) {
                sx += e.offset.0;
                sy += e.offset.1;
            }
        }
        let c = bf.content_rect;
        Ok(Some((
            rect.origin.x.to_f64() + c.origin.x.to_f64() - sx,
            rect.origin.y.to_f64() + c.origin.y.to_f64() - sy,
            c.size.width.to_f64(),
            c.size.height.to_f64(),
        )))
    }
    fn set_caret_state(&mut self, _id: DocumentId, node: NodeId, visible: bool, upstream: bool) {
        let visible = visible && self.window_focused;
        if self
            .pipeline
            .set_caret_state(visible, upstream, node)
            .is_ok()
        {
            self.repaint = true;
        }
        if let Some(b) = self.blink.as_mut().filter(|b| b.node == node) {
            b.visible = visible;
            b.upstream = upstream;
            if visible {
                b.deadline = Instant::now() + BLINK;
            }
        }
    }
    fn caret_blink(&mut self, _id: DocumentId, node: Option<NodeId>) {
        self.blink = node.map(|node| CaretBlink {
            node,
            deadline: Instant::now() + BLINK,
            visible: self.window_focused,
            upstream: false,
        });
    }
    fn clipboard_read(&mut self) -> std::result::Result<ClipboardData, Status> {
        let plain = self.clipboard.read_text().map_err(|message| {
            Status::new(Code::ResourceDenied, Stage::Platform).with_message(message)
        })?;
        let data = ClipboardData { plain, html: None };
        data.check_size()?;
        Ok(data)
    }
    fn clipboard_write(&mut self, data: &ClipboardData) -> std::result::Result<(), Status> {
        data.check_size()?;
        self.clipboard
            .write_text(data.plain.as_deref().unwrap_or(""))
            .map_err(|message| {
                Status::new(Code::ResourceDenied, Stage::Platform).with_message(message)
            })
    }
    fn ime_update(
        &mut self,
        _id: DocumentId,
        request: Option<ui4me_engine_types::ime::ImeRequest>,
    ) {
        self.ime = request.map(|r| ImeState {
            password: r.purpose == ui4me_engine_types::ime::ImePurposeKind::Password,
            cursor_area: r.cursor_area,
        });
    }
    fn ime_reset(&mut self, _id: DocumentId) {
        self.ime = None;
    }
    fn scroll_chain(
        &mut self,
        _id: DocumentId,
        from: NodeId,
    ) -> std::result::Result<Vec<ScrollTargetInfo>, Status> {
        self.pipeline.flush()?;
        Ok(self
            .pipeline
            .scroll_chain(from)
            .iter()
            .map(scroll_info)
            .collect())
    }
    fn scroll_info(
        &mut self,
        _id: DocumentId,
        target: Option<NodeId>,
    ) -> std::result::Result<Option<ScrollTargetInfo>, Status> {
        self.pipeline.flush()?;
        Ok(self
            .pipeline
            .scroll_entry(scroll_target(target))
            .as_ref()
            .map(scroll_info))
    }
    fn scroll_set(
        &mut self,
        _id: DocumentId,
        target: Option<NodeId>,
        x: f64,
        y: f64,
    ) -> std::result::Result<ScrollApplied, Status> {
        self.pipeline.flush()?;
        match self.pipeline.scroll_to(scroll_target(target), x, y) {
            Ok(a) => {
                self.repaint |= a.changed;
                Ok(ScrollApplied {
                    offset: a.offset,
                    changed: a.changed,
                    clamped: a.clamped,
                })
            }
            Err(ScrollError::NotScrollContainer) => Ok(ScrollApplied {
                offset: (0.0, 0.0),
                changed: false,
                clamped: false,
            }),
            Err(ScrollError::NonFinite) => Err(invalid("Non-finite scroll offset")),
        }
    }
}
impl Drop for Document {
    fn drop(&mut self) {
        let id = self.id();
        self.interaction.detach_document(id);
        let mut r = lock(&self.resources);
        r.set_wake(None);
        r.close_document(id);
        r.release_document(id);
        r.shutdown();
    }
}
fn finite_point(x: f64, y: f64) -> Result<()> {
    if x.is_finite() && y.is_finite() {
        Ok(())
    } else {
        Err(arg("Input coordinates must be finite"))
    }
}
fn check_text(text: &str) -> Result<()> {
    if text.len() > MAX_TEXT {
        Err(Error {
            code: 5,
            message: "Text exceeds 16 KiB".into(),
        })
    } else if text.contains('\0') {
        Err(arg("NUL is unsupported"))
    } else {
        Ok(())
    }
}
fn check_html(html: &str) -> Result<()> {
    if html.len() > MAX_HTML {
        Err(Error {
            code: 5,
            message: "HTML exceeds 1 MiB".into(),
        })
    } else if html.contains('\0') {
        Err(arg("NUL in HTML"))
    } else {
        Ok(())
    }
}
fn validate_id(id: &str) -> Result<()> {
    if id.len() > 256 || id.chars().any(char::is_whitespace) {
        Err(arg("Invalid public element ID"))
    } else {
        Ok(())
    }
}
fn validate_input_type(kind: InputType) -> std::result::Result<(), Status> {
    if matches!(
        kind,
        InputType::File
            | InputType::Color
            | InputType::Date
            | InputType::Time
            | InputType::Month
            | InputType::Week
            | InputType::DateTimeLocal
    ) {
        return Err(invalid(format!(
            "Input type '{}' requires a native picker and is unavailable in UI4ME 0.2",
            kind.as_str()
        )));
    }
    Ok(())
}
/// Validate the proposed connected tree before any fragment hooks or revision.
fn validate_document(
    d: &Model,
    replacing: Option<NodeId>,
    fragment: Option<NodeId>,
) -> std::result::Result<(), Status> {
    let mut ids = BTreeSet::new();
    let mut count = 0;
    let mut replacement_depth = 0;
    let mut stack = vec![(d.document_node(), 0usize)];
    let mut phase = 0;
    loop {
        while let Some((n, depth)) = stack.pop() {
            count += 1;
            if count > MAX_NODES || depth > MAX_DEPTH {
                return Err(limit("Document node/depth limit exceeded"));
            }
            if let Ok(tag) = d.local_name(n) {
                if matches!(tag, "script" | "iframe" | "object" | "embed") {
                    return Err(invalid(format!("Unsupported active element: {tag}")));
                }
                if let Some(kind) = d.input_type(n) {
                    validate_input_type(kind)?;
                }
                for attr in d.attributes(n)? {
                    let name: &str = &attr.name.local;
                    if name.starts_with("on") || name == "srcdoc" {
                        return Err(invalid("Script-bearing attributes are unsupported"));
                    }
                }
                if let Some(id) = d.get_attribute(n, "id")?.filter(|id| !id.is_empty()) {
                    validate_id(id).map_err(|e| invalid(e.message))?;
                    if !ids.insert(id.to_owned()) {
                        return Err(invalid(format!("Duplicate element ID: {id}")));
                    }
                }
            }
            if phase == 0 && Some(n) == replacing {
                replacement_depth = depth + 1;
                continue;
            }
            for &child in d.children(n)? {
                stack.push((child, depth + 1));
            }
            if let Some(contents) = d.template_contents(n).ok().flatten() {
                stack.push((contents, depth + 1));
            }
        }
        if phase == 0 {
            phase = 1;
            if let Some(f) = fragment {
                stack.push((f, replacement_depth));
                continue;
            }
        }
        break;
    }
    Ok(())
}
fn scroll_target(n: Option<NodeId>) -> ScrollTarget {
    n.map_or(ScrollTarget::Viewport, ScrollTarget::Node)
}
fn scroll_info(e: &crate::pipeline::scroll::ScrollEntry) -> ScrollTargetInfo {
    ScrollTargetInfo {
        target: match e.target {
            ScrollTarget::Viewport => None,
            ScrollTarget::Node(n) => Some(n),
        },
        offset: e.offset,
        min: e.range.min,
        max: e.range.max,
        scrollport: e.scrollport,
        user_x: e.user_x,
        user_y: e.user_y,
    }
}

#[cfg(test)]
mod tests;
