//! Deliberately small, strict form document. This is not a browser parser.
use crate::{Error, Result};
use font8x8::UnicodeFonts;
use std::collections::{BTreeMap, BTreeSet};

pub const MAX_TEXT: usize = 16 * 1024;
pub const MAX_PIXELS: usize = 16_777_216;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Kind { Heading, Text, Button, Input }

#[derive(Clone, Debug)]
pub struct Element {
    pub id: String,
    pub kind: Kind,
    pub text: String,
}

#[derive(Clone, Debug, Default)]
pub struct Document {
    pub elements: Vec<Element>,
    pub focus: Option<usize>,
    pub scroll: f64,
}

fn decode(raw: &str) -> Result<String> {
    let mut out = String::new();
    let mut rest = raw;
    while let Some(at) = rest.find('&') {
        out.push_str(&rest[..at]);
        rest = &rest[at + 1..];
        let end = rest.find(';').ok_or_else(|| Error::arg("unterminated HTML entity"))?;
        let entity = &rest[..end];
        let ch = match entity {
            "amp" => '&', "lt" => '<', "gt" => '>', "quot" => '"', "apos" | "#39" => '\'',
            x if x.starts_with("#x") || x.starts_with("#X") => {
                u32::from_str_radix(&x[2..], 16).ok().and_then(char::from_u32)
                    .ok_or_else(|| Error::arg("invalid numeric HTML entity"))?
            }
            x if x.starts_with('#') => x[1..].parse::<u32>().ok().and_then(char::from_u32)
                .ok_or_else(|| Error::arg("invalid numeric HTML entity"))?,
            _ => return Err(Error::arg(format!("unsupported HTML entity: &{entity};"))),
        };
        if ch == '\0' { return Err(Error::arg("NUL is not supported in documents")); }
        out.push(ch);
        rest = &rest[end + 1..];
    }
    out.push_str(rest);
    if out.len() > MAX_TEXT { return Err(Error::limit("element text exceeds 16 KiB")); }
    Ok(out)
}

fn tag_end(text: &str) -> Option<usize> {
    let mut quote = None;
    for (at, ch) in text.char_indices() {
        if let Some(q) = quote {
            if ch == q { quote = None; }
        } else if ch == '\'' || ch == '"' { quote = Some(ch); }
        else if ch == '>' { return Some(at); }
    }
    None
}

fn attributes(mut text: &str) -> Result<BTreeMap<String, String>> {
    let mut attrs = BTreeMap::new();
    while !text.trim().is_empty() {
        text = text.trim_start();
        let end = text.find(|c: char| c.is_whitespace() || c == '=').unwrap_or(text.len());
        if end == 0 { return Err(Error::arg("invalid attribute name")); }
        let key = text[..end].to_ascii_lowercase();
        if !matches!(key.as_str(), "id" | "value" | "type") {
            return Err(Error::arg(format!("unsupported attribute: {key}")));
        }
        text = text[end..].trim_start();
        text = text.strip_prefix('=').ok_or_else(|| Error::arg("attributes require quoted values"))?.trim_start();
        let quote = text.chars().next().ok_or_else(|| Error::arg("missing attribute value"))?;
        if quote != '\'' && quote != '"' { return Err(Error::arg("attributes require quoted values")); }
        text = &text[1..];
        let close = text.find(quote).ok_or_else(|| Error::arg("unterminated attribute value"))?;
        if attrs.insert(key, decode(&text[..close])?).is_some() { return Err(Error::arg("duplicate attribute")); }
        text = &text[close + 1..];
        if !text.is_empty() && !text.starts_with(char::is_whitespace) {
            return Err(Error::arg("attributes must be separated by whitespace"));
        }
    }
    Ok(attrs)
}

