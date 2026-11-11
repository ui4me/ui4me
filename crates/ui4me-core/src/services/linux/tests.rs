//! Linux desktop services tests: pure conversions, plus an integration test against fake
//! notification / tray / portal servers on a PRIVATE `dbus-daemon` the test starts itself
//! (never the real session bus):
//! `cargo test -p ui4me-core --lib services::linux -- --ignored`.

#![allow(clippy::type_complexity)]

use super::*;
use crate::services::{validate_notification, NotificationAction};
use std::io::{BufRead, BufReader};
use std::process::{Child, Command, Stdio};
use std::time::Instant;
use zbus::message::Header;

fn items(v: serde_json::Value) -> Vec<MenuItem> {
    serde_json::from_value(v).unwrap()
}

#[test]
fn pixmap_is_argb_network_order() {
    assert_eq!(
        rgba_to_argb(&[1, 2, 3, 4, 10, 20, 30, 255]),
        vec![4, 1, 2, 3, 255, 10, 20, 30]
    );
}

#[test]
fn urgency_maps_to_bytes() {
    assert_eq!(urgency_byte("low"), 0);
    assert_eq!(urgency_byte("normal"), 1);
    assert_eq!(urgency_byte("critical"), 2);
}

#[test]
fn accelerators_become_portal_triggers() {
    let t = |s: &str| portal_trigger(&Accelerator::parse(s).unwrap());
    assert_eq!(t("Ctrl+Alt+K"), "CTRL+ALT+k");
    assert_eq!(t("Ctrl+Shift+F5"), "CTRL+SHIFT+F5");
    assert_eq!(t("Super+Space"), "LOGO+space");
    assert_eq!(t("Alt+Enter"), "ALT+Return");
    assert_eq!(t("Ctrl+PageUp"), "CTRL+Page_Up");
    assert_eq!(t("Ctrl+5"), "CTRL+5");
}

#[test]
fn color_scheme_values() {
    assert_eq!(scheme_dark(0), None);
    assert_eq!(scheme_dark(1), Some(true));
    assert_eq!(scheme_dark(2), Some(false));
}

#[test]
fn dbusmenu_layout_is_built_from_the_menu() {
    let menu = items(json!([
        {"id":"open","label":"Open_file"},
        {"separator":true},
        {"id":"dark","label":"Dark","checked":true,"enabled":false},
        {"label":"More","items":[{"id":"quit","label":"Quit"}]}
    ]));
    let n = build_menu(&menu);
    assert_eq!(n.len(), 6);
    assert_eq!(n[0].children, vec![1, 2, 3, 4]);
    assert_eq!(n[1].props["label"], Prop::Str("Open__file".into()));
    assert_eq!(n[1].command.as_deref(), Some("open"));
    assert_eq!(n[2].props["type"], Prop::Str("separator".into()));
    assert_eq!(n[3].props["toggle-type"], Prop::Str("checkmark".into()));
    assert_eq!(n[3].props["toggle-state"], Prop::Int(1));
    assert_eq!(n[3].props["enabled"], Prop::Bool(false));
    assert_eq!(n[4].props["children-display"], Prop::Str("submenu".into()));
    assert_eq!(n[4].children, vec![5]);
    assert_eq!(n[5].command.as_deref(), Some("quit"));

    // Depth 1 lists the children without their own children; depth 0 none.
    let (id, props, kids) = node_parts(&n, 0, 1, &[]);
    assert_eq!((id, kids.len()), (0, 4));
    assert!(props.contains_key("children-display"));
    assert!(node_parts(&n, 0, 0, &[]).2.is_empty());
    let (_, p, _) = node_parts(&n, 1, 0, &["label".to_string()]);
    assert_eq!(p.len(), 1);
    assert_eq!(node_parts(&n, 99, -1, &[]).2.len(), 0);
}

