# Core long-range roadmap progress

**Baseline:** 0.4.0 released, 2026-11-11, tag `v0.4.0` at `8138e78feed4d63dcd6f189b0f96bb0fbbbc6ba6` (per release metadata). This roadmap was prepared by static reading only; no build/test of Core executed.

**Current milestone:** 0.5 (`versions/0_5.md`). **Status:** all eight items implemented; 0.5.0 candidate gate in progress (see below). Not published.

## Version ledger

| Version | Status | Source SHA | Linux GUI | Windows GUI | C/Python/PowerShell | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 0.4 | OWNER-REPORTED RELEASED | `8138e78` release tag | repository-reported PASS | repository-reported PASS | repository-reported release jobs | Do not requalify unless relevant change/new defect |
| 0.5 | CANDIDATE (gate in progress) | see gate entry | dev-build journeys PASS | dev-build journeys PASS | unit PASS; installed NOT_RUN yet | 8/8 items implemented |
| 0.6 | NOT_STARTED | — | NOT_RUN | NOT_RUN | NOT_RUN | — |
| 0.7 | NOT_STARTED | — | NOT_RUN | NOT_RUN | NOT_RUN | — |
| 0.8 | NOT_STARTED | — | NOT_RUN | NOT_RUN | NOT_RUN | — |
| 0.9 | NOT_STARTED | — | NOT_RUN | NOT_RUN | NOT_RUN | — |
| 0.10 | NOT_STARTED | — | NOT_RUN | NOT_RUN | NOT_RUN | — |
| 1.0 | NOT_STARTED | — | NOT_RUN | NOT_RUN | NOT_RUN | — |
| 1.1 | FUTURE OPTIONAL | — | NOT_RUN | NOT_RUN | NOT_RUN | — |

## Work-item ledger

Maintain ONE entry after each completed item:

`DATE | VERSION | ITEM | COMMIT SHA | changed paths | tests actually run / OS and binding | PASS/FAIL/BLOCKED/NOT_RUN | user-observable limitation | next task`

When a new session starts, choose the earliest release not marked GO, then first unresolved item. The agent can mark items `SATISFIED_EXISTING` with exact code/evidence to prevent reimplementation. The source doc `docs/PROJECT_STATUS.md` remains the authoritative current product status after each milestone; this is only an execution ledger.

2026-11-11 | 0.5 | F0501 IME preedit/commit | 6f762e5 | `crates/ui4me-core/src/{native,runtime}.rs`, `ui4me-renderer/src/{document.rs,interaction/editing{,/ime}.rs,interaction/controls.rs}`, `tests/native/{input_probe.py,input_probe.ps1,kwin/input_journey.py,kwin/scriptime.c}`, `tests/native/windows/input_journey.ps1` | renderer lib (new reset test); Linux virtual KWin + scripted zwp_input_method_v1: Python 17/17, PowerShell 17/17 (one early PS run flaked I06/I07 once, not reproduced in 3 reruns); Windows Server 2022 interactive session, Microsoft Japanese + Korean IMEs (dev build): Python 14/14, PowerShell 14/14 | PASS (dev build) | **Fixed P0:** a focus move during composition committed the preedit a second time into the next field (reproduced on 0.4: 'とうきょう' in both inputs); a host write left a stale preedit; a canceled composition never ended. No surrounding text to the IM (winit 0.30). Chinese only via the scripted Linux IM (no Windows Chinese IME installed) | F0502
2026-11-11 | 0.5 | F0502 layouts/dead keys/AltGr/repeat | 6f762e5 (KWin), Windows driver in the following commit | same journeys | cz (dead acute/caron, AltGr \ @ €, ů), us(intl) (é ü à ' ß), de (ö ä ü ß @ ô é), Ctrl/Alt shortcuts insert nothing, Ctrl+Z follows the layout, repeat flagged: Linux 6/6 per binding, Windows 6/6 per binding | PASS (dev build) | Automated compositor/SendInput input, not a person | F0503
2026-11-11 | 0.5 | F0503 bidi caret/selection | 1b261b7 (Sonnet worker) | `ui4me-engine-types/src/control_inner.rs`, `ui4me-renderer/src/{layout/replaced/inner.rs,interaction/editing.rs,document/bidi_tests.rs}` | renderer lib 245 → 8 new bidi tests | PASS | **Fixed:** clicking the visual left of an RTL word mapped to the wrong logical offset; End then Home on a wrapped line stayed put. Selection is logical (copy logical, highlight visual); visual arrow steps can skip a direction-boundary offset | F0504
2026-11-11 | 0.5 | F0504 accessible text | f134205, 7cde3ab | `ui4me-renderer/src/a11y/{mod,build}.rs`, `document.rs`, `document/a11y_text_tests.rs`, `interaction/{assistive,editing}.rs`, `tests/native/a11y_probe.py`, `tests/native/windows/{uia_probe.ps1,uia_native_text.py}` | renderer 4 new tests; Linux AT-SPI probe 16/16 (text, lines, caret, extents, selection, set_text_contents, reconnect); Windows UIA 17/17 (TextPattern text/range/select/bounds/line, ValuePattern, native COM selection read-back) | PASS (dev build) | Managed System.Windows.Automation crashes reading GetSelection() text under pwsh 7 (client defect; native COM client fine). No Orca/Narrator speech run | F0505
2026-11-11 | 0.5 | F0505 lifecycle faults | 322e6e4 | `ui4me-core/src/{runtime,tests}.rs`, `tests/native/a11y_probe.py` | core 33/33 (stop/close/remove-focused/remove-modal inside callbacks, stale assistive target, a close ends delivery at once) | PASS | **Fixed:** events and input for a window whose close was requested were still delivered until the loop processed it | F0506
2026-11-11 | 0.5 | F0506 live environment | cdeceda | `ui4me-renderer/src/document.rs`, `ui4me-core/src/{native,protocol,runtime,tests}.rs`, bindings, `tests/native/environment_probe.py` | core test; Python 35/35 + PowerShell 32/32 unit; Linux probe 3/3 (OS output scale 1→2 via kscreen-doctor under a focused edit) | PASS (Linux) / Windows theme flip in gate | OS theme changes only on Windows (winit 0.30); contrast/locale not evaluated; system font changes not live (reported) | F0507
2026-11-11 | 0.5 | F0507 focus/pointer matrix | 1e81621 (Sonnet worker) | `ui4me-renderer/src/{interaction/pointer.rs,interaction/sequences.rs,document.rs,document/focus_pointer_tests.rs}` | renderer 12 new tests (261 total) | PASS | **Fixed:** a press survived window focus loss and clicked on the next release; hover/active/press state kept pointing at removed nodes | F0508
2026-11-11 | 0.5 | F0508 capability report | bbeb3a9 | `ui4me-core/src/{protocol,runtime,native,tests}.rs`, bindings + tests, `tests/native/window_probe.py` | core; unit Python/PowerShell; KWin window probe 10/10 (report agrees with Wayland rules) | PASS (Linux) / Windows in gate | `denied` is defined but no current operation produces it | gate

## Outstanding defects / intentional exclusions

- Windows Chinese IME not exercised (only Japanese/Korean installed); Chinese composition is covered by the scripted Linux input method.
- Orca/Narrator speech journeys not run; AT-SPI and UIA were driven by automated clients.
- winit 0.30 limits: no IME surrounding text, OS theme changes only on Windows, no Wayland drag-and-drop.
- The private KWin used by `--plain` probes stores output settings in the user's `~/.config/kwinoutputconfig.json` (`Virtual-0` entry); the environment probe restores the scale it changes.
