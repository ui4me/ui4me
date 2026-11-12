# UI4ME Core public API

This is the reference for the public contract of UI4ME Core 1.0. The native boundary is
[`include/ui4me.h`](../include/ui4me.h) (ABI 1); every operation is a typed JSON command
defined in [`protocol.rs`](../crates/ui4me-core/src/protocol.rs). The Python, PowerShell and
LuaJIT bindings wrap those commands. Compatibility rules are in
[`COMPATIBILITY.md`](COMPATIBILITY.md), and the machine-readable list of every operation, event,
CSS feature and platform capability is [`SUPPORT_PROFILE_V1.json`](SUPPORT_PROFILE_V1.json).

### Session and threads

Python creates `App` on its owner thread, normally the main thread. `run()` blocks
until the last window closes or stop completes. After shutdown, that App is
terminal; construct a new App for another run. `post()` and `stop()` are safe
from other threads. Other operations require the owner. Posts always defer,
and their futures settle as result, exception or cancellation. Waiting for an
unfinished future on the owner is rejected.

PowerShell's `Invoke-Ui4meApp` retains one native owner thread and creates a fresh
runspace for each application. The initializer receives `$app` and explicit
`-ArgumentList` values; caller locals do not cross the runspace boundary
implicitly. ScriptBlocks are runspace-bound. Register `Post` from the owner;
external managed workers may use `PostManaged(Func<object?>)`.

`Work(script, arguments, completion)` uses an isolated background runspace.
Its result/error/cancel state is observable. It reserves a completion ticket
before accepting work, so a full ordinary post queue cannot lose the result.
Cancellation is cooperative. An executing arbitrary user script retains its
process worker slot until it actually exits; stopping the UI does not kill it.
The process permits four such workers, with at most 256 captured output entries
per work item. Keep long operations off UI callbacks.

### Binding methods

