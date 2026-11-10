# Testing and evidence

## Four useful layers

| Layer | Location/selector | Purpose |
| --- | --- | --- |
| Core contracts | Rust crate tests; `--binding core --suite unit` | Ownership, state, bounds, stale handles and error behavior |
| Binding contracts | Tests beside each binding; `--suite unit` | Host callbacks, wrapper lifetimes and language-specific failure behavior |
| Installed consumers | `--suite installed --manifest ...` | Actual shipped payload, versions, resources and installation outside the checkout |
| Native scenarios | `--suite native --interactive --manifest ...` | Real windows, input, close, forced stop, reuse and native lifecycle |

Tooling tests live in `tests/tooling/`. They should prove that broken or stale
evidence is rejected, in addition to checking archive and manifest handling.
Consult the generated reports for actual results on the exact source and packages.

## Small requirement catalog

`quality/scenarios.json` maps F01–F12 to requirements, owners, bindings,
environments and evidence. The definitions match the foundation specification.
Do not create a new top-level directory for each feature. Keep a test beside its
owner and add a scenario mapping when the behavior crosses layers.

The initial release matrix is Python/PowerShell × Windows/Linux × 12 scenarios.
Unit test counts are separate from these 48 required observations. A Python
package metadata range is not evidence that every Python version was tested;
record the actual interpreter and operating system in every run.

## Evidence policy

Each run has an attempt identity, source identity, harness/catalog identity,
platform, binding, start/end time, exact package identities and individual case
outcomes. Logs and image references must remain beside the run when it is moved.
Generate reports with:

```sh
python dev.py report
```

The Markdown overview links requirements and detailed runs. Visual scenarios can
show thumbnails linking to full captures. Nonvisual behavior needs assertions,
counters or traces. Missing captures must remain missing; no illustrative image
or generated mockup can substitute for a test screenshot.

Keep the latest attempt, last successful attempt and current published release
separate. A newer failure or interruption is not hidden by an older pass.
Missing required scenarios, zero selected tests, changed package bytes, stale
source/harness identity and malformed receipts fail qualification.

## Native acceptance procedure

Start native acceptance against the final release manifest on the target desktop.
Use the binding's native scenario driver where provided; read the scenario's
procedure before recording an outcome. Record the actual OS, runtime versions,
display backend/session and operator observations.

```sh
python dev.py test --binding python --suite native --manifest dist/release/manifest.json --interactive
```

The command emits a pending run path. Use that path for each completed case:

```sh
python dev.py attest --run build/reports/RUN_ID/run.json --scenario F03 --status passed --operator "YOUR_NAME" --notes "Typed Ada, activated the button, observed Hello Ada; assertions completed" --screenshot /absolute/path/native-input.png --capture-kind desktop
```

Replace the example run ID, notes and capture with the real run. `attest` is an
operator record, not an automatic test. It must not be used to turn a blocked
session green. Preserve console assertions and traces for race/bounds scenarios.

| Native case | Observe and assert |
| --- | --- |
| F02 | Useful frame, correct window title, input readiness; missing-display behavior separately |
| F03 | Keyboard focus, text input and button activation update the expected state |
| F04 | Two windows, native resize, one closes while the other still responds, final close returns |
| F05 | Ordinary close veto, later accepted close, handler failure and forced stop |
| F06 | Worker-to-owner post, deferred ordering, wrong-thread and nested-run rejection |
| F07 | Accepted posts settle once across stop, queued cancellation and stale late delivery |
| F08 | Two sessions in one process without replacing the owner thread |
| F10 | Bounded queue/timers/resources; stop remains usable; idle counters do not indicate busy spin |

The engine's `snapshot` output is a renderer capture, not an OS desktop image.
Use `--capture-kind desktop` only for a genuine desktop/window capture. Manual
attestation still relies on a trusted operator. Hashes detect changes, not false
statements. A release reviewer checks the run provenance and evidence.

## Add a feature later

1. Write the observable requirement and its scope.
2. Put focused tests beside the crate or binding that owns it.
3. Add/update a scenario only for cross-layer or native behavior.
4. Run the affected local binding and platform while developing.
5. Rebuild final packages and gather fresh candidate evidence before release.

For renderer changes, retain the small lifecycle application as a regression
test. New pixels must not silently change startup, exception, close or shutdown
semantics.

## Release review

Run qualification only after final-artifact installation and native acceptance
for both targets. Read all missing/blocked/failure reasons. Publication is a
separate deliberate step. An accepted upload to a registry is not proof that a
consumer can download and use that release; public verification follows it.
