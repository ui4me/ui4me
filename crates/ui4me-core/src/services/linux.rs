//! Linux desktop services adapter (Core 0.7), over the D-Bus session bus (zbus):
//!
//! * notifications: `org.freedesktop.Notifications` (`Notify`, `ActionInvoked`, `NotificationClosed`);
//! * tray: a StatusNotifierItem plus a `com.canonical.dbusmenu` menu, registered with the
//!   `org.kde.StatusNotifierWatcher`;
//! * global shortcuts: the xdg-desktop-portal `GlobalShortcuts` interface (request/response);
//! * OS preferences: the portal `Settings` interface (`color-scheme`, `contrast`).
//!
//! Wayland and X11 have no client menu bar protocol, so window and context menus are reported
//! unsupported. The connection is created lazily; one worker thread listens for signals and posts
//! events through the [`Sink`]; everything the owner thread calls is a short, time-limited D-Bus
//! call.

use super::{Accelerator, MenuItem, Notification, PlatformServices, Refusal, Sink, Tray};
use serde_json::{json, Value as Json};
use std::collections::{BTreeMap, HashMap, VecDeque};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{channel, Sender};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use zbus::blocking::{Connection, MessageIterator};
use zbus::interface;
use zbus::zvariant::{Array, Dict, ObjectPath, OwnedValue, StructureBuilder, Value};

const CALL_TIMEOUT: Duration = Duration::from_secs(3);
const BIND_TIMEOUT: Duration = Duration::from_secs(5);
const MAX_NOTIFICATIONS: usize = 64;
const ITEM_PATH: &str = "/StatusNotifierItem";
const MENU_PATH: &str = "/MenuBar";
const NOTIFY_NAME: &str = "org.freedesktop.Notifications";
const NOTIFY_PATH: &str = "/org/freedesktop/Notifications";
const WATCHER_NAME: &str = "org.kde.StatusNotifierWatcher";
const PORTAL_NAME: &str = "org.freedesktop.portal.Desktop";
const PORTAL_PATH: &str = "/org/freedesktop/portal/desktop";
const SHORTCUTS_IFACE: &str = "org.freedesktop.portal.GlobalShortcuts";
const NO_BUS: &str = "no D-Bus session bus";
const NO_SHORTCUTS: &str = "the desktop has no xdg-desktop-portal GlobalShortcuts";
const NO_NOTIFY: &str = "no notification server (org.freedesktop.Notifications)";
const NO_WATCHER: &str = "no StatusNotifierWatcher (system tray host)";
const NO_MENUBAR: &str =
    "Wayland/X11 desktops have no protocol for a client menu bar; render it in the document";

// ------------------------------------------------------------------ pure helpers

/// Notification urgency byte (`low` 0, `normal` 1, `critical` 2).
fn urgency_byte(u: &str) -> u8 {
    match u {
        "low" => 0,
        "critical" => 2,
        _ => 1,
    }
}

/// RGBA pixels to the SNI `ARGB32` (network byte order: A, R, G, B per pixel).
#[allow(clippy::chunks_exact_to_as_chunks)]
fn rgba_to_argb(rgba: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(rgba.len());
    for p in rgba.chunks_exact(4) {
        out.extend_from_slice(&[p[3], p[0], p[1], p[2]]);
    }
    out
}

/// `Ctrl+Shift+K` to the portal's trigger syntax (`CTRL+SHIFT+k`, xkb key names).
fn portal_trigger(a: &Accelerator) -> String {
    let mut s = String::new();
    for (on, name) in [
        (a.ctrl, "CTRL"),
        (a.alt, "ALT"),
        (a.shift, "SHIFT"),
        (a.meta, "LOGO"),
    ] {
        if on {
            s.push_str(name);
            s.push('+');
        }
    }
    let key = match a.key.as_str() {
        "Space" => "space".to_string(),
        "Enter" => "Return".into(),
        "Backspace" => "BackSpace".into(),
        "PageUp" => "Page_Up".into(),
        "PageDown" => "Page_Down".into(),
        "Plus" => "plus".into(),
        "Minus" => "minus".into(),
        "Comma" => "comma".into(),
        "Period" => "period".into(),
        k if k.len() == 1 => k.to_ascii_lowercase(),
        k => k.to_string(),
    };
    s.push_str(&key);
    s
}

/// The `color-scheme` portal value to `dark` (`None` = no preference).
fn scheme_dark(v: u32) -> Option<bool> {
    match v {
        1 => Some(true),
        2 => Some(false),
        _ => None,
    }
}

fn cap(status: &str, reason: &str) -> Json {
    if reason.is_empty() {
        json!({"status": status})
    } else {
        json!({"status": status, "reason": reason})
    }
}

/// A `dbusmenu` property value.
#[derive(Clone, Debug, PartialEq)]
enum Prop {
    Str(String),
    Bool(bool),
    Int(i32),
}

