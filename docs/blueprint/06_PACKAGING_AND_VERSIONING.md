# Separate UI package vs merging into Core

## Verdict: keep code and releases separate for now; provide a one-command installation.

This is not a permanent ban on monorepo consolidation. It separates product surface from native runtime stability.

### Actual supplied packaging state
- UI Python `pyproject.toml` is already `ui4me-ui` and declares `dependencies = ["ui4me>=1.0.0,<2"]`. If `ui4me-ui` is published to the package index, one `pip install ui4me-ui` resolves the Core dependency automatically (subject to platform availability). Its install README currently uses a local wheel because UI packages are not published in supplied snapshot.
- UI PowerShell `Ui4me.UI.psd1` already has `RequiredModules = @(@{ ModuleName='Ui4me'; ModuleVersion='1.0.0' })`. Standard dependency-aware module installation can install Core as needed; `Import-Module Ui4me.UI` pulls its required module when available.
- Core 1.0.1 is newer than the Core 1.0.0 which UI verified; compatibility must be demonstrated, not inferred from the version range alone.

### Option matrix

| Option | Install UX | Operational cost | Verdict |
|---|---|---|---|
| Two independent packages/repos, UI depends on Core | One UI install; raw Core optionally used directly | Separate release cadence, explicit compatibility matrix | **Recommended now** |
| Monorepo with two separately released packages | One UI install | Coordination easier, separate versioned artifacts still needed | Consider later for CI/code review convenience |
| Single combined wheel/module with Core and UI always bundled | One install | Changes and release failures coupled, larger footprint, platform wheel complex, raw Core churn | Not now |
| Thin `ui4me-desktop` umbrella/meta package | One obvious marketing/install name | Additional release and dependency indirection | Only if naming confusion proves real |
| UI code directly inside Core runtime source/ABI | One module | Blurs abstraction boundary, native release cadence drives widgets, more complex compatibility | Avoid |

### Recommendation for the near term
1. Publish Core as `ui4me` (Python) / `Ui4me` (PowerShell) and UI as `ui4me-ui` / `Ui4me.UI` with dependency metadata.
2. Default docs lead with the UI install for app authors; Core docs lead with Core install for low-level users.
3. Keep `from ui4me_ui import ui` and `Import-Module Ui4me.UI` while APIs evolve; do not rename import paths in every prototype iteration.
4. Use a release compatibility manifest: UI min Core, maximum validated Core major, tested Core patch, platform support, ABI version, capability flags and generated smoke evidence.
5. UI may evolve faster than Core, independent semantic versioning. Increment Core requirements only when a component actually needs a new public primitive.
6. If a single source repo improves workflow later, use monorepo with clearly separated `core/`, `ui/python/`, `ui/powershell/`, independent build/test/release jobs and separate version stamps.
7. Do not copy the Core native binary into the UI wheel/module to hide packaging. Let the package manager resolve it.
8. Prefer no compulsory dependency on a theme/runtime editor/plotting suite; ship modest default CSS and standard icons, optional features in extra packages or lazy optional adapters.

### When to reconsider a combined distribution
Revisit only after UI API stabilization and measurable maintenance overhead (duplicated CI, dependency release failures, installation confusion), and only if combined packaging significantly lowers user friction. Maintain separation of modules even in combined distribution. First measure one-command installation success in clean Python and PowerShell environments; this likely solves the actual pain without a source merge.

### Compatibility policy proposal
- During UI 0.x, document breaking changes explicitly, avoid premature frozen CSS internals, preserve migration notes.
- Before UI 1.0, publish public component/theme/behavior contracts and compatibility test suites.
- Major breaking change only with migration docs; distinguish Core ABI stability and UI API stability.
- Cross-binding parity is semantic: Python and PowerShell idioms can differ but states/events/theme controls/keyboard/AT semantics should align.

### Sources
Python Packaging User Guide: https://packaging.python.org/en/latest/discussions/install-requires-vs-requirements/
PowerShell Install-PSResource reference: https://learn.microsoft.com/powershell/module/microsoft.powershell.psresourceget/install-psresource
