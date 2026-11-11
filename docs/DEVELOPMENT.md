# Developing UI4ME Core

How to build, test, change and release UI4ME Core. What the project is and how it is built
internally is in [`PROJECT_SUMMARY.md`](PROJECT_SUMMARY.md); the public contract is in
[`API.md`](API.md); compatibility rules are in [`COMPATIBILITY.md`](COMPATIBILITY.md).

## Toolchain

- Python 3.11+ (the package supports 3.11–3.14), Rust **1.99.1** (selected by
  `rust-toolchain.toml`), .NET SDK **10** (`global.json`; the managed bridge targets .NET 8)
  and PowerShell **7.4+**. Windows PowerShell 5.1 is not supported.
- **Linux:** a C compiler, `pkg-config`, and X11/Wayland/xkbcommon development libraries. On
  Debian/Ubuntu, `scripts/bootstrap.sh --install-system` installs them (review it first).
- **Windows:** Visual Studio Build Tools with the C++ x64 toolset and a Windows SDK; build from an
  x64 developer prompt. `scripts/bootstrap.ps1` offers optional WinGet installation and the
  Python environment. PowerShell packaging needs PSResourceGet 1.1+.
- **LuaJIT** (optional, for the Lua binding tests): `bindings/lua/tools/build_luajit.sh` (`.cmd` on Windows)
  builds a pinned LuaJIT into `build/luajit`.

```sh
python -m venv .venv
# Linux: source .venv/bin/activate
# PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python dev.py doctor
python dev.py version --check
python dev.py build --binding all --profile dev
python dev.py test --binding all --suite unit --profile dev
```

`VERSION` is the single version authority; `python dev.py version --check` checks the derived
Rust, Python, PowerShell and managed metadata, and `python dev.py version --set X.Y.Z` updates
them. Keep the Cargo and NuGet lock files; `python dev.py lock` is for a deliberate, reviewed
dependency update.

The carried Stylo, Taffy and AccessKit sources under `patches/` are build inputs (verified by
each `verify.sh`). The build backend computes the local dependency and patch closure and stages
it into the sdist; do not remove patches from a source archive. Packages keep native dependency
notices and the bundled font licences.

## Running from a checkout

After the development build:

```sh
export UI4ME_NATIVE_LIB="$PWD/build/cargo/linux-x64/x86_64-unknown-linux-gnu/debug/libui4me_core.so"
export PYTHONPATH="$PWD/bindings/python/src"
python examples/python/hello.py
```

On Windows use the absolute path of
`build/cargo/win-x64/x86_64-pc-windows-msvc/debug/ui4me_core.dll`. For PowerShell, run
`python dev.py package --binding all --profile dev`, start a fresh PowerShell and
`Import-Module ./build/package/linux-x64/Ui4me/Ui4me.psd1` (`win-x64` on Windows). For LuaJIT,
set `UI4ME_NATIVE_LIB` and run `build/luajit/src/luajit examples/lua/notes.lua`.
`UI4ME_NATIVE_LIB` must be an absolute path; installed tests clear it.

## Tests

During iteration, test the area you changed, under `nice` when the machine is shared:

```sh
nice cargo test -p ui4me-renderer --lib <filter>
nice cargo test -p ui4me-core --lib
nice cargo clippy -p ui4me-renderer -p ui4me-core --all-targets
cargo fmt --all -- --check
python dev.py build --binding all --profile dev && python dev.py test --suite unit --binding python
python dev.py test --suite unit --binding powershell
UI4ME_NATIVE_LIB=$PWD/target/debug/libui4me_core.so build/luajit/src/luajit tests/lua/test_ui4me.lua
```

| Kind | Where |
| --- | --- |
| Renderer behaviour (style, layout, text, paint, interaction, a11y, editing, paging) | `crates/ui4me-renderer/src/**/*_tests.rs`, `regression/` |
| Wire protocol, sessions, support profile | `crates/ui4me-core/src/tests.rs` |
| DOM model, assets, engine types | `crates/ui4me-document`, `crates/ui4me-assets`, `crates/ui4me-engine-types` |
| Bindings | `bindings/python/tests/test_app.py`, `bindings/powershell/tests/smoke.ps1`, `tests/lua/test_ui4me.lua` |
| Installed packages (cases F01–F20) | `bindings/python/tests/installed.py`, `bindings/powershell/tests/installed.ps1`, `tests/tooling/c_consumer.c` |
| Build, release and packaging tooling | `tests/tooling/` |
| Native desktop journeys and probes | `tests/native/` (`kwin/` for Linux, `windows/` for Windows) |
| Upgrade and rollback matrix | `tests/packaging/upgrade_matrix.py` |
| Soak | `tests/soak/soak.py` |