impl Document {
    pub fn parse(html: &str) -> Result<Self> {
        if html.len() > 1024 * 1024 { return Err(Error::limit("HTML exceeds 1 MiB")); }
        if html.contains('\0') { return Err(Error::arg("NUL in HTML")); }
        let mut doc = Self::default();
        let mut stack: Vec<(String, Option<usize>)> = Vec::new();
        let mut ids = BTreeSet::new();
        let mut rest = html;
        while !rest.is_empty() {
            if let Some(comment) = rest.strip_prefix("<!--") {
                let end = comment.find("-->").ok_or_else(|| Error::arg("unterminated comment"))?;
                rest = &comment[end + 3..];
                continue;
            }
            if let Some(inner) = rest.strip_prefix('<') {
                let end = tag_end(inner).ok_or_else(|| Error::arg("unterminated tag"))?;
                let raw = inner[..end].trim();
                rest = &inner[end + 1..];
                if raw.eq_ignore_ascii_case("!doctype html") { continue; }
                if let Some(close) = raw.strip_prefix('/') {
                    let tag = close.trim().to_ascii_lowercase();
                    let (open, _) = stack.pop().ok_or_else(|| Error::arg("unexpected closing tag"))?;
                    if open != tag { return Err(Error::arg(format!("expected </{open}>, found </{tag}>"))); }
                    continue;
                }
                let self_closing = raw.ends_with('/');
                let raw = if self_closing { raw[..raw.len() - 1].trim_end() } else { raw };
                let sep = raw.find(char::is_whitespace).unwrap_or(raw.len());
                let tag = raw[..sep].to_ascii_lowercase();
                if !matches!(tag.as_str(), "html" | "body" | "div" | "h1" | "p" | "label" | "button" | "input") {
                    return Err(Error::arg(format!("unsupported tag: {tag}")));
                }
                let attrs = attributes(&raw[sep..])?;
                if tag != "input" && (attrs.contains_key("value") || attrs.contains_key("type")) {
                    return Err(Error::arg("value and type are only supported on input"));
                }
                if attrs.get("type").is_some_and(|v| v != "text") { return Err(Error::arg("only input type=text is supported")); }
                let id = attrs.get("id").cloned().unwrap_or_default();
                if id.len() > 256 || id.chars().any(char::is_whitespace) { return Err(Error::arg("invalid element id")); }
                if !id.is_empty() && !ids.insert(id.clone()) { return Err(Error::arg(format!("duplicate element id: {id}"))); }
                let container = matches!(tag.as_str(), "html" | "body") || (tag == "div" && id.is_empty());
                if container && !attrs.is_empty() { return Err(Error::arg("html/body do not accept attributes")); }
                let index = if container { None } else {
                    if doc.elements.len() >= 128 { return Err(Error::limit("document exceeds 128 elements")); }
                    let kind = match tag.as_str() { "h1" => Kind::Heading, "button" => Kind::Button, "input" => Kind::Input, _ => Kind::Text };
                    doc.elements.push(Element { id, kind, text: attrs.get("value").cloned().unwrap_or_default() });
                    Some(doc.elements.len() - 1)
                };
                if !self_closing && tag != "input" {
                    if stack.len() >= 64 { return Err(Error::limit("HTML nesting exceeds 64")); }
                    stack.push((tag, index));
                }
            } else {
                let end = rest.find('<').unwrap_or(rest.len());
                let raw = &rest[..end];
                rest = &rest[end..];
                if raw.trim().is_empty() { continue; }
                let text = decode(raw)?.split_whitespace().collect::<Vec<_>>().join(" ");
                if let Some(index) = stack.iter().rev().find_map(|(_, index)| *index) {
                    let element = &mut doc.elements[index];
                    if element.text.len() + text.len() + 1 > MAX_TEXT { return Err(Error::limit("element text exceeds 16 KiB")); }
                    if !element.text.is_empty() { element.text.push(' '); }
                    element.text.push_str(&text);
                } else {
                    if doc.elements.len() >= 128 { return Err(Error::limit("document exceeds 128 elements")); }
                    doc.elements.push(Element { id: String::new(), kind: Kind::Text, text });
                }
            }
        }
        if !stack.is_empty() { return Err(Error::arg("unclosed HTML tag")); }
        Ok(doc)
    }

    pub fn element(&self, id: &str) -> Result<&Element> {
        self.elements.iter().find(|e| !id.is_empty() && e.id == id).ok_or_else(|| Error::stale("unknown element id"))
    }

    pub fn set_text(&mut self, id: &str, text: &str) -> Result<()> {
        if text.len() > MAX_TEXT || text.contains('\0') { return Err(Error::limit("text must be NUL-free and at most 16 KiB")); }
        let element = self.elements.iter_mut().find(|e| !id.is_empty() && e.id == id).ok_or_else(|| Error::stale("unknown element id"))?;
        element.text = text.to_owned();
        Ok(())
    }

    pub fn hit(&self, x: f64, y: f64, logical_width: f64) -> Option<usize> {
        if x < 16.0 || x > logical_width - 16.0 { return None; }
        let local_y = y + self.scroll - 20.0;
        if local_y < 0.0 { return None; }
        let index = (local_y / 44.0) as usize;
        (index < self.elements.len() && local_y % 44.0 < 34.0).then_some(index)
    }

    pub fn next_focus(&mut self) {
        let n = self.elements.len();
        if n == 0 { self.focus = None; return; }
        let start = self.focus.map_or(0, |i| (i + 1) % n);
        self.focus = (0..n).map(|offset| (start + offset) % n)
            .find(|i| matches!(self.elements[*i].kind, Kind::Button | Kind::Input));
    }