#[test]
fn window_menus_are_unsupported_but_clearing_is_fine() {
    let mut s = LinuxServices::new(Arc::new(|_| {}));
    assert!(s.set_window_menu(1, None, None).is_ok());
    let m = items(json!([{"id":"a","label":"A"}]));
    assert!(matches!(
        s.set_window_menu(1, None, Some(&m)),
        Err(Refusal::Unsupported(_))
    ));
    assert!(matches!(
        s.show_context_menu(1, None, 0.0, 0.0, &m),
        Err(Refusal::Unsupported(_))
    ));
}

// ------------------------------------------------------------------ private bus + fakes

struct PrivateBus {
    child: Child,
    dir: std::path::PathBuf,
}

impl PrivateBus {
    fn start() -> Self {
        let dir = std::env::temp_dir().join(format!("ui4me-dbus-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let conf = dir.join("bus.conf");
        std::fs::write(
            &conf,
            format!(
                "<busconfig><type>session</type><listen>unix:path={}/bus</listen><auth>EXTERNAL</auth>\
                 <policy context=\"default\"><allow send_destination=\"*\" eavesdrop=\"true\"/>\
                 <allow eavesdrop=\"true\"/><allow own=\"*\"/></policy></busconfig>",
                dir.display()
            ),
        )
        .unwrap();
        let mut child = Command::new("dbus-daemon")
            .arg(format!("--config-file={}", conf.display()))
            .args(["--nofork", "--print-address=1"])
            .stdout(Stdio::piped())
            .spawn()
            .expect("dbus-daemon");
        let mut addr = String::new();
        BufReader::new(child.stdout.take().unwrap())
            .read_line(&mut addr)
            .unwrap();
        let addr = addr.trim().to_string();
        assert!(
            addr.contains(dir.to_str().unwrap()),
            "private bus address {addr}"
        );
        std::env::set_var("DBUS_SESSION_BUS_ADDRESS", &addr);
        PrivateBus { child, dir }
    }
}

impl Drop for PrivateBus {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
        let _ = std::fs::remove_dir_all(&self.dir);
    }
}

#[derive(Default)]
struct Log {
    notify: Vec<(
        String,
        u32,
        String,
        String,
        String,
        Vec<String>,
        HashMap<String, OwnedValue>,
    )>,
    closed: Vec<u32>,
    registered: Vec<String>,
    bound: Vec<Vec<(String, String)>>,
    /// 0 = accept, 1 = user cancel, 2 = bound without the shortcut.
    bind_mode: u32,
}

type SharedLog = Arc<Mutex<Log>>;

struct FakeNotifications(SharedLog);

#[interface(name = "org.freedesktop.Notifications")]
impl FakeNotifications {
    #[allow(clippy::too_many_arguments)]
    fn notify(
        &self,
        app: String,
        replaces: u32,
        icon: String,
        summary: String,
        body: String,
        actions: Vec<String>,
        hints: HashMap<String, OwnedValue>,
        _timeout: i32,
    ) -> u32 {
        self.0
            .lock()
            .unwrap()
            .notify
            .push((app, replaces, icon, summary, body, actions, hints));
        40 + self.0.lock().unwrap().notify.len() as u32
    }
    fn close_notification(&self, id: u32) {
        self.0.lock().unwrap().closed.push(id);
    }
}

struct FakeWatcher(SharedLog);

#[interface(name = "org.kde.StatusNotifierWatcher")]
impl FakeWatcher {
    fn register_status_notifier_item(&self, service: String) {
        self.0.lock().unwrap().registered.push(service);
    }
}

struct FakeSettings {
    scheme: u32,
}

#[interface(name = "org.freedesktop.portal.Settings")]
impl FakeSettings {
    fn read_one(&self, ns: String, key: String) -> zbus::fdo::Result<Value<'static>> {
        match (ns.as_str(), key.as_str()) {
            ("org.freedesktop.appearance", "color-scheme") => Ok(Value::U32(self.scheme)),
            ("org.freedesktop.appearance", "contrast") => Ok(Value::U32(1)),
            _ => Err(zbus::fdo::Error::Failed("no such setting".into())),
        }
    }
}

