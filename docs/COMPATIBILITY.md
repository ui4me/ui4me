# UI4ME Core 1.0 compatibility contract

This file is the stability promise of Core 1.0. It covers the native ABI
([`include/ui4me.h`](../include/ui4me.h)), the JSON wire protocol
([`crates/ui4me-core/src/protocol.rs`](../crates/ui4me-core/src/protocol.rs)), and the Python,
PowerShell and Lua bindings. The supported feature surface is the canonical profile
[`SUPPORT_PROFILE_V1.json`](SUPPORT_PROFILE_V1.json), generated from source and checked by
`cargo test -p ui4me-core support_profile`.

## Versions

| Item | Value | Rule |
| --- | --- | --- |
| Package version | semantic versioning, `MAJOR.MINOR.PATCH` (1.0.1) | Python wheel, PowerShell module and native library are released together with one version |
| ABI | `ui4me_abi_version() == 1` | Changes only with a major version. A binding checks it once at load and refuses a different ABI |
| Wire schema | Ops and events listed in the profile | Additive within 1.x |
| CSS profile | `css.profile_version` (1.27.x at 1.0.0) | Rows may move to `on` within 1.x; an `on` row is never removed or made `off` within 1.x |
| Diagnostics schema | `schema: 1` | Additive within 1.x |
| Support profile | `schema: 1` | Additive within 1.x |

## What 1.x may change

- **May change:** new wire ops; new optional request fields with defaults; new response and
  event fields; new event types; new capability keys; new binding methods; CSS rows promoted to
  `on`; new diagnostics kinds and codes; more accepted HTML/CSS.
- **Will not change:**
  - ABI function signatures and their return codes 0–9;
  - the owner-thread rules;
  - the callback lease;
  - existing ops, their required fields and their meaning;
  - existing event names and their fields;
  - error codes for a given failure;
  - the meaning of a capability status;
  - the generation check on handles.
- **Deprecation:** a deprecated op or method keeps working until the next major version. It is
  marked in the profile (`deprecated`, with its replacement) and in the binding docstrings for at
  least one minor release. Removal is a major-version change.
- **Compatibility aliases kept for 1.x:**
  - `change` is still sent after every `input` (since 0.1), next to `commit`;
  - `set_text` on a value control sets its value (0.1);
  - the unversioned `diagnostics` op is kept beside `get_diagnostics` (schema 1).

## ABI lifetime rules (unchanged since ABI 1)

- **Thread rules:**
  - Owner thread only: `ui4me_session_create`, `ui4me_session_command`, `ui4me_session_run`
    and `ui4me_session_destroy`.
  - Callable from any thread: `ui4me_session_post`, `ui4me_session_stop` and
    `ui4me_session_complete`.
  - A call from the wrong thread returns 3.
- **Command output:** command output is owned by Core. Copy it before the next command on the
  same thread, and never free it.
- **Callbacks:**
  - The callback and its user pointer are leased to Core until `destroy` succeeds.
  - `destroy` is refused while `run` or any callback is active.
  - A callback must not unwind or throw across the boundary. Every binding catches handler
    errors and reports them as an `error` event or on the posted future.
- **Handles:**
  - Session, window and node handles are generation-checked.
  - A stale handle returns 4. It never reaches another object.
- **Completions:**
  - Up to 128 tickets can be reserved.
  - `stop` retires the outstanding ones.
  - Each ticket is delivered at most once.
- **Return codes:** 0 ok, 1 invalid argument, 2 lifecycle, 3 wrong thread, 4 stale handle,
  5 resource limit, 6 native runtime, 7 callback, 8 poisoned, 9 IO. The message is in
  `ui4me_last_error()` on the calling thread.

## Supported version boundaries (tested)

| Client | Against | Evidence |
| --- | --- | --- |
| v0.4.0 installed contract test (`bindings/python/tests/installed.py` and `installed.ps1` at tag `v0.4.0`) | 1.0.x packages | Run in the release gate on Linux and Windows (`tests/packaging/upgrade_matrix.py`) |
| Current installed contract tests F01, F09, F11–F20 | 1.0.x packages | Release gate and the publishing workflow |
| C consumer (installed native SDK) | 1.0.x | Installed C test on both hosts |
| LuaJIT consumer over the C ABI | 1.0.x | `tests/lua` (Linux and Windows, and against the release zip in the publishing workflow), the KWin Lua probe (Linux) |
| Upgrade from 0.4.0 (pip upgrade, `Update-Module`-style replacement) and rollback | 1.0.x | `tests/packaging/upgrade_matrix.py` |

## Not covered

- **Unsupported platforms:** macOS and ARM64 are deferred (owner decision). Their builds are
  not supported, and no claim is made for them.
- **Out-of-profile behaviour:** behaviour of HTML and CSS outside the profile may change
  whenever such a feature is promoted. Unsupported constructs are reported as
  `UNSUPPORTED_FEATURE` and never silently emulated.
- **Diagnostic text:** the wording of diagnostic messages is not a contract. Codes, kinds and
  features are.