impl Prop {
    fn value(&self) -> Value<'static> {
        match self {
            Prop::Str(s) => Value::from(s.clone()),
            Prop::Bool(b) => Value::from(*b),
            Prop::Int(i) => Value::from(*i),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Default)]
struct MenuNode {
    props: BTreeMap<String, Prop>,
    children: Vec<i32>,
    command: Option<String>,
}

/// Flatten a menu tree into dbusmenu nodes; the node index is its id (the root is 0).
fn build_menu(items: &[MenuItem]) -> Vec<MenuNode> {
    fn add(nodes: &mut Vec<MenuNode>, parent: usize, items: &[MenuItem]) {
        for item in items {
            let id = nodes.len();
            let mut node = MenuNode::default();
            if item.separator {
                node.props
                    .insert("type".into(), Prop::Str("separator".into()));
            } else {
                // `_` marks a mnemonic in dbusmenu labels; a literal one is doubled.
                node.props
                    .insert("label".into(), Prop::Str(item.label.replace('_', "__")));
                node.props
                    .insert("enabled".into(), Prop::Bool(item.enabled));
                if let Some(c) = item.checked {
                    node.props
                        .insert("toggle-type".into(), Prop::Str("checkmark".into()));
                    node.props
                        .insert("toggle-state".into(), Prop::Int(i32::from(c)));
                }
                if item.items.is_some() {
                    node.props
                        .insert("children-display".into(), Prop::Str("submenu".into()));
                }
                node.command = item.id.clone();
            }
            nodes.push(node);
            nodes[parent].children.push(id as i32);
            if let Some(sub) = &item.items {
                add(nodes, id, sub);
            }
        }
    }
    let mut root = MenuNode::default();
    root.props
        .insert("children-display".into(), Prop::Str("submenu".into()));
    let mut nodes = vec![root];
    add(&mut nodes, 0, items);
    nodes
}

type Props = HashMap<String, Value<'static>>;

fn node_props(n: &MenuNode, names: &[String]) -> Props {
    n.props
        .iter()
        .filter(|(k, _)| names.is_empty() || names.contains(k))
        .map(|(k, v)| (k.clone(), v.value()))
        .collect()
}

/// `(id, properties, children)` of a node, `depth` levels deep (-1 = all).
fn node_parts(
    nodes: &[MenuNode],
    id: i32,
    depth: i32,
    names: &[String],
) -> (i32, Props, Vec<Value<'static>>) {
    let Some(n) = usize::try_from(id).ok().and_then(|i| nodes.get(i)) else {
        return (id, Props::new(), Vec::new());
    };
    let children = if depth == 0 {
        Vec::new()
    } else {
        n.children
            .iter()
            .map(|&c| {
                let (cid, props, kids) = node_parts(nodes, c, depth - 1, names);
                Value::Structure(
                    StructureBuilder::new()
                        .add_field(cid)
                        .append_field(Value::Dict(Dict::from(props)))
                        .append_field(Value::Array(Array::from(kids)))
                        .build()
                        .expect("static structure"),
                )
            })
            .collect()
    };
    (id, node_props(n, names), children)
}

/// An unsigned integer inside any number of variants.
fn value_u32(v: &Value<'_>) -> Option<u32> {
    match v {
        Value::U32(n) => Some(*n),
        Value::Value(inner) => value_u32(inner),
        _ => None,
    }
}

fn value_str(v: &Value<'_>) -> Option<String> {
    match v {
        Value::Str(s) => Some(s.to_string()),
        Value::ObjectPath(p) => Some(p.to_string()),
        Value::Value(inner) => value_str(inner),
        _ => None,
    }
}

/// Whether the `shortcuts` result (`a(sa{sv})`) lists `id` with a non-empty trigger description.
fn shortcut_assigned(v: &Value<'_>, id: &str) -> bool {
    match v {
        Value::Value(inner) => shortcut_assigned(inner, id),
        Value::Array(arr) => arr.iter().any(|item| {
            let mut item = item;
            while let Value::Value(inner) = item {
                item = inner;
            }
            let Value::Structure(s) = item else {
                return false;
            };
            let f = s.fields();
            if f.first().and_then(value_str).as_deref() != Some(id) {
                return false;
            }
            match f.get(1) {
                Some(Value::Dict(d)) => !matches!(
                    d.get::<String, Value<'_>>(&"trigger_description".to_string()),
                    Ok(Some(t)) if value_str(&t).is_some_and(|s| s.is_empty())
                ),
                _ => true,
            }
        }),
        _ => true,
    }
}

// ------------------------------------------------------------------ shared state

struct NotifEntry {
    token: u64,
    id: u32,
    acted: bool,
}

type Response = (u32, HashMap<String, OwnedValue>);

struct Shared {
    sink: Sink,
    notifications: Mutex<VecDeque<NotifEntry>>,
    /// Portal request path to the channel waiting for its `Response`.
    requests: Mutex<HashMap<String, Sender<Response>>>,
    /// The GlobalShortcuts session handle.
    session: Mutex<Option<String>>,
}

