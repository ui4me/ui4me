//! Read-only document text selection (Core 0.3 S4).
//!
//! A selection point is anchored to the DOM, not to a layout epoch: the inline root element of a
//! paragraph, the ordinal of that paragraph among the root's paragraphs (anonymous blocks may give
//! one element several), and a UTF-8 byte offset into the paragraph's processed text. Mutations
//! elsewhere (a growing log) leave a selection intact; text replaced inside the selected
//! paragraph clamps its offsets; a removed root clears it.
//!
//! Paragraphs are ordered as layout lists them (document order for in-flow content). The
//! contents of form controls and generated (`::before`/`::after`) text are never part of the
//! document selection, so a password value cannot be selected or copied through it.
//! The highlight is a translucent overlay blended over the rasterized frame, clipped to the
//! scrollports of the text's scroll containers.
use super::*;
use crate::layout::fragment::{FragmentId, FragmentKind, FragmentTree};
use std::collections::HashMap;

/// One DOM-anchored selection end.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) struct SelPoint {
    root: NodeId,
    nth: u32,
    byte: usize,
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum Unit {
    Char,
    /// The anchor unit of a double/triple-click drag, in paragraph-index space.
    Range(usize, usize, usize, usize),
}

#[derive(Debug, Default)]
pub(super) struct DocSelection {
    anchor: Option<SelPoint>,
    focus: Option<SelPoint>,
    dragging: bool,
    unit: Option<Unit>,
    last_click: Option<(Instant, f64, f64, u8)>,
}

/// Paragraph-index resolved point.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
struct Resolved {
    para: usize,
    byte: usize,
}

struct Para {
    root: NodeId,
    nth: u32,
    frags: Vec<FragmentId>,
}

/// The selectable paragraphs of the committed layout.
struct TextIndex {
    paras: HashMap<usize, Para>,
    by_root: HashMap<(NodeId, u32), usize>,
    order: Vec<usize>,
}

type Area = (f64, f64, f64, f64);
type Ordered = (
    Arc<crate::pipeline::publish::CommittedSet>,
    TextIndex,
    Resolved,
    Resolved,
);

const HIGHLIGHT: (u32, u32, u32) = (51, 144, 255);
const HIGHLIGHT_ALPHA: u32 = 90; // of 255
const MULTI_CLICK: Duration = Duration::from_millis(500);

fn in_control(d: &Model, n: NodeId) -> bool {
    d.arena().inclusive_ancestors(n).into_iter().any(|a| {
        d.local_name(a)
            .is_ok_and(|t| matches!(t, "input" | "textarea" | "select" | "button"))
    })
}

fn strip_controls(text: &str) -> String {
    text.chars()
        .filter(|c| {
            !matches!(c, '\u{200B}' | '\u{200E}' | '\u{200F}' | '\u{FEFF}'
                | '\u{202A}'..='\u{202E}' | '\u{2066}'..='\u{2069}')
        })
        .collect()
}

fn floor_boundary(text: &str, byte: usize) -> usize {
    let mut b = byte.min(text.len());
    while !text.is_char_boundary(b) {
        b -= 1;
    }
    b
}

