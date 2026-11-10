# Native contract

This document describes the ABI 1 implementation. Consult the generated evidence report for results on a particular source and artifact.

## Boundary and ownership

`include/ui4me.h` is the C-facing contract. Native filenames are `ui4me_core.dll` on Windows and `libui4me_core.so` on Linux. All strings are UTF-8 and NUL terminated. The caller must pass valid readable pointers and writable output pointers. This ABI cannot validate arbitrary addresses or catch access violations caused by invalid pointers.

`ui4me_session_create(config, callback, user, out)` creates one session. The creating thread owns its commands, `run` and `destroy`. Only `post` and `stop` are callable from other threads. Exactly one session exists at a time; destroy the previous one before creating another.

The callback and user data remain rooted until destroy succeeds. Callbacks execute on the owner thread, with no core mutex held, and may issue commands. Callbacks must catch language exceptions and return a negative status; foreign exceptions must never unwind through Rust. Return `1` to veto `close_requested`; other positive values do not veto. Return `0` to continue.

The output of `ui4me_session_command` is borrowed thread-local memory. Copy it before another command on that thread. Never free it. The caller should also copy `ui4me_last_error()` immediately after a failing call. `ui4me_build_info()` has process lifetime.

## Startup, run and shutdown

Configuration is a JSON object with optional `backend` (`native`, default, or `headless`), `app_id` (default `org.ui4me.app`) and `allow_any_thread` (boolean, default false). Unknown configuration keys are rejected. `app_id` maps to the Wayland application ID, X11 WM_CLASS names and Windows window class name. It does not create a desktop file, Windows AppUserModelID, installer identity or OS registration.

Sessions move from ready to running to stopped. A session runs at most once. Commands can create windows before run, but actual OS windows are created only after the event loop resumes. `started` means the loop can accept work, not that a frame has been presented.

The first native session fixes the process's native owner thread. The winit loop is retained on that thread and reused for later sessions. No window survives between runs. The PowerShell host sets `allow_any_thread: true` to explicitly enable winit's supported any-thread option on Windows and Linux. A subsequent native session on another thread returns an error. This is not a portable promise for macOS, mobile or Web.

Native initialization failure requires a new process before another native attempt. The original startup error is returned. A caught Rust panic poisons the process runtime and refuses new sessions. Panic containment cannot recover arbitrary foreign memory corruption, process abort, stack overflow or an exception thrown through the C boundary.

`stop` is idempotent for an existing session. It cancels queued posts, clears timers, releases native windows, emits `closed`, then `stopped`, and returns from run. `stop` overrides a close veto. `destroy` is rejected while run is active. Destroying a ready session releases its pending model/work without callbacks. The host binding must settle its own pending Future or delegate objects on disposal.

The last window's accepted close stops the session. A session that never opened a window remains active until stopped, which supports headless lifecycle and timer tests. Calling stop before run produces terminal cleanup without a started event.

## Commands

| `op` | Fields | Result / behavior |
| --- | --- | --- |
| `open` | `html`, optional `title`, `width`, `height` | Returns `{ "window": id }`; creation is deferred to the native loop. |
| `set_text` | `window`, `element`, `text` | Updates literal text or input value, never parses the replacement as HTML. |
| `get_value` | `window`, `element` | Returns `{ "value": "..." }`. |
| `close` | `window` | Requests close; veto can be returned from the later callback. |
| `set_title` | `window`, `title` | Updates the requested native title. |
| `resize` | `window`, `width`, `height` | Requests logical-pixel size; actual native size is reported separately. |
| `snapshot` | `window`, `path` | Writes a renderer PNG; response includes dimensions and `native_capture: false`. |
| `timer` | `token`, `milliseconds`, optional `repeat` | Adds or replaces a timer; interval must be 1–86,400,000 ms. |
| `cancel_timer` | `token` | Returns whether a timer existed. |
| `stats` | none | Returns phase, window/timer/queue counts and execution/cancellation counters. Allowed after stop. |

IDs are process-monotonic, never raw pointers, and stale IDs are rejected. A window ID does not become valid again for a later window. JSON strings are bounded to 2 MiB; the C caller still has to supply a valid NUL-terminated string.

## Events

Every event contains `type`. Window events contain `window`; element events contain `element`, and change events also contain `value`.