    pub fn edit(&mut self, text: Option<&str>, backspace: bool) -> Option<(String, String)> {
        let e = self.elements.get_mut(self.focus?)?;
        if e.kind != Kind::Input { return None; }
        let before = e.text.clone();
        if backspace { e.text.pop(); }
        if let Some(text) = text {
            for ch in text.chars().filter(|c| !c.is_control()) {
                if e.text.len() + ch.len_utf8() <= MAX_TEXT { e.text.push(ch); }
            }
        }
        (before != e.text).then(|| (e.id.clone(), e.text.clone()))
    }

    pub fn render(&self, width: u32, height: u32, scale: f64) -> Result<Vec<u32>> {
        let pixels = (width as usize).checked_mul(height as usize).ok_or_else(|| Error::limit("pixel count overflow"))?;
        if pixels == 0 || pixels > MAX_PIXELS { return Err(Error::limit("render size exceeds 16,777,216 pixels or is empty")); }
        let scale = if scale.is_finite() { scale.clamp(0.5, 8.0) } else { 1.0 };
        let mut canvas = Canvas { width, height, pixels: vec![0x00f4f6fa; pixels] };
        for (i, element) in self.elements.iter().enumerate() {
            let x = (16.0 * scale) as i32;
            let y = ((20.0 + i as f64 * 44.0 - self.scroll) * scale) as i32;
            let w = width as i32 - x * 2;
            let h = (34.0 * scale) as i32;
            let color = match element.kind {
                Kind::Button => { canvas.rect(x, y, w, h, 0x002b59c3); 0x00ffffff }
                Kind::Input => { canvas.rect(x, y, w, h, if self.focus == Some(i) { 0x002b59c3 } else { 0x00949caf }); canvas.rect(x + 2, y + 2, w - 4, h - 4, 0x00ffffff); 0x00182335 }
                _ => 0x00182335,
            };
            if element.kind == Kind::Button && self.focus == Some(i) { canvas.rect(x, y + h - 3, w, 3, 0x00efb236); }
            let glyph_scale = ((if element.kind == Kind::Heading { 3.0 } else { 2.0 }) * scale).round().max(1.0) as i32;
            canvas.text(x + (8.0 * scale) as i32, y + (7.0 * scale) as i32, &element.text, glyph_scale, color);
        }
        Ok(canvas.pixels)
    }
}

struct Canvas { width: u32, height: u32, pixels: Vec<u32> }
impl Canvas {
    fn rect(&mut self, x: i32, y: i32, w: i32, h: i32, color: u32) {
        let x0 = x.max(0).min(self.width as i32); let x1 = (x + w).max(0).min(self.width as i32);
        let y0 = y.max(0).min(self.height as i32); let y1 = (y + h).max(0).min(self.height as i32);
        for yy in y0..y1 { for xx in x0..x1 { self.pixels[yy as usize * self.width as usize + xx as usize] = color; } }
    }
    fn text(&mut self, mut x: i32, y: i32, text: &str, scale: i32, color: u32) {
        for ch in text.chars() {
            if x >= self.width as i32 { break; }
            let glyph = font8x8::BASIC_FONTS.get(ch).or_else(|| font8x8::BASIC_FONTS.get('?')).unwrap_or([0; 8]);
            for (row, bits) in glyph.iter().enumerate() {
                for col in 0..8 { if bits & (1 << col) != 0 { self.rect(x + col * scale, y + row as i32 * scale, scale, scale, color); } }
            }
            x += 9 * scale;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn entities_and_unicode_values_survive() { let d = Document::parse("<input id='x' value='Žluť &amp; café'>").unwrap(); assert_eq!(d.element("x").unwrap().text, "Žluť & café"); }
    #[test] fn rejects_duplicate_ids() { assert!(Document::parse("<p id='x'>A</p><p id='x'>B</p>").is_err()); }
    #[test] fn rejects_scripts_and_css() { assert!(Document::parse("<script>x</script>").is_err()); assert!(Document::parse("<p style='color:red'>x</p>").is_err()); }
    #[test] fn rejects_mismatched_tags() { assert!(Document::parse("<p>x</button>").is_err()); }
    #[test] fn input_edit_respects_utf8_boundaries() { let mut d = Document::parse("<input id='x' value='café'>").unwrap(); d.next_focus(); assert_eq!(d.edit(None, true).unwrap().1, "caf"); }
    #[test] fn bitmap_is_bounded() { let d = Document::parse("<p>Hello</p>").unwrap(); assert_eq!(d.render(160,120,1.0).unwrap().len(),19200); assert!(d.render(0,0,1.0).is_err()); }
    #[test] fn text_update_does_not_parse_markup() { let mut d = Document::parse("<p id='x'>Old</p>").unwrap(); d.set_text("x", "<script>literal</script>").unwrap(); assert_eq!(d.elements.len(),1); }
}
