# Reset and migration (2026-11-13)

The old `ui4me/ui4me` source is superseded by
[UI4ME Core](https://github.com/ui4me/ui4me-core), version 1.0.0. This repository
was intentionally reset to become the simple UI4ME frontend package.

- Existing historical commits are retained in the Git repository. The reset
  command makes an additional local `backup/pre-wrapper-reset-*` reference.
- No old Rust code or binary artifacts are copied forward.
- `import ui4me` now resolves the public API through `ui4me_core`.
- `Application`, `Window`, `Document`, `LiveBitmap`, protocol exceptions and
  Core's public launcher locator are **the same objects** exposed by Core.
- No old custom components or legacy API behavior is maintained. Applications
  targeting the old, unrelated API need migration to Core's documented API.
- Do not install the legacy `ui4me` package and the new wrapper into the same
  environment without first uninstalling the old package.

This wrapper deliberately has no separate PowerShell module yet. When PowerShell
support is added, use the same native host/protocol owned by Core rather than
restoring the obsolete Rust engine or copying its implementation.
