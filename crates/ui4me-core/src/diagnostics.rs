//! F1008 developer diagnostics (`get_diagnostics`, schema 1): a stable, bounded, redacted view of
//! the renderer's unsupported-CSS, stale-reference, layout, paint, resource and command reports.
//!
//! The renderer keeps *current* reports; this log gives each distinct report a monotonically
//! increasing `seq` the first time it is observed, so callers can poll with `since`. The log is
//! capped (`MAX_LOG`); evicted entries are counted in `dropped`. No engine pointers, arena
//! indices or node references appear in an item.

use serde_json::{json, Value};
use std::collections::VecDeque;

pub const SCHEMA: u64 = 1;
/// Distinct reports retained per window.
pub const MAX_LOG: usize = 256;
/// Items returned by one call.
pub const MAX_ITEMS: usize = 128;
const MAX_MESSAGE: usize = 256;
/// Stable `kind` names.
pub const KINDS: [&str; 7] = [
    "css_unsupported",
    "stale_reference",
    "layout",
    "paint",
    "resource",
    "text",
    "command",
];

#[derive(Clone, Debug, PartialEq, Eq)]
struct Entry {
    seq: u64,
    kind: &'static str,
    code: String,
    feature: Option<String>,
    element: Option<String>,
    stage: String,
    message: String,
    count: u64,
}

impl Entry {
    fn same(&self, o: &Entry) -> bool {
        self.kind == o.kind
            && self.code == o.code
            && self.feature == o.feature
            && self.element == o.element
            && self.stage == o.stage
            && self.message == o.message
    }
}

#[derive(Default)]
pub struct DiagLog {
    entries: VecDeque<Entry>,
    next_seq: u64,
    dropped: u64,
}

fn kind_of(code: &str, stage: &str) -> &'static str {
    match (code, stage) {
        ("STALE_HANDLE" | "WRONG_DOCUMENT" | "DOCUMENT_CLOSED" | "UNKNOWN_ELEMENT", _) => {
            "stale_reference"
        }
        (_, "resource") => "resource",
        (_, "text") => "text",
        (_, "layout" | "box") => "layout",
        (_, "scene" | "raster" | "platform") => "paint",
        ("UNSUPPORTED_PAINT_FEATURE", _) => "paint",
        ("UNSUPPORTED_FEATURE" | "STYLE_PARSE_DIAGNOSTIC", _) | (_, "cascade" | "parse") => {
            "css_unsupported"
        }
        _ => "command",
    }
}

/// Numeric core error code to its stable name.
pub fn error_code_name(code: i32) -> &'static str {
    match code {
        1 => "INVALID_ARGUMENT",
        2 => "INVALID_STATE",
        3 => "WRONG_THREAD",
        4 => "STALE_HANDLE",
        5 => "LIMIT",
        6 => "NATIVE",
        7 => "CALLBACK_FAILED",
        8 => "POISONED",
        9 => "IO",
        _ => "UNKNOWN",
    }
}

impl DiagLog {
    fn observe(&mut self, e: Entry) {
        if let Some(existing) = self.entries.iter_mut().find(|x| x.same(&e)) {
            existing.count = existing.count.max(e.count);
            return;
        }
        if self.entries.len() == MAX_LOG {
            self.entries.pop_front();
            self.dropped += 1;
        }
        self.next_seq += 1;
        self.entries.push_back(Entry {
            seq: self.next_seq,
            ..e
        });
    }

    /// Record a snapshot item produced by the renderer's `Document::diagnostics()`.
    pub fn observe_snapshot(&mut self, v: &Value) {
        let code = v["code"].as_str().unwrap_or("UNKNOWN").to_owned();
        let stage = v["stage"].as_str().unwrap_or("host").to_owned();
        let message = v["message"]
            .as_str()
            .or_else(|| v["reason"].as_str())
            .unwrap_or("")
            .to_owned();
        let kind = kind_of(&code, &stage);
        self.observe(Entry {
            seq: 0,
            kind,
            code,
            feature: v["feature"].as_str().map(str::to_owned),
            element: None,
            stage,
            message,
            count: 1,
        });
    }

    /// Record a numeric-code error (a failed render).
    pub fn observe_error(&mut self, code: i32, message: &str, stage: &str) {
        let name = error_code_name(code);
        self.observe(Entry {
            seq: 0,
            kind: kind_of(name, stage),
            code: name.to_owned(),
            feature: None,
            element: None,
            stage: stage.to_owned(),
            message: message.to_owned(),
            count: 1,
        });
    }