| Operation | Python | PowerShell/.NET |
| --- | --- | --- |
| Create document | `app.open(html, ..., base_path=...)` | `$app.Open(html, title, width, height, basePath)` / `New-Ui4meWindow` |
| Preserve a file's local base | `app.open_file(path, ...)` | `$app.OpenFile(path, ...)` |
| Subscribe | `window.on(name, handler, element="id")` | `$window.On(...)` / `Register-Ui4meEvent` |
| Set literal text | `window.set_text(id, text)` | `$window.SetText(id, text)` / `Set-Ui4meText` |
| Form value | `get_value` / `set_value` | `GetValue` / `SetValue`, corresponding cmdlets |
| Checkbox/radio | `get_checked` / `set_checked` | `GetChecked` / `SetChecked`, corresponding cmdlets |
| Attributes | `set_attribute` / `remove_attribute` | `SetAttribute` / `RemoveAttribute` |
| Classes | `add_class` / `remove_class` | `AddClass` / `RemoveClass` |
| Focus | `focus(id)` | `Focus(id)` |
| Replace children | `replace_children_html(id, html)` | `ReplaceChildrenHtml(id, html)` |
| Insert fragment (0.3) | `insert_html(id, position, html)`, `append_html`, `prepend_html`, `insert_html_before`, `insert_html_after` | `InsertHtml`, `AppendHtml`, `PrependHtml`, `InsertHtmlBefore`, `InsertHtmlAfter` |
| Remove / move (0.3) | `remove_element(id)`, `move_element(id, target, position="beforeend")` | `RemoveElement`, `MoveElement` |
| Atomic batch (0.3) | `batch([{"op": ..., ...}, ...])` | `Batch(@(@{op=...}, ...))` |
| Default-action rule (0.3) | `set_default_action(id, event, prevent=True, key=, shift=, ctrl=, alt=, meta=)` | `SetDefaultAction(id, event, prevent, key, shift, ctrl, alt, meta)` |
| Scroll (0.3) | `get_scroll(id=None)`, `scroll_to(id, x=, y=)`, `scroll_by(id, dx=, dy=)`, `scroll_into_view(id, block=, inline=)`, `set_scroll_follow(id=None, follow=True)` | `GetScroll`, `ScrollTo`, `ScrollBy`, `ScrollIntoView`, `SetScrollFollow` |
| Geometry (0.3) | `get_rect(id)` | `GetRect` |
| Selection (0.3) | `get_selection`, `select_text(id=None)`, `clear_selection`, `copy_selection` | `GetSelection`, `SelectText`, `ClearSelection`, `CopySelection` |
| Clipboard (0.3) | `get_clipboard_text`, `set_clipboard_text(text)` | `GetClipboardText`, `SetClipboardText` |
| Streaming (0.3) | `append_text(id, chunk)`, `trim_children(id, keep, from_="start")` | `AppendText`, `TrimChildren` |
| Dialog (0.4) | `show_dialog(id, modal=True)`, `close_dialog(id, return_value=None)`, `get_dialog(id)` | `ShowDialog`, `CloseDialog`, `GetDialog` |
| Select (0.4) | `get_options(id)`, `set_selected_values(id, values)`; `get_value`/`set_value` for single selects | `GetOptions`, `SetSelectedValues`, `GetValue`/`SetValue` |
| Native window (0.4) | `window_action(a)`, `show`, `hide`, `activate`, `minimize`, `maximize`, `restore`, `set_fullscreen`, `set_constraints(min_size=, max_size=, resizable=)`, `set_icon(path)`, `state()`; `app.monitors()` | `WindowAction`, `Show`, `Hide`, `Activate`, `Minimize`, `Maximize`, `Restore`, `SetFullscreen`, `SetConstraints`, `SetIcon`, `StateJson`; `$app.MonitorsJson()` |
| File dialogs (0.4) | `open_file_dialog(cb, multiple=, title=, directory=, filters=)`, `save_file_dialog(cb, file_name=, ...)`, `folder_dialog(cb, ...)`, `file_dialog(kind, cb, ...)` | `OpenFileDialog`, `SaveFileDialog`, `FolderDialog` (handler gets `$e.Paths`, `$e.Error`) |
| Read (0.3) | `get_text`, `get_attribute` (None if absent), `get_attributes`, `has_element`, `query(selector)` | `GetText`, `GetAttribute`, `GetAttributes`, `HasElement`, `Query` |
| Diagnostics | `diagnostics()` | `DiagnosticsJson()` |
| Window operations | `set_title`, `resize`, `snapshot`, `close`, `closed` | `SetTitle`, `Resize`, `Snapshot`, `Close`, `IsClosed` |
| App operations | `on`, `timer`, `post`, `stop`, `stats`, `run`, `close` | `On`, `Timer`, `Post`, `Work`, `Stop`, `StatsJson`, `Run`, `Dispose` |
| Capabilities (0.5) | `app.capabilities()` | `$app.CapabilitiesJson()` |
| Environment (0.5) | `set_environment(color_scheme=, reduced_motion=)`, `environment()`; event `environment_changed` | `SetEnvironment(colorScheme, reducedMotion)`, `EnvironmentJson()` |
| Serialization (0.6) | `get_html(id=None, node=, outer=False)` | `GetHtml(element, node, outer)` |
| Stylesheets (0.6) | `add_stylesheet(css)`, `replace_stylesheet(sheet, css)`, `remove_stylesheet(sheet)`, `stylesheets()` | `AddStylesheet`, `ReplaceStylesheet`, `RemoveStylesheet`, `StylesheetsJson` |
| Nodes (0.6) | `node_of(id=None)`, `get_node(ref)`, `node_children(ref, offset=, limit=)` | `NodeOf`, `NodeJson`, `NodeChildrenJson` |
| Text geometry (0.6) | `text_rects(id, node=, start=, end=)`, `text_at_point(x, y)` | `TextRectsJson`, `TextAtPointJson` |
| Computed style (0.6) | `computed_style(id, *properties)` | `ComputedStyleJson(id, ...)` |
| Forms (0.6) | `get_validity(id)`, `check_validity(id)`; event `invalid`; `submit` carries `submitter` | `GetValidityJson`, `CheckValidityJson` |
| File input (0.6) | `get_files(id)`; `commit`/`change` events carry `files`, `cancel` on dismissal | `GetFiles` |
| Links (0.6) | `app.set_link_policy(schemes, hosts=, open=False)`; event `link_activated` | `$app.SetLinkPolicy(schemes, hosts, open)` |
| Notifications (0.7) | `app.notify(title, body, icon=, urgency=, actions=, on_event=)`, `close_notification(token)`; event `notification` | `Notify`, `CloseNotification` |
| Tray (0.7) | `app.set_tray(icon=, tooltip=, menu=)`, `remove_tray()`; events `tray`, `menu_command` | `SetTray`, `RemoveTray` |
| Menus (0.7) | `window.set_menu(menu)`, `show_context_menu(x, y, menu)`; event `menu_command` | `SetMenu`, `ShowContextMenu` |
| Global shortcuts (0.7) | `app.register_hotkey(id, accelerator)`, `unregister_hotkey(id)`; event `hotkey` | `RegisterHotkey`, `UnregisterHotkey` |
| Rich clipboard (0.7) | `set_clipboard_html(html, text)`, `get_clipboard_html(raw=False)` | `SetClipboardHtml`, `GetClipboardHtml` |
| Pointer (0.7) | `set_pointer_grab(mode, cursor_visible=)`; event `pointer_grab` | `SetPointerGrab` |
| Instance (0.7) | `app.claim_instance(open_files)`; event `open_files` | `ClaimInstance` |
| Drag and drop (0.7) | `draggable="true"`; events `dragstart`, `dragover`, `drop`, `dragend`; `file_drop` carries `element` | — |
| Editing hosts (0.8) | `contenteditable` (plain text); events `beforeinput`, `input` with `input_type`, `data` | — |
| Pointer (0.8) | events `pointerdown`/`pointerup`/`pointermove`/`pointercancel` (`pointer_id`, `pointer_type`, `is_primary`, `pressure`, `buttons`), `got`/`lostpointercapture`, `touch`; `set_pointer_capture(id, pointer_id=1)`, `release_pointer_capture`, `get_pointer_capture()`; every event reports `cancelable` | `SetPointerCapture`, `ReleasePointerCapture`, `GetPointerCapture` |
| Scrolling (0.8) | `scroll_to`/`scroll_by`/`scroll_into_view(..., behavior="auto"\|"instant"\|"smooth")`; `get_scroll` reports `animating` | `ScrollTo`/`ScrollBy`/`ScrollIntoView(..., behavior)` |
| Popovers (0.8) | `show_popover(id)`, `hide_popover`, `toggle_popover` → bool, `get_popover` → `{open, kind}`; events `beforetoggle`, `toggle` | `ShowPopover`, `HidePopover`, `TogglePopover`, `GetPopoverJson` |
| Pagination (1.0) | `paginate(size=None, width=, height=, margins=, print_media=True)`, `get_page_rects(id)`, `render_page(page, path, dpi=96)` | `PaginateJson`, `GetPageRectsJson`, `RenderPage` |
| PDF and printing (1.0) | `export_pdf(path, size=None, ..., dpi=150, title=)`, `print_document(size=None, ..., dpi=300, title=)`; event `print` | `ExportPdf`, `PrintDocument` |
| Rich editing (1.0) | `exec_edit(id, command, value=None)`, `get_edit_state(id)` | `ExecEdit`, `GetEditStateJson` |
| Background work (1.0) | `app.run_in_background(fn, *args, on_done=, on_error=, on_cancel=, pass_task=False)` → `Task` | `$app.RunInBackground(work, onDone, onError[, arguments])` → `BackgroundTask` |
| Developer diagnostics (1.0) | `get_diagnostics(redact=True, since=None, kinds=None)`, `explain(id, property=None)` | `GetDiagnosticsJson`, `ExplainJson` |

