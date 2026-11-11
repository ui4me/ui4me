# CSS profile and fixed Core support boundary

The source includes `crates/ui4me-renderer/src/style/profile/table.rs` with **154** extracted named CSS feature-state rows: Filtered=10, Off=37, On=86, Unavailable=21. Snapshot lives in `data/CSS_PROFILE_V0_4.json` and `.csv`. All rows come directly from the uploaded source; no runtime enablement testing was done.

Classify each Off/Unavailable/Filtered item before 0.9/1.0 as one of:

- `ENABLE`: improves common native desktop HTML/CSS, has an implementation route, and is added to a milestone work item with a real fixture and profile update.
- `ENABLE_LATER`: valuable but requires a prerequisite like GPU, SVG DOM, animation clock or paged printing.
- `INTENTIONALLY_UNSUPPORTED`: web-only, security-hostile, JS/DOM browser-infrastructure dependent, or not useful in a standalone native desktop engine. Keep the diagnostic and rationale permanently.
- `ENGINE_UNAVAILABLE`: current Stylo/Taffy pipeline cannot implement safely without an extensive upstream fork; document honest support profile and an alternate CSS pattern.

Prefer app-developer stable CSS: flex, grid, subgrid, tables, responsive queries, content visibility, scroll and focus behavior, fixed/sticky, fonts, masks, popovers, animations/transitions and static inline SVG. Do not promise every WPT/CSS standard.

A CSS capability is truly `On` only if parsing, cascading, computed value, used layout/paint/interaction, invalidation and regression evidence agree. Changes that merely silence diagnostics are not completion. Keep a deterministic CPU oracle and meaningful unsupported diagnostics in the public interface.
