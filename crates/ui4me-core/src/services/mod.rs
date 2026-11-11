//! Native desktop services (Core 0.7): system notifications, the tray/status icon, window and
//! context menus, global shortcuts and the OS colour/contrast preference.
//!
//! One language-neutral contract (typed wire commands, events and capability statuses) sits over
//! optional platform adapters (`linux.rs`: D-Bus notifications, StatusNotifierItem + DBusMenu,
//! the xdg-desktop-portal GlobalShortcuts and Settings interfaces; `windows.rs`: Shell tray icon
//! and balloon notifications, Win32 menus, `RegisterHotKey`, the high-contrast setting). An
//! adapter runs on the owner thread (its own worker threads only post events back); events reach
//! the session through a [`Sink`], which queues them and wakes the loop. A service the platform
//! or session cannot offer answers `unsupported`/`unavailable`/`denied` with a reason; it is
//! never simulated.

use serde::Deserialize;
use serde_json::{json, Value};
use std::cell::RefCell;
use std::path::PathBuf;
use std::sync::Arc;

#[cfg(all(feature = "native", target_os = "linux"))]
mod linux;
#[cfg(all(feature = "native", target_os = "windows"))]
mod windows;

/// Delivers a service event (a JSON object with `type`) to the session from any thread.
pub type Sink = Arc<dyn Fn(Value) + Send + Sync>;

/// The outcome of a service request: `Ok(detail)` or a status with its reason.
#[derive(Clone, Debug, PartialEq)]
#[allow(dead_code)] // every variant is produced by some platform adapter
pub enum Refusal {
    /// The platform or Core does not offer it.
    Unsupported(String),
    /// A required service is missing now (no D-Bus, no tray host, no notification server).
    Unavailable(String),
    /// The user or a policy refused it.
    Denied(String),
    /// Another holder has it (a global shortcut taken by another application).
    Conflict(String),
}

impl Refusal {
    pub fn status(&self) -> (&'static str, &str) {
        match self {
            Refusal::Unsupported(r) => ("unsupported", r),
            Refusal::Unavailable(r) => ("unavailable", r),
            Refusal::Denied(r) => ("denied", r),
            Refusal::Conflict(r) => ("conflict", r),
        }
    }
    pub fn to_json(&self) -> Value {
        let (status, reason) = self.status();
        json!({"status": status, "reason": reason})
    }
}

// ------------------------------------------------------------------ requests (wire types)

/// One menu entry: a command (`id`), a separator or a submenu (`items`).
#[derive(Clone, Debug, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct MenuItem {
    #[serde(default)]
    pub id: Option<String>,
    #[serde(default)]
    pub label: String,
    #[serde(default = "yes")]
    pub enabled: bool,
    #[serde(default)]
    pub checked: Option<bool>,
    #[serde(default)]
    pub accelerator: Option<String>,
    #[serde(default)]
    pub separator: bool,
    #[serde(default)]
    pub items: Option<Vec<MenuItem>>,
}

fn yes() -> bool {
    true
}

/// A notification button.
#[derive(Clone, Debug, Deserialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct NotificationAction {
    pub id: String,
    pub label: String,
}

/// A validated notification request.
#[derive(Clone, Debug, PartialEq)]
pub struct Notification {
    pub token: u64,
    pub title: String,
    pub body: String,
    pub icon: Option<PathBuf>,
    /// `low`, `normal` or `critical`.
    pub urgency: String,
    pub actions: Vec<NotificationAction>,
}

/// A validated tray request: PNG icon pixels (RGBA, square, ≤ 256 px), tooltip and menu.
#[derive(Clone, Debug, PartialEq)]
pub struct Tray {
    pub icon: Option<(Vec<u8>, u32, u32)>,
    pub tooltip: String,
    pub menu: Vec<MenuItem>,
}

/// Modifier set and key of an accelerator such as `Ctrl+Shift+K`.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct Accelerator {
    pub ctrl: bool,
    pub alt: bool,
    pub shift: bool,
    pub meta: bool,
    /// Canonical key: `A`..`Z`, `0`..`9`, `F1`..`F24`, or a named key (`Space`, `Enter`, `Tab`,
    /// `Escape`, `Backspace`, `Delete`, `Insert`, `Home`, `End`, `PageUp`, `PageDown`, `Up`,
    /// `Down`, `Left`, `Right`, `Plus`, `Minus`, `Comma`, `Period`).
    pub key: String,
}

