# PowerShell UI4ME component reference

App: `Invoke-UI4MEApp -Title ... -Content {...} -OnReady {...} -OnClose {...} -OnCloseRequest {...} -OnError {...}`. Ordinary `pwsh -File app.ps1` is the entry point.

| Family | Public commands |
| --- | --- |
| State/work | `New-UI4MEState`, `New-UI4MEComputed`, `Start-/Stop-UI4MEUiTimer`, `Start-/Stop-UI4MEUiTask` |
| Layout | `New-UI4MERow`, `New-UI4MEColumn`, `New-UI4MEGrid`, `New-UI4MECard`, `New-UI4MEShell`, `New-UI4MESidebar`, `New-UI4MEContent`, `New-UI4MEHeader`, `New-UI4MEFooter`, `New-UI4MEStatusBar`, `New-UI4MEFieldset`, `New-UI4MEResizableSplit` |
| Inputs | `New-UI4MEInput`, `New-UI4MENumber`, `New-UI4METextArea`, `New-UI4MECheckbox`, `New-UI4MESelect`, `New-UI4MERadio`, `New-UI4MESegmented`, `New-UI4MEMultiSelect`, `New-UI4MESlider`, `New-UI4MEDate`, `New-UI4METime`, `New-UI4MEColor`, `New-UI4MEForm` |
| Content | `New-UI4METext`, `New-UI4MEHeading`, `New-UI4MEBadge`, `New-UI4MEIcon`, `New-UI4MEIconButton`, `New-UI4MEImage`, `New-UI4MELink`, `New-UI4MECode`, `New-UI4MEBreadcrumbs`, `New-UI4MEMetric`, `New-UI4MELog`, `Add-UI4MELogLine` |
| Navigation/data | `New-UI4METabs`, `New-UI4MEAccordion`, `New-UI4METable`, `New-UI4MEList`, `New-UI4MEEach`, `New-UI4MEWhen`, `Add-UI4MEUiContent` |
| Feedback | `New-UI4MEDialog`, `Show-/Close-UI4MEUiDialog`, `Show-UI4MEUiToast`, `New-UI4MEAlert`, `New-UI4MELoading`, `New-UI4MEEmpty`, `New-UI4MEProgress`, `New-UI4MESpinner`, `New-UI4METooltip`, `New-UI4MECopyButton` |
| Style/Core | `Set-UI4MEUiTheme`, `Add-UI4MEUiCss`, `Get-UI4MEUiContext`, `Show-UI4MEUiFileDialog`, `Get-/Set-UI4MEUiSetting` |

`New-UI4MEMultiSelect` expects a string-array `New-UI4MEState` via `-Bind`. `New-UI4MESegmented` uses radio buttons and works with the same state as `New-UI4MERadio`.

```powershell
Invoke-UI4MEApp -Title 'Components' -Content {
    $team = New-UI4MEState -Value @('alice')
    New-UI4MEMetric -Label 'Jobs running' -Value 4 -Detail 'Host active'
    New-UI4MEFieldset -Legend 'Members' -Content {
        New-UI4MEMultiSelect -Label 'Team' -Options @('alice','bob','carol') -Bind $team
    }
    New-UI4MEResizableSplit -Percent 40 -Side {
        New-UI4METext -Text 'Left'
    } -Main {
        New-UI4METext -Text 'Right'
    }
}
```

All UI4ME component IDs are generated and never require DOM selectors for normal application work. Use a `New-UI4MEHtml` island only for trusted markup.
