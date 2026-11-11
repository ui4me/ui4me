# Using the old and current source safely

Current source is always primary. The 0.4 uploaded archive has important code already in place in `crates/ui4me-document/src/serialize.rs`, `stylesheets.rs`, `crates/ui4me-renderer/src/style/animation.rs`, `layout/fragmentation/paged.rs`, `pipeline/update.rs`, `a11y/build.rs`. Their presence **does not** mean public API support; compare to `crates/ui4me-core/src/protocol.rs`, `include/ui4me.h`, Python facade and PowerShell wrapper.

Each `versions/*.md` item includes **actual source path+line leads** found via static text search of the supplied uploaded 0.4 archive, plus **old-source paths and ranges** from `docs/core-foundation/reference/data/features.json` when available. A current lead is a locator for review, not proof of implementation. Old references include confidence from research and often are only file leads. Recompute line numbers if `main` changed.

Old donor reference source is expected at `/home/toor/projects/ui4me-old-reference` or sibling `../ui4me-old-reference`. If absent, check user-specified local path once; don't fetch an old GitHub repository automatically. Old Rust crate names and host abstractions may differ drastically. Selectively migrate algorithm/fixture only after confirming current security, ID, thread, asset and ABI invariants. Don't add the 116MB old archive to Git.

Do not duplicate renderer implementations that already exist internally. If `FEATURES` profile state says `Off` or `Unavailable`, check the parser/style/layout/scene path before changing profile state. Flipping a feature flag without implementing the pipeline is a bug.