const NAMED_KEYS: &[&str] = &[
    "Space",
    "Enter",
    "Tab",
    "Escape",
    "Backspace",
    "Delete",
    "Insert",
    "Home",
    "End",
    "PageUp",
    "PageDown",
    "Up",
    "Down",
    "Left",
    "Right",
    "Plus",
    "Minus",
    "Comma",
    "Period",
];

impl Accelerator {
    /// Parse `Ctrl+Shift+K` (modifiers `Ctrl`/`Control`, `Alt`, `Shift`, `Super`/`Meta`/`Win`/`Cmd`).
    pub fn parse(text: &str) -> Result<Self, String> {
        let mut a = Accelerator {
            ctrl: false,
            alt: false,
            shift: false,
            meta: false,
            key: String::new(),
        };
        let parts: Vec<&str> = text.split('+').map(str::trim).collect();
        if parts.is_empty() || parts.len() > 5 || parts.iter().any(|p| p.is_empty()) {
            return Err(format!("invalid accelerator {text:?}"));
        }
        for (i, p) in parts.iter().enumerate() {
            let last = i + 1 == parts.len();
            match p.to_ascii_lowercase().as_str() {
                "ctrl" | "control" if !last => a.ctrl = true,
                "alt" | "option" if !last => a.alt = true,
                "shift" if !last => a.shift = true,
                "super" | "meta" | "win" | "cmd" | "command" if !last => a.meta = true,
                _ if last => {
                    a.key = canonical_key(p)
                        .ok_or_else(|| format!("unknown key {p:?} in accelerator {text:?}"))?
                }
                _ => return Err(format!("unknown modifier {p:?} in accelerator {text:?}")),
            }
        }
        Ok(a)
    }

    /// The display form (`Ctrl+Shift+K`).
    pub fn display(&self) -> String {
        let mut s = String::new();
        for (on, name) in [
            (self.ctrl, "Ctrl"),
            (self.alt, "Alt"),
            (self.shift, "Shift"),
            (self.meta, "Super"),
        ] {
            if on {
                s.push_str(name);
                s.push('+');
            }
        }
        s.push_str(&self.key);
        s
    }

    /// Whether a key event (DOM-style `key`/`code` and modifier states) triggers it. Letters and
    /// digits match the physical key (`KeyK`, `Digit5`) so that layouts and Shift do not change
    /// a shortcut; named and function keys match the logical key.
    pub fn matches(
        &self,
        key: &str,
        code: &str,
        ctrl: bool,
        alt: bool,
        shift: bool,
        meta: bool,
    ) -> bool {
        if (ctrl, alt, shift, meta) != (self.ctrl, self.alt, self.shift, self.meta) {
            return false;
        }
        let k = &self.key;
        if k.len() == 1 {
            let c = k.as_bytes()[0];
            if c.is_ascii_uppercase() {
                return code == format!("Key{k}") || key.eq_ignore_ascii_case(k);
            }
            if c.is_ascii_digit() {
                return code == format!("Digit{k}") || code == format!("Numpad{k}");
            }
        }
        let logical = match k.as_str() {
            "Space" => " ",
            "Escape" => "Escape",
            "Up" => "ArrowUp",
            "Down" => "ArrowDown",
            "Left" => "ArrowLeft",
            "Right" => "ArrowRight",
            "Plus" => "+",
            "Minus" => "-",
            "Comma" => ",",
            "Period" => ".",
            other => other,
        };
        key == logical || (k == "Space" && code == "Space")
    }
}

fn canonical_key(p: &str) -> Option<String> {
    if p.len() == 1 {
        let c = p.chars().next()?.to_ascii_uppercase();
        return (c.is_ascii_alphanumeric()).then(|| c.to_string());
    }
    let lower = p.to_ascii_lowercase();
    if let Some(n) = lower.strip_prefix('f').and_then(|n| n.parse::<u32>().ok()) {
        return (1..=24).contains(&n).then(|| format!("F{n}"));
    }
    let alias = match lower.as_str() {
        "esc" => "escape",
        "return" => "enter",
        "del" => "delete",
        "ins" => "insert",
        "pgup" => "pageup",
        "pgdn" => "pagedown",
        "arrowup" => "up",
        "arrowdown" => "down",
        "arrowleft" => "left",
        "arrowright" => "right",
        other => other,
    };
    NAMED_KEYS
        .iter()
        .find(|n| n.eq_ignore_ascii_case(alias))
        .map(|n| n.to_string())
}

