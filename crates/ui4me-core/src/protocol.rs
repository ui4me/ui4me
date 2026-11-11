//! The JSON wire format ends here. Internal dispatch uses typed, validated commands.
use crate::{Error, Result};
use serde::Deserialize;
use serde_json::Value;
use std::path::PathBuf;

#[derive(Clone, Copy, Debug, Default, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Backend {
    #[default]
    Native,
    Headless,
}

#[derive(Debug, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Config {
    pub backend: Backend,
    pub app_id: String,
    pub allow_any_thread: bool,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            backend: Backend::Native,
            app_id: "org.ui4me.app".into(),
            allow_any_thread: false,
        }
    }
}
impl Config {
    pub fn parse(value: Value) -> Result<Self> {
        let config: Self = serde_json::from_value(value).map_err(invalid)?;
        if config.app_id.is_empty()
            || config.app_id.len() > 128
            || !config
                .app_id
                .chars()
                .all(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '-' | '_'))
        {
            return Err(Error::arg(
                "app_id must be 1..128 ASCII letters, digits, dot, hyphen or underscore",
            ));
        }
        Ok(config)
    }
}

fn title() -> String {
    "ui4me".into()
}
fn width() -> u32 {
    640
}
fn start() -> String {
    "start".into()
}
/// `trim_children` direction: `start` removes the oldest children, `end` the newest.
pub fn trim_from_start(from: &str) -> Result<bool> {
    match from {
        "start" => Ok(true),
        "end" => Ok(false),
        _ => Err(Error::arg("from must be start or end")),
    }
}
fn nearest() -> String {
    "nearest".into()
}
fn dpi_screen() -> f32 {
    96.0
}
fn dpi_export() -> f32 {
    150.0
}
fn dpi_print() -> f32 {
    300.0
}
fn mouse_pointer() -> u32 {
    1
}
fn yes() -> bool {
    true
}
fn children_limit() -> usize {
    256
}
fn query_limit() -> usize {
    1024
}
fn height() -> u32 {
    480
}