struct FakeShortcuts(SharedLog);

fn request_path(hdr: &Header<'_>, options: &HashMap<String, OwnedValue>) -> String {
    let sender = hdr
        .sender()
        .unwrap()
        .as_str()
        .trim_start_matches(':')
        .replace('.', "_");
    let token = value_str(options.get("handle_token").unwrap()).unwrap();
    format!("/org/freedesktop/portal/desktop/request/{sender}/{token}")
}

#[interface(name = "org.freedesktop.portal.GlobalShortcuts")]
impl FakeShortcuts {
    #[zbus(property, name = "version")]
    fn version(&self) -> u32 {
        1
    }
    async fn create_session(
        &self,
        options: HashMap<String, OwnedValue>,
        #[zbus(header)] hdr: Header<'_>,
        #[zbus(connection)] conn: &zbus::Connection,
    ) -> zbus::fdo::Result<ObjectPath<'static>> {
        let path = request_path(&hdr, &options);
        let sender = hdr
            .sender()
            .unwrap()
            .as_str()
            .trim_start_matches(':')
            .replace('.', "_");
        let stoken = value_str(options.get("session_handle_token").unwrap()).unwrap();
        let session = format!("/org/freedesktop/portal/desktop/session/{sender}/{stoken}");
        let mut results: HashMap<&str, Value<'_>> = HashMap::new();
        results.insert("session_handle", Value::from(session));
        conn.emit_signal(
            hdr.sender().map(|s| s.as_str()),
            path.as_str(),
            "org.freedesktop.portal.Request",
            "Response",
            &(0u32, results),
        )
        .await?;
        Ok(ObjectPath::try_from(path).unwrap())
    }
    async fn bind_shortcuts(
        &self,
        _session: ObjectPath<'_>,
        shortcuts: Vec<(String, HashMap<String, OwnedValue>)>,
        _parent: String,
        options: HashMap<String, OwnedValue>,
        #[zbus(header)] hdr: Header<'_>,
        #[zbus(connection)] conn: &zbus::Connection,
    ) -> zbus::fdo::Result<ObjectPath<'static>> {
        let path = request_path(&hdr, &options);
        let mode = self.0.lock().unwrap().bind_mode;
        let mut listed = Vec::new();
        let mut set = Vec::new();
        for (id, props) in &shortcuts {
            let trig = value_str(props.get("preferred_trigger").unwrap()).unwrap();
            set.push((id.clone(), trig.clone()));
            let mut m: HashMap<String, Value<'static>> = HashMap::new();
            m.insert("trigger_description".into(), Value::from(trig));
            listed.push(Value::Structure(
                StructureBuilder::new()
                    .add_field(id.clone())
                    .append_field(Value::Dict(Dict::from(m)))
                    .build()
                    .unwrap(),
            ));
        }
        self.0.lock().unwrap().bound.push(set);
        if mode == 2 {
            listed.clear();
        }
        let mut results: HashMap<&str, Value<'_>> = HashMap::new();
        let mut arr = Array::new(&zbus::zvariant::Signature::try_from("(sa{sv})").unwrap());
        for v in listed {
            arr.append(v).unwrap();
        }
        results.insert("shortcuts", Value::Array(arr));
        let code = if mode == 1 { 1u32 } else { 0 };
        conn.emit_signal(
            hdr.sender().map(|s| s.as_str()),
            path.as_str(),
            "org.freedesktop.portal.Request",
            "Response",
            &(code, results),
        )
        .await?;
        Ok(ObjectPath::try_from(path).unwrap())
    }
}

fn events() -> (Sink, Arc<Mutex<Vec<Json>>>) {
    let log = Arc::new(Mutex::new(Vec::new()));
    let l = log.clone();
    (Arc::new(move |v| l.lock().unwrap().push(v)), log)
}

