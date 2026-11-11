//! Stable host seam around the private owner-thread document engine.
#[cfg(any(feature = "native", test))]
pub use ui4me_renderer::Input;
#[cfg(feature = "native")]
pub use ui4me_renderer::{Clipboard, ImeState};
pub use ui4me_renderer::{Document, MAX_PIXELS};
impl From<ui4me_renderer::Error> for crate::Error {
    fn from(error: ui4me_renderer::Error) -> Self {
        Self {
            code: error.code,
            message: error.message,
        }
    }
}