impl Shared {
    /// Handle one bus message (called by the worker thread).
    fn dispatch(&self, msg: &zbus::Message) {
        let h = msg.header();
        if h.message_type() != zbus::message::Type::Signal {
            return;
        }
        let (Some(iface), Some(member)) = (h.interface(), h.member()) else {
            return;
        };
        let body = msg.body();
        match (iface.as_str(), member.as_str()) {
            (NOTIFY_NAME, "ActionInvoked") => {
                if let Ok((id, action)) = body.deserialize::<(u32, String)>() {
                    let mut list = self.notifications.lock().unwrap();
                    if let Some(e) = list.iter_mut().find(|e| e.id == id) {
                        e.acted = true;
                        let token = e.token;
                        drop(list);
                        let ev = if action == "default" {
                            json!({"type":"notification","token":token,"event":"clicked"})
                        } else {
                            json!({"type":"notification","token":token,"event":"action","action":action})
                        };
                        (self.sink)(ev);
                    }
                }
            }
            (NOTIFY_NAME, "NotificationClosed") => {
                if let Ok((id, reason)) = body.deserialize::<(u32, u32)>() {
                    let mut list = self.notifications.lock().unwrap();
                    if let Some(pos) = list.iter().position(|e| e.id == id) {
                        let e = list.remove(pos).unwrap();
                        drop(list);
                        // A click or button press already reported the outcome.
                        if !e.acted {
                            let event = match reason {
                                2 => "dismissed",
                                1 => "expired",
                                _ => "closed",
                            };
                            (self.sink)(
                                json!({"type":"notification","token":e.token,"event":event}),
                            );
                        }
                    }
                }
            }
            ("org.freedesktop.portal.Settings", "SettingChanged") => {
                if let Ok((ns, key, v)) = body.deserialize::<(String, String, OwnedValue)>() {
                    if ns != "org.freedesktop.appearance" {
                        return;
                    }
                    match (key.as_str(), value_u32(&v)) {
                        ("color-scheme", Some(n)) => {
                            if let Some(d) = scheme_dark(n) {
                                (self.sink)(json!({"type":"system_preferences","dark":d}));
                            }
                        }
                        ("contrast", Some(n)) => {
                            (self.sink)(
                                json!({"type":"system_preferences","high_contrast":n == 1}),
                            );
                        }
                        _ => {}
                    }
                }
            }
            (SHORTCUTS_IFACE, "Activated") => {
                if let Ok((session, id, _ts, _opts)) =
                    body.deserialize::<(ObjectPath<'_>, String, u64, HashMap<String, OwnedValue>)>()
                {
                    let ours = self.session.lock().unwrap().clone();
                    if ours.as_deref() == Some(session.as_str()) {
                        (self.sink)(json!({"type":"hotkey","id":id}));
                    }
                }
            }
            ("org.freedesktop.portal.Request", "Response") => {
                if let (Some(path), Ok(resp)) = (h.path(), body.deserialize::<Response>()) {
                    if let Some(tx) = self.requests.lock().unwrap().remove(path.as_str()) {
                        let _ = tx.send(resp);
                    }
                }
            }
            _ => {}
        }
    }
}

// ------------------------------------------------------------------ SNI + dbusmenu objects

#[derive(Default)]
struct TrayProps {
    title: String,
    pixmap: Pixmaps,
}

type Pixmaps = Vec<(i32, i32, Vec<u8>)>;

struct Item {
    props: Arc<Mutex<TrayProps>>,
    sink: Sink,
}

#[interface(name = "org.kde.StatusNotifierItem")]
impl Item {
    #[zbus(property)]
    fn category(&self) -> String {
        "ApplicationStatus".into()
    }
    #[zbus(property)]
    fn id(&self) -> String {
        "ui4me".into()
    }
    #[zbus(property)]
    fn title(&self) -> String {
        self.props.lock().unwrap().title.clone()
    }
    #[zbus(property)]
    fn status(&self) -> String {
        "Active".into()
    }
    #[zbus(property)]
    fn window_id(&self) -> u32 {
        0
    }
    #[zbus(property)]
    fn icon_name(&self) -> String {
        String::new()
    }
    #[zbus(property)]
    fn icon_pixmap(&self) -> Pixmaps {
        self.props.lock().unwrap().pixmap.clone()
    }
    #[zbus(property)]
    fn tool_tip(&self) -> (String, Pixmaps, String, String) {
        (
            String::new(),
            Vec::new(),
            self.props.lock().unwrap().title.clone(),
            String::new(),
        )
    }
    #[zbus(property)]
    fn menu(&self) -> ObjectPath<'static> {
        ObjectPath::from_static_str_unchecked(MENU_PATH)
    }
    #[zbus(property)]
    fn item_is_menu(&self) -> bool {
        false
    }
    fn activate(&self, x: i32, y: i32) {
        let _ = (x, y);
        (self.sink)(json!({"type":"tray","event":"activate"}));
    }
    fn secondary_activate(&self, x: i32, y: i32) {
        let _ = (x, y);
        (self.sink)(json!({"type":"tray","event":"activate"}));
    }
    fn context_menu(&self, x: i32, y: i32) {
        let _ = (x, y);
        (self.sink)(json!({"type":"tray","event":"context"}));
    }
    fn scroll(&self, delta: i32, orientation: String) {
        let _ = (delta, orientation);
    }
}