/// Limits of one menu tree.
pub const MAX_MENU_ITEMS: usize = 512;
const MAX_MENU_DEPTH: usize = 4;

/// Validate a menu tree: labels, ids (unique), accelerators (parsed, no collisions), depth and
/// size. Returns the accelerator table `(accelerator, command id)`.
pub fn validate_menu(menu: &[MenuItem]) -> Result<Vec<(Accelerator, String)>, String> {
    fn walk(
        items: &[MenuItem],
        depth: usize,
        count: &mut usize,
        ids: &mut std::collections::BTreeSet<String>,
        accels: &mut Vec<(Accelerator, String)>,
    ) -> Result<(), String> {
        if depth > MAX_MENU_DEPTH {
            return Err(format!("menus nest at most {MAX_MENU_DEPTH} levels"));
        }
        for item in items {
            *count += 1;
            if *count > MAX_MENU_ITEMS {
                return Err(format!("a menu has at most {MAX_MENU_ITEMS} items"));
            }
            if item.separator {
                if item.id.is_some() || item.items.is_some() || item.accelerator.is_some() {
                    return Err("a separator has no id, items or accelerator".into());
                }
                continue;
            }
            if item.label.is_empty() || item.label.len() > 256 || item.label.contains('\0') {
                return Err("a menu label is 1..256 bytes without NUL".into());
            }
            match (&item.id, &item.items) {
                (Some(_), Some(_)) => {
                    return Err(format!(
                        "menu item {:?} has both an id and items",
                        item.label
                    ))
                }
                (None, None) => {
                    return Err(format!("menu item {:?} needs an id or items", item.label))
                }
                (Some(id), None) => {
                    if id.is_empty() || id.len() > 128 || id.contains('\0') {
                        return Err("a menu command id is 1..128 bytes".into());
                    }
                    if !ids.insert(id.clone()) {
                        return Err(format!("duplicate menu command id {id:?}"));
                    }
                    if let Some(a) = &item.accelerator {
                        let a = Accelerator::parse(a)?;
                        if let Some((_, other)) = accels.iter().find(|(x, _)| *x == a) {
                            return Err(format!(
                                "accelerator {} is used by {other:?} and {id:?}",
                                a.display()
                            ));
                        }
                        accels.push((a, id.clone()));
                    }
                }
                (None, Some(sub)) => {
                    if item.accelerator.is_some() {
                        return Err("a submenu has no accelerator".into());
                    }
                    walk(sub, depth + 1, count, ids, accels)?;
                }
            }
        }
        Ok(())
    }
    let mut accels = Vec::new();
    walk(menu, 1, &mut 0, &mut Default::default(), &mut accels)?;
    Ok(accels)
}

/// Validate a notification request.
pub fn validate_notification(
    token: u64,
    title: String,
    body: String,
    icon: Option<PathBuf>,
    urgency: Option<String>,
    actions: Vec<NotificationAction>,
) -> Result<Notification, String> {
    if title.is_empty() || title.len() > 512 || title.contains('\0') {
        return Err("title is 1..512 bytes without NUL".into());
    }
    if body.len() > 4096 || body.contains('\0') {
        return Err("body is at most 4096 bytes without NUL".into());
    }
    if icon.as_ref().is_some_and(|p| !p.is_absolute()) {
        return Err("icon must be an absolute path".into());
    }
    let urgency = urgency.unwrap_or_else(|| "normal".into());
    if !matches!(urgency.as_str(), "low" | "normal" | "critical") {
        return Err("urgency is low, normal or critical".into());
    }
    if actions.len() > 3
        || actions.iter().any(|a| {
            a.id.is_empty()
                || a.id.len() > 64
                || a.label.is_empty()
                || a.label.len() > 64
                || a.id == "default"
        })
    {
        return Err(
            "at most 3 actions with 1..64-byte ids and labels (id \"default\" is reserved)".into(),
        );
    }
    Ok(Notification {
        token,
        title,
        body,
        icon,
        urgency,
        actions,
    })
}

// ------------------------------------------------------------------ the adapter interface

