# Original `ui4me_old` code: verified file/line map

This is a **source-provenance map**, not a migration checklist or product-stability assessment. The user-supplied original archive is `bigbatmanorg-ui4me-old.zip` SHA-256 `5008aae9c8e3f460938667589c0a358b97e2f23558854925257a923925accdbc`; top-level path inside ZIP is `ui4me-main/`. Every file reference in this package begins at that root (example: `engine/crates/ui4me-dom/src/parse/fragment.rs:51-64`).

**224 features:** 129 have an implementation-looking source anchor; 15 have partial/related source anchors; 80 have no reliable old-code anchor in this catalog. All **144 anchored records** have an exact source path, line start/end, matched line number, and anchor excerpt in [`data/old-source-references.json`](data/old-source-references.json). Related **46 old test leads** are separately labeled, not treated as passes. The generated indexes cover declared symbols and tests inside the original owned Rust crates.

## Key warnings

1. The old repo reports `0.5.0-rc.1` **not release-qualified**, with remaining official Linux/provisional Windows pixel comparison failures. It also contains historical qualification exceptions and partial suites. See the original `PRODUCT_STATUS.md` and `RELEASE_EXECUTION.md`.
2. `ui4me_old` is *not* the refactored 0.2 repo. The old source line numbers should **never** be blindly applied to a file in current `main`.
3. Presence of a function cannot establish API exposure, tested semantics or performance. Parts of the old source contain stubs/reserved files; this catalogue explicitly avoids using a 1–3-line placeholder as evidence of an implemented feature.
4. Partial anchors (`old_evidence=partial-or-related`) demonstrate adjacent code but **not** the requested feature. Example: caret-position code is not complete read-only selection behavior.
5. `source_refs.csv` points to the *first verified textual match* in an original source file. The adjacent 3–13 lines are navigational excerpts; read surrounding implementations and target tests, not just the anchor window.
6. Test references are **leads**; do not claim a test passes until you execute that exact test in the new source context or review valid matching receipts.

## Locating code

Use any feature ID:

```bash
python - <<'PY'
import json
x=json.load(open('data/features.json'))
f=next(f for f in x['features'] if f['id']=='DOM-007')
print(f['title'], f['old_evidence'])
for ref in f['old_refs']:
    print(ref['path'], ref['line_start'], ref['line_end'], ref['match_text'])
PY
```

Then unzip the **original** archive into a separate checkout and inspect the referenced lines:

```bash
unzip bigbatmanorg-ui4me-old.zip -d old-source
nl -ba old-source/ui4me-main/engine/crates/ui4me-dom/src/parse/fragment.rs | sed -n '88,136p'
```

The package deliberately does not redistribute the 116MB donor archive. Provide the original zip separately to an agent when it needs to inspect actual donor implementations; the line reference and archive hash are enough to locate them reliably.

## Important source families

| Family | Original directory | What can be studied |
| --- | --- | --- |
| DOM parsing/tree/queries | `engine/crates/ui4me-dom/src/` | Parse, IDs, fragmentation, mutations, form state, journaling |
| CSS cascade/profiles | `engine/crates/ui4me-style/src/` | Selector/service, style sheets, computed values, profile filter |
| Layout | `engine/crates/ui4me-layout/src/` | Flex, grid, table, inline flow, scroll geometry, positioning |
| Text | `engine/crates/ui4me-text/src/` | Font environment, shaping, frozen paragraphs, selection/caret data |
| Interaction | `engine/crates/ui4me-interaction/src/` | Focus, default actions, keyboard, edit history, scroll, dialog |
| Scene/raster | `engine/crates/ui4me-scene/src/`, `ui4me-raster/src/` | Clip/paint/hit index, pixel output, damage |
| Assets | `engine/crates/ui4me-resources/src/` | URI/policy, worker pools, font/codec, SVG cache |
| Native platform | `engine/crates/ui4me-platform/src/` | Winit host, input, clipboard, accessibility adapters |
| Runtime/FFI | `engine/crates/ui4me-runtime/src/`, `ui4me-ffi/src/` | Owner loop, callbacks, C bridge, public API attempts |
| Accessibility | `engine/crates/ui4me-a11y/src/` | Accessibility tree and platform bridge candidates |
| Tests and diagnostics | `engine/crates/*/tests/`, `engine/crates/ui4me-oracle/` | Selected regressions and oracle techniques; qualify independently |

## High-priority old references to inspect first

The full feature catalogue contains every location. This shortlist directs the first implementation-agent deep dive:

- **DOM-007** incremental insertion: `engine/crates/ui4me-dom/src/parse/fragment.rs` (`insert_adjacent_html`).
- **DOM-009** atomic batch: `engine/crates/ui4me-dom/src/batch/exec.rs`.
- **DOM-017** geometry: `engine/crates/ui4me-runtime/src/geometry_query.rs`.
- **TEXT-007** read-only selection: related `engine/crates/ui4me-text/src/paragraph/frozen.rs` is **not** a finished document-selection implementation; additional design is required.
- **INTERACTION-006** program scroll: `engine/crates/ui4me-interaction/src/scroll.rs` (`scroll_to`, `scroll_by`).
- **INTERACTION-013** dialog semantics: `engine/crates/ui4me-interaction/src/dialog.rs`.
- **HOST-012** native clipboard: `engine/crates/ui4me-platform/src/clipboard/mod.rs`; inspect Windows/Wayland backends and the **lack of an equivalent old X11 system clipboard path**.
- **HOST-013/014** OS file and folder picker: partial FFI dialog code, **not** proof of a working cross-platform picker.
- **BIND-012** ownership: `engine/crates/ui4me-core/src/owner.rs`; new 0.2 owner design must take precedence over old runtime model.
- **QA-009** pixel oracle: `engine/crates/ui4me-oracle/src/compare/pixels.rs`.

## Reconciliation instructions for an implementation agent

For an old implementation candidate:

1. Read the **current** UI4ME file and API first. Confirm whether it already contains the relevant algorithm in a relocated form.
2. Inspect old anchor and entire function/module plus tests. Identify its assumptions about owner thread, DOM identity, stylesheet epochs, caching and platform services.
3. Check known old release failures and evaluate whether the exact algorithm was implicated, gated off or only conditionally supported.
4. Decide: **retain current**, **adapt donor algorithm**, **rewrite bounded adapter**, **defer**, or **reject**; document why.
5. Add a focused regression for the new public Core contract. Do not migrate an old full runtime or untested FFI surface by copying whole crates.
6. Update this map/registry with **new** source implementation paths and actual tests after work lands. Original donor anchors stay immutable historical references.

**Final rule:** code location = engineering lead; supported behavior = passing qualification for the exact new source and platform.
