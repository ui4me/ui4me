# Implementation mission — pragmatic Core 0.4

## Ground truth and precedence

1. Actual code + APIs in current `main` win over archived research assumptions. Verify working tree state, toolchain versions and existing tests before editing. Preserve pre-existing user edits.
2. Owner says 0.2 is already running and tested. This supersedes the **older research's assertion** that 0.2 must first be requalified. Don't burn agent credits rechecking that whole milestone. Existing `docs/PROJECT_STATUS.md` may record an older pre-release snapshot; update status only when evidence/new work warrants it.
3. Research catalogue is a feature dictionary, **not** a 224-item implementation instruction. Old donor's 0.5 source is a candidate and may have incompatible host/ABI contracts. Only selected 0.3 and practical 0.4 functionality is in scope.
4. Prioritize a stable public C ABI and both first-class bindings. Core must work directly with HTML/CSS from Python or PowerShell, no JS/browser dependency.

## Operating loop — one focused slice at a time

A. Read `PROGRESS.md` and select the first incomplete slice in `ACCEPTANCE.md`. Inspect current implementation paths and relevant current tests; skip intact 0.2 infrastructure.
B. Look up donor code with `DONOR_PRIORITY_MAP.md` (file/line ranges are for the **old** archive only). Analyze invariants before copying: native loop ownership, handle generations, event handlers, threading, cancellation, OS differences, resource caps, memory, API compatibility.
C. Add minimal C ABI/protocol surface and Python + PowerShell wrappers together; prefer additive contract and explicit typed unsupported/error results. Avoid stubs that report success.
D. Add focused boundary/negative tests and representative consumer behavior; run only changed crate + bindings + affected interactions while iterating. Run narrow Windows check only for affected native behavior.
E. Complete slice on a local commit, update `PROGRESS.md` with changed paths, what actually passed, deferred minor items, and next slice. Repeat, without requesting a new prompt.
F. At end of 0.3 and 0.4, freeze a candidate and run **one** release-gate verification using documented existing tools, clean installed packages and actual GUI journeys on Linux and Windows. Rerun only failing sections after fixes, then the minimal required cross-suite on final candidate; no repeated gratuitous hour-long full runs.

## Effort allocation and escalation

- Main session configured as `sonnet`; cost-efficient by default. Sonnet does coding, copying, ordinary debugging, tests, API wrappers.
- A second Sonnet `donor-migrator` can take one isolated file/slice while the primary does different work. **At most 2 concurrent implementation workers**. Don't create worktrees for read-only exploration. Main owns ABI changes/integration/commits.
- Opus `core-architect` is for hard design after a precise investigation has failed or exposed an unsafe tradeoff. Ask one sharply bounded question; implement its resolution on Sonnet. Don't use Opus for routine tests or release checklists.
- Avoid overengineering: no per-feature SpecKit flows, bespoke multi-agent coordinator, issue explosion or giant daily narrative reports.
- Prefer source reuse over rewriting proven algorithms, but don't import old architecture wholesale. Scope can be reduced if uncommon features are unstable, provided accepted core use cases still work.

## Testing budget

| Trigger | Required effort |
| --- | --- |
| Small Rust change | Relevant owning module/unit regressions and compilation where changed |
| ABI contract change | C ABI contract + Python and PowerShell calls for that contract |
| Renderer/layout change | Narrow targeted fixtures, affected WPT examples only where genuinely relevant |
| Linux/Windows native change | Actual relevant native-host journey, on affected host; no fake SSH desktop claims |
| Complete feature slice | Focused integration and negative/lifecycle test |
| End of 0.3 and 0.4 | One comprehensive milestone verification + independently installed native consumers |
| Follow-up minor visual/perf item | Document, don't block unless it produces observable UX harm or correctness issue |

## Defects that BLOCK and those that DON'T

**Block:** crash, deadlock, memory unsafety, unbounded run-away resource/callback accumulation, stale node/invalid owner-thread access, incorrect text focus/selection, silent file/data loss, native dialog failure in supported OS, broken installed import/ABI, severe visual/layout defect on a basic app flow, false cross-platform success claims.

**Usually don't block:** tiny and non-user-perceptible perf regression; isolated low-demand CSS/WPT failures beyond supported profile; minor rendering pixel differences; features not in accepted scope; unverified broad accessibility claims (must instead scope support explicitly and fix claimed basic accessible interactions).

**Performance rule:** Do not adopt unexplained p95 micro-budgets, optimize unrequested milliseconds or perform broad performance work. Do measure repeated updates sufficiently to catch jank/hangs and objectively unbounded growth. Any serious regression in a real consumer is a correctness/usability issue.

## Git and release discipline

- `main` is primary. Never overwrite, force-push, delete branches or dispose of another person's work. Keep changes reviewable and small; short-lived worktree only if it saves real integration time.
- Do not conflate shipping **source** with publishing to registries. When 0.3/0.4 is coded and locally qualified, report GO/BLOCKED with exact evidence. Wait for explicit request to publish to PyPI/PSGallery.
- Existing public release tooling under `.github/workflows/`, `dev.py` and `scripts/` should be reused, not replaced for this task.
- Append known non-blockers to `PROGRESS.md` and keep any unpromoted feature omitted from release promises.

## Source reference placement

`reference/` contains the original research charter, roadmap, full feature catalogue and donor traceability data (archive snapshot). **Don't blindly implement its hardening plan or all listed candidates.** Its old source anchors require the original old-repo archive or extracted copy accessible **outside Git**, ideally as a sibling path. Current source remains canonical and old paths are not current paths.
