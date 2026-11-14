# PowerShell API reference — UI4ME 2.1.0

`Import-Module UI4ME` loads the high-level module and its required dependency `UI4ME.Core>=1.0.1`. Run a plain `app.ps1` using `Invoke-UI4MEApp -Title ... -Content { ... }`, directly with `pwsh -File app.ps1` or `powershell.exe -File app.ps1` on Windows. UI4ME calls Core's `Start-UI4MEScript` internally.

## App, state and work

| Category | Exported commands |
| --- | --- |
| App | `Invoke-UI4MEApp`, `Stop-UI4MEUiApp`, `Wait-UI4MEUi`, `Get-UI4MEUiContext`, `Get-UI4MEUiDiagnostics` |
| State | `New-UI4MEState`, `New-UI4MEComputed` |
| Work | `Start-UI4MEUiTimer`, `Stop-UI4MEUiTimer`, `Start-UI4MEUiTask`, `Stop-UI4MEUiTask` |
| Settings | `Get-UI4MEUiSetting`, `Set-UI4MEUiSetting` |
| Skills | `Install-UI4MEUiSkill` |
| Legacy launcher | `Start-UI4MEUiScript -Path ... [-Headless]` |

## Components

| Group | Commands |
| --- | --- |
| Text | `New-UI4METext`, `New-UI4MEHeading`, `New-UI4MEBadge`, `New-UI4MEHtml`, `New-UI4MECode`, `New-UI4MEImage`, `New-UI4MELink`, `New-UI4MEIcon`, `New-UI4MEIconButton`, `New-UI4MEMetric` |
| Inputs | `New-UI4MEInput`, `New-UI4MENumber`, `New-UI4METextArea`, `New-UI4MECheckbox`, `New-UI4MESelect`, `New-UI4MERadio`, `New-UI4MESlider`, `New-UI4MEDate`, `New-UI4METime`, `New-UI4MEColor`, `New-UI4MESegmented`, `New-UI4MEMultiSelect` |
| Layout | `New-UI4MERow`, `New-UI4MEColumn`, `New-UI4MECard`, `New-UI4MEGrid`, `New-UI4METoolbar`, `New-UI4MEScroll`, `New-UI4MEForm`, `New-UI4MEFieldset`, `New-UI4MEShell`, `New-UI4MESidebar`, `New-UI4MEContent`, `New-UI4MEHeader`, `New-UI4MEFooter`, `New-UI4MEStatusBar`, `New-UI4MEResizableSplit`, `New-UI4MEDivider`, `New-UI4MESpacer` |
| Dynamic | `New-UI4MEWhen`, `New-UI4MEEach`, `Add-UI4MEUiContent`, `Remove-UI4MEUiContent` |
| Data | `New-UI4METable`, `New-UI4MEList`, `New-UI4MELog`, `Add-UI4MELogLine` |
| Navigation | `New-UI4METabs`, `New-UI4MEAccordion`, `New-UI4MEBreadcrumbs` |
| Feedback | `New-UI4MEDialog`, `Show-UI4MEUiDialog`, `Close-UI4MEUiDialog`, `Show-UI4MEUiToast`, `New-UI4MEAlert`, `New-UI4METooltip`, `New-UI4MEEmpty`, `New-UI4MELoading`, `New-UI4MEProgress`, `New-UI4MESpinner`, `New-UI4MECopyButton` |
| Theme/desktop | `Add-UI4MEUiCss`, `Set-UI4MEUiTheme`, `Show-UI4MEUiFileDialog` |

For exact parameters use `Get-Help <Command> -Full`, `Get-Command <Command> -Syntax` and the published module source in [`powershell/Ui4me/private`](https://github.com/ui4me/ui4me/tree/main/powershell/Ui4me/private). UI4ME.Core's own commands remain available through `Get-UI4MEUiContext` for native desktop APIs.

## Important differences from Python

PowerShell 2.1 is pure PowerShell and does not ship Python or a native host. It has explicit dependency-based computed state, one high-level window per `Invoke-UI4MEApp` invocation, and simpler table/form APIs. Python additionally has multiple windows, richer table loaders, automatic signals/effects, full Markdown/chat and command registries. Do not promise those as PowerShell parity features unless the tests show they were implemented. Never call Core UI commands from background runspaces.
