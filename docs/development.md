# Development on Windows and Linux

These commands operate on the current checkout. See [status](../STATUS.md) and generated reports for actual execution results.

## Prerequisites

| Tool | Contributor requirement |
| --- | --- |
| Python | 3.11 or newer for tooling; use 3.12 initially for the common path |
| Rust | The toolchain selected by `rust-toolchain.toml` (1.90.0) |
| Native linker | Windows MSVC Build Tools with Desktop C++ workload; Linux C compiler/linker |
| .NET SDK | 10.x selected by `global.json`, for building the PowerShell managed bridge |
| PowerShell | 7.6 recommended; the managed reference floor is 7.4; Windows PowerShell 5.1 is unsupported |
| PSResourceGet | 1.1 or newer for packing/publishing an existing nupkg |
| Linux GUI | A usable X11 or Wayland session and the required runtime libraries |

Python/PowerShell runtime consumers install packages containing the native
payload; they do not need the contributor Rust or .NET SDK toolchain.

Use `scripts/bootstrap.sh` on Linux or `scripts/bootstrap.ps1` in PowerShell for
the documented setup/check path. Read the script before opting into installation.
The scripts do not register registry accounts or publish anything.

## First checkout

Unzip the source, enter the `ui4me` directory, and create a Python environment:

```sh
python -m venv .venv
# Linux
. .venv/bin/activate
# PowerShell, instead of the line above
# .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python dev.py doctor
```

The lock command resolves Cargo and NuGet dependencies without publishing.
`Cargo.lock` and the managed project's `packages.lock.json` are committed. When updating dependencies, run `python dev.py lock` and review the lock changes separately. CI uses locked resolution.

## Current-host cycle

```sh
python dev.py build --binding all --profile dev
python dev.py test --binding all --suite unit --profile dev
python dev.py report
```

Use `--binding python`, `--binding powershell` or `--binding core` to focus the
cycle. `--binding tools` selects the developer-tool tests. Shared core/ABI changes
need both binding suites. A binding-only change can be developed independently;
the supported release matrix remains a separate requirement.

Run the sample from the installed package or the documented contributor path:

```sh
python -m ui4me demo
```

See the binding READMEs and `examples/` for contributor import paths, the
PowerShell application, and the native scenario driver. Avoid setting a global
`UI4ME_NATIVE_LIB`; use it only in a specific contributor shell when needed.

## Package the host output

```sh
python dev.py build --binding all --profile release
python dev.py package --binding all --profile release
```

The host manifest is `dist/linux-x64/manifest.json` or
`dist/win-x64/manifest.json`. Package output belongs in `dist/`; logs and local
evidence belong in `build/`. Both are ignored by git.

Produce both platforms from the same committed source. Copy their complete
candidate directories to the assembly machine, preserving relative paths:

```sh
python dev.py assemble --manifest dist/linux-x64/manifest.json --manifest dist/win-x64/manifest.json --out dist/release
python dev.py test --binding python --suite installed --manifest dist/release/manifest.json
python dev.py test --binding powershell --suite installed --manifest dist/release/manifest.json
python dev.py report
```

Repeat installed acceptance on the other platform using the same final release
directory. Installed tests clear development overrides and use a consumer path
outside the repository, including spaces and Unicode. They should load the
payload inside the package, never an accidental library from the checkout.

For the native SDK consumer, add `--binding core --suite installed`. On Windows,
run that C compilation from an x64 Visual Studio developer shell so `cl`, INCLUDE
and LIB are configured. CI includes a dedicated MSVC environment step.

## Native acceptance

Use a real desktop session. Headless contract tests do not verify focus, input,
window-manager integration, native resize or same-process native loop reuse.

```sh
python dev.py test --binding python --suite native --manifest dist/release/manifest.json --interactive
python dev.py test --binding powershell --suite native --manifest dist/release/manifest.json --interactive
```

Follow the emitted procedures and [testing guide](testing.md), record outcomes
and evidence, then regenerate the overview. Do not record a pass for a procedure
you have not completed. A remote noninteractive session may correctly be blocked.

## Common problems

| Symptom | First check |
| --- | --- |
| Native file missing | Build/package the current target; confirm the installed native path in diagnostics |
| Wrong architecture or ABI | Use matching x64 packages and a fresh process; do not copy unrelated DLLs into the package |
| Missing Linux display | Check the current desktop session; use headless only for the suites that permit it |
| Second app fails | Run on the retained owner; report native reuse as failed rather than restarting the shell to hide it |
| PowerShell does not see a module update | Start a fresh process; Remove-Module cannot unload every loaded assembly/library |
| Lock or source identity changed | Regenerate the candidate and its evidence; do not rename old packages to a new version |
| Queue is full | Reduce/coalesce producer work and handle the admission error; do not block the UI owner |