struct MenuState {
    revision: u32,
    nodes: Vec<MenuNode>,
}

struct MenuIface {
    state: Arc<Mutex<MenuState>>,
    sink: Sink,
}

impl MenuIface {
    fn click(&self, id: i32, event: &str) {
        if event != "clicked" {
            return;
        }
        let cmd = {
            let st = self.state.lock().unwrap();
            usize::try_from(id)
                .ok()
                .and_then(|i| st.nodes.get(i))
                .and_then(|n| n.command.clone())
        };
        if let Some(c) = cmd {
            (self.sink)(json!({"type":"menu_command","source":"tray","command":c}));
        }
    }
}

#[interface(name = "com.canonical.dbusmenu")]
impl MenuIface {
    #[zbus(property)]
    fn version(&self) -> u32 {
        3
    }
    #[zbus(property)]
    fn text_direction(&self) -> String {
        "ltr".into()
    }
    #[zbus(property)]
    fn status(&self) -> String {
        "normal".into()
    }
    #[zbus(property)]
    fn icon_theme_path(&self) -> Vec<String> {
        Vec::new()
    }
    fn get_layout(
        &self,
        parent_id: i32,
        recursion_depth: i32,
        property_names: Vec<String>,
    ) -> (u32, (i32, Props, Vec<Value<'static>>)) {
        let st = self.state.lock().unwrap();
        (
            st.revision,
            node_parts(&st.nodes, parent_id, recursion_depth, &property_names),
        )
    }
    fn get_group_properties(
        &self,
        ids: Vec<i32>,
        property_names: Vec<String>,
    ) -> Vec<(i32, Props)> {
        let st = self.state.lock().unwrap();
        let ids: Vec<i32> = if ids.is_empty() {
            (0..st.nodes.len() as i32).collect()
        } else {
            ids
        };
        ids.into_iter()
            .filter_map(|id| {
                let n = st.nodes.get(usize::try_from(id).ok()?)?;
                Some((id, node_props(n, &property_names)))
            })
            .collect()
    }
    fn get_property(&self, id: i32, name: String) -> zbus::fdo::Result<Value<'static>> {
        let st = self.state.lock().unwrap();
        usize::try_from(id)
            .ok()
            .and_then(|i| st.nodes.get(i))
            .and_then(|n| n.props.get(&name))
            .map(Prop::value)
            .ok_or_else(|| {
                zbus::fdo::Error::InvalidArgs(format!("no property {name} on item {id}"))
            })
    }
    fn event(&self, id: i32, event_id: String, data: Value<'_>, timestamp: u32) {
        let _ = (data, timestamp);
        self.click(id, &event_id);
    }
    fn event_group(&self, events: Vec<(i32, String, Value<'_>, u32)>) -> Vec<i32> {
        for (id, ev, _, _) in events {
            self.click(id, &ev);
        }
        Vec::new()
    }
    fn about_to_show(&self, id: i32) -> bool {
        let _ = id;
        false
    }
    fn about_to_show_group(&self, ids: Vec<i32>) -> (Vec<i32>, Vec<i32>) {
        let _ = ids;
        (Vec::new(), Vec::new())
    }
}

struct TrayHandle {
    bus_name: Option<String>,
    props: Arc<Mutex<TrayProps>>,
    menu: Arc<Mutex<MenuState>>,
}

// ------------------------------------------------------------------ the adapter

struct Bus {
    conn: Connection,
    stop: Arc<AtomicBool>,
    done: std::sync::mpsc::Receiver<()>,
}

struct PortalInfo {
    scheme: bool,
    contrast: bool,
    shortcuts: bool,
}

struct ShortcutSet {
    session: String,
    bound: Vec<(String, Accelerator)>,
}

pub struct LinuxServices {
    sink: Sink,
    shared: Arc<Shared>,
    bus: Option<Result<Bus, String>>,
    portal: Option<PortalInfo>,
    tray: Option<TrayHandle>,
    shortcuts: Option<ShortcutSet>,
    counter: u32,
}

fn bus_error(e: &zbus::Error, absent: &str) -> Refusal {
    match e {
        zbus::Error::MethodError(name, desc, _) => {
            let n = name.as_str();
            if n.ends_with("ServiceUnknown") || n.ends_with("NameHasNoOwner") {
                Refusal::Unavailable(absent.into())
            } else {
                Refusal::Unavailable(format!("{absent}: {n} {}", desc.as_deref().unwrap_or("")))
            }
        }
        other => Refusal::Unavailable(format!("{absent}: {other}")),
    }
}

impl LinuxServices {
    pub fn new(sink: Sink) -> Self {
        Self {
            shared: Arc::new(Shared {
                sink: sink.clone(),
                notifications: Mutex::new(VecDeque::new()),
                requests: Mutex::new(HashMap::new()),
                session: Mutex::new(None),
            }),
            sink,
            bus: None,
            portal: None,
            tray: None,
            shortcuts: None,
            counter: 0,
        }
    }