### Capabilities and media environment (0.5)

`capabilities` (wire op, no window) returns `platform` (`wayland`,
`x11`, `windows`, `headless`, or `pending` before `run()` starts the native backend),
`backend` and `features`: each feature is `{"status", "reason"}` with status
`supported`, `unsupported` (the platform or Core does not offer it), `denied` (refused
by the user or a policy), `unavailable` (a required service or device is missing now)
or `unknown`, and a reason for everything not plainly supported. Features include
`window.focus`, `window.show_hide`, `window.icon`, `window.minimize`,
`window.minimized_state`, `window.position`, `window.monitors`, `clipboard.text`,
`file_dialogs`, `file_drop`, `ime`, `ime.surrounding_text`, `accessibility`,
`keyboard.layouts`, `environment.*` and the 0.7 services (reported unsupported).
`set_environment` (`window`, optional `color_scheme` `light`/`dark`/`system`,
optional `reduced_motion` `reduce`/`no-preference`/`system`) restyles in place; the
app choice wins over later OS signals until set back to `system`. `get_environment`
reports `color_scheme`, `color_scheme_source` (`app`, `system`, `default`),
`system_color_scheme`, `reduced_motion`, `reduced_motion_source` and `scale`.
`environment_changed` (same fields) is emitted when an OS theme change alters the
scheme in force. `get_accessibility_tree` now reports a text field's `selection`
(`value`: anchor and focus as UTF-16 offsets) and one text-run child per laid-out
line with its UTF-16 `offsets`. A close requested for a window ends delivery of its
events at once; input to a closing window is refused.

### Document interface (0.6)

`get_html` serializes an element (`element`), a node reference (`node`)
or the whole document (neither); `outer` includes the node; control values typed by the
user are not markup; output is capped at 4 MiB (code 5). Author stylesheets attach after
the document's own sheets (at most 64, 1 MiB each) and return a `sheet` id and parse
`diagnostics` (`code`, `category`, `feature`, `line`, `column`, `excerpt`); invalid rules
are dropped, the rest applies; an unknown sheet id is code 4. `list_stylesheets` lists
`style`/`link` elements then attached sheets in cascade order. A node reference is the
string `node:<index>:<generation>`; it stays valid while the node is in the document (or in
a connected `template`'s contents) and is a stale-handle error (code 4) afterwards, never
another node. `get_node` reports `type` (`element`, `text`, `comment`, `document`,
`doctype`, `fragment`), `name`, `id`, `attributes`, `text`, `parent`, `previous`, `next`,
`child_count` and a template's `content`; `node_children` pages children (`limit` 1..4096).
Text geometry offsets are UTF-16 units over an element's **rendered text** (what selecting
it copies: its text blocks joined with `\n`, whitespace collapsed), not over DOM text
nodes; an inline element resolves to its containing block; rectangles are viewport CSS px
and marked `visible` when inside their scrollports. `get_computed_style` (schema 1, up to
64 properties) returns per property `supported` with `value` and `inherited`,
`unsupported` with the profile `feature`, or `invalid`. Constraint validation covers
required, minlength/maxlength, pattern (Rust regex syntax), email, url, number, step and
min/max; interactive submission (button, Enter) validates first, fires `invalid` at each
failing control, focuses the first and skips `submit`; `novalidate`/`formnovalidate`
skip it; `submit` carries `submitter`. A file input opens the OS picker on click or
Enter/Space (filters from `accept`); the chosen paths reach the app only after the user
chose them; Core reads no file. An activated `a[href]`/`area[href]` is reported as
`link_activated` with the resolved `url`, `allowed`, `opened` and `reason`/`error`; Core
never navigates; only `https`, `http` and `mailto` can be allowed (optionally per host,
`example.com` or `*.example.com`), and with `open` Core launches allowed links through the
OS handler without a shell. Declarative default-action rules also cancel link activation,
submission, dialog Escape (`cancel`), selection drags and `select` popups (`mousedown`).