#[derive(Debug, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum Command {
    Open {
        html: String,
        #[serde(default = "title")]
        title: String,
        #[serde(default = "width")]
        width: u32,
        #[serde(default = "height")]
        height: u32,
        #[serde(default)]
        base_path: Option<PathBuf>,
    },
    OpenFile {
        path: PathBuf,
        #[serde(default = "title")]
        title: String,
        #[serde(default = "width")]
        width: u32,
        #[serde(default = "height")]
        height: u32,
    },
    SetText {
        window: u64,
        element: String,
        text: String,
    },
    GetValue {
        window: u64,
        element: String,
    },
    SetValue {
        window: u64,
        element: String,
        value: String,
    },
    GetChecked {
        window: u64,
        element: String,
    },
    SetChecked {
        window: u64,
        element: String,
        checked: bool,
    },
    SetAttribute {
        window: u64,
        element: String,
        name: String,
        value: String,
    },
    RemoveAttribute {
        window: u64,
        element: String,
        name: String,
    },
    AddClass {
        window: u64,
        element: String,
        name: String,
    },
    RemoveClass {
        window: u64,
        element: String,
        name: String,
    },
    Focus {
        window: u64,
        element: String,
    },
    ReplaceChildrenHtml {
        window: u64,
        element: String,
        html: String,
    },
    InsertHtml {
        window: u64,
        element: String,
        position: String,
        html: String,
    },
    RemoveElement {
        window: u64,
        element: String,
    },
    MoveElement {
        window: u64,
        element: String,
        target: String,
        position: String,
    },
    /// HTML serialization (0.6 F0601): `element` or `node`, or the whole document.
    GetHtml {
        window: u64,
        #[serde(default)]
        element: Option<String>,
        #[serde(default)]
        node: Option<String>,
        #[serde(default)]
        outer: bool,
    },
    /// Text geometry (0.6 F0603): UTF-16 offsets over the text content of `element`/`node`.
    TextRects {
        window: u64,
        #[serde(default)]
        element: Option<String>,
        #[serde(default)]
        node: Option<String>,
        #[serde(default)]
        start: Option<u32>,
        #[serde(default)]
        end: Option<u32>,
    },
    TextAtPoint {
        window: u64,
        x: f64,
        y: f64,
    },
    /// Rich clipboard (0.7 F0706).
    SetClipboardHtml {
        window: u64,
        html: String,
        #[serde(default)]
        text: String,
    },
    GetClipboardHtml {
        window: u64,
        #[serde(default)]
        raw: bool,
    },
    /// The files chosen in a file input (0.6 F0606).
    GetFiles {
        window: u64,
        element: String,
    },
    /// Computed style introspection (0.6 F0609).
    GetComputedStyle {
        window: u64,
        #[serde(default)]
        element: Option<String>,
        #[serde(default)]
        node: Option<String>,
        properties: Vec<String>,
    },
    /// Author stylesheets (0.6 F0602).
    AddStylesheet {
        window: u64,
        css: String,
    },
    ReplaceStylesheet {
        window: u64,
        sheet: u64,
        css: String,
    },
    RemoveStylesheet {
        window: u64,
        sheet: u64,
    },
    ListStylesheets {
        window: u64,
    },
    /// Node references and traversal (0.6 F0604).
    NodeOf {
        window: u64,
        #[serde(default)]
        element: Option<String>,
    },
    GetNode {
        window: u64,
        node: String,
    },
    NodeChildren {
        window: u64,
        node: String,
        #[serde(default)]
        offset: usize,
        #[serde(default = "children_limit")]
        limit: usize,
    },
    GetText {
        window: u64,
        element: String,
    },
    GetAttribute {
        window: u64,
        element: String,
        name: String,
    },
    GetAttributes {
        window: u64,
        element: String,
    },
    HasElement {
        window: u64,
        element: String,
    },
    Query {
        window: u64,
        selector: String,
        #[serde(default = "query_limit")]
        limit: usize,
    },
    Batch {
        window: u64,
        ops: Vec<BatchOp>,
    },
    SetDefaultAction {
        window: u64,
        element: String,
        event: String,
        #[serde(default)]
        key: Option<String>,
        #[serde(default)]
        shift: Option<bool>,
        #[serde(default)]
        ctrl: Option<bool>,
        #[serde(default)]
        alt: Option<bool>,
        #[serde(default)]
        meta: Option<bool>,
        #[serde(default = "yes")]
        prevent: bool,
    },
    GetValidity {
        window: u64,
        element: String,
    },
    CheckValidity {
        window: u64,
        element: String,
    },
    GetScroll {
        window: u64,
        #[serde(default)]
        element: Option<String>,
    },
    ScrollTo {
        window: u64,
        #[serde(default)]
        element: Option<String>,
        #[serde(default)]
        x: Option<f64>,
        #[serde(default)]
        y: Option<f64>,
        /// `auto` (the element's `scroll-behavior`), `instant` or `smooth` (0.8 F0803).
        #[serde(default)]
        behavior: Option<String>,
    },
    ScrollBy {
        window: u64,
        #[serde(default)]
        element: Option<String>,
        #[serde(default)]
        dx: f64,
        #[serde(default)]
        dy: f64,
        #[serde(default)]
        behavior: Option<String>,
    },
    ScrollIntoView {
        window: u64,
        element: String,
        #[serde(default = "nearest")]
        block: String,
        #[serde(default = "nearest")]
        inline: String,
        #[serde(default)]
        behavior: Option<String>,
    },
    GetRect {
        window: u64,
        element: String,
    },
    /// App media preferences (0.5 F0506): `light`, `dark` or `system`; `reduce`,
    /// `no-preference` or `system`. Omitted fields stay as they are.
    SetEnvironment {
        window: u64,
        #[serde(default)]
        color_scheme: Option<String>,
        #[serde(default)]
        reduced_motion: Option<String>,
    },
    GetEnvironment {
        window: u64,
    },
    SetScrollFollow {
        window: u64,
        #[serde(default)]
        element: Option<String>,
        #[serde(default = "yes")]
        follow: bool,
    },
    GetSelection {
        window: u64,
    },
    ClearSelection {
        window: u64,
    },
    SelectText {
        window: u64,
        #[serde(default)]
        element: Option<String>,
    },
    CopySelection {
        window: u64,
    },
    GetClipboardText {
        window: u64,
    },
    SetClipboardText {
        window: u64,
        text: String,
    },
    AppendText {
        window: u64,
        element: String,
        text: String,
    },
    TrimChildren {
        window: u64,
        element: String,
        keep: usize,
        #[serde(default = "start")]
        from: String,
    },
    ShowDialog {
        window: u64,
        element: String,
        #[serde(default = "yes")]
        modal: bool,
    },
    CloseDialog {
        window: u64,
        element: String,
        #[serde(default)]
        return_value: Option<String>,
    },
    GetDialog {
        window: u64,
        element: String,
    },
    ShowPopover {
        window: u64,
        element: String,
    },
    HidePopover {
        window: u64,
        element: String,
    },
    TogglePopover {
        window: u64,
        element: String,
    },
    GetPopover {
        window: u64,
        element: String,
    },
    /// Rich-text editing command on a `contenteditable` host (F1003).
    ExecEdit {
        window: u64,
        element: String,
        command: String,
        #[serde(default)]
        value: Option<String>,
    },
    /// The formats at the selection of a `contenteditable` host (F1003).
    GetEditState {
        window: u64,
        element: String,
    },
    /// Pointer capture of the mouse pointer (0.8 F0807); `capture=false` releases.
    SetPointerCapture {
        window: u64,
        element: String,
        #[serde(default = "mouse_pointer")]
        pointer_id: u32,
        #[serde(default = "yes")]
        capture: bool,
    },
    GetPointerCapture {
        window: u64,
    },
    GetOptions {
        window: u64,
        element: String,
    },
    SetSelectedValues {
        window: u64,
        element: String,
        values: Vec<String>,
    },
    WindowAction {
        window: u64,
        action: String,
    },
    SetWindowConstraints {
        window: u64,
        #[serde(default)]
        min_width: Option<u32>,
        #[serde(default)]
        min_height: Option<u32>,
        #[serde(default)]
        max_width: Option<u32>,
        #[serde(default)]
        max_height: Option<u32>,
        #[serde(default = "yes")]
        resizable: bool,
    },
    SetWindowIcon {
        window: u64,
        #[serde(default)]
        path: Option<PathBuf>,
    },
    GetWindowState {
        window: u64,
    },
    ListMonitors,
    /// The platform capability report (0.5 F0508).
    Capabilities,
    /// Single instance and open-with delivery (0.7 F0710).
    ClaimInstance {
        #[serde(default)]
        open_files: Vec<String>,
    },
    /// Native desktop services (0.7).
    Notify {
        token: u64,
        title: String,
        #[serde(default)]
        body: String,
        #[serde(default)]
        icon: Option<PathBuf>,
        #[serde(default)]
        urgency: Option<String>,
        #[serde(default)]
        actions: Vec<crate::services::NotificationAction>,
    },
    CloseNotification {
        token: u64,
    },
    SetTray {
        #[serde(default)]
        icon: Option<PathBuf>,
        #[serde(default)]
        tooltip: String,
        #[serde(default)]
        menu: Vec<crate::services::MenuItem>,
    },
    RemoveTray,
    SetMenu {
        window: u64,
        #[serde(default)]
        menu: Option<Vec<crate::services::MenuItem>>,
    },
    /// Pointer confinement/lock and cursor visibility (0.7 F0709).
    SetPointerGrab {
        window: u64,
        mode: String,
        #[serde(default = "yes")]
        cursor_visible: bool,
    },
    ShowContextMenu {
        window: u64,
        x: f64,
        y: f64,
        menu: Vec<crate::services::MenuItem>,
    },
    RegisterHotkey {
        id: String,
        accelerator: String,
    },
    UnregisterHotkey {
        id: String,
    },
    /// External link policy (0.6 F0608).
    SetLinkPolicy {
        #[serde(default)]
        schemes: Vec<String>,
        #[serde(default)]
        hosts: Option<Vec<String>>,
        #[serde(default)]
        open: bool,
    },
    FileDialog {
        window: u64,
        token: u64,
        kind: String,
        #[serde(default)]
        title: Option<String>,
        #[serde(default)]
        directory: Option<PathBuf>,
        #[serde(default)]
        file_name: Option<String>,
        #[serde(default)]
        filters: Vec<FileFilter>,
    },
    GetAccessibilityTree {
        window: u64,
    },
    Diagnostics {
        window: u64,
    },
    Close {
        window: u64,
    },
    SetTitle {
        window: u64,
        title: String,
    },
    Resize {
        window: u64,
        width: u32,
        height: u32,
    },
    Snapshot {
        window: u64,
        path: PathBuf,
    },
    /// Paged media (1.0 F1001): paginate with a page size (a CSS name or `width`/`height` CSS px;
    /// default the document's `@page`, else A4), margins (CSS px) and print media.
    Paginate {
        window: u64,
        #[serde(default)]
        size: Option<String>,
        #[serde(default)]
        width: Option<f32>,
        #[serde(default)]
        height: Option<f32>,
        #[serde(default)]
        margins: Option<[f32; 4]>,
        #[serde(default = "yes")]
        print: bool,
    },
    GetPageRects {
        window: u64,
        element: String,
    },
    /// Render one page of the current pagination to a PNG file.
    RenderPage {
        window: u64,
        page: usize,
        #[serde(default = "dpi_screen")]
        dpi: f32,
        path: PathBuf,
    },
    /// Paginate and write a PDF (1.0 F1002; pages are images).
    ExportPdf {
        window: u64,
        path: PathBuf,
        #[serde(default)]
        size: Option<String>,
        #[serde(default)]
        width: Option<f32>,
        #[serde(default)]
        height: Option<f32>,
        #[serde(default)]
        margins: Option<[f32; 4]>,
        #[serde(default = "yes")]
        print: bool,
        #[serde(default = "dpi_export")]
        dpi: f32,
        #[serde(default)]
        title: String,
    },
    /// Paginate and print through the native print dialog; the outcome is a `print` event.
    Print {
        window: u64,
        #[serde(default)]
        size: Option<String>,
        #[serde(default)]
        width: Option<f32>,
        #[serde(default)]
        height: Option<f32>,
        #[serde(default)]
        margins: Option<[f32; 4]>,
        #[serde(default = "yes")]
        print: bool,
        #[serde(default = "dpi_print")]
        dpi: f32,
        #[serde(default)]
        title: String,
    },
    Timer {
        token: u64,
        milliseconds: u64,
        #[serde(default)]
        repeat: bool,
    },
    CancelTimer {
        token: u64,
    },
    ReserveCompletion {
        token: u64,
    },
    CancelCompletion {
        token: u64,
    },
    /// Developer diagnostics, schema 1 (0.10 F1008).
    GetDiagnostics {
        window: u64,
        #[serde(default = "yes")]
        redact: bool,
        #[serde(default)]
        since: Option<u64>,
        #[serde(default)]
        kinds: Option<Vec<String>>,
    },
    /// Why a CSS property has no effect on an element (0.10 F1008).
    Explain {
        window: u64,
        element: String,
        #[serde(default)]
        property: Option<String>,
        #[serde(default = "yes")]
        redact: bool,
    },
    Stats,
}
/// A file dialog filter: a label and extensions without dots (`["png", "jpg"]`).
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FileFilter {
    pub name: String,
    pub extensions: Vec<String>,
}

