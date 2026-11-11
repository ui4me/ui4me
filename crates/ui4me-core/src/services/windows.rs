//! Windows desktop services adapter (Core 0.7).
//!
//! Everything runs on the owner thread (winit's event-loop thread). One hidden message-only
//! window (created on first use) receives the tray callbacks, `WM_HOTKEY` and timers; winit's loop
//! dispatches them. Messages that are only broadcast to top-level windows (`WM_SETTINGCHANGE`,
//! `TaskbarCreated`) and the menu `WM_COMMAND` of app windows arrive through [`msg_hook`].
//!
//! * Tray: `Shell_NotifyIconW` (version 4 callbacks), RGBA icon via `CreateIconIndirect`.
//! * Notifications: balloon notifications through the tray icon, or a temporary hidden
//!   notification icon when the application has no tray icon. One balloon at a time.
//! * Menus: HMENU trees on the window (`SetMenu`) and `TrackPopupMenuEx` pop-ups.
//! * Global shortcuts: `RegisterHotKey` on the message window.
//! * Preferences: `AppsUseLightTheme` registry value and `SPI_GETHIGHCONTRAST`.
//!
//! State lives in a thread-local touched only through short borrows; events are sent to the
//! [`Sink`] after the borrow ends, and no borrow is held across a Win32 call that may pump
//! messages (pop-up menus).

use super::{Accelerator, MenuItem, Notification, PlatformServices, Refusal, Sink, Tray};
use serde_json::{json, Value};
use std::cell::RefCell;
use std::collections::HashMap;
use std::ffi::c_void;
use std::ptr::{null, null_mut};
use windows_sys::Win32::Foundation::{
    GetLastError, ERROR_HOTKEY_ALREADY_REGISTERED, HWND, LPARAM, LRESULT, POINT, WPARAM,
};
use windows_sys::Win32::Graphics::Gdi::{
    ClientToScreen, CreateBitmap, CreateDIBSection, DeleteObject, BITMAPINFO, BITMAPINFOHEADER,
    BI_RGB, DIB_RGB_COLORS,
};
use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
use windows_sys::Win32::UI::Input::KeyboardAndMouse::{
    RegisterHotKey, UnregisterHotKey, MOD_ALT, MOD_CONTROL, MOD_NOREPEAT, MOD_SHIFT, MOD_WIN,
};
use windows_sys::Win32::UI::Shell::{
    Shell_NotifyIconW, NIF_ICON, NIF_INFO, NIF_MESSAGE, NIF_SHOWTIP, NIF_STATE, NIF_TIP, NIIF_INFO,
    NIIF_NOSOUND, NIIF_WARNING, NIM_ADD, NIM_DELETE, NIM_MODIFY, NIM_SETVERSION, NIS_HIDDEN,
    NOTIFYICONDATAW,
};
use windows_sys::Win32::UI::WindowsAndMessaging::{
    AppendMenuW, CreateIconIndirect, CreateMenu, CreatePopupMenu, CreateWindowExW, DefWindowProcW,
    DestroyIcon, DestroyMenu, DestroyWindow, DrawMenuBar, GetCursorPos, IsWindow, KillTimer,
    LoadIconW, PostMessageW, RegisterClassExW, RegisterWindowMessageW, SetForegroundWindow,
    SetMenu, SetTimer, SystemParametersInfoW, TrackPopupMenuEx, HICON, HMENU, HWND_MESSAGE,
    ICONINFO, IDI_APPLICATION, MF_CHECKED, MF_GRAYED, MF_POPUP, MF_SEPARATOR, MF_STRING, MSG,
    SPI_GETHIGHCONTRAST, TPM_RETURNCMD, TPM_RIGHTBUTTON, WM_APP, WM_COMMAND, WM_CONTEXTMENU,
    WM_HOTKEY, WM_LBUTTONUP, WM_NULL, WM_RBUTTONUP, WM_SETTINGCHANGE, WM_SYSCOLORCHANGE,
    WM_THEMECHANGED, WM_TIMER, WNDCLASSEXW,
};

const WM_TRAY: u32 = WM_APP + 1;
const WM_SHOW_CONTEXT: u32 = WM_APP + 2;
const NIN_SELECT: u32 = 0x400;
const NIN_KEYSELECT: u32 = 0x401;
const NIN_BALLOONHIDE: u32 = 0x403;
const NIN_BALLOONTIMEOUT: u32 = 0x404;
const NIN_BALLOONUSERCLICK: u32 = 0x405;
const TRAY_ID: u32 = 1;
const TEMP_ID: u32 = 2;
const TIMER_BALLOON: usize = 1;
/// A balloon whose outcome never arrives (Focus Assist, a hidden host) is reported expired.
const BALLOON_SAFETY_MS: u32 = 30_000;
const MAX_HOTKEYS: usize = 64;
const MAX_WINDOW_MENUS: usize = 256;
const HIGH_CONTRAST_ON: u32 = 0x1;

const CLASS_NAME: &str = "UI4ME_ServicesWindow";

// ---------------------------------------------------------------- pure helpers