### Desktop services (0.7)

Desktop services answer `{"status": ..., "reason"?}` with `sent`/`ok`/
`registered`/`supported`, or `unsupported`, `unavailable`, `denied`, `conflict` and the exact
cause; nothing is simulated, and headless sessions report `unavailable`. Linux uses D-Bus
(`org.freedesktop.Notifications`; StatusNotifierItem + dbusmenu with the
StatusNotifierWatcher; the xdg-desktop-portal GlobalShortcuts and Settings interfaces);
Windows uses the notification area (balloon notifications: no action buttons, Focus Assist
may suppress them), Win32 menus and `RegisterHotKey`. Menus are trees of `{id, label,
enabled, checked, accelerator}`, separators and submenus (unique ids, at most 512 items, 4
levels, colliding accelerators rejected). Window menu bars and context menus are native on
Windows and `unsupported` on Linux (no client menu-bar protocol on Wayland/X11): render them in
the document; menu accelerators are matched by Core on every platform and arrive as
`menu_command` with `source: "accelerator"`. Global shortcuts need Ctrl, Alt or Super (or a
function key), at most 32, end with the session; the KDE portal may ask the user. The OS
colour scheme and high contrast come from the portal (Linux) or the registry/system settings
(Windows) and update every window (`environment_changed`; `high_contrast` is reported, but
`forced-colors` is not evaluated). `get_clipboard_html` sanitizes by default (scripts,
styles, embedded content, comments, handlers, style attributes and non-http(s)/mailto URLs
removed); image clipboard formats are unsupported. `set_pointer_grab` (`confined`, `locked`,
`none`) reports its outcome as `pointer_grab` and is released on focus loss. On Linux the
launcher's activation token activates the first window; activating an existing window stays
unsupported on Wayland (winit 0.30). `claim_instance` makes the first process per user and
`app_id` the primary (a 0600 socket in `XDG_RUNTIME_DIR` or a local named pipe); later ones
forward bounded path lists (data only) and get `primary: false`. Core installs no file
associations.

### Plain-text editing, pointer, scrolling and popovers (0.8)

(Since 1.0 this applies to `contenteditable="plaintext-only"`; `""` and `true`
are rich hosts, see the 1.0 contract.) An element with `contenteditable` (`false` ends it) is a
focusable plain-text editing host laid out `pre-wrap`: its content is
one text node (the first edit flattens markup to text; typed and pasted content is never
parsed as HTML). The document selection is its caret/selection; characters, Enter,
Backspace/Delete (grapheme; Ctrl: word), arrows, Home/End (visual line), Up/Down, Ctrl+Home/
End, Ctrl+A/C/X/V and Ctrl+Z/Y (100 steps; app writes are not undo steps) edit after an
uncanceled `keydown`, each change firing a cancelable `beforeinput` and an `input`; IME
preedit shows in the text and commits once; the caret is kept visible in scroll containers;
hosts are multi-line text fields for assistive technology. Rich-text editing (formatting
commands, `execCommand`) is outside the profile. Touch: every contact is a `touch` event; the
primary contact taps (click) and drags to scroll; pens arrive as touch or mouse (winit 0.30
has no distinct stylus API: stylus is not exercised). Pointer events precede the
compatibility mouse events (a host rule canceling `pointerdown` suppresses `mousedown`);
pointer capture applies from the pointer's next event while a button is pressed, ends at the
release, and a removed capture target loses it at the Document (`lostpointercapture` with
an empty `element`). Smooth scrolls animate on the document clock (200–400 ms, one per
container, replaced by a new request, canceled by user scrolling; app reduced motion makes
them instant); `scroll-snap-type`/`-align`/`-stop`, `scroll-padding`/`-margin` (no `calc()`)
and `overscroll-behavior` apply to user scrolls, `scroll_to` and `scroll_by` (not to
`scroll_into_view` or follow-end; vertical writing modes are not mapped). Popovers: `auto`
(light dismiss, Escape in top-layer order with dialogs, nested by ancestry/invoker) and
`manual`; invokers `popovertarget`/`popovertargetaction`; focus moves to `autofocus` and
returns to the invoker; the invoker exposes `expanded`. Anchor positioning: `anchor-name`,
`position-anchor` and `anchor()` in insets (shift-based; margins, `anchor-size()`,
`position-area` and `position-try*` are not implemented and reported Off). Range ignores
`readonly` (HTML), mirrors under `dir=rtl` and reports its sanitized value; a number is never
changed by the wheel and parses only the HTML floating-point syntax.

