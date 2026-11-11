# Release engineering and evidence policy

## Scope

Two release lines: Core (`ui4me` Python wheel, `Ui4me` PowerShell module and public native C ABI); optional UI (`ui4me-ui` Python wheel and possibly `Ui4me.UI` PowerShell module) with an explicit minimum compatible Core. They **must** be independently installable and versioned. A change to optional UI must not force a Core rebuild unless it requires a documented public Core capability.

## The release lifecycle

**Development → source freeze → host builds → installed tests → cross-platform assembly → desktop qualification → review → authorized publication → downloaded-install verification.** Separate build success, testing, native acceptance and publication status. The 0.2 source candidate is not public qualification evidence for 0.3.

### Core release invariants

- Match Git commit and normalized source identity across every Linux/Windows artifact, including C ABI, Rust library, Python wheel, PowerShell managed DLL and package resources.
- Lock Rust dependencies, vendored/patched Stylo/Taffy and relevant font/assets licenses; source distributions include all sources/patches required for an isolated build.
- Build Linux x64 and Windows x64 from the same committed tree; package both host-native payloads as required. Do not call a Linux cross-check a Windows native run.
- Run isolated installed consumers with development loader overrides cleared, outside the checkout, in fresh processes.
- Test Python and PowerShell separately plus an external C API consumer; include configured runtime floors and metadata-compatible Python versions.
- Verify real forward upgrades from a *public* previous version, with the previous package actually installed before the candidate; also verify clean installation and exact candidate reinstallation.
- Hold source immutable after qualification. A code/doc/API change affecting source manifest invalidates the dependent receipt; do not patch after green CI without rebuilding.
- Public publication is a separate explicit authorization. Test the actual downloaded registry bytes after authorization.

### Optional UI library invariants

- Importing only `ui4me` must not import/install `ui4me_ui`, JavaScript, FastAPI, a socket server or a framework state engine.
- All UI components use published Core API. No private Rust/FFI imports or hidden semantic difference between Python and PowerShell bindings.
- Component version metadata defines Core min/max supported range, with forward tests against Core stable candidates.
- Components should be testable headlessly with mock Core mutations and in installed GUI on native OS. Accessibility keyboard/focus tests are mandatory for promoted interactive components.
- Markdown conversion sanitizes untrusted HTML by default; dependency security and bundled asset licenses are evaluated independently.
- Specialized extensions declare optional dependencies. Core size and install times should not grow because an extension exists.

## Evidence tiers — no substitution

| Tier | What it proves | What it doesn't prove |
| --- | --- | --- |
| Static `cargo check`, formatter, clippy | Source types/lints and some target-conditional correctness | OS linking, input, layout fidelity |
| Unit tests | Contracts of exercised pure code | Desktop integration and native OS behavior |
| Headless renderer/snapshot | Deterministic pixel and geometry output for fixture | Real compositor, clipboard, keyboard, human a11y |
| Cross-platform ABI/installed tests | Wheel/module/native loader and lifecycle under test environment | Actual physical/virtual desktop experience |
| Native desktop automation | Input/resize/window/clipboard scenario on named environment | Human AT acceptance or untested hosts |
| Person-run accessibility review | Particular assistive interaction on named OS/version | All AT implementations or full WCAG conformance |
| Artifact comparison/upgrade | Identical bytes and backward compatibility in tested process | Safety of publishing without remaining gates |

## Per-milestone gate suggestions

### 0.2-hardening

Current supported subset, KDE Wayland/X11 and Windows native runs, clipboard & typing, close/reopen, independent windows, frozen source package identity, Python/PS installed consumers and upgrade. Refuse publication if any mandatory target remains missing.

### Core 0.3

All new raw DOM/scroll/selection/clipboard/event features have documented C ABI semantics and both binding wrappers. Headless tests, negative tests, at least one independent Core-only streaming consumer, actual OS text selection/copy, native window acceptance and bounded resource/queue stress. If Unicode/bidi selection is incomplete, label exact supported scope and do not claim full selection.

### Core 0.4