fn wait_for(log: &Arc<Mutex<Vec<Json>>>, want: Json) {
    let end = Instant::now() + Duration::from_secs(5);
    while Instant::now() < end {
        if log.lock().unwrap().contains(&want) {
            return;
        }
        std::thread::sleep(Duration::from_millis(20));
    }
    panic!("event {want} not seen; got {:?}", log.lock().unwrap());
}

fn status(caps: &[(&'static str, Json)], key: &str) -> String {
    caps.iter().find(|(k, _)| *k == key).unwrap().1["status"]
        .as_str()
        .unwrap()
        .to_string()
}

#[test]
#[ignore = "starts a private dbus-daemon; run with --ignored"]
fn private_bus_services() {
    let bus = PrivateBus::start();

    // Phase 1: a bus with none of the services.
    {
        let (sink, _) = events();
        let mut s = LinuxServices::new(sink);
        let caps = s.capabilities();
        assert_eq!(status(&caps, "notifications"), "unavailable");
        assert_eq!(status(&caps, "system_tray"), "unavailable");
        assert_eq!(status(&caps, "global_hotkeys"), "unsupported");
        assert_eq!(status(&caps, "native_menus"), "unsupported");
        assert_eq!(status(&caps, "environment.theme_changes"), "unsupported");
        let n = validate_notification(1, "T".into(), "".into(), None, None, vec![]).unwrap();
        assert_eq!(s.notify(&n), Err(Refusal::Unavailable(NO_NOTIFY.into())),);
        assert!(
            matches!(s.set_tray(Some(&Tray { icon: None, tooltip: "t".into(), menu: vec![] })), Err(Refusal::Unavailable(r)) if r == NO_WATCHER)
        );
        assert!(matches!(
            s.register_hotkey("a", &Accelerator::parse("Ctrl+Alt+K").unwrap()),
            Err(Refusal::Unsupported(r)) if r == NO_SHORTCUTS
        ));
        assert_eq!(s.system_preferences(), (None, None));
        s.shutdown();
    }

    // Phase 2: fakes.
    let log: SharedLog = Arc::default();
    let fake = zbus::blocking::connection::Builder::session()
        .unwrap()
        .serve_at(
            "/org/freedesktop/Notifications",
            FakeNotifications(log.clone()),
        )
        .unwrap()
        .serve_at("/StatusNotifierWatcher", FakeWatcher(log.clone()))
        .unwrap()
        .serve_at(PORTAL_PATH, FakeSettings { scheme: 1 })
        .unwrap()
        .serve_at(PORTAL_PATH, FakeShortcuts(log.clone()))
        .unwrap()
        .name(NOTIFY_NAME)
        .unwrap()
        .name(WATCHER_NAME)
        .unwrap()
        .name(PORTAL_NAME)
        .unwrap()
        .build()
        .unwrap();

    let (sink, events) = events();
    let mut s = LinuxServices::new(sink);
    let caps = s.capabilities();
    for k in [
        "notifications",
        "system_tray",
        "global_hotkeys",
        "environment.theme_changes",
        "environment.contrast",
    ] {
        assert_eq!(status(&caps, k), "supported", "{k}");
    }
    assert_eq!(s.system_preferences(), (Some(true), Some(true)));

    // Notifications: Notify arguments, then click, action and close signals.
    let n = validate_notification(
        7,
        "Title".into(),
        "Body".into(),
        Some("/tmp/icon.png".into()),
        Some("critical".into()),
        vec![NotificationAction {
            id: "snooze".into(),
            label: "Snooze".into(),
        }],
    )
    .unwrap();
    s.notify(&n).unwrap();
    {
        let l = log.lock().unwrap();
        let (app, replaces, icon, summary, body, actions, hints) = &l.notify[0];
        assert_eq!(
            (app.as_str(), *replaces, icon.as_str()),
            ("ui4me", 0, "/tmp/icon.png")
        );
        assert_eq!((summary.as_str(), body.as_str()), ("Title", "Body"));
        assert_eq!(actions, &["default", "Open", "snooze", "Snooze"]);
        assert_eq!(
            u8::try_from(hints["urgency"].try_clone().unwrap()).unwrap(),
            2
        );
    }
    macro_rules! sig {
        ($member:expr, $body:expr $(,)?) => {
            fake.emit_signal(
                None::<&str>,
                "/org/freedesktop/Notifications",
                NOTIFY_NAME,
                $member,
                $body,
            )
            .unwrap()
        };
    }
    sig!("ActionInvoked", &(41u32, "snooze"));
    wait_for(
        &events,
        json!({"type":"notification","token":7,"event":"action","action":"snooze"}),
    );
    sig!("NotificationClosed", &(41u32, 3u32)); // closed after the action: not reported again
    s.notify(&validate_notification(8, "T2".into(), "".into(), None, None, vec![]).unwrap())
        .unwrap();
    sig!("ActionInvoked", &(42u32, "default"));
    wait_for(
        &events,
        json!({"type":"notification","token":8,"event":"clicked"}),
    );
    s.notify(&validate_notification(9, "T3".into(), "".into(), None, None, vec![]).unwrap())
        .unwrap();
    sig!("NotificationClosed", &(43u32, 2u32));
    wait_for(
        &events,
        json!({"type":"notification","token":9,"event":"dismissed"}),
    );
    assert!(!events
        .lock()
        .unwrap()
        .iter()
        .any(|e| e["token"] == 7 && e["event"] == "dismissed"));
    s.notify(&validate_notification(10, "T4".into(), "".into(), None, None, vec![]).unwrap())
        .unwrap();
    s.close_notification(10);
    assert_eq!(log.lock().unwrap().closed, vec![44]);

    // Preferences change.
    fake.emit_signal(
        None::<&str>,
        PORTAL_PATH,
        "org.freedesktop.portal.Settings",
        "SettingChanged",
        &("org.freedesktop.appearance", "color-scheme", Value::U32(2)),
    )
    .unwrap();
    wait_for(&events, json!({"type":"system_preferences","dark":false}));

    // Tray: registration, activate, context, menu command, update, removal.
    let menu = items(json!([
        {"id":"open","label":"Open"},
        {"label":"More","items":[{"id":"quit","label":"Quit"}]}
    ]));
    let icon = Some((
        vec![255, 0, 0, 128, 0, 255, 0, 255, 0, 0, 255, 255, 1, 2, 3, 4],
        2u32,
        2u32,
    ));
    s.set_tray(Some(&Tray {
        icon,
        tooltip: "My app".into(),
        menu,
    }))
    .unwrap();
    let service = log.lock().unwrap().registered[0].clone();
    assert_eq!(
        service,
        format!("org.kde.StatusNotifierItem-{}-1", std::process::id())
    );
    macro_rules! call {
        ($path:expr, $iface:expr, $member:expr, $body:expr $(,)?) => {
            fake.call_method(Some(service.as_str()), $path, Some($iface), $member, $body)
        };
    }
    let sni = "org.kde.StatusNotifierItem";
    call!(ITEM_PATH, sni, "Activate", &(1i32, 2i32)).unwrap();
    wait_for(&events, json!({"type":"tray","event":"activate"}));
    call!(ITEM_PATH, sni, "ContextMenu", &(1i32, 2i32)).unwrap();
    wait_for(&events, json!({"type":"tray","event":"context"}));
    let pix = call!(
        ITEM_PATH,
        "org.freedesktop.DBus.Properties",
        "Get",
        &(sni, "IconPixmap"),
    )
    .unwrap();
    let v: OwnedValue = pix.body().deserialize().unwrap();
    let pix: Vec<(i32, i32, Vec<u8>)> = v.try_into().unwrap();
    assert_eq!(pix[0].0, 2);
    assert_eq!(&pix[0].2[..4], &[128, 255, 0, 0]);
    let menu_prop = call!(
        ITEM_PATH,
        "org.freedesktop.DBus.Properties",
        "Get",
        &(sni, "Menu"),
    )
    .unwrap();
    let v: OwnedValue = menu_prop.body().deserialize().unwrap();
    assert_eq!(value_str(&v).as_deref(), Some(MENU_PATH));
    let dm = "com.canonical.dbusmenu";
    let layout = call!(
        MENU_PATH,
        dm,
        "GetLayout",
        &(0i32, -1i32, Vec::<String>::new()),
    )
    .unwrap();
    let (rev, (root, _props, kids)): (u32, (i32, HashMap<String, OwnedValue>, Vec<OwnedValue>)) =
        layout.body().deserialize().unwrap();
    assert_eq!((rev, root, kids.len()), (1, 0, 2));
    call!(
        MENU_PATH,
        dm,
        "Event",
        &(3i32, "clicked", Value::U8(0), 0u32),
    )
    .unwrap();
    wait_for(
        &events,
        json!({"type":"menu_command","source":"tray","command":"quit"}),
    );
    call!(
        MENU_PATH,
        dm,
        "Event",
        &(1i32, "hovered", Value::U8(0), 0u32),
    )
    .unwrap();
    // Update bumps the layout revision.
    s.set_tray(Some(&Tray {
        icon: None,
        tooltip: "x".into(),
        menu: items(json!([{"id":"a","label":"A"}])),
    }))
    .unwrap();
    let layout = call!(
        MENU_PATH,
        dm,
        "GetLayout",
        &(0i32, 1i32, Vec::<String>::new()),
    )
    .unwrap();
    let (rev, (_, _, kids)): (u32, (i32, HashMap<String, OwnedValue>, Vec<OwnedValue>)) =
        layout.body().deserialize().unwrap();
    assert_eq!((rev, kids.len()), (2, 1));
    assert_eq!(log.lock().unwrap().registered.len(), 1);
    s.set_tray(None).unwrap();
    assert!(call!(ITEM_PATH, sni, "Activate", &(0i32, 0i32)).is_err());

    // Global shortcuts: a refused, a taken and an accepted shortcut, activation, unregister.
    let acc = Accelerator::parse("Ctrl+Alt+K").unwrap();
    log.lock().unwrap().bind_mode = 1;
    assert!(matches!(
        s.register_hotkey("a", &acc),
        Err(Refusal::Denied(_))
    ));
    log.lock().unwrap().bind_mode = 2;
    assert!(matches!(
        s.register_hotkey("a", &acc),
        Err(Refusal::Conflict(_))
    ));
    log.lock().unwrap().bind_mode = 0;
    // The portal session path used by the fake.
    s.register_hotkey("a", &acc).unwrap();
    s.register_hotkey("b", &Accelerator::parse("Super+F5").unwrap())
        .unwrap();
    {
        let l = log.lock().unwrap();
        let last = l.bound.last().unwrap();
        assert_eq!(
            last,
            &vec![
                ("a".to_string(), "CTRL+ALT+k".to_string()),
                ("b".to_string(), "LOGO+F5".to_string())
            ]
        );
    }
    let session = s.shared.session.lock().unwrap().clone().unwrap();
    fake.emit_signal(
        None::<&str>,
        PORTAL_PATH,
        SHORTCUTS_IFACE,
        "Activated",
        &(
            ObjectPath::try_from(session.as_str()).unwrap(),
            "b",
            5u64,
            HashMap::<&str, Value<'_>>::new(),
        ),
    )
    .unwrap();
    wait_for(&events, json!({"type":"hotkey","id":"b"}));
    // Another application's session is ignored.
    fake.emit_signal(
        None::<&str>,
        PORTAL_PATH,
        SHORTCUTS_IFACE,
        "Activated",
        &(
            ObjectPath::try_from("/org/freedesktop/portal/desktop/session/other/x").unwrap(),
            "zzz",
            5u64,
            HashMap::<&str, Value<'_>>::new(),
        ),
    )
    .unwrap();
    s.shutdown();
    std::thread::sleep(Duration::from_millis(100));
    assert!(!events.lock().unwrap().iter().any(|e| e["id"] == "zzz"));
    drop(fake);
    drop(bus);
}