### Animations, advanced CSS and SVG (0.9)

CSS profile 1.26.0 (carried Stylo patches P-006-18, P-006-19). Transitions
and `@keyframes` animations run on the document clock shared with smooth scrolling: a window
requests frames (about 60 Hz) only while one runs, `display: none` cancels them, removal drops
them, and the `transition*`/`animation*` events reach hosts with `property_name`/
`animation_name`, `elapsed_time` and `pseudo_element`. `@starting-style` gives inserted or
newly displayed elements their before-change style; `prefers-reduced-motion` is honoured by
author CSS through the media query (Core does not disable author animations);
`animation-timeline`/`animation-range` and `display` transitions are not implemented
(reported). `content-visibility: hidden` skips the contents (no boxes, paint, hit testing,
focus or accessibility); `auto` implies containment and always renders.
`contain-intrinsic-size` sizes size-contained boxes; `field-sizing: content` sizes text inputs
and textareas to their value; `resize` lets a corner drag set the inline `width`/`height`.
Inline `<svg>` renders through the bounded vector raster path with document CSS for SVG
presentation properties; a click on a shape reports the shape's id; `pointer-events`,
`role="img"`/`aria-label`/`<title>` are honoured; limits and the supported subset are in
[`reference/SVG_PROFILE.md`](reference/SVG_PROFILE.md) (SVG `<text>`,
`foreignObject`, scripting, animation and external references are not supported, and
reported). Hyphenation covers en-US, de, fr, es, pt, nl, sk, pl and uk (Czech patterns are
GPL-only and not shipped). `backdrop-filter` is On (its `url()` forms stay reported); a
`border-radius` box no longer hits outside its rounded border; blur deviations are bounded.
Framework-style markup (utility-class and component-library HTML) is covered by fixtures in
`document/framework_fixtures_tests.rs`; framework JavaScript and build-time CSS directives are
out of scope.
Ruby layout, `shape-outside`, `clip-path`/`filter` `url()` references, `cross-fade()`,
`shape()` and `corner-shape` are not implemented.

### Paged media, printing, rich editing, background work and diagnostics (1.0)

CSS profile 1.27.0 (`@page` and `page` On). `paginate` lays the document
out into pages (`size` a named size or `width`/`height` in CSS px, `margins`, `print` media;
an `@page` size wins) and returns `{count, pages:[{width, height, content}], revision}`;
`get_page_rects` maps an element to its page boxes, `render_page` writes one page as PNG at
`dpi`, and `export_pdf` writes a deterministic raster PDF (one image per page, `dpi` default 150).
A DOM change after `paginate` makes the page commands fail as stale until it is called again;
at most 2000 pages and a bounded pixel budget per job. `print_document` opens the native print
dialog (Windows `PrintDlgEx` + GDI; Linux the xdg-desktop-portal Print interface) and reports a
`print` event with `status` (`printed`, `cancelled`, `failed`, `unavailable` headless); the
`printing` capability says whether it is available. `contenteditable` `""`/`true` hosts are rich
editing hosts over a bounded HTML subset (b/strong, i/em, u, s/del, code, links, paragraphs,
line breaks): typing, Enter (new paragraph), Shift+Enter, Ctrl+B/I/U, sanitized HTML paste and
undo/redo; `exec_edit` applies a command (formatting, link, paragraph) and `get_edit_state`
reports the active formats. Element ids inside a rich host are not stable across edits.
`run_in_background` (Python) / `RunInBackground` (PowerShell) run a function on a bounded worker
pool and settle exactly once on the owner thread (done, error or cancelled); unfinished tasks
are cancelled at stop. A running Python function should poll `task.cancelled` and return; PowerShell
requests a pipeline stop for running work. Closing waits at most 30 s for running work (Python
`close(timeout=30.0)`, `None` for no limit), then leaves anything still running on its worker
thread instead of hanging (Python warns with `RuntimeWarning`). Nothing is killed, and the
Python interpreter still waits for such a thread at exit. `get_diagnostics` returns schema 1 (redacted by default, `since` cursor,
`kinds` filter; [`reference/DIAGNOSTICS_SCHEMA_V1.md`](reference/DIAGNOSTICS_SCHEMA_V1.md))
and `explain` answers why an element looks or behaves as it does (matched rules, box, hit and
focus state) without exposing engine handles. The LuaJIT binding (`bindings/lua/ui4me.lua`,
release asset `ui4me-lua-<version>.zip`) is a pure FFI binding over ABI 1 with the same owner-thread
model. It does not contain the native library: it loads the one named by `UI4ME_NATIVE_LIB` (an
absolute path) or a `libui4me_core.so` / `ui4me_core.dll` placed next to `ui4me.lua` (or in a
`native/` directory beside it), for example `lib/` from the native SDK zip of the same version.

