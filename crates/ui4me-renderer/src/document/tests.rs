//! Application-facing regressions: the production facade, actual scene, and
//! production interaction algorithms, with no alternate headless editor.
use super::*;
use std::cell::RefCell;
use std::rc::Rc;

fn key(key: &str, ctrl: bool, shift: bool) -> Input {
    Input::Key {
        key: key.into(),
        code: key.into(),
        pressed: true,
        repeat: false,
        shift,
        ctrl,
        alt: false,
        meta: false,
    }
}
fn press(d: &mut Document, name: &str) -> Vec<Value> {
    d.handle_input(key(name, false, false)).unwrap()
}
fn rect(d: &mut Document, element: &str) -> (f64, f64, f64, f64) {
    let node = d.node(element).unwrap();
    d.element_content_rect(d.id(), node).unwrap().unwrap()
}
fn click(d: &mut Document, element: &str) -> Vec<Value> {
    let (x, y, w, h) = rect(d, element);
    let (x, y) = (x + w / 2.0, y + h / 2.0);
    let mut events = d
        .handle_input(Input::PointerButton {
            pressed: true,
            button: 0,
            x,
            y,
        })
        .unwrap();
    events.extend(
        d.handle_input(Input::PointerButton {
            pressed: false,
            button: 0,
            x,
            y,
        })
        .unwrap(),
    );
    events
}

#[test]
fn nested_flex_layout_and_css_mutations_change_real_pixels() {
    let html = r#"<!doctype html><style>
        html,body{margin:0} #row{display:flex;gap:10px;padding:8px;background:#eee}
        #red{width:30px;height:24px;background:#ff0000} #blue{width:40px;height:24px;background:#0000ff}
        #blue.changed{background:#00ff00}
        </style><section id=row><div id=red></div><div id=blue></div></section>"#;
    let mut d = Document::parse(html).unwrap();
    let pixels = d.render(200, 80, 1.0).unwrap();
    assert_eq!(pixels[10 * 200 + 10], 0x00ff0000);
    assert_eq!(pixels[10 * 200 + 50], 0x000000ff);
    assert_eq!(rect(&mut d, "blue").0, 48.0);
    d.add_class("blue", "changed").unwrap();
    assert_eq!(d.render(200, 80, 1.0).unwrap()[10 * 200 + 50], 0x0000ff00);
    d.remove_class("blue", "changed").unwrap();
    assert_eq!(d.render(200, 80, 1.0).unwrap()[10 * 200 + 50], 0x000000ff);
    let scaled = d.render(400, 160, 2.0).unwrap();
    assert_eq!(scaled.len(), 400 * 160);
    assert_eq!(scaled[20 * 400 + 100], 0x000000ff);
}

#[test]
fn text_shapes_unicode_and_set_text_remains_literal() {
    let mut d = Document::parse("<!doctype html><style>body{margin:0;font-size:24px;color:#111}</style><p id=p>Žluťoučký kůň — Ελληνικά</p>").unwrap();
    let before = d.render(400, 100, 1.0).unwrap();
    assert!(before.iter().filter(|&&p| p != 0x00ff_ffff).count() > 100);
    d.set_text("p", "<b>literal & text</b>").unwrap();
    assert_eq!(d.get_value("p").unwrap(), "<b>literal & text</b>");
    let after = d.render(400, 100, 1.0).unwrap();
    assert_ne!(before, after);
    assert!(d.pipeline.document().element_by_id("b").is_none());
}

#[test]
fn invalid_subtree_replacement_is_atomic_and_old_events_cannot_retarget() {
    let mut d = Document::parse(
        "<!doctype html><div id=host><input id=edit value=old></div><p id=other>outside</p>",
    )
    .unwrap();
    d.focus("edit").unwrap();
    d.drain_events();
    let events = d.handle_input(Input::Text("!".into())).unwrap();
    let input = events
        .iter()
        .find(|e| e["type"] == "input")
        .unwrap()
        .clone();
    assert!(d.event_is_current(&input));
    let old = d.node("edit").unwrap();
    let revision = d.pipeline.document().revision();
    assert!(d.replace_children_html("host", "<input id=other>").is_err());
    assert_eq!(d.node("edit").unwrap(), old);
    assert_eq!(d.pipeline.document().revision(), revision);
    assert_eq!(d.get_value("edit").unwrap(), "old!");
    assert!(d.event_is_current(&input));
    assert!(
        d.replace_children_html("host", "<script>bad()</script>")
            .is_err()
    );
    d.replace_children_html("host", "<input id=edit value=new>")
        .unwrap();
    assert_eq!(d.get_value("edit").unwrap(), "new");
    assert!(!d.event_is_current(&input));
    assert_eq!(d.interaction.focused_element(d.id()), None);
    assert!(d.blink.is_none());
}