/// One operation of a `batch` command; the same fields as the single command.
#[derive(Debug, Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum BatchOp {
    SetText {
        element: String,
        text: String,
    },
    SetAttribute {
        element: String,
        name: String,
        value: String,
    },
    RemoveAttribute {
        element: String,
        name: String,
    },
    AddClass {
        element: String,
        name: String,
    },
    RemoveClass {
        element: String,
        name: String,
    },
    InsertHtml {
        element: String,
        position: String,
        html: String,
    },
    ReplaceChildrenHtml {
        element: String,
        html: String,
    },
    RemoveElement {
        element: String,
    },
    MoveElement {
        element: String,
        target: String,
        position: String,
    },
    AppendText {
        element: String,
        text: String,
    },
    TrimChildren {
        element: String,
        keep: usize,
        #[serde(default = "start")]
        from: String,
    },
}

impl Command {
    pub fn parse(value: Value) -> Result<Self> {
        serde_json::from_value(value).map_err(invalid)
    }
}
fn invalid(error: serde_json::Error) -> Error {
    Error::arg(format!("invalid protocol request: {error}"))
}

pub fn validate_title(value: &str) -> Result<()> {
    if value.len() > 4096 || value.contains('\0') {
        Err(Error::arg("title is too long or contains NUL"))
    } else {
        Ok(())
    }
}
pub fn validate_size(width: u32, height: u32) -> Result<()> {
    if !(160..=4096).contains(&width) {
        return Err(Error::arg("width must be 160..4096 logical pixels"));
    }
    if !(120..=4096).contains(&height) {
        return Err(Error::arg("height must be 120..4096 logical pixels"));
    }
    Ok(())
}