### Documents, scrolling, selection, controls and windows (0.3–0.4)

`set_text` inserts literal text; it never treats that text as markup. For 0.1
compatibility, calling it on a supported value control updates its value.
0.3 DOM commands (wire ops `insert_html`, `remove_element`, `move_element`,
`get_text`, `get_attribute`, `get_attributes`, `has_element`, `query`): positions
are the `insertAdjacentHTML` names `beforebegin`, `afterbegin`, `beforeend`,
`afterend`. The public identity is the HTML `id`; an unknown ID is error 1, and a
removed element's ID may be reused by new content (queued events for the old node
are dropped by the generational check). `insert_html` validates the whole fragment
before insertion. `move_element` keeps the node, its control value/selection and
focus inside the moved subtree (no focus events); moving into itself/a descendant
and removing or inserting beside `html`/`head`/`body` are rejected. `query`
returns the IDs of matching identified elements in tree order (at most `limit`,
default 1024) and `count` of all matches. Only selectors supported by the style
engine are accepted.
`batch` (wire op, `ops` array of up to 1024 operations, 4 MiB payload) accepts
`set_text` (non-control), `set_attribute`, `remove_attribute`, `add_class`,
`remove_class`, `insert_html`, `replace_children_html`, `remove_element` and
`move_element` with the single-command fields. It applies all of them with one
document revision and one invalidation, or none: the first failure rolls back the
tree, attributes, text and focus, and its message starts with `batch operation N`.
Value, checked and focus changes are not batch operations. The batch is atomic for
the document only, never for callbacks or OS actions.
Binding callbacks run after dispatch, so they cannot cancel an event.
`set_default_action` registers a rule instead (`keydown`, `click`, `mousedown`,
`wheel`, `submit`, `reset`; up to 256 per window) matching events at or inside the
element, optionally filtered by exact `key` and modifier states; `prevent=false`
removes the identical rule, and rules are retired with their element. Cancelable
delivered events carry `default_prevented`. Example: prevent `keydown` `Enter`
with `shift=false` on a chat form, and send on the delivered `keydown` event.
Scroll and geometry values are CSS px at any device scale. Omitting `element`
addresses the viewport. `get_scroll` returns `x`, `y`, `min_x/min_y/max_x/max_y`, the
scrollport `width`/`height` and `scrollable` (false and zeros for a non-scroll
container). `scroll_to`/`scroll_by` are instant and clamped, keep an omitted axis,
emit `scroll` when the offset changes and return the new state.
`scroll_into_view` aligns the element in each enclosing scroll container, innermost
first (`start`, `center`, `end`, `nearest`; default `nearest`). `get_rect` is the
border box relative to the viewport (`getBoundingClientRect`), or null without a box.
Resize and scale changes apply to these queries immediately.
`set_scroll_follow` keeps a log/chat container at its end while content grows, as
long as it is at the end. A user or programmatic scroll away stops following until
the reader returns to the end. Follow adjustments do not emit `scroll`.
Document text is selectable with the mouse: drag, Shift+click to extend,
double-click for a word, triple-click for a paragraph, Ctrl+A for all text and
Ctrl+C/Ctrl+Insert to copy, when focus is not in a form control. The selection is
anchored to its block elements. Mutating or appending other content keeps it;
removing a selected block clears it. Copied text is the rendered text of each
block, joined by line feeds. Form-control contents (including passwords), button
labels and generated `::before`/`::after` text are never part of the document
selection. Text controls keep their own selection and clipboard behavior. The
highlight is a translucent overlay clipped to scroll containers. Bidi text is
selected in logical order. Dragging past the edge of a scroll container scrolls it
(while the pointer moves). Every change of the document selection emits a document-level
`selectionchange` event (subscribe with `window.on("selectionchange", ...)`). `get_clipboard_text`/`set_clipboard_text` use the native OS clipboard (plain
text, 16 MiB), or process memory in headless sessions.
For streaming, `append_text` appends a literal chunk of up to 16 KiB. It extends a
small trailing text node or starts a new one, so each append costs only the chunk's
size; `set_text` replaces all text and is limited to 16 KiB. `trim_children` (also a
batch op) keeps at most `keep` element children, removing the oldest (`start`) or
newest (`end`). Removed nodes are collected at the next commit. A document holds up
to 65,536 nodes. Layout reuses unchanged block rows where it can prove the result is the
same and otherwise lays out the whole document, so frame cost still grows with the retained DOM:
on the reference Linux host (release build), typical updates take about 10–50 ms at 1,000 log
rows and 80–600 ms at 3,000–10,000. Keep long logs bounded with
`batch([insert_html, trim_children])`.
HTML semantics (0.4): a modal `<dialog>` enters the top layer and makes the rest of
the document inert (not hit-testable, not focusable). It focuses its autofocus or first
focusable element, keeps Tab inside, and Escape requests a close: a cancelable `cancel`,
then `close` with `return_value`. Prevent `cancel` with a default-action rule to keep it
open. Focus returns to the previously focused element. `<details>`/`<summary>` toggle
on click, Enter or Space, with a `toggle` event (`new_state`, `old_state`). A
drop-down `<select>` opens an in-window popup by mouse, Enter/Space or Alt+Down. Arrows,
Home/End, PageUp/PageDown and type-ahead skip disabled options; a committed change
emits `input` and `commit` with `value`. A listbox `<select multiple>` supports
Ctrl/Shift picking. Clicking a `<label>` focuses or activates its control. PowerShell
events expose `ReturnValue` and `NewState`.
Window services (0.4): actions are queued and applied by the native event loop.
- **Results:** `window_action` returns `applied`. Where the platform forbids an action it returns `applied: false` with an `unsupported` reason, never a fake success. On Wayland: focus/activation (needs an activation token), show/hide, and the window icon (it comes from the app_id desktop entry); Wayland also cannot un-minimize.
- **State:** `state()` reports what the platform observed: `visible`, `focused`, `minimized`, `maximized` and `fullscreen` are `null` when unknown (for example, minimized on Wayland). It also reports size in CSS px and pixels, `scale`, `monitor`, constraints and `platform`. A `window_state` event fires when the state changes.
- **Constraints:** they apply to user resizing and also clamp `resize`.
- **Monitors:** `monitors()` lists name, physical size, scale, refresh rate and primary flag. Position is null on Wayland. The list is empty in headless sessions.
- **Headless:** actions update a deterministic model.
Native file dialogs (0.4) never block the UI.
- **Native backend:** the OS dialog runs on a worker thread (xdg-desktop-portal on Linux; `IFileDialog` on Windows, owned by and modal to the window). The result arrives once as a `file_dialog` event carrying the request `token`: `paths` is a list, or `null` when cancelled, plus `error` on platform failure. Bindings turn that into a one-shot callback.
- **Limits and validation:** at most 4 dialogs at once. Paths are Unicode strings; a non-UTF-8 selection reports an error instead of a lossy path. Filters are a label plus extensions without dots. `directory` must be absolute; `file_name` has no separators.
- **Headless:** sessions complete each request as cancelled with `headless: true`.
- **Lifetime:** stopping the app does not dismiss an open OS dialog; its result is discarded.
- **Linux runtime:** dialogs need a running xdg-desktop-portal with a file-chooser backend (KDE or GTK); libdbus is loaded at run time, not linked.
- **File drops:** dropped files arrive as `file_drop` events (`paths`), and hover as `file_hover`/`file_hover_cancelled`, where winit supports them (Windows and X11). On Wayland, winit 0.30 delivers no drops.
Accessibility (0.4, measured scope):
- **Keyboard:** ordinary interactions are keyboard-operable. Tab/Shift+Tab follow document and `tabindex` order, skip disabled and inert content, and wrap; keyboard focus matches `:focus-visible`. Enter/Space activate buttons and links, Space toggles checkboxes, arrows move through radio groups and selects, Escape closes modal dialogs, and a modal dialog traps focus.
- **Screen readers:** each native window exposes its document through AccessKit (accesskit 0.25 / accesskit_winit 0.34): AT-SPI on Linux, UI Automation on Windows. The tree is built only while an assistive technology is attached. It has roles from HTML and ARIA, accessible names (label, `aria-label`/`labelledby`, content, `title`, `placeholder`), states (checked, disabled, expanded, selected, focused, modal), control values, bounds and focus, and excludes `display:none`, `visibility:hidden` and `aria-hidden` content. Assistive actions (focus, click/default action, set value, increment/decrement) run as trusted user input. Text fields (0.5) are one text run per laid-out line with grapheme characters, positions/widths, word starts, direction and hard line breaks, plus the field's caret/selection; set-selection and replace-selection actions edit through the editing engine. Measured: a Linux AT-SPI client read heading, button, labelled entry, checkbox state and link names and invoked a button; read field text and lines, moved the caret, read character extents, selected and replaced text, and reconnected; a Windows UIA client did the TextPattern/ValuePattern equivalents, and the native COM client read a selection back. `accessibility_tree()` / `AccessibilityTreeJson()` return the same tree for tests. Since 1.0, automated journeys also check what Orca (its braille presentation) and NVDA (its speech log) present. Not claimed: WCAG conformance; Narrator was not run. The managed System.Windows.Automation client crashes reading text from a `GetSelection()` range under PowerShell 7; the native COM client is not affected. On Linux, `aria-expanded`/`aria-invalid` states come from a carried patch to accesskit_atspi_common 0.21.1 (`patches/accesskit_atspi_common/verify.sh`).
New applications should use `set_value` for form controls. `replace_children_html`
parses and validates a fragment before committing it. Duplicate IDs, unsupported
active content and limits cannot leave a half-replaced subtree. Unrelated
control values, selection and scroll are preserved; removed nodes' focus,
resource interests and queued events are retired.