#[test]
fn accepted_text_altgr_grapheme_deletion_and_committed_change_share_one_value() {
    let mut d =
        Document::parse("<!doctype html><input id=edit><button id=next>Next</button>").unwrap();
    d.focus("edit").unwrap();
    d.drain_events();
    d.handle_input(Input::Modifiers {
        shift: false,
        ctrl: true,
        alt: true,
        meta: false,
    })
    .unwrap();
    let events = d.handle_input(Input::Text("é😀@".into())).unwrap();
    assert_eq!(d.get_value("edit").unwrap(), "é😀@");
    assert_eq!(events.iter().filter(|e| e["type"] == "input").count(), 1);
    assert_eq!(events.iter().filter(|e| e["type"] == "change").count(), 1);
    press(&mut d, "Backspace");
    assert_eq!(d.get_value("edit").unwrap(), "é😀");
    press(&mut d, "Backspace");
    assert_eq!(d.get_value("edit").unwrap(), "é");
    d.focus("next").unwrap();
    let events = d.drain_events();
    assert_eq!(events.iter().filter(|e| e["type"] == "commit").count(), 1);
    assert_eq!(
        events.iter().find(|e| e["type"] == "commit").unwrap()["value"],
        "é"
    );
}

#[test]
fn readonly_disabled_and_hidden_controls_are_not_editable_or_tab_stops() {
    let mut d = Document::parse("<!doctype html><input id=a><input id=disabled disabled tabindex=1><div style='display:none'><input id=hidden></div><input id=readonly readonly value=locked><button id=b>Done</button>").unwrap();
    assert!(d.focus("disabled").is_err());
    assert!(d.focus("hidden").is_err());
    d.focus("readonly").unwrap();
    d.handle_input(Input::Text("no".into())).unwrap();
    assert_eq!(d.get_value("readonly").unwrap(), "locked");
    d.focus("a").unwrap();
    d.drain_events();
    let events = press(&mut d, "Tab");
    assert!(
        events
            .iter()
            .any(|e| e["type"] == "focus" && e["element"] == "readonly")
    );
    press(&mut d, "Tab");
    assert_eq!(
        d.interaction.focused_element(d.id()),
        Some(d.node("b").unwrap())
    );
}

#[test]
fn pointer_and_keyboard_activation_use_scene_geometry() {
    let mut d = Document::parse("<!doctype html><style>#go{margin:40px;padding:18px}#off{margin:10px}</style><button id=go>Go</button><button id=off disabled>Disabled</button>").unwrap();
    let events = click(&mut d, "go");
    assert!(
        events
            .iter()
            .any(|e| e["type"] == "mousedown" && e["element"] == "go")
    );
    assert!(
        events
            .iter()
            .any(|e| e["type"] == "mouseup" && e["element"] == "go")
    );
    assert!(
        events
            .iter()
            .any(|e| e["type"] == "click" && e["element"] == "go")
    );
    d.focus("go").unwrap();
    let events = press(&mut d, "Enter");
    assert!(
        events
            .iter()
            .any(|e| e["type"] == "click" && e["element"] == "go")
    );
    let events = click(&mut d, "off");
    assert!(
        !events
            .iter()
            .any(|e| e["type"] == "click" && e["element"] == "off")
    );
}