    /// The session-bus connection, created (with the signal worker) on first use.
    fn conn(&mut self) -> Result<Connection, Refusal> {
        if self.bus.is_none() {
            self.bus = Some(self.connect());
        }
        match self.bus.as_ref().unwrap() {
            Ok(b) => Ok(b.conn.clone()),
            Err(e) => Err(Refusal::Unavailable(format!("{NO_BUS} ({e})"))),
        }
    }

    fn connect(&self) -> Result<Bus, String> {
        let conn = zbus::blocking::connection::Builder::session()
            .and_then(|b| b.method_timeout(CALL_TIMEOUT).build())
            .map_err(|e| e.to_string())?;
        for rule in [
            "type='signal',interface='org.freedesktop.Notifications'",
            "type='signal',interface='org.freedesktop.portal.Settings',member='SettingChanged'",
            "type='signal',interface='org.freedesktop.portal.GlobalShortcuts'",
            "type='signal',interface='org.freedesktop.portal.Request',member='Response'",
        ] {
            conn.call_method(
                Some("org.freedesktop.DBus"),
                "/org/freedesktop/DBus",
                Some("org.freedesktop.DBus"),
                "AddMatch",
                &(rule,),
            )
            .map_err(|e| e.to_string())?;
        }
        let stop = Arc::new(AtomicBool::new(false));
        let (done_tx, done) = channel();
        let iter = MessageIterator::from(&conn);
        let shared = self.shared.clone();
        let flag = stop.clone();
        std::thread::Builder::new()
            .name("ui4me-dbus".into())
            .spawn(move || {
                for msg in iter {
                    if flag.load(Ordering::SeqCst) {
                        break;
                    }
                    match msg {
                        Ok(m) => shared.dispatch(&m),
                        Err(_) => break,
                    }
                }
                let _ = done_tx.send(());
            })
            .map_err(|e| e.to_string())?;
        Ok(Bus { conn, stop, done })
    }

    fn name_available(conn: &Connection, name: &str) -> bool {
        let bus = |member: &str, body: &(&str,)| {
            conn.call_method(
                Some("org.freedesktop.DBus"),
                "/org/freedesktop/DBus",
                Some("org.freedesktop.DBus"),
                member,
                body,
            )
        };
        if let Ok(m) = bus("NameHasOwner", &(name,)) {
            if m.body().deserialize::<bool>().unwrap_or(false) {
                return true;
            }
        }
        conn.call_method(
            Some("org.freedesktop.DBus"),
            "/org/freedesktop/DBus",
            Some("org.freedesktop.DBus"),
            "ListActivatableNames",
            &(),
        )
        .ok()
        .and_then(|m| m.body().deserialize::<Vec<String>>().ok())
        .is_some_and(|l| l.iter().any(|n| n == name))
    }

    fn read_setting(conn: &Connection, key: &str) -> Option<u32> {
        let call = |member: &str| {
            conn.call_method(
                Some(PORTAL_NAME),
                PORTAL_PATH,
                Some("org.freedesktop.portal.Settings"),
                member,
                &("org.freedesktop.appearance", key),
            )
        };
        let reply = call("ReadOne").or_else(|_| call("Read")).ok()?;
        let v: OwnedValue = reply.body().deserialize().ok()?;
        value_u32(&v)
    }

    /// What the portal offers (detected once).
    fn portal(&mut self, conn: &Connection) -> &PortalInfo {
        self.portal.get_or_insert_with(|| {
            let shortcuts = conn
                .call_method(
                    Some(PORTAL_NAME),
                    PORTAL_PATH,
                    Some("org.freedesktop.DBus.Properties"),
                    "Get",
                    &(SHORTCUTS_IFACE, "version"),
                )
                .is_ok();
            PortalInfo {
                scheme: Self::read_setting(conn, "color-scheme").is_some(),
                contrast: Self::read_setting(conn, "contrast").is_some(),
                shortcuts,
            }
        })
    }

    fn next_token(&mut self, what: &str) -> String {
        self.counter += 1;
        format!("ui4me_{what}_{}", self.counter)
    }