/// What a platform adapter offers. Every method runs on the owner thread. Requests return at
/// once; outcomes that arrive later (a notification click, a menu command, a shortcut press, a
/// preference change) are sent through the adapter's [`Sink`] as events:
/// `{"type":"notification","token","event":"clicked"|"action"|"dismissed"|"failed", "action"?, "reason"?}`,
/// `{"type":"tray","event":"activate"|"context"}`,
/// `{"type":"menu_command","source":"window"|"context"|"tray"|"accelerator","window"?,"command"}`,
/// `{"type":"hotkey","id"}`, `{"type":"system_preferences","dark"?,"high_contrast"?}`.
pub trait PlatformServices {
    /// Feature statuses this adapter reports (`notifications`, `system_tray`, `native_menus`,
    /// `native_menus.context`, `global_hotkeys`, `environment.theme_changes`, `environment.contrast`).
    fn capabilities(&mut self) -> Vec<(&'static str, Value)>;
    /// Show a notification; its outcome follows as `notification` events.
    fn notify(&mut self, n: &Notification) -> Result<(), Refusal>;
    fn close_notification(&mut self, token: u64);
    /// Create, update (`Some`) or remove (`None`) the application's tray icon.
    fn set_tray(&mut self, tray: Option<&Tray>) -> Result<(), Refusal>;
    /// Set or clear the menu bar of a native window (`handle` is its raw window handle).
    fn set_window_menu(
        &mut self,
        window: u64,
        handle: Option<winit_handle::Raw>,
        menu: Option<&[MenuItem]>,
    ) -> Result<(), Refusal>;
    /// Show a context menu at window-relative physical pixels; the chosen command follows as a
    /// `menu_command` event (nothing when it is dismissed).
    fn show_context_menu(
        &mut self,
        window: u64,
        handle: Option<winit_handle::Raw>,
        x: f64,
        y: f64,
        menu: &[MenuItem],
    ) -> Result<(), Refusal>;
    /// Register a global shortcut; presses follow as `hotkey` events.
    fn register_hotkey(&mut self, id: &str, accelerator: &Accelerator) -> Result<(), Refusal>;
    fn unregister_hotkey(&mut self, id: &str);
    /// The OS preferences now: `(dark, high_contrast)`; `None` when the platform does not say.
    fn system_preferences(&mut self) -> (Option<bool>, Option<bool>);
    /// Release everything (tray icon, shortcuts, notifications); called when the session stops.
    fn shutdown(&mut self);
}

/// A raw native window handle, opaque to this module.
pub mod winit_handle {
    #[cfg(feature = "native")]
    pub type Raw = winit::raw_window_handle::RawWindowHandle;
    #[cfg(not(feature = "native"))]
    pub type Raw = ();
}

/// The adapter used when the platform has none: every service is unsupported, with the reason.
pub struct Unsupported(pub &'static str);

impl PlatformServices for Unsupported {
    fn capabilities(&mut self) -> Vec<(&'static str, Value)> {
        [
            "notifications",
            "system_tray",
            "native_menus",
            "native_menus.context",
            "global_hotkeys",
        ]
        .into_iter()
        .map(|f| (f, json!({"status":"unsupported","reason":self.0})))
        .collect()
    }
    fn notify(&mut self, _: &Notification) -> Result<(), Refusal> {
        Err(Refusal::Unsupported(self.0.into()))
    }
    fn close_notification(&mut self, _: u64) {}
    fn set_tray(&mut self, tray: Option<&Tray>) -> Result<(), Refusal> {
        match tray {
            None => Ok(()),
            Some(_) => Err(Refusal::Unsupported(self.0.into())),
        }
    }
    fn set_window_menu(
        &mut self,
        _: u64,
        _: Option<winit_handle::Raw>,
        menu: Option<&[MenuItem]>,
    ) -> Result<(), Refusal> {
        match menu {
            None => Ok(()),
            Some(_) => Err(Refusal::Unsupported(self.0.into())),
        }
    }
    fn show_context_menu(
        &mut self,
        _: u64,
        _: Option<winit_handle::Raw>,
        _: f64,
        _: f64,
        _: &[MenuItem],
    ) -> Result<(), Refusal> {
        Err(Refusal::Unsupported(self.0.into()))
    }
    fn register_hotkey(&mut self, _: &str, _: &Accelerator) -> Result<(), Refusal> {
        Err(Refusal::Unsupported(self.0.into()))
    }
    fn unregister_hotkey(&mut self, _: &str) {}
    fn system_preferences(&mut self) -> (Option<bool>, Option<bool>) {
        (None, None)
    }
    fn shutdown(&mut self) {}
}

thread_local! {
    /// The owner thread's adapter, created on first use.
    static SERVICES: RefCell<Option<Box<dyn PlatformServices>>> = const { RefCell::new(None) };
}

/// Run `f` with the owner thread's adapter (created on first use with `sink`).
pub fn with<R>(sink: &Sink, f: impl FnOnce(&mut dyn PlatformServices) -> R) -> R {
    SERVICES.with(|cell| {
        let mut slot = cell.borrow_mut();
        let services = slot.get_or_insert_with(|| create(sink.clone()));
        f(services.as_mut())
    })
}

/// Shut the adapter down (session stop) and forget it; the next session creates a new one.
pub fn shutdown() {
    SERVICES.with(|cell| {
        if let Some(mut s) = cell.borrow_mut().take() {
            s.shutdown();
        }
    });
}

#[allow(unused_variables)]
fn create(sink: Sink) -> Box<dyn PlatformServices> {
    #[cfg(all(feature = "native", target_os = "linux"))]
    {
        return Box::new(linux::LinuxServices::new(sink));
    }
    #[cfg(all(feature = "native", target_os = "windows"))]
    {
        return Box::new(windows::WindowsServices::new(sink));
    }
    #[allow(unreachable_code)]
    Box::new(Unsupported("no native desktop services on this platform"))
}

/// Windows: the adapter's hook for messages of app windows (menu `WM_COMMAND`); returns whether
/// the message was handled. Installed by the native event loop.
#[cfg(all(feature = "native", target_os = "windows"))]
pub fn windows_msg_hook(msg: *const std::ffi::c_void) -> bool {
    windows::msg_hook(msg)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accelerators_parse_display_and_match() {
        let a = Accelerator::parse("ctrl+Shift+k").unwrap();
        assert_eq!(a.display(), "Ctrl+Shift+K");
        assert!(a.matches("K", "KeyK", true, false, true, false));
        assert!(
            a.matches("ť", "KeyK", true, false, true, false),
            "physical letter key"
        );
        assert!(!a.matches("K", "KeyK", true, false, false, false));
        assert_eq!(Accelerator::parse("Alt+F4").unwrap().key, "F4");
        assert!(Accelerator::parse("Ctrl+Esc")
            .unwrap()
            .matches("Escape", "Escape", true, false, false, false));
        assert!(Accelerator::parse("Ctrl+").is_err());
        assert!(Accelerator::parse("Hyper+K").is_err());
        assert!(Accelerator::parse("Ctrl+F25").is_err());
        assert!(Accelerator::parse("Ctrl+Shift").is_err());
    }

    #[test]
    fn menus_validate_ids_accelerators_and_shape() {
        let m: Vec<MenuItem> = serde_json::from_value(json!([
            {"label":"File","items":[{"id":"open","label":"Open…","accelerator":"Ctrl+O"},{"separator":true},{"id":"quit","label":"Quit","accelerator":"Ctrl+Q"}]},
            {"label":"View","items":[{"id":"dark","label":"Dark","checked":true}]}
        ]))
        .unwrap();
        let accels = validate_menu(&m).unwrap();
        assert_eq!(accels.len(), 2);
        let dup: Vec<MenuItem> = serde_json::from_value(json!([{"id":"a","label":"A","accelerator":"Ctrl+O"},{"id":"b","label":"B","accelerator":"ctrl+o"}])).unwrap();
        assert!(validate_menu(&dup).unwrap_err().contains("used by"));
        let ids: Vec<MenuItem> =
            serde_json::from_value(json!([{"id":"a","label":"A"},{"id":"a","label":"B"}])).unwrap();
        assert!(validate_menu(&ids).unwrap_err().contains("duplicate"));
        let both: Vec<MenuItem> =
            serde_json::from_value(json!([{"id":"a","label":"A","items":[]}])).unwrap();
        assert!(validate_menu(&both).is_err());
    }

    #[test]
    fn notifications_validate() {
        assert!(validate_notification(1, "T".into(), "".into(), None, None, vec![]).is_ok());
        assert!(validate_notification(1, "".into(), "".into(), None, None, vec![]).is_err());
        assert!(validate_notification(
            1,
            "T".into(),
            "".into(),
            Some("rel.png".into()),
            None,
            vec![]
        )
        .is_err());
        assert!(
            validate_notification(1, "T".into(), "".into(), None, Some("loud".into()), vec![])
                .is_err()
        );
    }
}
