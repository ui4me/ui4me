# Contributor instructions

Read `docs/PROJECT_STATUS.md` before changing lifecycle behavior. Keep runtime
ownership explicit and public APIs small.

- Maintain one source tree and separate Python and PowerShell packages. Keep the C ABI language-neutral.
- Do not claim a test passed without evidence from this source and the exact packaged artifacts.
- Preserve `not_run`, `blocked`, `failed`, `interrupted` and `passed` as distinct results.
- Run only the selected platform/binding locally; release qualification requires the complete supported matrix.
- Keep generated files in `build/` or `dist/`. Do not commit credentials, logs, screenshots, binaries, or local environments.
- Publishing is explicit and separate from build/test. Never publish automatically on pull requests.
- Do not reuse test evidence from a different source identity.
- Honor source-only/no-execution requests. Otherwise use the documented local commands for the affected binding and platform before claiming validation.