    /// Record a command that failed: why a DOM/CSS command had no effect.
    pub fn observe_command(&mut self, op: &str, element: Option<&str>, code: i32, message: &str) {
        let unknown = message.starts_with("Unknown element ID");
        let name = if unknown {
            "UNKNOWN_ELEMENT"
        } else {
            error_code_name(code)
        };
        let before = self.entries.iter().position(|x| {
            x.kind == kind_of(name, "command")
                && x.code == name
                && x.element.as_deref() == element
                && x.message == format!("{op}: {message}")
        });
        if let Some(i) = before {
            self.entries[i].count += 1;
            return;
        }
        self.observe(Entry {
            seq: 0,
            kind: kind_of(name, "command"),
            code: name.to_owned(),
            feature: None,
            element: element.map(str::to_owned),
            stage: "command".to_owned(),
            message: format!("{op}: {message}"),
            count: 1,
        });
    }

    /// The `get_diagnostics` answer.
    pub fn report(&self, redact: bool, since: Option<u64>, kinds: Option<&[String]>) -> Value {
        let since = since.unwrap_or(0);
        let items: Vec<Value> = self
            .entries
            .iter()
            .filter(|e| e.seq > since)
            .filter(|e| kinds.is_none_or(|k| k.iter().any(|x| x == e.kind)))
            .take(MAX_ITEMS)
            .map(|e| {
                let mut item = json!({
                    "seq": e.seq,
                    "kind": e.kind,
                    "code": e.code,
                    "stage": e.stage,
                    "message": clip(&if redact { redact_text(&e.message) } else { e.message.clone() }),
                    "count": e.count,
                });
                if let Some(f) = &e.feature {
                    item["feature"] = json!(f);
                }
                if let Some(el) = &e.element {
                    item["element"] = json!(if redact { redact_text(el) } else { el.clone() });
                }
                item
            })
            .collect();
        json!({"schema": SCHEMA, "items": items, "dropped": self.dropped})
    }
}

fn clip(s: &str) -> String {
    if s.chars().count() <= MAX_MESSAGE {
        s.to_owned()
    } else {
        let mut out: String = s.chars().take(MAX_MESSAGE).collect();
        out.push('…');
        out
    }
}

fn is_path_start(token: &str) -> bool {
    let b = token.as_bytes();
    token.starts_with('/')
        || token.starts_with("file:")
        || token.starts_with("\\\\")
        || (b.len() >= 3
            && b[0].is_ascii_alphabetic()
            && b[1] == b':'
            && (b[2] == b'\\' || b[2] == b'/'))
}

/// Replace absolute file paths with `<path>` and strip query strings and fragments from URLs.
/// Text between quotes that is longer than 32 characters is content and becomes `<text>`.
pub fn redact_text(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut rest = text;
    while !rest.is_empty() {
        let end = rest
            .find(|c: char| c.is_whitespace())
            .map(|i| i + rest[i..].chars().next().map_or(1, char::len_utf8))
            .unwrap_or(rest.len());
        let (word, tail) = rest.split_at(end);
        rest = tail;
        let trimmed = word.trim_end();
        let space = &word[trimmed.len()..];
        out.push_str(&redact_word(trimmed));
        out.push_str(space);
    }
    out
}

fn redact_word(word: &str) -> String {
    // Peel wrapping punctuation so `"/home/x/a.css",` and `(https://h/p?q=1)` are recognised.
    let start = word
        .find(|c: char| !matches!(c, '"' | '\'' | '`' | '(' | '[' | '<' | '=' | ','))
        .unwrap_or(word.len());
    let body_end = word[start..]
        .rfind(|c: char| {
            !matches!(
                c,
                '"' | '\'' | '`' | ')' | ']' | '>' | ',' | ';' | ':' | '.'
            )
        })
        .map(|i| start + i + word[start + i..].chars().next().map_or(1, char::len_utf8))
        .unwrap_or(start);
    let (lead, body, trail) = (&word[..start], &word[start..body_end], &word[body_end..]);
    let replaced =
        if body.starts_with("http://") || body.starts_with("https://") || body.starts_with("data:")
        {
            if body.starts_with("data:") {
                "data:<redacted>".to_owned()
            } else {
                body.split(['?', '#']).next().unwrap_or(body).to_owned()
            }
        } else if is_path_start(body) {
            "<path>".to_owned()
        } else if body.len() > 34 && (word.starts_with('"') || word.starts_with('\'')) {
            "<text>".to_owned()
        } else {
            body.to_owned()
        };
    format!("{lead}{replaced}{trail}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn redaction_rules() {
        assert_eq!(
            redact_text("cannot read /home/me/secret/a.css now"),
            "cannot read <path> now"
        );
        assert_eq!(
            redact_text(r"open C:\Users\me\x.png failed"),
            "open <path> failed"
        );
        assert_eq!(
            redact_text("GET https://h.example/p/a.png?token=abc#frag failed"),
            "GET https://h.example/p/a.png failed"
        );
        assert_eq!(redact_text("file:///tmp/a.html"), "<path>");
        assert_eq!(redact_text("keep this plain"), "keep this plain");
    }
}
