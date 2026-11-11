//! Windows desktop services adapter (Core 0.7). Stub: every service reports unsupported until
//! the platform implementation lands.

use super::{
    Accelerator, MenuItem, Notification, PlatformServices, Refusal, Sink, Tray, Unsupported,
};
use serde_json::Value;

pub struct WindowsServices {
    #[allow(dead_code)]
    sink: Sink,
    fallback: Unsupported,
}

impl WindowsServices {
    pub fn new(sink: Sink) -> Self {
        Self {
            sink,
            fallback: Unsupported("not implemented yet on this platform"),
        }
    }
}

impl PlatformServices for WindowsServices {
    fn capabilities(&mut self) -> Vec<(&'static str, Value)> {
        self.fallback.capabilities()
    }
    fn notify(&mut self, n: &Notification) -> Result<(), Refusal> {
        self.fallback.notify(n)
    }
    fn close_notification(&mut self, token: u64) {
        self.fallback.close_notification(token)
    }
    fn set_tray(&mut self, tray: Option<&Tray>) -> Result<(), Refusal> {
        self.fallback.set_tray(tray)
    }
    fn set_window_menu(
        &mut self,
        window: u64,
        handle: Option<super::winit_handle::Raw>,
        menu: Option<&[MenuItem]>,
    ) -> Result<(), Refusal> {
        self.fallback.set_window_menu(window, handle, menu)
    }
    fn show_context_menu(
        &mut self,
        window: u64,
        handle: Option<super::winit_handle::Raw>,
        x: f64,
        y: f64,
        menu: &[MenuItem],
    ) -> Result<(), Refusal> {
        self.fallback.show_context_menu(window, handle, x, y, menu)
    }
    fn register_hotkey(&mut self, id: &str, accelerator: &Accelerator) -> Result<(), Refusal> {
        self.fallback.register_hotkey(id, accelerator)
    }
    fn unregister_hotkey(&mut self, id: &str) {
        self.fallback.unregister_hotkey(id)
    }
    fn system_preferences(&mut self) -> (Option<bool>, Option<bool>) {
        self.fallback.system_preferences()
    }
    fn shutdown(&mut self) {}
}

/// Messages of app windows (Win32 `MSG`) offered to the adapter first (menu `WM_COMMAND`).
pub fn msg_hook(_msg: *const std::ffi::c_void) -> bool {
    false
}