impl TextIndex {
    fn build(tree: &FragmentTree, d: &Model) -> Self {
        // A paragraph's identity is the element of the block that contains its lines (the inline
        // root), found from its first text fragment.
        let mut frags: HashMap<usize, (NodeId, Vec<FragmentId>)> = HashMap::new();
        for (i, f) in tree.fragments.iter().enumerate() {
            if let FragmentKind::Text(tf) = &f.kind
                && tf.pseudo.is_none()
            {
                let id = FragmentId(i as u32);
                match frags.get_mut(&tf.paragraph_index) {
                    Some(p) => p.1.push(id),
                    None => {
                        if let Some(root) = Document::container_of(tree, id) {
                            frags.insert(tf.paragraph_index, (root, vec![id]));
                        }
                    }
                }
            }
        }
        let mut paras = HashMap::new();
        let mut by_root = HashMap::new();
        let mut order: Vec<usize> = frags.keys().copied().collect();
        order.sort_unstable();
        let mut counts: HashMap<NodeId, u32> = HashMap::new();
        order.retain(|&i| {
            let (root, list) = frags.remove(&i).expect("indexed paragraph");
            let nth = counts.entry(root).or_insert(0);
            let this = *nth;
            *nth += 1;
            if !d.arena().contains(root) || in_control(d, root) {
                return false;
            }
            by_root.insert((root, this), i);
            paras.insert(
                i,
                Para {
                    root,
                    nth: this,
                    frags: list,
                },
            );
            true
        });
        Self {
            paras,
            by_root,
            order,
        }
    }
    fn resolve(&self, tree: &FragmentTree, p: SelPoint) -> Option<Resolved> {
        let para = *self.by_root.get(&(p.root, p.nth))?;
        let text = tree.paragraphs.get(para)?.text();
        Some(Resolved {
            para,
            byte: floor_boundary(text, p.byte),
        })
    }
    fn point(&self, r: Resolved) -> Option<SelPoint> {
        let p = self.paras.get(&r.para)?;
        Some(SelPoint {
            root: p.root,
            nth: p.nth,
            byte: r.byte,
        })
    }
}

