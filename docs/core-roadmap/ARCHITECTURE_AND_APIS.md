# Architecture prescriptions and API design patterns

All examples are **proposed contracts**, not proof that these methods currently exist. Reconcile names with live protocol and user-facing API style before merging.

## Native interface first

- Keep the stable `ui4me_session_command` / typed JSON protocol for additive commands; don't add an enormous C function per HTML/CSS property.
- Command structure must name the window and target when applicable, validate size/security limits, return machine-readable errors, and preserve owner-thread semantics.
- Python/PowerShell wrapper names should be idiomatic, but same behavior and status. No UI4ME UI dependency from Core.
- Public node handles: generational/capability-safe IDs, invalidated on removal, bounded queries, no leaking renderer internals.

## Example commands (design candidates)

```json
{"op":"get_outer_html","window":12,"element":"entry"}
{"op":"attach_stylesheet","window":12,"css":".warning { color: red }"}
{"op":"query_text_rects","window":12,"element":"article","start":0,"end":5}
{"op":"platform_capabilities"}
{"op":"notify","title":"Completed","body":"Export is ready"}
```

All JSON samples are **sketches**; verify `Command` enum before implementing and choose actual response shape consistent with existing wire types. Avoid identifier-only operations for anonymous text unless a stable node reference contract is established first.

## OS services pattern

Native feature statuses: `supported`, `unsupported`, `permission_denied`, `temporarily_unavailable`. Returned event results have correlation token, window/app scope, final outcome, and stop/cancel disposal. Wayland may permanently prohibit raise/absolute placement in compositor environments: never misrepresent success.

## Text and editing pattern

Composition transactions: preedit (not committed) → commit once → changed value/text → selection/caret notification; cancel discards preedit, deletion repairs grapheme boundaries. A user-extensible rich text *editor* remains outside Core; a low-level contenteditable selection/edit action belongs Core. Expose text ranges by stable UTF-8/Unicode offset contract with explicit generation and clamp/error semantics; do not assume Python UTF-16 indices equal Rust byte offsets.

## Styling/layout pattern

Old source may have animations, multicolumn, GPU-related concepts. Verify current pipeline before porting. Animation scheduler uses owner frame clock, reduced-motion and shutdown cancellation. Incremental layout must compare with cold rendering on tracked fixtures and fallback if proof fails. GPU backend is optional, with deterministic CPU fallback and no device-loss crash.

## Printing pattern

Renderer produces paginated layout/scene pages; host print adapter consumes pages and reports async status. Separate platform-specific print-dialog ownership from pure layout. PDF export should use existing scene/paged data or a separate adapter and must never block basic native printing.

## Security and safety

No JavaScript, browser DOM compatibility objects, remote resource fetching, app servers, unsafe URL opening, arbitrary plugins inside renderer, unrestricted file system access, or invalid cross-thread mutations. Malformed HTML/CSS/SVG/fonts, callbacks, platform denials and long-running background tasks must have bounded deterministic failure behavior.
