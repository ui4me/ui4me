//! `<input type=file>` (0.6 F0606): activation (click, Enter/Space) asks the host to open its
//! native picker; the host completes the request with the chosen paths (the input gets them, and
//! `input` then `change` fire) or with nothing (`cancel` fires). Paths reach the app only after
//! the user chose them in the OS picker; Core reads no file.

use super::*;
use crate::interaction::frame::EventInit;

/// A picker request: the input, whether it takes several files, and its `accept` list.
#[derive(Clone, Debug, PartialEq)]
pub struct FileInputRequest {
    pub input: NodeId,
    pub element: Option<String>,
    pub multiple: bool,
    pub accept: Vec<String>,
}

/// Bytes of one path / paths per input the host may write.
const MAX_PATH: usize = 4096;
const MAX_FILES: usize = 1024;

impl Document {
    /// The picker requests of activated file inputs since the last call (still connected).
    pub fn take_file_requests(&mut self) -> Vec<FileInputRequest> {
        let requests = std::mem::take(&mut self.file_requests);
        let d = self.pipeline.document();
        requests
            .into_iter()
            .filter(|&n| d.arena().contains(n) && d.is_connected(n).unwrap_or(false))
            .map(|n| FileInputRequest {
                input: n,
                element: d.get_attribute(n, "id").ok().flatten().map(str::to_owned),
                multiple: d.get_attribute(n, "multiple").ok().flatten().is_some(),
                accept: d
                    .get_attribute(n, "accept")
                    .ok()
                    .flatten()
                    .unwrap_or("")
                    .split(',')
                    .map(|a| a.trim().to_ascii_lowercase())
                    .filter(|a| !a.is_empty())
                    .collect(),
            })
            .collect()
    }

    /// Complete a picker request: `Some(paths)` sets the input's files and fires `input` and
    /// `change`; `None` (canceled) fires `cancel`. A removed input completes silently.
    pub fn complete_file_input(&mut self, input: NodeId, paths: Option<Vec<String>>) -> Result<()> {
        {
            let d = self.pipeline.document();
            if !d.arena().contains(input) || !d.is_connected(input).unwrap_or(false) {
                return Ok(());
            }
        }
        if let Some(p) = &paths
            && (p.len() > MAX_FILES || p.iter().any(|x| x.len() > MAX_PATH || x.contains('\0')))
        {
            return Err(arg("invalid file paths"));
        }
        let id = self.id();
        let events: Vec<EventInit> = match paths {
            None => vec![EventInit::new("cancel").bubbles(true)],
            Some(paths) => {
                self.input_files.insert(input, paths);
                vec![
                    EventInit::new("input").bubbles(true),
                    EventInit::new("change").bubbles(true),
                ]
            }
        };
        for init in events {
            let _ =
                crate::interaction::element_events::dispatch_element_task(self, id, input, init);
        }
        self.after_mutation(false);
        Ok(())
    }

    /// The files chosen in a file input (empty before a choice, after a reset or a cancel that
    /// followed no choice).
    pub fn get_files(&self, element: &str) -> Result<Vec<String>> {
        let n = self.node(element)?;
        let d = self.pipeline.document();
        let is_file = d.local_name(n).is_ok_and(|t| t == "input")
            && d.get_attribute(n, "type")
                .ok()
                .flatten()
                .is_some_and(|t| t.trim().eq_ignore_ascii_case("file"));
        if !is_file {
            return Err(arg("get_files requires an input of type file"));
        }
        Ok(self.input_files.get(&n).cloned().unwrap_or_default())
    }

    /// Forget the files of inputs reset by a form reset or removed (called after mutations).
    pub(super) fn prune_input_files(&mut self) {
        let d = self.pipeline.document();
        self.input_files
            .retain(|&n, _| d.arena().contains(n) && d.is_connected(n).unwrap_or(false));
    }
}