    /// Call a portal method that answers through a `Request` and wait for its `Response`.
    fn portal_request(
        &self,
        conn: &Connection,
        method: &str,
        token: &str,
        body: &(impl serde::Serialize + zbus::zvariant::DynamicType),
        wait: Duration,
    ) -> Result<Response, Refusal> {
        let me = conn
            .unique_name()
            .map(|n| n.as_str().to_string())
            .unwrap_or_default();
        let sender = me.trim_start_matches(':').replace('.', "_");
        let path = format!("/org/freedesktop/portal/desktop/request/{sender}/{token}");
        let (tx, rx) = channel();
        self.shared
            .requests
            .lock()
            .unwrap()
            .insert(path.clone(), tx);
        let reply = conn.call_method(
            Some(PORTAL_NAME),
            PORTAL_PATH,
            Some(SHORTCUTS_IFACE),
            method,
            body,
        );
        if let Err(e) = reply {
            self.shared.requests.lock().unwrap().remove(&path);
            return Err(bus_error(&e, NO_SHORTCUTS));
        }
        let out = rx.recv_timeout(wait);
        self.shared.requests.lock().unwrap().remove(&path);
        out.map_err(|_| Refusal::Unavailable("the portal did not answer in time".into()))
    }

    fn close_session(&mut self) {
        let session = self.shortcuts.take().map(|s| s.session);
        *self.shared.session.lock().unwrap() = None;
        if let (Some(s), Ok(conn)) = (session, self.conn()) {
            let _ = conn.call_method(
                Some(PORTAL_NAME),
                s.as_str(),
                Some("org.freedesktop.portal.Session"),
                "Close",
                &(),
            );
        }
    }

    fn bind(
        &mut self,
        conn: &Connection,
        session: &str,
        set: &[(String, Accelerator)],
        id: &str,
    ) -> Result<(), Refusal> {
        let token = self.next_token("bind");
        let shortcuts: Vec<(String, HashMap<&str, Value<'_>>)> = set
            .iter()
            .map(|(sid, a)| {
                let mut m: HashMap<&str, Value<'_>> = HashMap::new();
                m.insert("description", Value::from(sid.clone()));
                m.insert("preferred_trigger", Value::from(portal_trigger(a)));
                (sid.clone(), m)
            })
            .collect();
        let mut opts: HashMap<&str, Value<'_>> = HashMap::new();
        opts.insert("handle_token", Value::from(token.clone()));
        let sess =
            ObjectPath::try_from(session).map_err(|e| Refusal::Unavailable(e.to_string()))?;
        let (code, results) = self.portal_request(
            conn,
            "BindShortcuts",
            &token,
            &(sess, shortcuts, "", opts),
            BIND_TIMEOUT,
        )?;
        match code {
            0 => {}
            1 => {
                return Err(Refusal::Denied(
                    "the user refused the global shortcut".into(),
                ))
            }
            _ => {
                return Err(Refusal::Unavailable(
                    "the portal could not bind the shortcut".into(),
                ))
            }
        }
        // The portal answers with the shortcuts it bound; ours missing or without a trigger
        // means another holder owns it or the user cleared it.
        let assigned = results
            .get("shortcuts")
            .is_none_or(|v| shortcut_assigned(v, id));
        if assigned {
            Ok(())
        } else {
            Err(Refusal::Conflict(
                "the desktop did not assign the shortcut (the trigger may be taken)".into(),
            ))
        }
    }
}

impl PlatformServices for LinuxServices {
    fn capabilities(&mut self) -> Vec<(&'static str, Json)> {
        let menu = cap("unsupported", NO_MENUBAR);
        let conn = match self.conn() {
            Ok(c) => c,
            Err(r) => {
                let off = r.to_json();
                return vec![
                    ("notifications", off.clone()),
                    ("system_tray", off.clone()),
                    ("native_menus", menu.clone()),
                    ("native_menus.context", menu),
                    ("global_hotkeys", off.clone()),
                    ("environment.theme_changes", off.clone()),
                    ("environment.contrast", off),
                ];
            }
        };
        let notifications = if Self::name_available(&conn, NOTIFY_NAME) {
            cap("supported", "")
        } else {
            cap("unavailable", NO_NOTIFY)
        };
        let tray = if Self::name_available(&conn, WATCHER_NAME) {
            cap("supported", "")
        } else {
            cap("unavailable", NO_WATCHER)
        };
        let p = self.portal(&conn);
        let (scheme, contrast, shortcuts) = (p.scheme, p.contrast, p.shortcuts);
        let by = |on: bool, reason: &str| {
            if on {
                cap("supported", "")
            } else {
                cap("unsupported", reason)
            }
        };
        vec![
            ("notifications", notifications),
            ("system_tray", tray),
            ("native_menus", menu.clone()),
            ("native_menus.context", menu),
            ("global_hotkeys", by(shortcuts, NO_SHORTCUTS)),
            (
                "environment.theme_changes",
                by(
                    scheme,
                    "the desktop portal does not report org.freedesktop.appearance color-scheme",
                ),
            ),
            (
                "environment.contrast",
                by(
                    contrast,
                    "the desktop portal does not report org.freedesktop.appearance contrast",
                ),
            ),
        ]
    }

