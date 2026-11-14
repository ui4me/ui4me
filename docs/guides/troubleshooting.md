# Troubleshooting

| Symptom | What to check |
| --- | --- |
| No window | Installed `ui4me-core` platform wheel, valid Wayland/Windows graphical session, not SSH-only; `ui4me-host doctor` |
| `UI4ME_ENDPOINT` missing | UI4ME 2.1 should bootstrap automatically; check installed Core is >=1.0.1, not an old editable installation |
| A script appears to start twice | Core supervises the backend by reexecuting it. Put side effects after bootstrap, not at module import level |
| Python `ui4me-run` works but `python app.py` fails | Confirm `ui4me==2.1.0` and `ui4me-core>=1.0.1`, inspect traceback, test fresh venv |
| PowerShell module not found on Linux | Directory/manifest must use exact `Ui4me` spelling; install a new version rather than relying on 2.0.0 Gallery casing |
| PowerShell 5.1 failure | Verify `.ps1` encoding, dependencies and script portability; run tests under **Windows PowerShell**, not only pwsh |
| UI stops updating after an error | DOM transaction failed; inspect `app.on_error()` / PowerShell `-OnError`, root cause, document generation; fail-closed until recovered |
| Events stop after replacing raw document | UI4ME owns its managed document. Do not `load_html` into a managed window; use `ui.html` islands or a raw Core window |
| `lambda` logic fails | Use named `def on_click(event)` for callbacks. Reactive Python expressions are `lambda: ...` or `ui.computed` |
| CSS looks wrong | Core implements a desktop HTML/CSS subset, not every browser feature. Check unsupported selectors/input types in Core docs |
| Wayland focus/placement ignored | Compositor policy limits focus and window positioning; check native capability response |
| PowerShell tasks don't update UI | UI calls must run in the owning runspace; use the supplied UI task/completion machinery |
| The app closes by itself during a theme change or heavy animation ("Backend connection lost: closed by host", "outgoing queue unavailable" in the log) | Core 1.0.1 forwards every DOM event and disconnects an app that falls behind. Remove CSS transitions/animations that start on many elements at once; UI4ME's own theme switch already suspends them. See [Core integration](../concepts/core-integration.md#measured-core-101-behavior-that-affects-applications) |
| A traceback scrolls by but the window never appears | Startup errors are printed in the terminal you started from and the exit status is 1; fix the error shown first |
| PowerShell: a state variable inside `-Content` turns into a string | You wrapped `Invoke-UI4MEApp` in your own function with a typed parameter of the same name (`[string]$Theme` vs `$theme = New-UI4MEState`). `-Content` runs in your function's scope and PowerShell variable names are case-insensitive; rename the variable or drop the type |
| `on_change` fires with half-typed text while using an IME | Composition updates the value before commit (browser semantics). Validate on blur/submit, or use `ui.form(validation_mode="blur")` |

Report bugs with operating system/desktop session, Python/PowerShell/Core/UI4ME versions, a minimal example, and native/headless status. No test mode can substitute for real keyboard, IME or accessibility verification.
