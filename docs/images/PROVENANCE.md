# Screenshot provenance

Every image here is an unedited capture of an unmodified example app from this repository, taken
during the UI4ME 2.1.0 native qualification on 2026-11-14 with the release build
(`ui4me-2.1.0-py3-none-any.whl` sha256 `ba118d0d1b4d5984600154d969f3135fc248dd0a5cbfde50683946e59d921c84`,
`UI4ME-2.1.0.zip` sha256 `fec313f7101fc2670f3a9d042cb2572e59252e813ed8df7f3fc12abc6ab3fc48`) and UI4ME Core 1.0.1.
No mockups; nothing was retouched.

| File | App | Platform | Captured by |
| --- | --- | --- | --- |
| `gallery-python-kde.png` | `examples/python/gallery.py` | Debian 13, KDE Plasma 6.3 Wayland (KWin 6.3.6 virtual output), Python 3.13, dark system theme | `tests/native/linux/vkwin.py` + `tests/native/apps/py_showcase.py` (spectacle inside the private session) |
| `gallery-powershell-kde.png` | `examples/powershell/gallery.ps1` | same, PowerShell 7.7 | `vkwin.py` + `tests/native/apps/ps_showcase.ps1` |
| `gallery-python-windows.png` | `examples/python/gallery.py` | Windows Server 2022 (10.0.20348), RDP session, Python 3.13.17, light theme | `tests/native/windows/rdp_driver.py` + `py_showcase.py` (window frame capture in the session) |
| `operations-python-windows.png` | `examples/python/operations_dashboard.py` | same | same |

SHA-256:

```
cfaefcd47de4d3c76b2c3da3c1825b69bf89dbfd10ab8b67763bbdb94d7e7b8d  gallery-powershell-kde.png
f440573a1564daac847170bab03c3bb6a8415dce07df9212094a14e817041b60  gallery-python-kde.png
535b3e4a5b6904e5d2532ece01b4f22d3cafd783ae29bdbf3ff934a8900b589d  gallery-python-windows.png
baec4433fbc3cdc983c930c69ecd1d841a0270591f9cda670161c21d4116938d  operations-python-windows.png
```