    fn notify(&mut self, n: &Notification) -> Result<(), Refusal> {
        let conn = self.conn()?;
        let mut actions: Vec<String> = vec!["default".into(), "Open".into()];
        for a in &n.actions {
            actions.push(a.id.clone());
            actions.push(a.label.clone());
        }
        let mut hints: HashMap<&str, Value<'_>> = HashMap::new();
        hints.insert("urgency", Value::U8(urgency_byte(&n.urgency)));
        let icon = n
            .icon
            .as_ref()
            .map(|p| p.to_string_lossy().into_owned())
            .unwrap_or_default();
        let reply = conn
            .call_method(
                Some(NOTIFY_NAME),
                NOTIFY_PATH,
                Some(NOTIFY_NAME),
                "Notify",
                &(
                    "ui4me", 0u32, icon, &n.title, &n.body, actions, hints, -1i32,
                ),
            )
            .map_err(|e| bus_error(&e, NO_NOTIFY))?;
        let id: u32 = reply
            .body()
            .deserialize()
            .map_err(|e| Refusal::Unavailable(format!("bad Notify reply: {e}")))?;
        let mut list = self.shared.notifications.lock().unwrap();
        while list.len() >= MAX_NOTIFICATIONS {
            list.pop_front();
        }
        list.push_back(NotifEntry {
            token: n.token,
            id,
            acted: false,
        });
        Ok(())
    }

    fn close_notification(&mut self, token: u64) {
        let id = {
            let mut list = self.shared.notifications.lock().unwrap();
            list.iter()
                .position(|e| e.token == token)
                .and_then(|p| list.remove(p))
                .map(|e| e.id)
        };
        if let (Some(id), Ok(conn)) = (id, self.conn()) {
            let _ = conn.call_method(
                Some(NOTIFY_NAME),
                NOTIFY_PATH,
                Some(NOTIFY_NAME),
                "CloseNotification",
                &(id,),
            );
            // The token is forgotten above, so the server's NotificationClosed finds nothing:
            // report the app-requested close here, once.
            (self.sink)(serde_json::json!({"type":"notification","token":token,"event":"closed"}));
        }
    }

    fn set_tray(&mut self, tray: Option<&Tray>) -> Result<(), Refusal> {
        let Some(tray) = tray else {
            if let Some(h) = self.tray.take() {
                if let Ok(conn) = self.conn() {
                    let os = conn.object_server();
                    let _ = os.remove::<Item, _>(ITEM_PATH);
                    let _ = os.remove::<MenuIface, _>(MENU_PATH);
                    drop(os);
                    if let Some(name) = h.bus_name {
                        let _ = conn.release_name(name.as_str());
                    }
                }
            }
            return Ok(());
        };
        let conn = self.conn()?;
        let pixmap = tray
            .icon
            .as_ref()
            .map(|(rgba, w, h)| vec![(*w as i32, *h as i32, rgba_to_argb(rgba))])
            .unwrap_or_default();
        let title = if tray.tooltip.is_empty() {
            "ui4me".to_string()
        } else {
            tray.tooltip.clone()
        };
        let nodes = build_menu(&tray.menu);
        if let Some(h) = &self.tray {
            {
                let mut p = h.props.lock().unwrap();
                p.title = title;
                p.pixmap = pixmap;
            }
            let rev = {
                let mut m = h.menu.lock().unwrap();
                m.revision += 1;
                m.nodes = nodes;
                m.revision
            };
            for sig in ["NewIcon", "NewToolTip", "NewTitle"] {
                let _ = conn.emit_signal(
                    None::<&str>,
                    ITEM_PATH,
                    "org.kde.StatusNotifierItem",
                    sig,
                    &(),
                );
            }
            let _ = conn.emit_signal(
                None::<&str>,
                MENU_PATH,
                "com.canonical.dbusmenu",
                "LayoutUpdated",
                &(rev, 0i32),
            );
            return Ok(());
        }
        if !Self::name_available(&conn, WATCHER_NAME) {
            return Err(Refusal::Unavailable(NO_WATCHER.into()));
        }
        let props = Arc::new(Mutex::new(TrayProps { title, pixmap }));
        let menu = Arc::new(Mutex::new(MenuState { revision: 1, nodes }));
        {
            let os = conn.object_server();
            let item = Item {
                props: props.clone(),
                sink: self.sink.clone(),
            };
            let m = MenuIface {
                state: menu.clone(),
                sink: self.sink.clone(),
            };
            os.at(ITEM_PATH, item)
                .map_err(|e| Refusal::Unavailable(format!("tray object: {e}")))?;
            os.at(MENU_PATH, m)
                .map_err(|e| Refusal::Unavailable(format!("tray menu object: {e}")))?;
        }
        let well_known = format!("org.kde.StatusNotifierItem-{}-1", std::process::id());
        let (service, bus_name) = match conn.request_name(well_known.as_str()) {
            Ok(()) => (well_known.clone(), Some(well_known)),
            Err(_) => (
                conn.unique_name()
                    .map(|n| n.as_str().to_string())
                    .unwrap_or_default(),
                None,
            ),
        };
        let registered = conn.call_method(
            Some(WATCHER_NAME),
            "/StatusNotifierWatcher",
            Some(WATCHER_NAME),
            "RegisterStatusNotifierItem",
            &(service.as_str(),),
        );
        if let Err(e) = registered {
            let os = conn.object_server();
            let _ = os.remove::<Item, _>(ITEM_PATH);
            let _ = os.remove::<MenuIface, _>(MENU_PATH);
            drop(os);
            if let Some(n) = &bus_name {
                let _ = conn.release_name(n.as_str());
            }
            return Err(bus_error(&e, NO_WATCHER));
        }
        self.tray = Some(TrayHandle {
            bus_name,
            props,
            menu,
        });
        Ok(())
    }

