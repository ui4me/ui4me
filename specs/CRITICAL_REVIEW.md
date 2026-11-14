# Last critical review — design tradeoffs and implementation risks

| Risk | Assessment | Decision / gate |
| --- | --- | --- |
| Reimplementing host launchers | Core 1.0.1 directly boots scripts; UI's launcher duplicated host lifecycle and version metadata | Delegate automatic bootstrap to Core; keep legacy CLI only for backwards compatibility and headless tests |
| Private notification monkeypatch | UI2.0 replaced `native.rpc`'s `window.event` callback to observe Core internals | Use `Application.on_window_event`; preserve Core bookkeeping; test ordering and late close events |
| PowerShell mega-module | ~2k lines, projected more with components; difficult to reason about and test | Split private implementation into purpose-oriented dot-sourced `.ps1` files, retain explicit manifest exports and PS5.1 parseability |
| Feature count as quality | Catalog lists 155; Core cannot natively support six entries | Prioritize operational journeys and P0/P1 feature contracts; mark non-goals honestly |
| Python/PS semantic drift | 71 vs 29 implemented features in old matrix; code can silently diverge | Feature verification matrix, equivalent gallery/demo and reusable language-independent scenario fixtures |
| Unbounded internal Python queue | Events cannot be lost but stream floods can grow memory | Measure/coalesce safe nonsemantic event types; keep discrete events and lifecycle reliable |
| Focus & accessibility | Native UI itself exists but component keyboard patterns incomplete | Tests with tab/arrow/escape, focus return, accessible names; native assistive evidence needed |
| DOM desynchronization | Current Python stops updates on failed Core batch | Preserve fail-closed and report exact component/operation; document and test recovery policy |
| CSS theme replacement | Functional CSS needed for behavior, visual layer is replaceable | Keep both; document stable CSS hooks and parity |
| Settings and file paths | Settings persist in shared per-app path; invalid IDs may collide | Respect user app ID, stable defaults, atomic writes, safe filenames and permission boundaries |
| Native PS parity | No Python runtime and Windows PS 5.1 supported | No Python bridge or .NET packaging; PS module remains pure script depending on Core |
| Docs/published metadata mismatch | README 2.0.0 vs pyproject 2.0.1; PowerShell casing fixed in 2.0.1 on GitHub only | Version 2.1.0, replace user docs and release metadata; verify produced package readmes |
| Production claims | Cloud cannot perform interactive Linux/Windows GUI tests | Never declare production-ready before local agent records those gates; report executed tests separately |

## Research basis

- NiceGUI's official documentation: Python-first declarative layout, model binding, lifecycle, testable UI, background work. Implementation is browser/HTTP-centric and **not** suitable to copy: https://nicegui.io/documentation
- Mantine: composable selection/combobox primitives, stable styling API, functional CSS separable from visual CSS, theme variables. Its React implementation is not reused: https://mantine.dev/ and https://mantine.dev/styles/styles-api/
- WAI-ARIA Authoring Practices: named widgets, keyboard sequences, focus management. Validate host's actual accessibility outputs before claiming complete compliance: https://www.w3.org/WAI/ARIA/apg/
- Existing UI4ME source and Core 1.0.1 source shipped by the user are authoritative for protocol, supported DOM commands, packaging, platform constraints, tests and licensing.

No external code is copied from other frameworks.