Test native OS capabilities and standard HTML controls across platform availability; file dialogs with cancel/Unicode paths, focus trapping/modal HTML, screen reader automated bridge and person-run acceptance for any public accessibility claim. Declared CSS subset with scoped WPT; no generic browser conformance promise.

### Core 0.5

Measure long-running workloads against documented baseline, all promoted features have evidence and no unresolved P0 ownership/selection/painting issues. Reproduce packages and upgrades. Reassess dependencies, binary size and licensing; retain an explicit non-goal list.

### UI 0.1 and 0.2

Build against the minimum declared Core, the latest stable supported Core and a relevant candidate. Component state must survive unrelated Core mutations. Run keyboard/accessibility pattern tests and one installed consumer in a separate project; prove Core-only installation still works. Package review must not conflate optional components with Core shipping.

## Test strategy (cheap while coding, comprehensive when qualifying)

1. **Per edit** — smallest owning unit and directly affected regressions; no hour-long suite after each small change.
2. **Per integrated slice** — related subcrate and interface tests, plus headless fixture/performance spot-check.
3. **Per source freeze** — full mandatory current matrix, clean-source package/ABI/upgrade, relevant WPT/corpus selection, no skips masked as passes.
4. **Per release candidate** — actual installed Linux and Windows native journeys, human observations as specified, manual review of known deviations and support claims.

`old_tests_index.csv` exists for discovering historical tests. It does not define a mandatory 3,000-test release suite. Select tests by supported behavior and risk, not by donor directory size.

## Versioning policy (proposal)

- Core `0.2.x`: correctness/qualification changes only, no silent protocol semantic redesign.
- Core `0.3.0`: additive DOM/scroll/selection primitives; ABI version may remain stable **only if** additive and backward compatible. Explicit feature negotiation for callers on older runtimes.
- Core `0.4.0`: HTML and OS semantics expansion, platform-dependent operations return typed `unsupported`/`denied` rather than fake success.
- Core `0.5.0`: public API stability and performance release, not UI component amalgamation.
- `ui4me-ui` `0.1.0`: independent first component release, pinned to Core range; `0.2.0` expands reactivity/components.
- Python and PowerShell packaging versions should correspond to the same Core ABI/source identity, even if published separately on the two registries.

No `1.0` promise until ABI and native lifecycle/desktop support are stable enough for a clear compatibility contract. Document deprecation warnings and an explicit migration interval before removing public methods.

## Security and capability checklist

- HTML snippets containing script-bearing tags/event attributes and unsupported active elements reject or sanitize according to the public safe input contract. Core has no JS execution; do not assume markup is inherently safe.
- Network fetch, shell invocation, clipboard read/write and file pickers are **explicit** capabilities, not side effects of CSS or standard link text.
- Local resource roots are canonical and limited; symlink traversal, encoding, oversized files, cancellation, and restart are test cases.
- On Wayland, lack of arbitrary window-position control or global shortcut privileges returns a capability failure. Do not bypass compositor policy.
- Async completions contain document generation; late work cannot mutate freed windows. Ensure callback leases and managed runspace lifetime.
- Library Markdown/templating escapes user- or agent-provided markup by default. App owns credentials and approvals.
- Third-party dependencies, license notices and vendored sources tracked; avoid fetching unreviewed code at user runtime.

## Documentation and evidence record for each shipped feature

Every feature record in `data/features.json` gets implementation paths, API/version, selected acceptance tests, platform support classification, known deviations, updated evidence and release status when work lands. Make evidence source/artifact-bound. A separate `SUPPORTED_FEATURES.md` (or equivalent) should be generated from **release-qualified** state, not the planning candidate catalogue.

## Example release approval summary

```
Core release candidate: 0.3.0-rc.1
Git SHA + normalized source ID: ...
Artifact hashes Linux: ...   Windows: ...
Public ABI and compatibility: ...
Mandatory unit / installed / native / WPT subsets: PASS/FAIL/UNRUN by host
Real clipboard and selection: observed on ...
Accessibility claim level: ...
Known unsupported operations: ...
Upgrade from public previous version: ...
Open P0/P1: ...
Decision: GO / BLOCKED (with evidence, reviewer, date)
Publication: NOT AUTHORIZED until separately approved
```