#[test]
fn window_focus_pauses_the_caret_without_discarding_element_focus() {
    let mut d = Document::parse("<input id=field value=kept>").unwrap();
    d.focus("field").unwrap();
    d.render(200, 80, 1.0).unwrap();
    let field = d.node("field").unwrap();
    assert!(d.blink.as_ref().unwrap().visible);
    assert!(d.ime_request().is_some());
    d.handle_input(Input::Focus(false)).unwrap();
    assert_eq!(d.interaction.focused_element(d.id()), Some(field));
    assert!(!d.blink.as_ref().unwrap().visible);
    assert!(d.ime_request().is_none());
    assert!(d.next_wake_in().is_none());
    d.handle_input(Input::Focus(true)).unwrap();
    assert!(d.blink.as_ref().unwrap().visible);
    assert!(d.ime_request().is_some());
    assert!(d.next_wake_in().is_some());
    assert_eq!(d.get_value("field").unwrap(), "kept");
}

#[test]
fn nested_button_content_keeps_its_subscription_path_and_identity() {
    let mut d = Document::parse("<!doctype html><button id=go><span id=caption>Nested label</span></button><button id=off disabled><span>Disabled label</span></button>").unwrap();
    let events = click(&mut d, "go");
    let event = events.iter().find(|e| e["type"] == "click").unwrap();
    assert!(
        event["path"]
            .as_array()
            .unwrap()
            .iter()
            .any(|id| id == "go")
    );
    assert!(d.event_is_current(event));
    d.set_text("go", "Replaced label").unwrap();
    // The hit may be the button itself or its label depending on glyph location.
    // A descendant hit must never transfer to a replacement descendant.
    if event["element"] == "caption" {
        assert!(!d.event_is_current(event));
    }
    assert!(!click(&mut d, "off").iter().any(|e| e["type"] == "click"));
}

