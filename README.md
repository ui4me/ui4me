# ui4me

A small native application foundation for Python and PowerShell, backed by one
Rust engine. Version 0.1 establishes the application lifecycle, package delivery
and testing workflow before broader rendering work.

**Release qualification is pending.** See [STATUS](STATUS.md) and the
[acceptance tasks](specs/001-foundation/tasks.md) for the actual evidence and gaps.

## Start here

1. Read [development setup](docs/development.md) for Windows or Linux.
2. Install the contributor tools and Python build requirements.
3. Use the committed Cargo and NuGet locks; regenerate them only when updating dependencies.
4. Build and test your current host and binding.
5. Package, install the final artifacts outside the checkout, and record native acceptance.

```sh
python -m pip install -r requirements-dev.txt
python dev.py doctor
python dev.py build --binding all --profile dev
python dev.py test --binding all --suite unit --profile dev
python dev.py report
```

Run these commands on the target host. Release qualification also requires exact packaged artifacts and native acceptance on both platforms.

## Small user-facing APIs

After building and installing the Python wheel:

```python
from ui4me import App

with App() as app:
    window = app.open('<h1>Hello</h1><button id="close">Close</button>')
    window.on("click", lambda event: app.stop(), element="close")
    app.run()
```

After building and importing the PowerShell module:

```powershell
Import-Module Ui4me
Invoke-Ui4meApp {
    param($app)
    $window = New-Ui4meWindow '<h1>Hello</h1><button id="close">Close</button>'
    $null = Register-Ui4meEvent $window click {
        param($event)
        Stop-Ui4meApp
    } -Element close
}
```

The call returns when the application completes. Examples with input, additional
windows, posting, timers and native acceptance live in `examples/` and the
binding tests. [Python API](bindings/python/README.md) · [PowerShell API](bindings/powershell/README.md).

## What the foundation contains

| Area | Source implementation |
| --- | --- |
| Application host | One native owner, explicit sessions, multiple windows and return to the embedding process |
| Lifecycle | Close veto, forced stop, terminal handles, bounded posts/timers and failure propagation |
| Native integration | Windows and Linux winit windows with software presentation |
| Basic UI | Text, labels, buttons, text input and a fixed vertical form layout |
| Bindings | Python App/Window objects and seven PowerShell cmdlets with advanced object methods |
| Package flow | Per-platform Python wheels, native SDKs, one combined PowerShell package |
| Developer cycle | Shared build/test/package/report/qualify/publish commands |
| Evidence | Requirements, exact artifacts, latest attempts, logs and available screenshots |

The minimal renderer supports inline text and background colors, but no stylesheets, CSS layout, full text shaping, IME, clipboard/selection
editing or accessibility bridge. Mac/ARM and external event-loop integration are
not supported targets. Native behavior on the initial Windows/Linux targets is
pending local acceptance; target metadata is not a successful test result.

## One repository, separate outputs

```text
crates/ui4me-core/          Native runtime, platform adapter and renderer
include/ui4me.h             C ABI
bindings/python/           Python package and tests
bindings/powershell/       PowerShell module, managed bridge and tests
examples/                  Small consumer applications
tools/ui4me_dev/            Development and release orchestration
quality/scenarios.json     Requirement/scenario catalog
tests/tooling/              Harness tests and external C SDK consumer
specs/001-foundation/       Specification, plan and tasks
docs/                      Focused contributor and release documentation
.github/workflows/         CI, native evidence and guarded publishing
```

Generated files stay in `build/` and `dist/`. The source archive excludes
binaries, old project material and test artifacts. The root documentation site
is intended to be [ui4me.github.io](https://ui4me.github.io/); its hosting
repository is generated output, while documentation is maintained here.

## Targeted work

```sh
python dev.py build --binding python --profile dev
python dev.py test --binding python --suite unit --profile dev
python dev.py test --binding tools --suite unit
```

Use `powershell` or `core` for the other components. A release still needs both
platforms and both bindings. See [testing and evidence](docs/testing.md) for the
48 required scenario observations and [publishing](docs/publishing.md) for the
registry setup, final package assembly, release gates and public verification.

The checked-in [acceptance baseline](quality/README.md) shows all required
observations as not run. Generated overviews add logs and screenshot links as
real evidence becomes available.

## Design and contribution

Read the [foundation specification](specs/001-foundation/spec.md),
[architecture decisions](docs/architecture.md) and [native contract](docs/native-contract.md)
before changing lifecycle behavior. Add rendering capabilities as small changes
that preserve the foundation scenarios. The project uses the MIT license;
dependency licenses and notices remain separate obligations.
