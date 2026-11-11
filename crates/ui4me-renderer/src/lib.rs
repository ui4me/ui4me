//! Native HTML/CSS document engine. Backend stages are private implementation details.
// Private backend helpers also support internal regression/diagnostic tools. Keeping
// them private intentionally makes them unreachable to application callers.
pub mod a11y;
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
/// The CSS feature profile: its version and every row (feature id, state name) (1.0 F1102).
pub fn css_profile() -> (&'static str, Vec<(&'static str, &'static str)>) {
    (
        style::profile::VERSION,
        style::profile::table::FEATURES
            .iter()
            .map(|(id, s)| (*id, s.name()))
            .collect(),
    )
}
/// Page size of a pagination request (1.0 F1001).
pub use document::paged_facade::PageSize;
pub use document::{
    Clipboard, DefaultActionRule, Document, DomOp, Error, ImeState, Input, MAX_PIXELS, MAX_TEXT,
    Rect, Result, ScrollState,
};
/// Generation-checked DOM node identity (opaque to hosts).
pub use ui4me_engine_types::ids::NodeId;

#[cfg(test)]
mod regression;
