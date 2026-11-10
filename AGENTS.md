# Contributor instructions

This is the clean ui4me v0.1 foundation. Keep runtime ownership explicit and public APIs small.

- Read `specs/001-foundation/spec.md` and `docs/native-contract.md` before changing lifecycle behavior.
- One source tree, separate Python and PowerShell packages. Keep the C ABI language-neutral.
- Do not claim a test passed without evidence from this source and the exact packaged artifacts.
- Preserve `not_run`, `blocked`, `failed`, and `passed` as distinct results.
- Run only the selected platform/binding locally; release qualification requires the complete supported matrix.
- Keep generated files in `build/` or `dist/`. Do not commit credentials, logs, screenshots, binaries, or local environments.
- Publishing is explicit and separate from build/test. Never publish automatically on pull requests.
- The initial delivered reconstruction has not been compiled or executed. Do not reuse results from the lost implementation.

## Current reconstruction constraint

The user requested source delivery without running the code. During this reconstruction, do not compile, launch, import, test, or publish project code. File creation, reading, static review, archiving, checksums and saving deliverables are allowed. Subsequent local execution is the user's decision.
