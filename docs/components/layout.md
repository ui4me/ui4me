# Layout, shells, and dashboard widgets

**Python:** `ui.row`, `ui.column`, `ui.stack`, `ui.grid`, `ui.card`, `ui.surface`, `ui.paper`, `ui.shell`, `ui.sidebar`, `ui.content`, `ui.header`, `ui.footer`, `ui.statusbar`, `ui.toolbar`, `ui.split` (fixed split), `ui.resizable_split` (range adjustable), `ui.fieldset`, `ui.metric`, `ui.spacer`, `ui.divider`.

```python
with ui.row(gap='lg'):
    ui.metric('Jobs', 18, detail='3 active')
    ui.metric('Healthy', '97%', tone='success')
with ui.resizable_split(percent=35, label='Panel width') as panes:
    with panes.side:
        ui.text('Navigation')
    with panes.main:
        ui.text('Details')
```

**PowerShell:** `New-UI4MERow`, `New-UI4MEColumn`, `New-UI4MECard`, `New-UI4MEGrid`, `New-UI4MEShell`, `New-UI4MESidebar`, `New-UI4MEContent`, `New-UI4METoolbar`, `New-UI4MEHeader`, `New-UI4MEFooter`, `New-UI4MEStatusBar`, `New-UI4MEFieldset`, `New-UI4MEMetric`, `New-UI4MEResizableSplit`.

```powershell
New-UI4MERow -Content {
    New-UI4MEMetric -Label 'Jobs' -Value 18 -Detail '3 active'
    New-UI4MEMetric -Label 'Healthy' -Value '97%'
}
```

CSS themes use `--u4-*` tokens, stable `u4-*` classes. The adjustable split uses an accessible *range input*, not a fragile custom drag handler, so keyboard arrow keys work. Responsive behavior is primarily Core CSS flex/grid/media-query layout, not a JavaScript breakpoint engine. Verify narrow/wide windows and focus preservation in native tests.