    fn set_window_menu(
        &mut self,
        _window: u64,
        _handle: Option<super::winit_handle::Raw>,
        menu: Option<&[MenuItem]>,
    ) -> Result<(), Refusal> {
        match menu {
            None => Ok(()),
            Some(_) => Err(Refusal::Unsupported(NO_MENUBAR.into())),
        }
    }

    fn show_context_menu(
        &mut self,
        _window: u64,
        _handle: Option<super::winit_handle::Raw>,
        _x: f64,
        _y: f64,
        _menu: &[MenuItem],
    ) -> Result<(), Refusal> {
        Err(Refusal::Unsupported(NO_MENUBAR.into()))
    }

    fn register_hotkey(&mut self, id: &str, accelerator: &Accelerator) -> Result<(), Refusal> {
        let conn = self.conn()?;
        if !self.portal(&conn).shortcuts {
            return Err(Refusal::Unsupported(NO_SHORTCUTS.into()));
        }
        let mut created = false;
        if self.shortcuts.is_none() {
            let token = self.next_token("session");
            let stoken = self.next_token("shortcuts");
            let mut opts: HashMap<&str, Value<'_>> = HashMap::new();
            opts.insert("handle_token", Value::from(token.clone()));
            opts.insert("session_handle_token", Value::from(stoken));
            let (code, results) =
                self.portal_request(&conn, "CreateSession", &token, &(opts,), CALL_TIMEOUT)?;
            if code != 0 {
                return Err(Refusal::Denied(
                    "the desktop refused a global shortcuts session".into(),
                ));
            }
            let session = results
                .get("session_handle")
                .and_then(|v| value_str(v))
                .ok_or_else(|| Refusal::Unavailable("the portal returned no session".into()))?;
            *self.shared.session.lock().unwrap() = Some(session.clone());
            self.shortcuts = Some(ShortcutSet {
                session,
                bound: Vec::new(),
            });
            created = true;
        }
        let set = self.shortcuts.as_ref().unwrap();
        let session = set.session.clone();
        let mut next: Vec<(String, Accelerator)> =
            set.bound.iter().filter(|(i, _)| i != id).cloned().collect();
        next.push((id.to_string(), accelerator.clone()));
        match self.bind(&conn, &session, &next, id) {
            Ok(()) => {
                self.shortcuts.as_mut().unwrap().bound = next;
                Ok(())
            }
            Err(e) => {
                if created {
                    self.close_session();
                }
                Err(e)
            }
        }
    }

    fn unregister_hotkey(&mut self, id: &str) {
        let Some(set) = &self.shortcuts else { return };
        if !set.bound.iter().any(|(i, _)| i == id) {
            return;
        }
        let rest: Vec<_> = set.bound.iter().filter(|(i, _)| i != id).cloned().collect();
        // The portal has no per-shortcut unbind: end the session, then rebind the others.
        self.close_session();
        for (i, a) in rest {
            let _ = self.register_hotkey(&i, &a);
        }
    }

    fn system_preferences(&mut self) -> (Option<bool>, Option<bool>) {
        let Ok(conn) = self.conn() else {
            return (None, None);
        };
        let p = self.portal(&conn);
        let (scheme, contrast) = (p.scheme, p.contrast);
        let dark = if scheme {
            Self::read_setting(&conn, "color-scheme").and_then(scheme_dark)
        } else {
            None
        };
        let high = if contrast {
            Self::read_setting(&conn, "contrast").map(|n| n == 1)
        } else {
            None
        };
        (dark, high)
    }

    fn shutdown(&mut self) {
        let tokens: Vec<u64> = self
            .shared
            .notifications
            .lock()
            .unwrap()
            .iter()
            .map(|e| e.token)
            .collect();
        for t in tokens {
            self.close_notification(t);
        }
        if self.bus.as_ref().is_some_and(|b| b.is_ok()) {
            let _ = self.set_tray(None);
            self.close_session();
        }
        if let Some(Ok(bus)) = self.bus.take() {
            bus.stop.store(true, Ordering::SeqCst);
            // Wake the worker with a signal addressed to ourselves.
            if let Some(me) = bus.conn.unique_name() {
                let _ = bus.conn.emit_signal(
                    Some(me.as_str()),
                    "/org/ui4me/wake",
                    "org.ui4me.Wake",
                    "Wake",
                    &(),
                );
            }
            let _ = bus.done.recv_timeout(Duration::from_secs(2));
        }
    }
}

#[cfg(test)]
mod tests;
