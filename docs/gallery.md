# UI4ME component gallery and application demos

The gallery is a **real runnable application**, not mock screenshots. It exercises component creation, reactive updates, tables, charts, forms, theme changes, backgrounds, keyboard navigation and desktop interactions. It is designed as both a documentation resource and a native integration-test target.

## Launch Python gallery

```bash
python examples/python/gallery.py
# or: uv run examples/python/gallery.py
```

## Launch PowerShell gallery

```powershell
pwsh -NoProfile -File ./examples/powershell/gallery.ps1
# Windows PowerShell 5.1:
powershell.exe -NoProfile -File .\examples\powershell\gallery.ps1
```

The library has additional applications in `examples/python/apps/` and `examples/powershell/apps/`: an administration dashboard, settings editor, file utility and monitoring tool. These are small reproducible reference applications, not simulations of native OS services.

**Screenshots:** produce screenshots using the installed release candidate on KDE Wayland and Windows, then add verified, real captures to `docs/images/`. Do not fabricate or label renderer screenshots as native desktop evidence. Record commit/version and environment with each asset.

In testing, use the gallery to verify narrow/wide windows, each control's interaction, light/dark theme, keyboard-only paths, screen-reader names and controlled/uncontrolled state changes.