**Fuzz harnesses** are ignored tests with a time budget:

```sh
UI4ME_FUZZ_SECS=300 nice cargo test -p ui4me-renderer --lib --release fuzz_gate::harness -- --ignored --nocapture --test-threads=1
UI4ME_FUZZ_SECS=300 nice cargo test -p ui4me-renderer --lib --release fuzz_resources::harness -- --ignored --nocapture
UI4ME_FUZZ_SECS=300 nice cargo test -p ui4me-core --lib --release fuzz_gate::harness -- --ignored --nocapture --test-threads=1
```

`UI4ME_FUZZ_SEED` (default 1), `UI4ME_FUZZ_ITERS`, `UI4ME_FUZZ_TIMEOUT_MS` (watchdog, default
30000) and `UI4ME_FUZZ_OUT` (where failing inputs are saved) control them. A panic or a watchdog
timeout is a finding.

**Soak:** `python tests/soak/soak.py --minutes 60` runs repeated headless sessions with a mixed
workload (append/trim/stream, style and class changes, focus, scroll, SVG, adverse CSS and
assets, background tasks, timers, pagination and PDF export) and fails on unexpected errors,
leaked threads or file descriptors, unbounded queues or memory growth after warm-up. `--native`
runs it in a private KWin session; `UI4ME_INSTALLED=1` soaks the installed package instead of the
checkout. The long-document harness (`regression/long_document.rs`, ignored; `UI4ME_LD_ROWS`,
`UI4ME_LD_ITERS`) reports update times per scenario.

## Native desktop tests

Native journeys drive real windows with real OS input, against installed candidate packages.

