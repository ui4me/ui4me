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
fn yes() -> bool {
    true
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
    },
    ScrollBy {
        window: u64,
        #[serde(default)]
        element: Option<String>,
        #[serde(default)]
        dx: f64,
        #[serde(default)]
        dy: f64,
    },
    ScrollIntoView {
        window: u64,
        element: String,
        #[serde(default = "nearest")]
        block: String,
        #[serde(default = "nearest")]
        inline: String,
    },
    GetRect {
        window: u64,
        element: String,
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
    GetOptions {
        window: u64,
        element: String,
    },
    SetSelectedValues {
        window: u64,
        element: String,
        values: Vec<String>,
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
    Stats,
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