#[test]
fn unpromoted_motion_and_paging_are_reported_and_static_styles_apply() {
    let mut d = Document::parse(r#"<!doctype html><style>
        @page invoice { size:20px 20px; }
        @keyframes fade { from{opacity:0}to{opacity:1} }
        body{margin:0}#box{width:24px;height:24px;background:#ff0000;transition:background-color 1s;animation:fade 2s;-webkit-transition:background-color 1s;-webkit-animation:fade 2s;page:invoice}
        #box.on{background:#0000ff}
        </style><div id=box></div>"#).unwrap();
    assert_eq!(d.render(100, 80, 1.0).unwrap()[5 * 100 + 5], 0x00ff0000);
    d.add_class("box", "on").unwrap();
    assert_eq!(d.render(100, 80, 1.0).unwrap()[5 * 100 + 5], 0x000000ff);
    assert!(
        d.diagnostics()
            .iter()
            .any(|e| e["feature"] == "css.property.transition")
    );
    assert!(
        d.diagnostics()
            .iter()
            .any(|e| e["feature"] == "css.property.page")
    );
}

#[test]
fn checkbox_and_radio_activation_update_the_canonical_model() {
    let mut d = Document::parse("<!doctype html><input type=checkbox id=c><input type=radio name=g id=a checked><input type=radio name=g id=b>").unwrap();
    let events = click(&mut d, "c");
    assert!(d.get_checked("c").unwrap());
    assert!(
        events
            .iter()
            .any(|e| e["type"] == "change" && e["checked"] == true)
    );
    d.set_checked("b", true).unwrap();
    assert!(!d.get_checked("a").unwrap());
    assert!(d.get_checked("b").unwrap());
    click(&mut d, "a");
    assert!(d.get_checked("a").unwrap());
    assert!(!d.get_checked("b").unwrap());
}

#[derive(Clone)]
struct TestClipboard(Rc<RefCell<String>>);
impl Clipboard for TestClipboard {
    fn read_text(&mut self) -> std::result::Result<Option<String>, String> {
        Ok(Some(self.0.borrow().clone()))
    }
    fn write_text(&mut self, text: &str) -> std::result::Result<(), String> {
        *self.0.borrow_mut() = text.into();
        Ok(())
    }
}

#[test]
fn selection_clipboard_undo_and_redo_use_the_same_editing_engine() {
    let shared = Rc::new(RefCell::new(String::new()));
    let mut d = Document::parse("<!doctype html><textarea id=t>Český text</textarea>").unwrap();
    d.set_clipboard(Box::new(TestClipboard(shared.clone())));
    d.focus("t").unwrap();
    d.handle_input(key("a", true, false)).unwrap();
    d.handle_input(key("c", true, false)).unwrap();
    assert_eq!(&*shared.borrow(), "Český text");
    d.handle_input(key("x", true, false)).unwrap();
    assert_eq!(d.get_value("t").unwrap(), "");
    d.handle_input(key("z", true, false)).unwrap();
    assert_eq!(d.get_value("t").unwrap(), "Český text");
    d.handle_input(key("z", true, true)).unwrap();
    assert_eq!(d.get_value("t").unwrap(), "");
    d.handle_input(key("v", true, false)).unwrap();
    assert_eq!(d.get_value("t").unwrap(), "Český text");
}

#[test]
fn ime_commit_replaces_preedit_once_and_uses_utf8_cursor_offsets() {
    let mut d = Document::parse("<!doctype html><input id=t>").unwrap();
    d.focus("t").unwrap();
    d.handle_input(Input::ImeEnabled).unwrap();
    d.handle_input(Input::ImePreedit {
        text: "ž😀".into(),
        cursor: Some((2, 6)),
    })
    .unwrap();
    let state = d
        .pipeline
        .document()
        .control_state(d.node("t").unwrap())
        .unwrap()
        .unwrap();
    assert_eq!(state.value.as_deref(), Some("ž😀"));
    press(&mut d, "Backspace");
    press(&mut d, "Enter");
    assert_eq!(
        d.get_value("t").unwrap(),
        "ž😀",
        "the IME owns preedit editing keys"
    );
    d.handle_input(Input::ImeCommit("žluťoučký".into()))
        .unwrap();
    assert_eq!(d.get_value("t").unwrap(), "žluťoučký");
    d.handle_input(Input::ImeDisabled).unwrap();
    assert_eq!(d.get_value("t").unwrap(), "žluťoučký");
}

#[test]
fn scrolling_moves_hit_geometry_and_subtree_replacement_retires_it() {
    let mut d = Document::parse("<!doctype html><style>body{margin:0}#s{height:80px;width:180px;overflow:auto}#pad{height:150px}#go{width:80px;height:30px}</style><div id=s><div id=pad></div><button id=go>Go</button></div>").unwrap();
    d.render(200, 200, 1.0).unwrap();
    let before = rect(&mut d, "go").1;
    let events = d
        .handle_input(Input::Wheel {
            dx: 0.0,
            dy: 150.0,
            x: 50.0,
            y: 40.0,
        })
        .unwrap();
    assert!(events.iter().any(|e| e["type"] == "scroll"));
    assert!(rect(&mut d, "go").1 < before);
    assert!(
        click(&mut d, "go")
            .iter()
            .any(|e| e["type"] == "click" && e["element"] == "go")
    );
    d.replace_children_html("s", "<button id=go>New</button>")
        .unwrap();
    assert_eq!(d.get_value("go").unwrap(), "New");
}

#[test]
fn local_stylesheet_image_and_font_resolve_from_the_document_directory() {
    static NEXT: AtomicU32 = AtomicU32::new(1);
    let root = std::env::temp_dir().join(format!(
        "ui4me-renderer-assets-{}-{}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    std::fs::create_dir_all(&root).unwrap();
    std::fs::write(root.join("app.css"), "@font-face{font-family:AppFont;src:url(font.ttf)}body{margin:0;font-family:AppFont}#color{width:20px;height:20px;background:#123456}img{display:block;width:24px;height:24px}").unwrap();
    std::fs::write(root.join("icon.svg"), r##"<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><path fill="#ff00ff" d="M0 0h24v24H0z"/></svg>"##).unwrap();
    std::fs::copy(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("test-data/fonts/noto-sans/NotoSans-Regular.ttf"),
        root.join("font.ttf"),
    )
    .unwrap();
    let mut d = Document::parse_with_source("<!doctype html><link rel=stylesheet href=app.css><div id=color></div><img src=icon.svg><p>Local font</p>", Some(&root), 160, 120).unwrap();
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        let pixels = d.render(160, 120, 1.0).unwrap();
        if pixels[5 * 160 + 5] == 0x00123456
            && pixels[25 * 160 + 5] == 0x00ff00ff
            && !d.has_pending_resources()
        {
            break;
        }
        assert!(
            Instant::now() < deadline,
            "assets did not settle: {:?}",
            d.diagnostics()
        );
        std::thread::sleep(Duration::from_millis(10));
    }
    let faces = lock(&d.resources).document_faces(d.id()).unwrap();
    assert!(
        faces.iter().any(|f| f.family == "AppFont"
            && matches!(f.state, ui4me_assets::fonts::FaceState::Loaded(_)))
    );
    drop(d);
    std::fs::remove_dir_all(root).unwrap();
}

#[test]
fn limits_and_active_content_fail_before_use() {
    assert!(Document::parse("<script>alert(1)</script>").is_err());
    assert!(Document::parse("<button onclick='bad()'>No</button>").is_err());
    assert!(Document::parse("<div id=x></div><div id=x></div>").is_err());
    let deep = format!("{}x{}", "<div>".repeat(257), "</div>".repeat(257));
    assert_eq!(Document::parse(&deep).unwrap_err().code, 5);
    let mut d = Document::parse("<p id=p>ok</p>").unwrap();
    assert_eq!(d.render(0, 100, 1.0).unwrap_err().code, 5);
    assert_eq!(d.render(5000, 5000, 1.0).unwrap_err().code, 5);
    assert!(d.set_text("p", &"x".repeat(MAX_TEXT + 1)).is_err());
    assert_eq!(d.get_value("p").unwrap(), "ok");
}

#[test]
fn unsupported_pickers_are_rejected_without_mutating_the_live_document() {
    let mut d = Document::parse("<section id=host><input id=field value=kept></section>").unwrap();
    let field = d.node("field").unwrap();
    for kind in [
        "file",
        "color",
        "date",
        "time",
        "month",
        "week",
        "datetime-local",
    ] {
        let html = format!("<input type='{kind}'>");
        let error = Document::parse(&html).unwrap_err();
        assert_eq!(error.code, 1);
        assert!(error.message.contains("requires a native picker"));
        assert!(d.set_attribute("field", "type", Some(kind)).is_err());
        assert_eq!(
            d.pipeline.document().input_type(field),
            Some(InputType::Text)
        );
        assert!(d.replace_children_html("host", &html).is_err());
        assert_eq!(d.node("field").unwrap(), field);
        assert_eq!(d.get_value("field").unwrap(), "kept");
    }
}

fn button(d: &mut Document, pressed: bool, x: f64, y: f64) {
    d.handle_input(Input::PointerButton {
        pressed,
        button: 0,
        x,
        y,
    })
    .unwrap();
}

#[test]
fn document_text_selection_drag_copy_and_controls() {
    let mut d = Document::parse(
        "<!doctype html><style>body{margin:0;font-size:20px} p{margin:0;height:40px}</style>\
         <p id=a>Alpha beta</p><p id=b>Gamma delta</p><input id=pw type=password value=secret><p id=c>Omega</p>",
    )
    .unwrap();
    d.render(640, 480, 1.0).unwrap();
    let a = d.element_rect("a").unwrap().unwrap();
    let b = d.element_rect("b").unwrap().unwrap();
    // Drag from the start of "Alpha" to the end of the second paragraph's text.
    button(&mut d, true, a.x + 1.0, a.y + 10.0);
    d.handle_input(Input::PointerMoved {
        x: b.x + 600.0,
        y: b.y + 10.0,
    })
    .unwrap();
    button(&mut d, false, b.x + 600.0, b.y + 10.0);
    assert_eq!(d.selection_text().unwrap(), "Alpha beta\nGamma delta");
    // The highlight paints only inside the selection.
    let plain = {
        let mut e = Document::parse("<!doctype html><style>body{margin:0;font-size:20px} p{margin:0;height:40px}</style><p id=a>Alpha beta</p><p id=b>Gamma delta</p><input id=pw type=password value=secret><p id=c>Omega</p>").unwrap();
        e.render(640, 480, 1.0).unwrap()
    };
    let selected = d.render(640, 480, 1.0).unwrap();
    let row = |y: f64| (y as usize) * 640;
    assert!((0..40).any(|x| selected[row(a.y + 10.0) + x] != plain[row(a.y + 10.0) + x]));
    assert_eq!(
        selected[row(b.y + 30.0) + 630],
        plain[row(b.y + 30.0) + 630],
        "outside the text"
    );
    // Ctrl+C copies the document selection.
    d.handle_input(key("c", true, false)).unwrap();
    assert_eq!(
        d.clipboard_text().unwrap().as_deref(),
        Some("Alpha beta\nGamma delta")
    );
    // Mutating another paragraph keeps the selection.
    d.set_text("c", "Changed").unwrap();
    assert_eq!(d.selection_text().unwrap(), "Alpha beta\nGamma delta");
    // Ctrl+A selects all document text, never the password value.
    d.handle_input(key("a", true, false)).unwrap();
    let all = d.selection_text().unwrap();
    assert!(
        all.starts_with("Alpha beta") && all.ends_with("Changed"),
        "{all:?}"
    );
    assert!(!all.contains("secret"));
    // Double-click selects a word; a press on a control clears the document selection.
    let (x, y) = (a.x + 90.0, a.y + 10.0);
    button(&mut d, true, x, y);
    button(&mut d, false, x, y);
    button(&mut d, true, x, y);
    button(&mut d, false, x, y);
    assert_eq!(d.selection_text().unwrap(), "beta");
    let mut b2 =
        Document::parse("<!doctype html><p id=t>Keep me</p><button id=copy>Copy</button>").unwrap();
    b2.render(640, 480, 1.0).unwrap();
    b2.select_text(Some("t")).unwrap();
    let r = b2.element_rect("copy").unwrap().unwrap();
    button(&mut b2, true, r.x + 4.0, r.y + 4.0);
    button(&mut b2, false, r.x + 4.0, r.y + 4.0);
    assert_eq!(
        b2.selection_text().unwrap(),
        "Keep me",
        "a button press keeps the selection"
    );
    let pw = d.element_rect("pw").unwrap().unwrap();
    button(&mut d, true, pw.x + 5.0, pw.y + 5.0);
    button(&mut d, false, pw.x + 5.0, pw.y + 5.0);
    assert_eq!(d.selection_text().unwrap(), "");
    // Removing the selected paragraph clears the selection.
    d.select_text(Some("b")).unwrap();
    assert_eq!(d.selection_text().unwrap(), "Gamma delta");
    d.remove_element("b").unwrap();
    assert_eq!(d.selection_text().unwrap(), "");
}

#[test]
#[ignore = "measurement"]
fn measure_long_log_append() {
    let n: usize = std::env::var("LINES")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(10_000);
    let mut d =
        Document::parse("<!doctype html><div id=log style='height:400px;overflow:auto'></div>")
            .unwrap();
    d.set_scroll_follow(Some("log"), true).unwrap();
    let start = std::time::Instant::now();
    let (mut ins, mut ren, mut worst_ins, mut worst_ren) = (
        std::time::Duration::ZERO,
        std::time::Duration::ZERO,
        std::time::Duration::ZERO,
        std::time::Duration::ZERO,
    );
    for i in 0..n {
        let t = std::time::Instant::now();
        d.insert_html(
            "log",
            "beforeend",
            &format!("<div>line {i} lorem ipsum dolor sit amet</div>"),
        )
        .unwrap();
        let e = t.elapsed();
        ins += e;
        worst_ins = worst_ins.max(e);
        if i % 50 == 0 {
            let t = std::time::Instant::now();
            d.render(800, 600, 1.0).unwrap();
            let e = t.elapsed();
            ren += e;
            worst_ren = worst_ren.max(e);
        }
        if i % 1000 == 999 {
            eprintln!(
                "{}: total {:?} insert {:?} (worst {:?}) render {:?} (worst {:?})",
                i + 1,
                start.elapsed(),
                ins,
                worst_ins,
                ren,
                worst_ren
            );
            (ins, ren, worst_ins, worst_ren) = Default::default();
        }
    }
    let t = std::time::Instant::now();
    d.render(800, 600, 1.0).unwrap();
    eprintln!("final render {:?}; one more append+render:", t.elapsed());
    for _ in 0..3 {
        let t = std::time::Instant::now();
        d.insert_html("log", "beforeend", "<div>x</div>").unwrap();
        let a = t.elapsed();
        d.pipeline.flush().unwrap();
        let b = t.elapsed();
        let stages = d.pipeline.last_stage_ms;
        d.render(800, 600, 1.0).unwrap();
        eprintln!(
            "  insert {a:?} flush {:?} render {:?} stats {stages:?}",
            b - a,
            t.elapsed() - b
        );
    }
}

/// S5: a 10k-line log streamed through a bounded window and three chat views streaming tokens
/// keep the DOM, the arena and the selection bounded and consistent.
#[test]
fn sustained_log_and_chat_streams_stay_bounded() {
    let mut log = Document::parse("<!doctype html><style>body{margin:0}</style><div id=log style='height:300px;overflow:auto'></div>").unwrap();
    log.set_scroll_follow(Some("log"), true).unwrap();
    let mut chats: Vec<Document> = (0..3)
        .map(|_| Document::parse("<!doctype html><div id=msgs style='height:300px;overflow:auto'></div><input id=search value=keep>").unwrap())
        .collect();
    for c in &mut chats {
        c.set_scroll_follow(Some("msgs"), true).unwrap();
        c.focus("search").unwrap();
    }
    let mut peak = 0;
    for i in 0..10_000 {
        log.apply_batch(&[
            DomOp::InsertHtml {
                element: "log".into(),
                position: "beforeend".into(),
                html: format!("<div>line {i} ✓ žluťoučký</div>"),
            },
            DomOp::TrimChildren {
                element: "log".into(),
                keep: 300,
                from_start: true,
            },
        ])
        .unwrap();
        for (n, c) in chats.iter_mut().enumerate() {
            if i % 40 == 0 {
                c.insert_html("msgs", "beforeend", &format!("<p id=m{n}x{i}></p>"))
                    .unwrap();
                c.trim_children("msgs", 50, true).unwrap();
            }
            let last = format!("m{n}x{}", i / 40 * 40);
            c.append_text(&last, "tok ").unwrap();
        }
        if i % 500 == 0 {
            log.render(400, 300, 1.0).unwrap();
            for c in &mut chats {
                c.render(400, 300, 1.0).unwrap();
            }
            if i == 5000 {
                log.select_text(Some("log")).unwrap();
            }
        }
        peak = peak.max(log.pipeline.document().arena().live_count());
    }
    assert!(peak < 2_000, "arena grows: {peak}");
    let (ids, count) = log.query_ids("#log > div", 1).unwrap();
    assert!(ids.is_empty());
    assert_eq!(count, 300);
    assert_eq!(log.get_text("log").unwrap().matches("line 9999").count(), 1);
    assert_eq!(
        log.scroll_state(Some("log")).unwrap().y,
        log.scroll_state(Some("log")).unwrap().max_y
    );
    for c in &mut chats {
        assert!(c.pipeline.document().arena().live_count() < 1_000);
        assert_eq!(c.get_value("search").unwrap(), "keep");
        assert_eq!(
            c.query_ids(":focus", 4).unwrap().0,
            vec!["search".to_owned()]
        );
        assert_eq!(
            c.get_text("m0x9960")
                .or_else(|_| c.get_text("m1x9960"))
                .or_else(|_| c.get_text("m2x9960"))
                .unwrap(),
            "tok ".repeat(40)
        );
    }
    // A long streamed message is split into bounded text nodes.
    let mut d = Document::parse("<p id=m></p>").unwrap();
    for _ in 0..20_000 {
        d.append_text("m", "0123456789").unwrap();
    }
    assert_eq!(d.get_text("m").unwrap().len(), 200_000);
    assert!(d.append_text("m", &"x".repeat(MAX_TEXT + 1)).is_err());
}

#[test]
fn sub_pixel_overflow_is_not_scrollable() {
    let mut d = Document::parse("<!doctype html><style>body{margin:0}#b{height:100px;overflow:auto}#c{height:100.4px}</style><div id=b><div id=c></div></div>").unwrap();
    d.render(400, 300, 1.0).unwrap();
    let s = d.scroll_state(Some("b")).unwrap();
    assert_eq!((s.max_y, s.scrollable), (0.0, true));
}
