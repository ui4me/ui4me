# Install UI4ME for Python

**Platform:** Python 3.11+; Linux x86-64 with glibc 2.34+ and Wayland (qualified on KDE Plasma 6), or Windows x64 (qualified on Windows Server 2022). macOS, ARM and X11 desktop support are not qualified. Python `ui4me` installs native `ui4me-core` transitively; no Rust compiler is needed for the published wheel.

## uv (recommended)

```bash
uv init --bare my-desktop-app
cd my-desktop-app
uv add 'ui4me>=2.1,<3'
uv run ui4me-ui-new first-app --name 'My App'   # create in a new subfolder
```

For an existing uv project, use `uv add ui4me`, then run your own `app.py` with `uv run app.py`. If your folder is already populated, use `uv run ui4me-ui-new first-app --name 'First App'` and run that script from the project root.

## pip/venv

```bash
python -m venv .venv
source .venv/bin/activate       # Linux
# .venv\Scripts\Activate.ps1    # Windows PowerShell
python -m pip install ui4me
python -c 'import ui4me, ui4me_core; print(ui4me.__version__, ui4me_core.__version__)'
```

Next: [quickstart](quickstart-python.md), [recipes](../recipes/python.md), [components](../components/index.md). Development from a source checkout: `python -m pip install -e .` (with published Core already installed).