- **Linux:** `tests/native/kwin/*` start a private `dbus-run-session` plus a nested
  `kwin_wayland --virtual` session and drive it with KWin fake input (built from the
  compositor's protocol with `wayland-scanner` and `gcc`). They strip the real display
  variables, so portals and other D-Bus-activated services never appear on the developer's
  desktop, and reap every process on the private bus at the end. `--plain` runs a self-checking
  probe, for example
  `python3 tests/native/kwin/chat_journey.py --plain --out DIR -- python3 tests/native/print_probe.py --out DIR/print.json`.
  The services, print and capabilities probes start the KDE services they need with private XDG
  directories. Orca runs with private preferences.
- **Windows:** the journeys run in an interactive desktop session of an ordinary test user
  (an SSH or SYSTEM session has no desktop). Attach that user's session to the console
  (`tscon <id> /dest:console` from a SYSTEM task) and run the work through an interactive
  scheduled task under that user; `tools/gate/windows/task.ps1` does this and waits for a
  marker file. Stage packages and scripts in a directory the test user can read
  (`C:\Users\Public\ui4me-gui`), with a Python that user can run. The NVDA journey needs a
  portable NVDA at `C:\Users\Public\ui4me-gui\nvda\portable\nvda.exe`.

All input in these tests is automated; they do not replace a person's judgement of usability.

## Changing one feature

1. **Behaviour:** implement it in the owning module and add tests next to it.
2. **Public command:**
   1. Add a `Command` variant in `protocol.rs`, with `#[serde(default)]` for every optional field.
   2. Handle it in `runtime.rs`.
   3. Add the Python method (`bindings/python/src/ui4me/app.py`) and the PowerShell method
      (`bindings/powershell/Ui4me.Managed/App.cs`), each with a unit test.
   4. Regenerate the support profile with
      `UI4ME_UPDATE_PROFILE=1 cargo test -p ui4me-core support_profile`. The test fails if a wire
      op has no binding method and is not listed in `BINDING_EXCEPTIONS`.
   5. Document it in [`API.md`](API.md).
3. **CSS feature:**
   - If Stylo lacks it in Servo mode, add a carried patch `patches/stylo/P-006-N.patch` and list
     it in `patches/stylo/verify.sh`.
   - Set the pref and the `FEATURES` row in `crates/ui4me-renderer/src/style/profile/table.rs`,
     and remove its `PROPERTY_FEATURES` entry (otherwise the profile filter drops it before
     Stylo).
   - Bump `VERSION` in `style/profile/mod.rs` and describe the change there.
   - Nothing is marked `On` without parse, compute, use and paint tests.
4. **Platform behaviour:** report the real status through `capabilities()`, and record it with
   `tests/native/capabilities_probe.py --update` on both platforms
   ([`reference/PLATFORM_CAPABILITIES_V1.json`](reference/PLATFORM_CAPABILITIES_V1.json)).
5. **Changelog:** add the change to [`CHANGELOG.md`](../CHANGELOG.md).

Parallel branches that touch `protocol.rs`, `runtime.rs` or `document.rs`, or that bump the CSS
profile version or a Stylo patch number, conflict: agree on patch numbers up front and bump the
profile version when merging.

## Release

1. **Freeze:**
   - `python dev.py version --set X.Y.Z`, then `python dev.py version --check`.
   - Update [`CHANGELOG.md`](../CHANGELOG.md) and write `docs/release-notes/vX.Y.Z.md` (the
     release workflow uses it as the GitHub release text).
   - If the release adds public behaviour, add an installed contract case to both
     `installed.py` and `installed.ps1`, and to `INSTALLED` in `tools/ui4me_dev/testing.py`
     and `.github/scripts/check-sdist.py`.
2. **Candidates** on Linux and on Windows, from the same commit:

   ```sh
   python dev.py build --binding all --profile release
   python dev.py package --binding all --profile release
   python dev.py test --binding all --suite installed --manifest dist/<platform>/manifest.json
   ```

   Run with the development environment and the .NET 10 SDK on `PATH`. The installed
   `run.json` shows one expected `failed` step per binding (the "missing native" negative test,
   `expected_failure: true`). Build receipts record the exact source identity; any edit
   invalidates them, so rebuild after a change, and keep line endings as committed (a CRLF copy
   on Windows changes the source id).
3. **Native gate:**
   - **Linux:** `tools/gate/linux_gate.sh OUT_DIR` installs the candidate into fresh
     environments and runs every journey and probe, the Lua probe and the upgrade matrix. It
     writes `OUT_DIR/results/summary.txt`.
   - **Windows:** copy `tools/gate/windows/*` to `C:\Users\Public\ui4me-gui\tools`, then:

     ```powershell
     pwsh -File C:\Users\Public\ui4me-gui\tools\prep_gate.ps1            # as the administrator
     $t = 'C:\Users\Public\ui4me-gui\tools\task.ps1'
     $ps5 = 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
     pwsh -File $t -Script C:\Users\Public\ui4me-gui\tools\setlang.ps1 -Marker C:\Users\Public\ui4me-gui\gate\lang-done.txt -Exe $ps5
     pwsh -File $t -Script C:\Users\Public\ui4me-gui\tools\run_gate.ps1 -Marker C:\Users\Public\ui4me-gui\gate\results\all-done.txt -Seconds 3300
     pwsh -File $t -Script C:\Users\Public\ui4me-gui\tools\unlang.ps1 -Marker C:\Users\Public\ui4me-gui\gate\unlang-done.txt -Exe $ps5
     python C:\Users\Public\ui4me-gui\tools\summarize.py
     ```

     `setlang.ps1` adds the Japanese and Korean IMEs for the input journey and `unlang.ps1`
     restores en-US; always run both. To rerun some steps, write a comma list (for example
     `fileinput,print`) to `gate\only.txt` and delete it afterwards. Run the upgrade matrix as
     the administrator from the checkout (it reads the `v0.4.0` tag):
     `python tests\packaging\upgrade_matrix.py --wheel <whl> --stage <stage.zip> --out upgrade.json`.
   - **Soak:** `UI4ME_INSTALLED=1 python tests/soak/soak.py --minutes 60` with the candidate
     wheel installed.
   - Every journey must pass; record failures and reruns honestly in the release notes.
4. **Publish** (needs the maintainer's decision): push, wait about 15 s so the dispatch sees the
   pushed commit, then run `gh workflow run publish.yml --ref main`. The workflow builds both
   platforms on clean runners, assembles the packages and publishes the wheels to PyPI, the
   module to the PowerShell Gallery, and a GitHub release with the native SDKs, the LuaJIT zip,
   `manifest.json` and `SHA256SUMS`. It does not run the native gate. Verify
   `https://pypi.org/pypi/ui4me/X.Y.Z/json` (the simple index can lag by minutes), the Gallery
   and the GitHub assets, and install from PyPI in a clean environment.

`dev.py` also has a stricter local path (`assemble`, `report`, `attest`, `qualify`,
`upgrade-check`, `publish`) built on the scenario catalogue in `quality/scenarios.json` and the
`native-evidence` workflow, which records reviewed native evidence from a self-hosted runner.
CI (`.github/workflows/ci.yml`) builds and tests both platforms on every push.
