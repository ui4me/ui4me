# Maintaining UI4ME Core

This is a short guide for changing one feature safely and releasing it. The contract is in
[`PROJECT_STATUS.md`](PROJECT_STATUS.md), the compatibility rules are in
[`COMPATIBILITY.md`](COMPATIBILITY.md), and the supported surface is
[`SUPPORT_PROFILE_V1.json`](SUPPORT_PROFILE_V1.json).

## Where things live

| Area | Path |
| --- | --- |
| DOM model, mutation, control state | `crates/ui4me-document` |
| Style (Stylo + carried patches), layout (Taffy fork), text, scene, raster, a11y tree, interaction | `crates/ui4me-renderer/src/{style,layout,text,scene,raster,a11y,interaction}` |
| The facade one window's document exposes (every public document operation) | `crates/ui4me-renderer/src/document.rs`, `document/*.rs` |
| Wire protocol, session/runtime, native loop, desktop services, printing, C ABI | `crates/ui4me-core/src/{protocol,runtime,native,services,print}`, `include/ui4me.h` |
| Bindings | `bindings/python`, `bindings/powershell`, `bindings/lua` |
| CSS feature profile (state of every CSS feature) | `crates/ui4me-renderer/src/style/profile/table.rs` (`FEATURES`, prefs, drop tables) |
| Carried Stylo patches | `patches/stylo/P-006-*.patch`, verified by `patches/stylo/verify.sh` |
| Native GUI harnesses | `tests/native/kwin/*` (private nested KWin), `tests/native/windows/*`, probes `tests/native/*_probe.py` |
| Gate scripts | `tools/gate/` |

## Changing one feature

1. **Behaviour:** implement it in the owning module and add tests next to it. Renderer
   behaviour goes in a `crates/ui4me-renderer/src/document/*_tests.rs` module; wire and
   session behaviour goes in `crates/ui4me-core/src/tests.rs`.
2. **Public command:** add a public command as follows.
   1. Add a `Command` variant in `protocol.rs`, with `#[serde(default)]` for every optional
      field.
   2. Handle it in `runtime.rs`.
   3. Add the Python method in `bindings/python/src/ui4me/app.py` and the PowerShell method in
      `bindings/powershell/Ui4me.Managed/App.cs`, each with a unit test (`tests/test_app.py`,
      `tests/smoke.ps1`).
   4. Regenerate the profile with `UI4ME_UPDATE_PROFILE=1 cargo test -p ui4me-core support_profile`.
      The test fails if a wire op has no binding method and is not in `BINDING_EXCEPTIONS`.
3. **CSS feature:**
   - If Stylo lacks it under Servo, add a carried patch `P-006-N.patch` and list it in
     `verify.sh`.
   - Set the pref and the `FEATURES` row, and remove its entry from `PROPERTY_FEATURES`
     (otherwise the profile filter drops it before Stylo).
   - Bump `style/profile/mod.rs` `VERSION`.
   - Nothing may be marked `On` without parse, compute, use and paint tests.
4. **Platform behaviour:** report the real status through `capabilities()`, and record the
   expectation with `tests/native/capabilities_probe.py --update` on both hosts.
5. **Ledger:** record the slice in `docs/core-roadmap/PROGRESS.md`, with its commit, tests and
   limitations.

Tests during iteration, always under `nice` because the machine is shared:

```sh
nice cargo test -p ui4me-renderer --lib <filter>
nice cargo test -p ui4me-core --lib
nice cargo clippy -p ui4me-renderer -p ui4me-core --all-targets
python dev.py build --binding all --profile dev && python dev.py test --suite unit --binding python
python dev.py test --suite unit --binding powershell
```

## Release recipe

1. **Freeze:**
   - Set `VERSION` and the versions in `Cargo.toml`, `bindings/python/pyproject.toml`,
     `_version.py`, `Ui4me.psd1`, `Ui4me.Managed.csproj` and `BuildVersion.cs`, then run
     `python dev.py version --check`.
   - Update `PROJECT_STATUS.md`, `CHANGELOG.md`, `docs/release-notes/vX.Y.Z.md` and the ledger.
2. **Candidates on both hosts:**
   ```sh
   python dev.py build --binding all --profile release
   python dev.py package --binding all --profile release
   python dev.py test --binding all --suite installed --manifest dist/<platform>/manifest.json
   ```
   Run these with `build/devenv` on `PATH`. On Windows, use a VS x64 developer prompt.
3. **Native gate:**
   - Linux: `tools/gate/linux_gate.sh`. It runs the KWin journeys and probes in private nested
     sessions, then the upgrade matrix.
   - Windows: `tools/gate/windows/README.md` describes the interactive session, the scheduled
     task in the test user's session, and adding and removing the IMEs.
   - Every journey must pass. Record failures and flakes honestly in the ledger.
4. **Record and publish:**
   - Commit the gate entry and push.
   - Wait about 15 s, then run `gh workflow run publish.yml --ref main`. It builds on clean
     GitHub runners, assembles, and publishes to PyPI, the PowerShell Gallery and GitHub with
     `SHA256SUMS`.
   - Publishing needs the owner's authorization.
   - Verify `https://pypi.org/pypi/ui4me/<v>/json` (the project JSON can lag), the Gallery and
     the GitHub assets. Record the release in the ledger.

## Pitfalls

- **Source id:** it hashes the working tree. Don't edit files during a build, and keep line
  endings as committed (CRLF copies on Windows change the id).
- **Stale build receipts:** `dev.py test` refuses them. Rebuild after any edit.
- **Parallel work:** branches that touch `protocol.rs`, `runtime.rs` or `document.rs`, or that
  bump the profile version or a Stylo patch number, conflict. Assign patch numbers up front and
  bump the version at merge.
- **Private test sessions:** `tests/native/kwin/*` start private nested KWin sessions. Never
  point them at a real desktop session.