fn wide(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

/// Copy `s` into a fixed NUL-terminated UTF-16 buffer, truncating.
fn fill(dst: &mut [u16], s: &str) {
    let mut n = 0;
    for u in s.encode_utf16().take(dst.len() - 1) {
        dst[n] = u;
        n += 1;
    }
    dst[n] = 0;
}

/// Virtual-key code of a canonical accelerator key.
fn virtual_key(key: &str) -> Option<u32> {
    let b = key.as_bytes();
    if b.len() == 1 && (b[0].is_ascii_uppercase() || b[0].is_ascii_digit()) {
        return Some(b[0] as u32);
    }
    if let Some(n) = key.strip_prefix('F').and_then(|n| n.parse::<u32>().ok()) {
        return (1..=24).contains(&n).then(|| 0x6F + n);
    }
    Some(match key {
        "Backspace" => 0x08,
        "Tab" => 0x09,
        "Enter" => 0x0D,
        "Escape" => 0x1B,
        "Space" => 0x20,
        "PageUp" => 0x21,
        "PageDown" => 0x22,
        "End" => 0x23,
        "Home" => 0x24,
        "Left" => 0x25,
        "Up" => 0x26,
        "Right" => 0x27,
        "Down" => 0x28,
        "Insert" => 0x2D,
        "Delete" => 0x2E,
        "Plus" => 0xBB,
        "Comma" => 0xBC,
        "Minus" => 0xBD,
        "Period" => 0xBE,
        _ => return None,
    })
}

fn hotkey_modifiers(a: &Accelerator) -> u32 {
    let mut m = MOD_NOREPEAT;
    if a.ctrl {
        m |= MOD_CONTROL;
    }
    if a.alt {
        m |= MOD_ALT;
    }
    if a.shift {
        m |= MOD_SHIFT;
    }
    if a.meta {
        m |= MOD_WIN;
    }
    m
}

/// The menu text: `&` is literal, the accelerator is shown after a tab.
fn menu_text(label: &str, accelerator: Option<&str>) -> String {
    let mut s = label.replace('&', "&&");
    if let Some(a) = accelerator {
        if let Ok(a) = Accelerator::parse(a) {
            s.push('\t');
            s.push_str(&a.display());
        }
    }
    s
}

/// RGBA to BGRA (the DIB layout).
fn rgba_to_bgra(rgba: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(rgba.len());
    for p in rgba.as_chunks::<4>().0.iter() {
        out.extend_from_slice(&[p[2], p[1], p[0], p[3]]);
    }
    out
}

/// A menu tree with command ids assigned (pure; realised into an HMENU separately).
#[derive(Debug, PartialEq)]
enum Plan {
    Separator,
    Command {
        cmd: u16,
        text: String,
        enabled: bool,
        checked: bool,
    },
    Submenu {
        text: String,
        enabled: bool,
        children: Vec<Plan>,
    },
}

/// Assign command ids 1.. in tree order; returns the plan and fills the id table.
fn plan_menu(items: &[MenuItem], next: &mut u16, ids: &mut Vec<(u16, String)>) -> Vec<Plan> {
    let mut out = Vec::new();
    for it in items {
        if it.separator {
            out.push(Plan::Separator);
        } else if let Some(sub) = &it.items {
            out.push(Plan::Submenu {
                text: menu_text(&it.label, None),
                enabled: it.enabled,
                children: plan_menu(sub, next, ids),
            });
        } else if let Some(id) = &it.id {
            let cmd = *next;
            *next = next.saturating_add(1);
            ids.push((cmd, id.clone()));
            out.push(Plan::Command {
                cmd,
                text: menu_text(&it.label, it.accelerator.as_deref()),
                enabled: it.enabled,
                checked: it.checked == Some(true),
            });
        }
    }
    out
}

/// SAFETY: creates Win32 menus (owner thread); on failure everything made so far is destroyed.
unsafe fn realize(plan: &[Plan], bar: bool) -> Option<HMENU> {
    let menu = if bar { CreateMenu() } else { CreatePopupMenu() };
    if menu.is_null() {
        return None;
    }
    for p in plan {
        let ok = match p {
            Plan::Separator => AppendMenuW(menu, MF_SEPARATOR, 0, null()) != 0,
            Plan::Command {
                cmd,
                text,
                enabled,
                checked,
            } => {
                let mut f = MF_STRING;
                if !enabled {
                    f |= MF_GRAYED;
                }
                if *checked {
                    f |= MF_CHECKED;
                }
                AppendMenuW(menu, f, *cmd as usize, wide(text).as_ptr()) != 0
            }
            Plan::Submenu {
                text,
                enabled,
                children,
            } => match realize(children, false) {
                Some(sub) => {
                    let mut f = MF_POPUP | MF_STRING;
                    if !enabled {
                        f |= MF_GRAYED;
                    }
                    let ok = AppendMenuW(menu, f, sub as usize, wide(text).as_ptr()) != 0;
                    if !ok {
                        DestroyMenu(sub);
                    }
                    ok
                }
                None => false,
            },
        };
        if !ok {
            DestroyMenu(menu);
            return None;
        }
    }
    Some(menu)
}

fn hwnd_of(handle: Option<super::winit_handle::Raw>) -> Option<isize> {
    match handle? {
        winit::raw_window_handle::RawWindowHandle::Win32(h) => Some(h.hwnd.get()),
        _ => None,
    }
}

// ---------------------------------------------------------------- state

struct WinMenu {
    window: u64,
    hmenu: isize,
    ids: HashMap<u16, String>,
}

struct Balloon {
    token: u64,
    icon_id: u32,
}

struct PendingContext {
    hwnd: isize,
    window: u64,
    x: i32,
    y: i32,
    plan: Vec<Plan>,
    ids: HashMap<u16, String>,
}

struct State {
    sink: Sink,
    hwnd: isize,
    taskbar_created: u32,
    v4: bool,
    tray_added: bool,
    tray_icon: isize,
    tray_tip: String,
    tray_menu: Vec<MenuItem>,
    temp_added: bool,
    balloon: Option<Balloon>,
    hotkeys: HashMap<String, i32>,
    hotkey_ids: HashMap<i32, String>,
    next_hotkey: i32,
    window_menus: HashMap<isize, WinMenu>,
    pending_context: Option<PendingContext>,
    in_popup: bool,
    last_prefs: (Option<bool>, Option<bool>),
}

thread_local! {
    static STATE: RefCell<Option<State>> = const { RefCell::new(None) };
}

/// Run `f` on the state when it exists and is not borrowed (re-entrant calls are ignored).
fn with_state<R>(f: impl FnOnce(&mut State) -> R) -> Option<R> {
    STATE.with(|c| c.try_borrow_mut().ok().and_then(|mut s| s.as_mut().map(f)))
}

fn emit(sink: &Sink, events: Vec<Value>) {
    for e in events {
        sink(e);
    }
}

fn read_preferences() -> (Option<bool>, Option<bool>) {
    (read_dark(), read_high_contrast())
}

#[repr(C)]
struct HighContrastW {
    cb_size: u32,
    flags: u32,
    default_scheme: *mut u16,
}

fn read_high_contrast() -> Option<bool> {
    let mut hc = HighContrastW {
        cb_size: std::mem::size_of::<HighContrastW>() as u32,
        flags: 0,
        default_scheme: null_mut(),
    };
    // SAFETY: SPI_GETHIGHCONTRAST fills a HIGHCONTRASTW (same layout as `HighContrastW`) whose
    // cbSize is set; the scheme name pointer is left null (not requested).
    let ok = unsafe {
        SystemParametersInfoW(
            SPI_GETHIGHCONTRAST,
            hc.cb_size,
            &mut hc as *mut _ as *mut c_void,
            0,
        )
    };
    (ok != 0).then_some(hc.flags & HIGH_CONTRAST_ON != 0)
}

#[link(name = "advapi32")]
extern "system" {
    fn RegGetValueW(
        hkey: isize,
        subkey: *const u16,
        value: *const u16,
        flags: u32,
        kind: *mut u32,
        data: *mut c_void,
        size: *mut u32,
    ) -> i32;
}

fn read_dark() -> Option<bool> {
    const HKEY_CURRENT_USER: isize = 0x8000_0001u32 as i32 as isize;
    const RRF_RT_REG_DWORD: u32 = 0x10;
    let sub = wide(r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
    let val = wide("AppsUseLightTheme");
    let mut data: u32 = 1;
    let mut size: u32 = 4;
    // SAFETY: valid NUL-terminated names; `data` is a 4-byte DWORD buffer with `size` = 4.
    let r = unsafe {
        RegGetValueW(
            HKEY_CURRENT_USER,
            sub.as_ptr(),
            val.as_ptr(),
            RRF_RT_REG_DWORD,
            null_mut(),
            &mut data as *mut u32 as *mut c_void,
            &mut size,
        )
    };
    (r == 0).then_some(data == 0)
}

fn nid(hwnd: isize, id: u32, flags: u32) -> NOTIFYICONDATAW {
    // SAFETY: NOTIFYICONDATAW is plain data; all-zero is a valid empty value.
    let mut d: NOTIFYICONDATAW = unsafe { std::mem::zeroed() };
    d.cbSize = std::mem::size_of::<NOTIFYICONDATAW>() as u32;
    d.hWnd = hwnd as HWND;
    d.uID = id;
    d.uFlags = flags;
    d.uCallbackMessage = WM_TRAY;
    d
}

fn default_icon() -> HICON {
    // SAFETY: a null instance loads the shared system icon, which must not be destroyed.
    unsafe { LoadIconW(null_mut(), IDI_APPLICATION) }
}

/// Build an HICON from RGBA pixels; the caller owns (and destroys) it.
fn make_icon(rgba: &[u8], w: u32, h: u32) -> Option<HICON> {
    if w == 0 || h == 0 || rgba.len() != (w as usize) * (h as usize) * 4 {
        return None;
    }
    let bgra = rgba_to_bgra(rgba);
    // SAFETY: the DIB section pointer is valid for w*h*4 bytes (top-down 32bpp) and is written
    // once from a buffer of exactly that size; the bitmaps are deleted after CreateIconIndirect
    // has copied them.
    unsafe {
        let mut bi: BITMAPINFO = std::mem::zeroed();
        bi.bmiHeader = BITMAPINFOHEADER {
            biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
            biWidth: w as i32,
            biHeight: -(h as i32),
            biPlanes: 1,
            biBitCount: 32,
            biCompression: BI_RGB,
            ..std::mem::zeroed()
        };
        let mut bits: *mut c_void = null_mut();
        let color = CreateDIBSection(null_mut(), &bi, DIB_RGB_COLORS, &mut bits, null_mut(), 0);
        if color.is_null() || bits.is_null() {
            return None;
        }
        std::ptr::copy_nonoverlapping(bgra.as_ptr(), bits as *mut u8, bgra.len());
        let mask_bits = vec![0u8; ((w as usize).div_ceil(16) * 2) * h as usize];
        let mask = CreateBitmap(
            w as i32,
            h as i32,
            1,
            1,
            mask_bits.as_ptr() as *const c_void,
        );
        if mask.is_null() {
            DeleteObject(color);
            return None;
        }
        let info = ICONINFO {
            fIcon: 1,
            xHotspot: 0,
            yHotspot: 0,
            hbmMask: mask,
            hbmColor: color,
        };
        let icon = CreateIconIndirect(&info as *const ICONINFO as *mut ICONINFO);
        DeleteObject(color);
        DeleteObject(mask);
        (!icon.is_null()).then_some(icon)
    }
}

impl State {
    fn notify_icon(&self, msg: u32, data: &mut NOTIFYICONDATAW) -> bool {
        // SAFETY: `data` is a fully initialised NOTIFYICONDATAW with the correct cbSize.
        unsafe { Shell_NotifyIconW(msg, data) != 0 }
    }

    fn set_version(&mut self, id: u32) {
        let mut d = nid(self.hwnd, id, 0);
        d.Anonymous.uVersion = 4;
        self.v4 = self.notify_icon(NIM_SETVERSION, &mut d);
    }

    fn add_tray(&mut self) -> bool {
        let icon = if self.tray_icon != 0 {
            self.tray_icon as HICON
        } else {
            default_icon()
        };
        let mut d = nid(
            self.hwnd,
            TRAY_ID,
            NIF_ICON | NIF_TIP | NIF_MESSAGE | NIF_SHOWTIP,
        );
        d.hIcon = icon;
        fill(&mut d.szTip, &self.tray_tip);
        if self.notify_icon(NIM_ADD, &mut d) {
            self.set_version(TRAY_ID);
            self.tray_added = true;
            true
        } else {
            self.tray_added = false;
            false
        }
    }

    fn remove_temp(&mut self) {
        if self.temp_added {
            let mut d = nid(self.hwnd, TEMP_ID, 0);
            self.notify_icon(NIM_DELETE, &mut d);
            self.temp_added = false;
        }
    }

    fn end_balloon(&mut self) {
        if let Some(b) = self.balloon.take() {
            if b.icon_id == TEMP_ID {
                self.remove_temp();
            }
        }
        // SAFETY: killing a timer of our own window; failure (no timer) is harmless.
        unsafe { KillTimer(self.hwnd as HWND, TIMER_BALLOON) };
    }

    fn balloon_event(&mut self, event: &str) -> Option<Value> {
        let token = self.balloon.as_ref()?.token;
        self.end_balloon();
        Some(json!({"type":"notification","token":token,"event":event}))
    }
}

// ---------------------------------------------------------------- window procedure

unsafe extern "system" fn wndproc(hwnd: HWND, msg: u32, wp: WPARAM, lp: LPARAM) -> LRESULT {
    // The body is panic-free by construction; catch_unwind keeps an unforeseen panic from
    // unwinding through the system frame.
    let r = std::panic::catch_unwind(|| handle_message(msg, wp, lp));
    match r {
        Ok(Some(v)) => v,
        // SAFETY: forwarding the unchanged message of this window to the default procedure.
        _ => DefWindowProcW(hwnd, msg, wp, lp),
    }
}

fn handle_message(msg: u32, wp: WPARAM, lp: LPARAM) -> Option<LRESULT> {
    match msg {
        WM_TRAY => {
            tray_callback(wp, lp);
            Some(0)
        }
        WM_HOTKEY => {
            let ev = with_state(|s| {
                s.hotkey_ids
                    .get(&(wp as i32))
                    .map(|id| (s.sink.clone(), json!({"type":"hotkey","id":id})))
            })
            .flatten();
            if let Some((sink, e)) = ev {
                emit(&sink, vec![e]);
            }
            Some(0)
        }
        WM_TIMER if wp == TIMER_BALLOON => {
            let ev =
                with_state(|s| s.balloon_event("expired").map(|e| (s.sink.clone(), e))).flatten();
            if let Some((sink, e)) = ev {
                emit(&sink, vec![e]);
            }
            Some(0)
        }
        WM_SHOW_CONTEXT => {
            show_pending_context();
            Some(0)
        }
        WM_SETTINGCHANGE | WM_SYSCOLORCHANGE | WM_THEMECHANGED => {
            preferences_changed();
            None
        }
        m if m != 0 && with_state(|s| s.taskbar_created == m).unwrap_or(false) => {
            taskbar_created();
            Some(0)
        }
        _ => None,
    }
}

fn tray_callback(wp: WPARAM, lp: LPARAM) {
    let v4 = with_state(|s| s.v4).unwrap_or(true);
    let (event, id) = if v4 {
        ((lp as u32) & 0xFFFF, ((lp as u32) >> 16) & 0xFFFF)
    } else {
        (lp as u32, wp as u32)
    };
    let mut events = Vec::new();
    let mut open_menu = false;
    let sink = match with_state(|s| s.sink.clone()) {
        Some(s) => s,
        None => return,
    };
    if id == TRAY_ID {
        match event {
            NIN_SELECT | NIN_KEYSELECT => events.push(json!({"type":"tray","event":"activate"})),
            WM_LBUTTONUP if !v4 => events.push(json!({"type":"tray","event":"activate"})),
            WM_CONTEXTMENU => {
                events.push(json!({"type":"tray","event":"context"}));
                open_menu = true;
            }
            WM_RBUTTONUP if !v4 => {
                events.push(json!({"type":"tray","event":"context"}));
                open_menu = true;
            }
            _ => {}
        }
    }
    if matches!(id, TRAY_ID | TEMP_ID) {
        let ev = match event {
            NIN_BALLOONUSERCLICK => Some("clicked"),
            NIN_BALLOONTIMEOUT => Some("expired"),
            NIN_BALLOONHIDE => Some("dismissed"),
            _ => None,
        };
        if let Some(ev) = ev {
            // only the icon that carries the current balloon reports it
            if let Some(Some(e)) = with_state(|s| {
                if s.balloon.as_ref().is_some_and(|b| b.icon_id == id) {
                    s.balloon_event(ev)
                } else {
                    None
                }
            }) {
                events.push(e);
            }
        }
    }
    emit(&sink, events);
    if open_menu {
        show_tray_menu(&sink);
    }
}

fn show_tray_menu(sink: &Sink) {
    let Some((hwnd, items, busy)) = with_state(|s| {
        let busy = s.in_popup;
        if !busy {
            s.in_popup = true;
        }
        (s.hwnd, s.tray_menu.clone(), busy)
    }) else {
        return;
    };
    if busy {
        return;
    }
    let result = (|| {
        if items.is_empty() {
            return None;
        }
        let mut ids = Vec::new();
        let plan = plan_menu(&items, &mut 1, &mut ids);
        // SAFETY: owner thread; the menu is destroyed below; the modal loop runs with no state
        // borrowed.
        unsafe {
            let menu = realize(&plan, false)?;
            let mut pt = POINT { x: 0, y: 0 };
            GetCursorPos(&mut pt);
            SetForegroundWindow(hwnd as HWND);
            let cmd = TrackPopupMenuEx(
                menu,
                TPM_RETURNCMD | TPM_RIGHTBUTTON,
                pt.x,
                pt.y,
                hwnd as HWND,
                null(),
            );
            PostMessageW(hwnd as HWND, WM_NULL, 0, 0);
            DestroyMenu(menu);
            ids.into_iter()
                .find(|(c, _)| *c as i32 == cmd)
                .map(|(_, id)| id)
        }
    })();
    with_state(|s| s.in_popup = false);
    if let Some(command) = result {
        sink(json!({"type":"menu_command","source":"tray","command":command}));
    }
}

fn show_pending_context() {
    let Some((pending, sink)) = with_state(|s| {
        if s.in_popup {
            return None;
        }
        s.pending_context.take().map(|p| {
            s.in_popup = true;
            (p, s.sink.clone())
        })
    })
    .flatten() else {
        return;
    };
    // SAFETY: owner thread; the owner window is checked alive; the menu is destroyed below and no
    // state is borrowed while the modal menu loop runs.
    let cmd = unsafe {
        if IsWindow(pending.hwnd as HWND) == 0 {
            0
        } else if let Some(menu) = realize(&pending.plan, false) {
            let mut pt = POINT {
                x: pending.x,
                y: pending.y,
            };
            ClientToScreen(pending.hwnd as HWND, &mut pt);
            let c = TrackPopupMenuEx(
                menu,
                TPM_RETURNCMD | TPM_RIGHTBUTTON,
                pt.x,
                pt.y,
                pending.hwnd as HWND,
                null(),
            );
            DestroyMenu(menu);
            c
        } else {
            0
        }
    };
    with_state(|s| s.in_popup = false);
    if cmd > 0 {
        if let Some(command) = pending.ids.get(&(cmd as u16)) {
            sink(
                json!({"type":"menu_command","source":"context","window":pending.window,"command":command}),
            );
        }
    }
}

fn taskbar_created() {
    let ev = with_state(|s| {
        s.temp_added = false;
        if s.tray_added {
            s.tray_added = false;
            s.add_tray();
        }
        s.balloon_event("dismissed").map(|e| (s.sink.clone(), e))
    })
    .flatten();
    if let Some((sink, e)) = ev {
        emit(&sink, vec![e]);
    }
}

fn preferences_changed() {
    let now = read_preferences();
    let change = with_state(|s| {
        let old = s.last_prefs;
        s.last_prefs = now;
        let mut ev = json!({"type":"system_preferences"});
        let mut any = false;
        if now.0.is_some() && now.0 != old.0 {
            ev["dark"] = json!(now.0);
            any = true;
        }
        if now.1.is_some() && now.1 != old.1 {
            ev["high_contrast"] = json!(now.1);
            any = true;
        }
        any.then(|| (s.sink.clone(), ev))
    })
    .flatten();
    if let Some((sink, ev)) = change {
        emit(&sink, vec![ev]);
    }
}

/// Messages of app windows (Win32 `MSG`) offered to the adapter first (menu `WM_COMMAND`,
/// settings and Explorer-restart broadcasts that message-only windows do not receive).
pub fn msg_hook(msg: *const c_void) -> bool {
    if msg.is_null() {
        return false;
    }
    // SAFETY: winit passes a valid `*const MSG` for the duration of the call.
    let m = unsafe { &*(msg as *const MSG) };
    match m.message {
        WM_COMMAND if (m.wParam >> 16) & 0xFFFF == 0 => {
            let cmd = (m.wParam & 0xFFFF) as u16;
            let ev = with_state(|s| {
                let w = s.window_menus.get(&(m.hwnd as isize))?;
                let id = w.ids.get(&cmd)?;
                Some((
                    s.sink.clone(),
                    json!({"type":"menu_command","source":"window","window":w.window,"command":id}),
                ))
            })
            .flatten();
            match ev {
                Some((sink, e)) => {
                    emit(&sink, vec![e]);
                    true
                }
                None => false,
            }
        }
        WM_SETTINGCHANGE | WM_SYSCOLORCHANGE | WM_THEMECHANGED => {
            preferences_changed();
            false
        }
        t if t != 0 && with_state(|s| s.taskbar_created == t).unwrap_or(false) => {
            taskbar_created();
            false
        }
        _ => false,
    }
}

// ---------------------------------------------------------------- the adapter

pub struct WindowsServices {
    sink: Sink,
}

impl WindowsServices {
    pub fn new(sink: Sink) -> Self {
        Self { sink }
    }

    /// Create the state and the message window on first use.
    fn ensure(&self) -> Result<(), Refusal> {
        if STATE.with(|c| c.borrow().is_some()) {
            return Ok(());
        }
        // SAFETY: registers a window class and creates a message-only window on this thread; the
        // wndproc above is a valid `extern "system"` function for the life of the process.
        let hwnd = unsafe {
            let hinst = GetModuleHandleW(null());
            let class = wide(CLASS_NAME);
            let wc = WNDCLASSEXW {
                cbSize: std::mem::size_of::<WNDCLASSEXW>() as u32,
                style: 0,
                lpfnWndProc: Some(wndproc),
                cbClsExtra: 0,
                cbWndExtra: 0,
                hInstance: hinst,
                hIcon: null_mut(),
                hCursor: null_mut(),
                hbrBackground: null_mut(),
                lpszMenuName: null(),
                lpszClassName: class.as_ptr(),
                hIconSm: null_mut(),
            };
            RegisterClassExW(&wc); // already registered by an earlier session: fine
            CreateWindowExW(
                0,
                class.as_ptr(),
                null(),
                0,
                0,
                0,
                0,
                0,
                HWND_MESSAGE,
                null_mut(),
                hinst,
                null(),
            )
        };
        if hwnd.is_null() {
            return Err(Refusal::Unavailable(
                "could not create the services message window".into(),
            ));
        }
        // SAFETY: registering a message name; the id is valid process-wide.
        let tbc = unsafe { RegisterWindowMessageW(wide("TaskbarCreated").as_ptr()) };
        STATE.with(|c| {
            *c.borrow_mut() = Some(State {
                sink: self.sink.clone(),
                hwnd: hwnd as isize,
                taskbar_created: tbc,
                v4: true,
                tray_added: false,
                tray_icon: 0,
                tray_tip: String::new(),
                tray_menu: Vec::new(),
                temp_added: false,
                balloon: None,
                hotkeys: HashMap::new(),
                hotkey_ids: HashMap::new(),
                next_hotkey: 1,
                window_menus: HashMap::new(),
                pending_context: None,
                in_popup: false,
                last_prefs: read_preferences(),
            });
        });
        Ok(())
    }

    fn st<R>(&self, f: impl FnOnce(&mut State) -> R) -> Result<R, Refusal> {
        self.ensure()?;
        with_state(f).ok_or_else(|| Refusal::Unavailable("services are busy".into()))
    }
}

impl PlatformServices for WindowsServices {
    fn capabilities(&mut self) -> Vec<(&'static str, Value)> {
        let ok = || json!({"status":"supported"});
        vec![
            (
                "notifications",
                json!({"status":"supported","reason":"balloon-style notifications through the notification area: no action buttons (actions are accepted but not shown), icon paths are ignored, and Focus Assist / Do Not Disturb may suppress them (expired is reported after 30 s without an outcome)"}),
            ),
            ("system_tray", ok()),
            ("native_menus", ok()),
            ("native_menus.context", ok()),
            ("global_hotkeys", ok()),
            ("environment.contrast", ok()),
        ]
    }

    fn notify(&mut self, n: &Notification) -> Result<(), Refusal> {
        self.st(|s| {
            let mut events = Vec::new();
            if let Some(old) = s.balloon.take() {
                events.push(json!({"type":"notification","token":old.token,"event":"replaced"}));
                if old.icon_id == TEMP_ID && s.tray_added {
                    s.remove_temp();
                }
            }
            let icon_id = if s.tray_added {
                TRAY_ID
            } else {
                if !s.temp_added {
                    let mut d = nid(s.hwnd, TEMP_ID, NIF_ICON | NIF_MESSAGE | NIF_STATE);
                    d.hIcon = default_icon();
                    d.dwState = NIS_HIDDEN;
                    d.dwStateMask = NIS_HIDDEN;
                    if !s.notify_icon(NIM_ADD, &mut d) {
                        return Err(Refusal::Unavailable(
                            "the notification area is not available".into(),
                        ));
                    }
                    s.set_version(TEMP_ID);
                    s.temp_added = true;
                }
                TEMP_ID
            };
            let mut d = nid(s.hwnd, icon_id, NIF_INFO);
            fill(&mut d.szInfoTitle, &n.title);
            fill(&mut d.szInfo, &n.body);
            d.dwInfoFlags = match n.urgency.as_str() {
                "critical" => NIIF_WARNING,
                "low" => NIIF_INFO | NIIF_NOSOUND,
                _ => NIIF_INFO,
            };
            if !s.notify_icon(NIM_MODIFY, &mut d) {
                if icon_id == TEMP_ID {
                    s.remove_temp();
                }
                return Err(Refusal::Unavailable(
                    "the shell refused the notification".into(),
                ));
            }
            s.balloon = Some(Balloon {
                token: n.token,
                icon_id,
            });
            // SAFETY: timer on our own window.
            unsafe { SetTimer(s.hwnd as HWND, TIMER_BALLOON, BALLOON_SAFETY_MS, None) };
            let sink = s.sink.clone();
            emit(&sink, events);
            Ok(())
        })?
    }

    fn close_notification(&mut self, token: u64) {
        let _ = self.st(|s| {
            if s.balloon.as_ref().map(|b| b.token) != Some(token) {
                return;
            }
            let id = s.balloon.as_ref().map(|b| b.icon_id).unwrap_or(TRAY_ID);
            // An empty info text removes the balloon.
            let mut d = nid(s.hwnd, id, NIF_INFO);
            s.notify_icon(NIM_MODIFY, &mut d);
            if let Some(e) = s.balloon_event("dismissed") {
                let sink = s.sink.clone();
                emit(&sink, vec![e]);
            }
        });
    }

    fn set_tray(&mut self, tray: Option<&Tray>) -> Result<(), Refusal> {
        if tray.is_none() && STATE.with(|c| c.borrow().is_none()) {
            return Ok(());
        }
        self.st(|s| {
            let Some(t) = tray else {
                if s.tray_added {
                    let mut d = nid(s.hwnd, TRAY_ID, 0);
                    s.notify_icon(NIM_DELETE, &mut d);
                    s.tray_added = false;
                    if s.balloon.as_ref().is_some_and(|b| b.icon_id == TRAY_ID) {
                        if let Some(e) = s.balloon_event("dismissed") {
                            let sink = s.sink.clone();
                            emit(&sink, vec![e]);
                        }
                    }
                }
                if s.tray_icon != 0 {
                    // SAFETY: the icon was created by `make_icon` and is no longer in use.
                    unsafe { DestroyIcon(s.tray_icon as HICON) };
                    s.tray_icon = 0;
                }
                s.tray_menu.clear();
                return Ok(());
            };
            let new_icon = match &t.icon {
                Some((px, w, h)) => make_icon(px, *w, *h).map(|i| i as isize).unwrap_or(0),
                None => 0,
            };
            let old_icon = std::mem::replace(&mut s.tray_icon, new_icon);
            s.tray_tip = t.tooltip.clone();
            s.tray_menu = t.menu.clone();
            let ok = if s.tray_added {
                let mut d = nid(
                    s.hwnd,
                    TRAY_ID,
                    NIF_ICON | NIF_TIP | NIF_MESSAGE | NIF_SHOWTIP,
                );
                d.hIcon = if new_icon != 0 {
                    new_icon as HICON
                } else {
                    default_icon()
                };
                fill(&mut d.szTip, &t.tooltip);
                s.notify_icon(NIM_MODIFY, &mut d)
            } else {
                s.add_tray()
            };
            if old_icon != 0 {
                // SAFETY: the shell has been given the new icon; the old one is ours to free.
                unsafe { DestroyIcon(old_icon as HICON) };
            }
            if ok {
                Ok(())
            } else {
                Err(Refusal::Unavailable(
                    "the shell refused the notification-area icon".into(),
                ))
            }
        })?
    }

    fn set_window_menu(
        &mut self,
        window: u64,
        handle: Option<super::winit_handle::Raw>,
        menu: Option<&[MenuItem]>,
    ) -> Result<(), Refusal> {
        let hwnd = hwnd_of(handle)
            .ok_or_else(|| Refusal::Unavailable("the window has no native handle".into()))?;
        if menu.is_none() && STATE.with(|c| c.borrow().is_none()) {
            return Ok(());
        }
        self.st(|s| {
            // forget menus of windows that no longer exist (the system destroyed their menus)
            // SAFETY: IsWindow accepts any handle value.
            s.window_menus
                .retain(|h, _| unsafe { IsWindow(*h as HWND) } != 0);
            let new = match menu {
                None => None,
                Some(items) => {
                    if !s.window_menus.contains_key(&hwnd)
                        && s.window_menus.len() >= MAX_WINDOW_MENUS
                    {
                        return Err(Refusal::Unavailable("too many windows with menus".into()));
                    }
                    let mut ids = Vec::new();
                    let plan = plan_menu(items, &mut 1, &mut ids);
                    // SAFETY: owner thread; ownership passes to SetMenu below.
                    let h = unsafe { realize(&plan, true) }
                        .ok_or_else(|| Refusal::Unavailable("could not build the menu".into()))?;
                    Some(WinMenu {
                        window,
                        hmenu: h as isize,
                        ids: ids.into_iter().collect(),
                    })
                }
            };
            // SAFETY: `hwnd` is the app's window on this thread; SetMenu with null removes the
            // menu; the replaced menu is detached before it is destroyed.
            let ok = unsafe {
                let ok = SetMenu(
                    hwnd as HWND,
                    new.as_ref().map(|m| m.hmenu as HMENU).unwrap_or(null_mut()),
                ) != 0;
                if ok {
                    DrawMenuBar(hwnd as HWND);
                }
                ok
            };
            if !ok {
                if let Some(n) = new {
                    // SAFETY: never attached.
                    unsafe { DestroyMenu(n.hmenu as HMENU) };
                }
                return Err(Refusal::Unavailable("could not attach the menu".into()));
            }
            if let Some(old) = s.window_menus.remove(&hwnd) {
                // SAFETY: detached by the SetMenu above.
                unsafe { DestroyMenu(old.hmenu as HMENU) };
            }
            if let Some(n) = new {
                s.window_menus.insert(hwnd, n);
            }
            Ok(())
        })?
    }

    fn show_context_menu(
        &mut self,
        window: u64,
        handle: Option<super::winit_handle::Raw>,
        x: f64,
        y: f64,
        menu: &[MenuItem],
    ) -> Result<(), Refusal> {
        let hwnd = hwnd_of(handle)
            .ok_or_else(|| Refusal::Unavailable("the window has no native handle".into()))?;
        self.st(|s| {
            let mut ids = Vec::new();
            let plan = plan_menu(menu, &mut 1, &mut ids);
            s.pending_context = Some(PendingContext {
                hwnd,
                window,
                x: x.round() as i32,
                y: y.round() as i32,
                plan,
                ids: ids.into_iter().collect(),
            });
            // The modal menu loop runs from the message pump, not inside this request.
            // SAFETY: posting to our own message window.
            if unsafe { PostMessageW(s.hwnd as HWND, WM_SHOW_CONTEXT, 0, 0) } == 0 {
                s.pending_context = None;
                return Err(Refusal::Unavailable("could not show the menu".into()));
            }
            Ok(())
        })?
    }

    fn register_hotkey(&mut self, id: &str, accelerator: &Accelerator) -> Result<(), Refusal> {
        let vk = virtual_key(&accelerator.key).ok_or_else(|| {
            Refusal::Unsupported(format!(
                "key {} has no Windows virtual key",
                accelerator.key
            ))
        })?;
        let mods = hotkey_modifiers(accelerator);
        self.st(|s| {
            if let Some(old) = s.hotkeys.remove(id) {
                s.hotkey_ids.remove(&old);
                // SAFETY: unregistering our own hot key id.
                unsafe { UnregisterHotKey(s.hwnd as HWND, old) };
            } else if s.hotkeys.len() >= MAX_HOTKEYS {
                return Err(Refusal::Denied(format!(
                    "at most {MAX_HOTKEYS} global shortcuts"
                )));
            }
            let n = s.next_hotkey;
            // SAFETY: registering on our message window; ids stay within 1..0xBFFF.
            if unsafe { RegisterHotKey(s.hwnd as HWND, n, mods, vk) } == 0 {
                // SAFETY: reads the calling thread's last error.
                let e = unsafe { GetLastError() };
                return Err(if e == ERROR_HOTKEY_ALREADY_REGISTERED {
                    Refusal::Conflict("the shortcut is registered by another application".into())
                } else {
                    Refusal::Denied(format!("the system refused the shortcut (error {e})"))
                });
            }
            s.next_hotkey = if n >= 0xBFFF { 1 } else { n + 1 };
            s.hotkeys.insert(id.to_string(), n);
            s.hotkey_ids.insert(n, id.to_string());
            Ok(())
        })?
    }

    fn unregister_hotkey(&mut self, id: &str) {
        let _ = self.st(|s| {
            if let Some(n) = s.hotkeys.remove(id) {
                s.hotkey_ids.remove(&n);
                // SAFETY: unregistering our own hot key id.
                unsafe { UnregisterHotKey(s.hwnd as HWND, n) };
            }
        });
    }

    fn system_preferences(&mut self) -> (Option<bool>, Option<bool>) {
        let now = read_preferences();
        let _ = self.st(|s| s.last_prefs = now);
        now
    }

    fn shutdown(&mut self) {
        let Some(mut s) = STATE.with(|c| c.borrow_mut().take()) else {
            return;
        };
        s.balloon = None;
        s.remove_temp();
        // SAFETY: owner thread; every handle below was created by this adapter.
        unsafe {
            KillTimer(s.hwnd as HWND, TIMER_BALLOON);
            if s.tray_added {
                let d = nid(s.hwnd, TRAY_ID, 0);
                Shell_NotifyIconW(NIM_DELETE, &d);
            }
            if s.tray_icon != 0 {
                DestroyIcon(s.tray_icon as HICON);
            }
            for n in s.hotkeys.values() {
                UnregisterHotKey(s.hwnd as HWND, *n);
            }
            for (h, m) in s.window_menus.drain() {
                if IsWindow(h as HWND) != 0 {
                    SetMenu(h as HWND, null_mut());
                }
                DestroyMenu(m.hmenu as HMENU);
            }
            DestroyWindow(s.hwnd as HWND);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Mutex};

    fn items(v: Value) -> Vec<MenuItem> {
        serde_json::from_value(v).unwrap()
    }

    #[test]
    fn keys_and_modifiers_map_to_windows_codes() {
        assert_eq!(virtual_key("K"), Some(0x4B));
        assert_eq!(virtual_key("5"), Some(0x35));
        assert_eq!(virtual_key("F1"), Some(0x70));
        assert_eq!(virtual_key("F24"), Some(0x87));
        assert_eq!(virtual_key("Space"), Some(0x20));
        assert_eq!(virtual_key("PageDown"), Some(0x22));
        assert_eq!(virtual_key("Plus"), Some(0xBB));
        assert_eq!(virtual_key("Bogus"), None);
        let a = Accelerator::parse("Ctrl+Alt+Shift+Win+K").unwrap();
        assert_eq!(
            hotkey_modifiers(&a),
            MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_WIN | MOD_NOREPEAT
        );
        assert_eq!(
            hotkey_modifiers(&Accelerator::parse("Ctrl+K").unwrap()),
            MOD_CONTROL | MOD_NOREPEAT
        );
    }

    #[test]
    fn labels_escape_ampersands_and_show_accelerators() {
        assert_eq!(menu_text("Save & Quit", None), "Save && Quit");
        assert_eq!(menu_text("Open", Some("ctrl+o")), "Open\tCtrl+O");
    }

    #[test]
    fn pixels_convert_to_bgra() {
        assert_eq!(
            rgba_to_bgra(&[1, 2, 3, 4, 5, 6, 7, 8]),
            vec![3, 2, 1, 4, 7, 6, 5, 8]
        );
        assert!(make_icon(&[0; 3], 1, 1).is_none());
    }

    #[test]
    fn command_ids_map_back_to_items() {
        let m = items(json!([
            {"label":"File","items":[{"id":"open","label":"Open","accelerator":"Ctrl+O"},{"separator":true},{"id":"quit","label":"Quit","enabled":false}]},
            {"id":"dark","label":"Dark","checked":true}
        ]));
        let mut ids = Vec::new();
        let plan = plan_menu(&m, &mut 1, &mut ids);
        assert_eq!(
            ids,
            vec![(1, "open".into()), (2, "quit".into()), (3, "dark".into())]
        );
        assert_eq!(plan.len(), 2);
        match &plan[0] {
            Plan::Submenu { children, .. } => {
                assert_eq!(children[1], Plan::Separator);
                assert!(matches!(
                    &children[2],
                    Plan::Command {
                        cmd: 2,
                        enabled: false,
                        ..
                    }
                ));
            }
            _ => panic!("submenu expected"),
        }
        assert!(matches!(
            &plan[1],
            Plan::Command {
                cmd: 3,
                checked: true,
                ..
            }
        ));
    }

    #[test]
    fn fill_truncates_with_nul() {
        let mut b = [9u16; 4];
        fill(&mut b, "abcdef");
        assert_eq!(b, [97, 98, 99, 0]);
    }

    #[test]
    fn message_window_hotkeys_menus_and_tray_round_trip() {
        let events: Arc<Mutex<Vec<Value>>> = Default::default();
        let e2 = events.clone();
        let sink: Sink = Arc::new(move |v| e2.lock().unwrap().push(v));
        let mut svc = WindowsServices::new(sink);
        if svc.ensure().is_err() {
            eprintln!("skipped: no message window in this session");
            return;
        }
        let a = Accelerator::parse("Ctrl+Alt+Shift+F23").unwrap();
        match svc.register_hotkey("t1", &a) {
            Ok(()) => {
                // a second registration of the same chord (another id) must conflict
                assert!(matches!(
                    svc.register_hotkey("t2", &a),
                    Err(Refusal::Conflict(_))
                ));
                let (hwnd, n) = with_state(|s| (s.hwnd, s.hotkeys["t1"])).unwrap();
                // SAFETY: posting to and pumping our own message window on this thread.
                unsafe {
                    use windows_sys::Win32::UI::WindowsAndMessaging::{
                        DispatchMessageW, PeekMessageW, PM_REMOVE,
                    };
                    PostMessageW(hwnd as HWND, WM_HOTKEY, n as usize, 0);
                    let mut m: MSG = std::mem::zeroed();
                    while PeekMessageW(&mut m, null_mut(), 0, 0, PM_REMOVE) != 0 {
                        DispatchMessageW(&m);
                    }
                }
                assert!(events
                    .lock()
                    .unwrap()
                    .contains(&json!({"type":"hotkey","id":"t1"})));
                svc.unregister_hotkey("t1");
                assert!(
                    svc.register_hotkey("t2", &a).is_ok(),
                    "a released chord can be registered again"
                );
            }
            Err(e) => eprintln!("hotkey registration unavailable here: {e:?}"),
        }
        let tray = Tray {
            icon: Some((vec![255; 16 * 16 * 4], 16, 16)),
            tooltip: "ui4me test".into(),
            menu: vec![],
        };
        match svc.set_tray(Some(&tray)) {
            Ok(()) => {
                assert!(svc.set_tray(Some(&tray)).is_ok(), "update");
                assert!(svc.set_tray(None).is_ok());
            }
            Err(e) => eprintln!("tray unavailable here: {e:?}"),
        }
        let (_dark, hc) = svc.system_preferences();
        assert!(hc.is_some(), "high contrast readable");
        svc.shutdown();
        assert!(STATE.with(|c| c.borrow().is_none()));
    }
}
