# Building the Python and PowerShell artifacts

UI4ME itself is pure Python / PowerShell + CSS and does **not** build a Rust host. Runtime dependency resolution installs Core from PyPI/PowerShell Gallery. The release source artifact must never contain `ui4me_core` or native binaries.

```bash
python -m pip install -e . pytest build twine
python tools/sync_skills.py --check
python -m pytest -q tests/unit tests/bridge
python tools/build_dist.py dist
python -m twine check dist/*.whl dist/*.tar.gz
python tools/release/source_manifest.py --check
python tools/check_artifacts.py dist
```

Expected release triple: `ui4me-2.1.0-py3-none-any.whl`, `ui4me-2.1.0.tar.gz`, `UI4ME-2.1.0.zip` plus `SHA256SUMS`. The PowerShell ZIP contains a single `Ui4me/` module directory with `Ui4me.psd1`, `Ui4me.psm1`, `private/`, `assets/`, user README, and coding-agent skills. The Python wheel must contain `ui4me-ui-python` skill files and the standalone Python package description.

Do not confuse a built artifact with qualified artifact. Verify the **installed** wheel in an empty venv outside the checkout and the **staged** PowerShell module on Linux and Windows. Keep any benchmark evidence outside release archives. See [testing](testing.md) and [publishing](publishing.md).