impl Document {
    fn committed_tree(&mut self) -> Result<Option<Arc<crate::pipeline::publish::CommittedSet>>> {
        self.pipeline.flush()?;
        Ok(self.pipeline.committed.clone())
    }
    /// The viewport offset of content inside `container`'s scroll chain (its own scroll included).
    fn content_scroll(&self, container: Option<NodeId>) -> (f64, f64) {
        let chain = match container {
            Some(n) => self.pipeline.scroll_chain(n),
            None => self
                .pipeline
                .scroll_entry(ScrollTarget::Viewport)
                .into_iter()
                .collect(),
        };
        chain
            .iter()
            .fold((0.0, 0.0), |a, e| (a.0 + e.offset.0, a.1 + e.offset.1))
    }
    fn container_of(tree: &FragmentTree, f: FragmentId) -> Option<NodeId> {
        let mut at = tree.get(f).parent;
        while let Some(id) = at {
            if let FragmentKind::Box(b) = &tree.get(id).kind
                && let Some(n) = b.owner_node()
            {
                return Some(n);
            }
            at = tree.get(id).parent;
        }
        None
    }
    /// Viewport geometry of one text fragment: its line's vertical extent, its horizontal origin
    /// and the paragraph-space x of its first cluster.
    fn frag_geometry(
        &self,
        tree: &FragmentTree,
        f: FragmentId,
        scroll: &mut HashMap<Option<NodeId>, (f64, f64)>,
    ) -> Option<(
        f64,
        f64,
        f64,
        f64,
        f64,
        Vec<crate::text::paragraph::frozen::ClusterExtent>,
    )> {
        let FragmentKind::Text(tf) = &tree.get(f).kind else {
            return None;
        };
        let container = Self::container_of(tree, f);
        let (sx, sy) = *scroll
            .entry(container)
            .or_insert_with(|| self.content_scroll(container));
        let r = tree.document_rect(f).rect;
        let line = tree
            .get(f)
            .parent
            .map(|l| tree.document_rect(l).rect)
            .unwrap_or(r);
        let p = tree.paragraphs.get(tf.paragraph_index)?;
        let clusters: Vec<_> = p
            .cluster_extents(tf.line_index)
            .into_iter()
            .filter(|c| {
                c.start >= tf.text_range.start && c.end <= tf.text_range.end && c.end > c.start
            })
            .collect();
        let base = clusters.iter().map(|c| c.x0).fold(f32::INFINITY, f32::min);
        let base = if base.is_finite() {
            f64::from(base)
        } else {
            0.0
        };
        Some((
            r.origin.x.to_f64() - sx,
            line.origin.y.to_f64() - sy,
            r.size.width.to_f64(),
            line.size.height.to_f64(),
            base,
            clusters,
        ))
    }
    /// The selectable text position nearest to a viewport point.
    fn position_at(
        &self,
        tree: &FragmentTree,
        index: &TextIndex,
        x: f64,
        y: f64,
    ) -> Option<Resolved> {
        let mut scroll = HashMap::new();
        let mut best: Option<((f64, f64), Resolved)> = None;
        for &para in &index.order {
            for &f in &index.paras[&para].frags {
                let Some((fx, fy, fw, fh, base, clusters)) =
                    self.frag_geometry(tree, f, &mut scroll)
                else {
                    continue;
                };
                let dy = if y < fy {
                    fy - y
                } else if y > fy + fh {
                    y - fy - fh
                } else {
                    0.0
                };
                let dx = if x < fx {
                    fx - x
                } else if x > fx + fw {
                    x - fx - fw
                } else {
                    0.0
                };
                if best.as_ref().is_some_and(|(d, _)| (dy, dx) >= *d) {
                    continue;
                }
                let FragmentKind::Text(tf) = &tree.get(f).kind else {
                    continue;
                };
                let mut byte = tf.text_range.start;
                for c in &clusters {
                    let x0 = fx + f64::from(c.x0) - base;
                    let x1 = fx + f64::from(c.x1) - base;
                    let (lead, trail) = if c.rtl {
                        (c.end, c.start)
                    } else {
                        (c.start, c.end)
                    };
                    if x >= (x0 + x1) / 2.0 {
                        byte = trail;
                    } else {
                        byte = lead;
                        if !c.rtl {
                            break;
                        }
                    }
                }
                best = Some(((dy, dx), Resolved { para, byte }));
            }
        }
        best.map(|(_, r)| r)
    }
    fn ordered(&mut self) -> Result<Option<Ordered>> {
        let (Some(a), Some(f)) = (self.selection.anchor, self.selection.focus) else {
            return Ok(None);
        };
        let Some(c) = self.committed_tree()? else {
            return Ok(None);
        };
        let tree = &c.layout.fragments;
        let index = TextIndex::build(tree, self.pipeline.document());
        let (Some(a), Some(f)) = (index.resolve(tree, a), index.resolve(tree, f)) else {
            self.selection.anchor = None;
            self.selection.focus = None;
            self.repaint = true;
            return Ok(None);
        };
        let (start, end) = if a <= f { (a, f) } else { (f, a) };
        if start == end {
            return Ok(None);
        }
        Ok(Some((c, index, start, end)))
    }
    /// The selected text: each paragraph's rendered text, paragraphs joined by a line feed.
    pub fn selection_text(&mut self) -> Result<String> {
        let Some((c, index, start, end)) = self.ordered()? else {
            return Ok(String::new());
        };
        let tree = &c.layout.fragments;
        let mut out = String::new();
        let mut first = true;
        for &para in index
            .order
            .iter()
            .filter(|&&p| p >= start.para && p <= end.para)
        {
            let text = tree.paragraphs[para].text();
            let s = if para == start.para { start.byte } else { 0 };
            let e = if para == end.para {
                end.byte
            } else {
                text.len()
            };
            if !first {
                out.push('\n');
            }
            first = false;
            out.push_str(&strip_controls(text.get(s..e).unwrap_or("")));
            if out.len() > 16 * 1024 * 1024 {
                return Err(limit_error("Selected text exceeds 16 MiB"));
            }
        }
        Ok(out)
    }
    pub fn clear_selection(&mut self) {
        if self.selection.anchor.is_some() {
            self.repaint = true;
        }
        self.selection.anchor = None;
        self.selection.focus = None;
        self.selection.dragging = false;
        self.selection.unit = None;
    }
    /// Select all document text inside `element` (or the whole document for `None`).
    pub fn select_text(&mut self, element: Option<&str>) -> Result<()> {
        let scope = element.map(|e| self.node(e)).transpose()?;
        self.clear_selection();
        let Some(c) = self.committed_tree()? else {
            return Ok(());
        };
        let tree = &c.layout.fragments;
        let d = self.pipeline.document();
        let index = TextIndex::build(tree, d);
        let mut first: Option<Resolved> = None;
        let mut last: Option<Resolved> = None;
        for &para in &index.order {
            for &f in &index.paras[&para].frags {
                let FragmentKind::Text(tf) = &tree.get(f).kind else {
                    continue;
                };
                if scope.is_some_and(|s| !d.arena().is_inclusive_ancestor(s, tf.owner)) {
                    continue;
                }
                let a = Resolved {
                    para,
                    byte: tf.text_range.start,
                };
                let b = Resolved {
                    para,
                    byte: tf.text_range.end,
                };
                first = Some(first.map_or(a, |x| x.min(a)));
                last = Some(last.map_or(b, |x| x.max(b)));
            }
        }
        if let (Some(a), Some(b)) = (first, last) {
            self.selection.anchor = index.point(a);
            self.selection.focus = index.point(b);
            self.repaint = true;
        }
        Ok(())
    }
    /// Copy the selection to the clipboard; returns the copied text (empty: nothing copied).
    pub fn copy_selection(&mut self) -> Result<String> {
        let text = self.selection_text()?;
        if !text.is_empty() {
            self.clipboard.write_text(&text).map_err(|e| Error {
                code: 6,
                message: format!("Clipboard write failed: {e}"),
            })?;
        }
        Ok(text)
    }
    pub fn clipboard_text(&mut self) -> Result<Option<String>> {
        self.clipboard.read_text().map_err(|e| Error {
            code: 6,
            message: format!("Clipboard read failed: {e}"),
        })
    }
    pub fn set_clipboard_text(&mut self, text: &str) -> Result<()> {
        if text.len() > 16 * 1024 * 1024 || text.contains('\0') {
            return Err(arg("Clipboard text must be at most 16 MiB without NUL"));
        }
        self.clipboard.write_text(text).map_err(|e| Error {
            code: 6,
            message: format!("Clipboard write failed: {e}"),
        })
    }
    fn focus_in_control(&self) -> bool {
        let d = self.pipeline.document();
        self.interaction
            .focused_element(self.id())
            .is_some_and(|n| in_control(d, n))
    }
    /// Pointer/keyboard handling after the engine processed the input (its events are `events`).
    pub(super) fn selection_input(&mut self, input: &Input, events: &[Value]) -> Result<()> {
        let prevented = |ty: &str| {
            events
                .iter()
                .any(|e| e["type"] == ty && e["default_prevented"] == true)
        };
        match *input {
            Input::PointerButton {
                pressed: true,
                button: 0,
                x,
                y,
            } => {
                if prevented("mousedown") {
                    return Ok(());
                }
                let id = self.id();
                let hit = self.hit_test(id, x, y)?;
                let d = self.pipeline.document();
                if hit.is_some_and(|n| in_control(d, n)) {
                    self.clear_selection();
                    return Ok(());
                }
                let Some(c) = self.committed_tree()? else {
                    return Ok(());
                };
                let tree = &c.layout.fragments;
                let index = TextIndex::build(tree, self.pipeline.document());
                let Some(at) = self.position_at(tree, &index, x, y) else {
                    self.clear_selection();
                    return Ok(());
                };
                let now = Instant::now();
                let count = match self.selection.last_click {
                    Some((t, px, py, n))
                        if now.duration_since(t) < MULTI_CLICK
                            && (px - x).abs() < 4.0
                            && (py - y).abs() < 4.0 =>
                    {
                        n % 3 + 1
                    }
                    _ => 1,
                };
                self.selection.last_click = Some((now, x, y, count));
                let shift = self.modifiers.shift;
                let text = tree.paragraphs[at.para].text();
                let (a, b) = match count {
                    2 => word_at(text, at.byte),
                    3 => (0, text.len()),
                    _ => (at.byte, at.byte),
                };
                let (a, b) = (
                    Resolved {
                        para: at.para,
                        byte: a,
                    },
                    Resolved {
                        para: at.para,
                        byte: b,
                    },
                );
                if shift && count == 1 && self.selection.anchor.is_some() {
                    self.selection.focus = index.point(b);
                } else {
                    self.selection.anchor = index.point(a);
                    self.selection.focus = index.point(b);
                    self.selection.unit =
                        (count > 1).then_some(Unit::Range(a.para, a.byte, b.para, b.byte));
                }
                if count == 1 {
                    self.selection.unit = Some(Unit::Char);
                }
                self.selection.dragging = true;
                self.repaint = true;
            }
            Input::PointerMoved { x, y }
                if self.selection.dragging && self.pointer_buttons & 1 != 0 =>
            {
                let Some(c) = self.committed_tree()? else {
                    return Ok(());
                };
                let tree = &c.layout.fragments;
                let index = TextIndex::build(tree, self.pipeline.document());
                if let Some(at) = self.position_at(tree, &index, x, y) {
                    match self.selection.unit {
                        Some(Unit::Range(ap, ab, bp, bb)) => {
                            let (us, ue) = (
                                Resolved { para: ap, byte: ab },
                                Resolved { para: bp, byte: bb },
                            );
                            let text = tree.paragraphs[at.para].text();
                            let (ws, we) = match () {
                                _ if ap == bp
                                    && ab == 0
                                    && bb == tree.paragraphs[ap].text().len() =>
                                {
                                    (0, text.len())
                                }
                                _ => word_at(text, at.byte),
                            };
                            let (ws, we) = (
                                Resolved {
                                    para: at.para,
                                    byte: ws,
                                },
                                Resolved {
                                    para: at.para,
                                    byte: we,
                                },
                            );
                            if ws < us {
                                self.selection.anchor = index.point(ue);
                                self.selection.focus = index.point(ws);
                            } else {
                                self.selection.anchor = index.point(us);
                                self.selection.focus = index.point(we.max(ue));
                            }
                        }
                        _ => self.selection.focus = index.point(at),
                    }
                    self.repaint = true;
                }
            }
            Input::PointerButton {
                pressed: false,
                button: 0,
                ..
            } => self.selection.dragging = false,
            Input::Focus(false) | Input::PointerLeft if self.pointer_buttons & 1 == 0 => {
                self.selection.dragging = false
            }
            Input::Key {
                ref key,
                pressed: true,
                ctrl,
                alt: false,
                ..
            } if ctrl && !self.focus_in_control() => {
                if prevented("keydown") {
                    return Ok(());
                }
                match key.as_str() {
                    "c" | "C" | "Insert" => {
                        // A clipboard failure must not fail the input event; it is reported as a
                        // document error like other default-action failures.
                        if let Err(e) = self.copy_selection() {
                            self.record_error(
                                self.id(),
                                Status::new(Code::InvalidArgument, Stage::Host)
                                    .with_message(e.message),
                            );
                        }
                    }
                    "a" | "A" => self.select_text(None)?,
                    _ => {}
                }
            }
            _ => {}
        }
        Ok(())
    }
    /// Highlight rectangles (viewport CSS px) clipped to their scrollports.
    fn selection_rects(&mut self) -> Result<Vec<(f64, f64, f64, f64)>> {
        let Some((c, index, start, end)) = self.ordered()? else {
            return Ok(Vec::new());
        };
        let tree = &c.layout.fragments;
        let mut scroll = HashMap::new();
        let mut clips: HashMap<Option<NodeId>, Option<Area>> = HashMap::new();
        let mut out = Vec::new();
        for &para in index
            .order
            .iter()
            .filter(|&&p| p >= start.para && p <= end.para)
        {
            let p = &tree.paragraphs[para];
            let s = if para == start.para { start.byte } else { 0 };
            let e = if para == end.para {
                end.byte
            } else {
                p.text().len()
            };
            for &f in &index.paras[&para].frags {
                let FragmentKind::Text(tf) = &tree.get(f).kind else {
                    continue;
                };
                let (a, b) = (s.max(tf.text_range.start), e.min(tf.text_range.end));
                if a >= b {
                    continue;
                }
                let Some((fx, fy, _, fh, base, _)) = self.frag_geometry(tree, f, &mut scroll)
                else {
                    continue;
                };
                let container = Self::container_of(tree, f);
                let clip = *clips
                    .entry(container)
                    .or_insert_with(|| self.clip_for(container));
                for (x0, x1) in p.selection_spans(tf.line_index, a..b) {
                    let r = (fx + f64::from(x0) - base, fy, f64::from(x1 - x0), fh);
                    if let Some(r) = intersect(r, clip) {
                        out.push(r);
                    }
                }
            }
        }
        Ok(out)
    }
    fn clip_for(&self, container: Option<NodeId>) -> Option<(f64, f64, f64, f64)> {
        let mut clip = (
            f64::NEG_INFINITY,
            f64::NEG_INFINITY,
            f64::INFINITY,
            f64::INFINITY,
        );
        if let Some(n) = container {
            for e in self.pipeline.scroll_chain(n) {
                if e.target == ScrollTarget::Viewport {
                    continue;
                }
                let port = self.scrollport_rect(e.target)?;
                clip = intersect_ltrb(clip, port)?;
            }
        }
        Some((clip.0, clip.1, clip.2 - clip.0, clip.3 - clip.1))
    }
    /// Blend the selection highlight over a rendered frame (device pixels, `0x00RRGGBB`).
    pub(super) fn paint_selection(
        &mut self,
        pixels: &mut [u32],
        width: u32,
        height: u32,
        scale: f64,
    ) -> Result<()> {
        if self.selection.anchor.is_none() {
            return Ok(());
        }
        for (x, y, w, h) in self.selection_rects()? {
            let x0 = ((x * scale).round().max(0.0) as u32).min(width);
            let y0 = ((y * scale).round().max(0.0) as u32).min(height);
            let x1 = (((x + w) * scale).round().max(0.0) as u32).min(width);
            let y1 = (((y + h) * scale).round().max(0.0) as u32).min(height);
            for row in y0..y1 {
                let line = &mut pixels[(row * width) as usize..((row + 1) * width) as usize];
                for px in &mut line[x0 as usize..x1 as usize] {
                    let ch = |shift: u32, c: u32| {
                        let v = (*px >> shift) & 0xff;
                        ((v * (255 - HIGHLIGHT_ALPHA) + c * HIGHLIGHT_ALPHA + 127) / 255) << shift
                    };
                    *px = ch(16, HIGHLIGHT.0) | ch(8, HIGHLIGHT.1) | ch(0, HIGHLIGHT.2);
                }
            }
        }
        Ok(())
    }
}

