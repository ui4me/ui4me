# UI4ME — future architecture, research and roadmap

**Planning baseline:** 2026-11-11  
**Current upstream:** [`ui4me/ui4me` `main` at `cbb8a5e`](https://github.com/ui4me/ui4me/commit/cbb8a5efa50505e262b1747c55e38be5838e6b8d) (a 0.2 *source candidate*, not a qualified public release).  
**Original implementation:** supplied `bigbatmanorg-ui4me-old.zip`, SHA-256 `5008aae9c8e3f460938667589c0a358b97e2f23558854925257a923925accdbc` (0.5.0-rc.1 candidate, *not* release-qualified).  
**Package type:** architecture/research/planning only. No replacement implementation, test execution, release authorization or repo mutation.

## The decision in one paragraph

**UI4ME Core** is a minimal, reliable native application host and HTML/CSS renderer with DOM, input/event semantics, platform services, and language-neutral bindings. It must remain usable with raw HTML/CSS from Python or PowerShell and have **no dependency on optional component libraries, application protocols, persistence, authentication or JavaScript**. A separately versioned **UI4ME UI** package can supply declarative components, state binding, Markdown, layouts, themes and convenience widgets. Specialized code editors, terminals and visualization engines should be optional extensions. ACP/SSE, data storage, business rules and policy remain application-owned.

## How to use this package

1. **Start at [`ARCHITECTURE_CHARTER.md`](ARCHITECTURE_CHARTER.md).** It contains non-negotiable boundaries, the ownership test and the feature-decision rubric.
2. **Read [`ROADMAP.md`](ROADMAP.md).** It defines recommended 0.2 hardening, Core 0.3, Core 0.4, Core 0.5, separately versioned `ui4me-ui` 0.1/0.2, release gates and deferred work.
3. **Use [`FEATURE_CATALOG.md`](FEATURE_CATALOG.md)** or machine-readable [`data/features.json`](data/features.json) / [`data/features.csv`](data/features.csv) to plan a feature. All **224** records include owner, target, priority, rationale, acceptance, dependencies where important and original donor-code evidence where available.
4. **Trace old code** via [`OLD_SOURCE_TRACEABILITY.md`](OLD_SOURCE_TRACEABILITY.md), [`data/old-source-references.csv`](data/old-source-references.csv) or the complete Rust [`data/old-symbol-index.csv`](data/old-symbol-index.csv). **144** planned features have a code-location lead with exact file and line range in the supplied original zip. Lines do **not** refer to current `main`.
5. **Read [`RESEARCH_COMPARISON.md`](RESEARCH_COMPARISON.md) and [`CRITICAL_REVIEW.md`](CRITICAL_REVIEW.md)** for toolkit findings, hard tradeoffs, and explicitly rejected alternatives.
6. For implementation planning, give an agent [`agents/PLANNING_PROMPT.md`](agents/PLANNING_PROMPT.md) together with this package, then let it validate current source and propose bounded specifications/tasks.
7. For release decisions, use [`RELEASE_ENGINEERING.md`](RELEASE_ENGINEERING.md) and [`decisions/ADR_INDEX.md`](decisions/ADR_INDEX.md).

## Interpretation of evidence

- **`current_02`** is an inspection-based classification of the UI4ME 0.2 public surface, **not** a fresh test result.
- **`old_evidence = implementation-source-present`** means the identified old file contains relevant code, **not** that its behavior is stable, supported or migrated. `partial-or-related` is weaker; inspect carefully.
- **`old_evidence = none`** means this research did not locate a reliable original-code anchor. It is **not** proof the old repo had no relevant implementation.
- Related old test files are **leads**, not proof that tests passed, covered the full claim or match today’s source.
- Tests and code in `ui4me_old` were built under a very different architecture. Reuse algorithms selectively after checking ownership, lifetime, memory, platform expectations, API contracts and licenses.
- *Proposed release target* is a priority hypothesis; each milestone must pass its entry/exit gates before release. There is no obligation to add all features listed in a version bucket.

## Contents

| File | Purpose |
| --- | --- |
| `ARCHITECTURE_CHARTER.md` | Architectural invariants and decision rules |
| `ROADMAP.md` | Version plan with contracts, dependencies and stop conditions |
| `FEATURE_CATALOG.md` | Full human-readable, source-indexed feature inventory |
| `OLD_SOURCE_TRACEABILITY.md` | How to use the exact old file/line evidence and avoid false claims |
| `RESEARCH_COMPARISON.md` | NiceGUI, Textual, Flet, Toga, Reflex, pywebview, Tauri, Qt, Slint and Dear PyGui review |
| `CRITICAL_REVIEW.md` | Brainstorming, antifeatures, risk register, measurable hypotheses |
| `RELEASE_ENGINEERING.md` | Reproducibility, CI/evidence rules, ABI, distribution and migration |
| `decisions/ADR_INDEX.md` | Explicit draft ADRs and open decision policy |
| `agents/PLANNING_PROMPT.md` | Pasteable prompt for another local implementation/planning agent |
| `agents/RECONCILIATION_CHECKLIST.md` | Pre-implementation drift and donor-evidence review |
| `data/features.json` | Machine-readable, normalized 224-feature registry |
| `data/features.csv` | Spreadsheet-friendly filtered planning view |
| `data/old-source-references.json` / `.csv` | Old source file paths, exact line ranges and anchored source lines |
| `data/old-test-leads.json` / `.csv` | Related old test file leads, not verified passes |
| `data/old-symbol-index.csv` | Searchable declared Rust symbols in original owned crates |
| `data/old-test-index.csv` | Searchable test declarations in original owned crates and tools |
| `data/dependency-graph.json` | Core/optional dependency edges |
| `data/catalog-summary.json` | Counts, provenance and snapshot identifiers |
| `data/SOURCE_MANIFEST.json` | Hashes of generated package contents (created at finalization) |
| `research/SOURCES.md` | Primary external references and why they matter |

## Minimal independent consumers

- **Core-only document app:** raw HTML/CSS, text editing, scrolling, basic controls and callbacks; imports *only* `ui4me`.
- **Core-only OS utility:** window states, clipboard and native file picker; imports *only* `ui4me`.
- **Optional component example:** imports `ui4me_ui` and `ui4me`; no private Rust interfaces.
- **Application stress consumer:** ACP client or SSE agent chat built in a separate repo; networking/auth/database/agents never imported into Core or UI package.

**Quality beats feature count.** A narrow feature with truthful support/acceptance evidence is better than an unqualified claim of NiceGUI parity or full browser compatibility.