`open_file` reads bounded UTF-8 and keeps the canonical containing directory as
the resource base/root. Relative stylesheet/image/font URLs resolve there, with
nested stylesheet URLs resolving relative to their sheet. For a string document,
use `base_path` explicitly if it has local resources. Without a base, arbitrary
local files are not implicitly available. Native clipboard is plain text and
uses the OS; the headless clipboard is process memory.

### Events and compatibility

Typical element events are `click`, `input`, `change`, `commit`, focus/blur,
key and mouse events, scrolling and composition events. A user edit emits
canonical `input` and the legacy per-edit `change` alias. A committed value
change emits `commit` (for example blur or Enter where appropriate). Programmatic
value/checked updates do not pretend to be user typing. Do not subscribe to both
`input` and its `change` alias for the same action unless duplicate notification
is intentional.

Document and window events include `type` and `window` plus relevant value,
checked, keyboard, modifier, mouse or composition fields. Application events
include `type` and relevant fields such as `token`, `backend` or `app_id`,
without a window ID. `element` is the nearest identified
target and `path` contains identified ancestors for bubbling events. An
ID-filtered handler can receive a click on nested content within its button;
each subscription is invoked at most once for that dispatch. Before delivering
each queued document event to the binding, the host rechecks its generational
target identity. Replacing a node with the same HTML ID cannot revive an obsolete
queued event. Within one event's binding dispatch, matching handlers receive the
same event/path snapshot; identity is not rechecked between individual language
handlers.