fn intersect_ltrb(
    a: (f64, f64, f64, f64),
    (x, y, w, h): (f64, f64, f64, f64),
) -> Option<(f64, f64, f64, f64)> {
    let r = (a.0.max(x), a.1.max(y), a.2.min(x + w), a.3.min(y + h));
    (r.0 < r.2 && r.1 < r.3).then_some(r)
}

fn intersect(
    r: (f64, f64, f64, f64),
    clip: Option<(f64, f64, f64, f64)>,
) -> Option<(f64, f64, f64, f64)> {
    let clip = clip?;
    let i = intersect_ltrb((r.0, r.1, r.0 + r.2, r.1 + r.3), clip)?;
    Some((i.0, i.1, i.2 - i.0, i.3 - i.1))
}

/// The word (a run of alphanumeric characters, or a single other character) around `byte`.
fn word_at(text: &str, byte: usize) -> (usize, usize) {
    let byte = floor_boundary(text, byte);
    let is_word = |c: char| c.is_alphanumeric() || c == '_' || c == '\'';
    let after = text[byte..].chars().next();
    let before = text[..byte].chars().next_back();
    let kind = match (before, after) {
        (_, Some(c)) if is_word(c) => true,
        (Some(c), _) if is_word(c) => true,
        (_, Some(c)) => return (byte, byte + c.len_utf8()),
        (Some(c), None) => return (byte - c.len_utf8(), byte),
        (None, None) => return (byte, byte),
    };
    let start = text[..byte]
        .char_indices()
        .rev()
        .take_while(|&(_, c)| is_word(c) == kind)
        .last()
        .map_or(byte, |(i, _)| i);
    let end = text[byte..]
        .char_indices()
        .take_while(|&(_, c)| is_word(c) == kind)
        .last()
        .map_or(byte, |(i, c)| byte + i + c.len_utf8());
    (start, end)
}
