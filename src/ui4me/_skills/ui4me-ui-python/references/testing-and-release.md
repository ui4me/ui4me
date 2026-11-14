# Testing and deployment

Fast: `python -m pytest tests/unit tests/bridge -q` with package installed/editable. Real headless: `python -m pytest tests/host -q`; first ensure the Core platform wheel is installed.

Normal application: `python app.py`, `uv run app.py`. Old launcher: `ui4me-run app.py`; CI headless: `ui4me-run --headless app.py` or `UI4ME_TEST_MODE=1 python app.py` (Core test mode).

Gallery: `python examples/python/gallery.py`. Native qualification: Linux KDE Plasma/Wayland and Windows interactive session, real input and keyboard. Automated fake Core tests do not qualify native focus, input-method editors, filesystem dialogs, or accessibility.

Packages: `python tools/build_dist.py dist` for wheel+sdist+PowerShell ZIP. `python tools/check_artifacts.py dist` checks no Rust or Core binaries are bundled. Release is manual-only after tests, fresh-installed wheels/modules, exact Core compatibility and registry version preflight. Do not publish from an unqualified tree or silently skip broken tests.

The UI Python package and PowerShell module have the same UI version but independent artifacts; Core is versioned separately. Use project-scoped skill installation during development if preferred: `ui4me-ui-skill install --scope project --project . --agents claude,codex`.