Application/window lifecycle includes `started`, `stopped`, `shown`, `closed`,
`close_requested`, `resized`, `scale_changed`, timer and post/completion delivery. A close-request
handler returns `False`/`$false` to veto. Forced stop bypasses veto, closes windows,
settles pending work and returns to the embedding host. No intended runtime
path exits the Python or PowerShell process.

### C ABI and errors

ABI remains **1**, with an additive 0.2 entry point:
`ui4me_session_complete(session, token)`. Reserve/cancel tickets through typed
`reserve_completion` / `cancel_completion` commands before/after background
work. Up to 128 can be reserved. Completion publication is thread-safe and uses
its reserved capacity independently of ordinary posts. Stop retires remaining
tickets; bindings own payload storage and must settle their tasks on teardown.

Strings are UTF-8, NUL-terminated and borrowed. Copy command output before the
next command on that thread; never free it. The caller keeps callback/user data
alive until destroy succeeds. The ABI assumes valid readable/writable pointers;
it cannot validate arbitrary foreign addresses. Unknown JSON fields and wrong
types are rejected at the boundary before mutation.

| Status | Meaning |
| --- | --- |
| 0 | Success |
| 1 | Invalid argument/protocol |
| 2 | Lifecycle/state |
| 3 | Wrong thread |
| 4 | Stale handle |
| 5 | Capacity/size limit |
| 6 | Native runtime |
| 7 | Callback |
| 8 | Poisoned runtime |
| 9 | I/O/resource failure |

`ui4me_last_error()` returns the calling thread's diagnostic JSON. Successful
status calls clear it. Unhandled event, timer or completion-handler errors stop the session and are
raised after native cleanup. A posted action's exception is retained by its
returned future/work object; it does not automatically stop the application. `build_info()` / `Get-Ui4meInfo` exposes
version, ABI, source identity, target and explicit package library path.
`UI4ME_NATIVE_LIB` is an absolute-path development override; installed tests
clear it and never search the working directory or PATH for an alternative
library. Restart the process after changing a loaded native version.

### Limits

Current public limits include 32 windows, 512 queued ordinary posts, 128 timers,
128 reserved completions, 1 MiB HTML input/fragment, 16,384 DOM nodes, depth 256,
16 KiB host-set text and a 16,777,216-pixel framebuffer. Requested window sizes
are 160–4096 by 120–4096 logical pixels. Physical allocation is also checked after
DPI scaling. Timer intervals are 1–86,400,000 ms. Source JSON is capped at 2 MiB.

The fixed asset service admits 128 jobs, with 16 MiB queued source descriptions,
128 MiB in-flight encoded-input allowance and 256 MiB completed-result allowance.
Each document defaults to a 128 MiB decoded asset cache allowance, 64 MiB
unreferenced cache and 16,777,216 decoded image pixels, plus encoded-file limits.
The retained SVG backend has its own 128 MiB raster allowance; scene-held pixel
Arcs remain charged after eviction in both caches. There can be 4,096
current requesters per resource document. Text/layout/decorations and diagnostics
also have bounded caches/history. Exceeding a bound is an explicit error; avoid
submitting hundreds of distinct assets in a single burst.
