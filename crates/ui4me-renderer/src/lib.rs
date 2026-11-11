//! Native HTML/CSS document engine. Backend stages are private implementation details.
// Private backend helpers also support internal regression/diagnostic tools. Keeping
// them private intentionally makes them unreachable to application callers.
#[allow(dead_code)]
pub(crate) mod diagnostics;
mod document;
#[allow(dead_code)]
pub(crate) mod interaction;
#[allow(dead_code)]
pub(crate) mod layout;
#[allow(dead_code)]
pub(crate) mod pipeline;
#[allow(dead_code)]
pub(crate) mod raster;
#[allow(dead_code)]
pub(crate) mod scene;
#[allow(dead_code)]
pub(crate) mod style;
#[allow(dead_code)]
pub(crate) mod text;
pub use document::{Clipboard, Document, Error, ImeState, Input, MAX_PIXELS, MAX_TEXT, Result};

#[cfg(test)]
mod regression;
