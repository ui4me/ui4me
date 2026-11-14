# Feedback, overlays and desktop actions

**Python:** `ui.alert`, `ui.notify` (in-window toast), `ui.dialog`, `ui.confirm`, `ui.tooltip`, `ui.empty`, `ui.loading`, `ui.error_state`, `ui.progress`, `ui.spinner`, `ui.copy_button` (Core plain-text clipboard). Native file dialogs are available through Core wrappers.

**PowerShell:** `New-UI4MEAlert`, `Show-UI4MEUiToast`, `New-UI4MEDialog`, `Show-UI4MEUiDialog`, `Close-UI4MEUiDialog`, `New-UI4METooltip`, `New-UI4MEEmpty`, `New-UI4MELoading`, `New-UI4MEProgress`, `New-UI4MESpinner`, `New-UI4MECopyButton`, `Show-UI4MEUiFileDialog`.

Use messages as escaped *text*; the high-level toast and alert APIs are not arbitrary HTML injection points. Clipboard access may require a recent user gesture on Wayland. Dialog and focus behavior depends on the native Core capabilities: test real pointer and keyboard journeys. In-window toast is **not** a system notification; OS notifications and system tray are not currently supported.