- `started`, `stopped`
- `post` and `timer`, with `token`
- `click`, `change`
- `close_requested`, `closed`
- `resized`, with actual `width`, `height`, and `units: "physical_pixels"`

Closed means core-owned native window resources were released before notification. It does not guarantee that an external compositor has already removed the last visible pixels. Callbacks are synchronous; long callbacks stall input and rendering. Background work must post its result back to the owner thread.

## Queues, timers and idle behavior

There are at most 512 pending posts, 128 timers and 32 windows. A post accepted before stop is either dispatched once or counted as cancelled. Rejected posts are not counted as accepted. A callback failure while dispatching a post counts it as executed, with the error returned after cleanup.

The native loop drains bounded batches to avoid starving OS events. Repeating timers skip missed intervals rather than replaying a backlog. Timers use monotonic time. Callback commands can cancel later due timers before their callbacks are dispatched.

An idle loop waits for OS events or the next timer. A continuously full post queue may use polling so that bounded batches continue. Bindings can add their own interruption timer; that policy is separate from the core idle behavior.

## Minimal document and renderer

The supported tags are `html`, `body`, `div`, `h1`, `p`, `label`, `button` and `input`. Attributes are quoted `id`, inline `style`, and input-only `value` and `type="text"`. Inline styles on rendered elements support `color` and `background-color`; `body` supports only `background-color`. Colors are `#RRGGBB`, `black`, `white`, `red`, `green`, or `blue`. Styles do not inherit. Unsupported declarations are errors. Comments and an optional HTML doctype are accepted. IDs must be unique and whitespace-free. Unknown tags/attributes, malformed nesting, unsupported entities and oversized input are errors.

The renderer uses a fixed vertical layout, basic bitmap text, pointer interaction, forward Tab navigation, Enter/Space activation, input append/Backspace and vertical scrolling. Unsupported glyphs display as `?`; UTF-8 values remain intact. There are no CSS stylesheets or layout properties, JavaScript, network fetch, accessibility bridge, IME composition, clipboard integration, text selection, caret positioning or browser compatibility claim.

Document limits: 1 MiB HTML, 128 rendered elements, 64 levels of nesting, 16 KiB text per element. Requested window dimensions are 160–4096 by 120–4096 logical pixels. Native buffers have a 16,777,216-pixel limit; a large high-DPI resize can exceed that limit and returns a runtime error instead of allocating unbounded memory.

Renderer snapshots use the model's pixel dimensions and scale. They are not OS desktop captures and never qualify focus, DPI, input or window-manager acceptance by themselves. A headless session never proves native startup.

## Error codes

| Code | Category |
| --- | --- |
| 0 | Success |
| 1 | Invalid argument or document |
| 2 | Lifecycle violation |
| 3 | Wrong owner thread |
| 4 | Stale or unknown handle / element |
| 5 | Resource limit |
| 6 | Native runtime or display initialization |
| 7 | Binding callback failure |
| 8 | Poisoned runtime |
| 9 | File / snapshot IO |

`last_error` is JSON with `code` and `message`. A successful status-returning ABI call clears the current thread's error. The host binding should retain its original language exception when a callback returns a failure.

## Dependencies and local acceptance

Direct dependencies and the Rust toolchain are pinned. Cargo and NuGet lockfiles are tracked; locked builds prevent silent dependency re-resolution.

The adapter follows the documented winit application-handler and reusable-loop APIs and softbuffer 0.4.6 surface APIs. These references informed static implementation; they are not validation results:

- [winit run-on-demand contract](https://docs.rs/winit/latest/src/winit/platform/run_on_demand.rs.html)
- [winit Windows thread policy](https://docs.rs/winit/latest/winit/platform/windows/trait.EventLoopBuilderExtWindows.html)
- [winit X11 thread policy](https://docs.rs/winit/0.30.12/x86_64-unknown-linux-gnu/winit/platform/x11/trait.EventLoopBuilderExtX11.html)
- [softbuffer 0.4.6 Surface](https://docs.rs/softbuffer/0.4.6/softbuffer/struct.Surface.html)

First local acceptance must compile this exact source, run the headless tests, test isolated installed packages, and then run the real Windows and Linux desktop scenarios. A reconstruction does not inherit results from another source archive.
