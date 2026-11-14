# UI4ME 2.1 component layer for PowerShell on UI4ME.Core 1.x.
# Pure PowerShell (5.1 and 7.2+): no compiled assembly, no Python, no second native host.
# Every native operation goes through documented UI4ME.Core commands.
Set-StrictMode -Version 2.0

$script:UiBuilder = $null
$script:ModuleRoot = $PSScriptRoot
$script:AssetPath = Join-Path $PSScriptRoot 'assets'
$script:BlockedTags = @('script', 'style', 'iframe', 'object', 'embed')

# Load implementation in dependency order into this module's own scope.
# Fixed filenames: do not import arbitrary or user-controlled scripts.
. (Join-Path $PSScriptRoot 'private/00-helpers.ps1')
. (Join-Path $PSScriptRoot 'private/10-context-events.ps1')
. (Join-Path $PSScriptRoot 'private/20-application.ps1')
. (Join-Path $PSScriptRoot 'private/30-tasks.ps1')
. (Join-Path $PSScriptRoot 'private/40-state.ps1')
. (Join-Path $PSScriptRoot 'private/50-components.ps1')
. (Join-Path $PSScriptRoot 'private/55-advanced.ps1')
. (Join-Path $PSScriptRoot 'private/60-dynamic.ps1')
. (Join-Path $PSScriptRoot 'private/70-themes.ps1')
. (Join-Path $PSScriptRoot 'private/80-settings.ps1')
. (Join-Path $PSScriptRoot 'private/90-desktop.ps1')
. (Join-Path $PSScriptRoot 'private/95-skills.ps1')

Export-ModuleMember -Function @(
    'Invoke-UI4MEApp', 'Stop-UI4MEUiApp', 'Wait-UI4MEUi', 'Get-UI4MEUiContext', 'Get-UI4MEUiDiagnostics',
    'New-UI4MEState', 'New-UI4MEComputed',
    'Start-UI4MEUiTimer', 'Stop-UI4MEUiTimer', 'Start-UI4MEUiTask', 'Stop-UI4MEUiTask',
    'New-UI4METext', 'New-UI4MEHeading', 'New-UI4MEButton', 'New-UI4MEInput', 'New-UI4MENumber', 'New-UI4METextArea',
    'New-UI4MECheckbox', 'New-UI4MESelect', 'New-UI4MERadio', 'New-UI4MESlider', 'New-UI4MEDate', 'New-UI4METime', 'New-UI4MEColor',
    'New-UI4MERow', 'New-UI4MEColumn', 'New-UI4MECard', 'New-UI4MEGrid', 'New-UI4METoolbar', 'New-UI4MEScroll',
    'New-UI4MEForm', 'New-UI4MEDivider', 'New-UI4MESpacer', 'New-UI4MEBadge', 'New-UI4MEHtml', 'New-UI4MEImage',
    'New-UI4MELink', 'New-UI4MECode', 'New-UI4MEAlert', 'New-UI4MEProgress', 'New-UI4MESpinner', 'New-UI4MEAccordion',
    'New-UI4METabs', 'New-UI4MEList', 'New-UI4METable', 'New-UI4MEDialog', 'Show-UI4MEUiDialog', 'Close-UI4MEUiDialog',
    'Show-UI4MEUiToast', 'Add-UI4MEUiContent', 'Remove-UI4MEUiContent', 'New-UI4MEWhen', 'New-UI4MEEach',
    'Add-UI4MEUiCss', 'Set-UI4MEUiTheme', 'Show-UI4MEUiFileDialog', 'Start-UI4MEUiScript',
    'Get-UI4MEUiSetting', 'Set-UI4MEUiSetting',
    'New-UI4MEShell', 'New-UI4MESidebar', 'New-UI4MEContent', 'New-UI4MEHeader', 'New-UI4MEFooter',
    'New-UI4MEStatusBar', 'New-UI4MEFieldset', 'New-UI4MEMetric', 'New-UI4MEEmpty', 'New-UI4MELoading',
    'New-UI4MEIcon', 'New-UI4MEIconButton', 'New-UI4METooltip', 'New-UI4MEBreadcrumbs',
    'New-UI4MESegmented', 'New-UI4MEMultiSelect', 'New-UI4MEResizableSplit',
    'New-UI4MELog', 'Add-UI4MELogLine', 'New-UI4MECopyButton', 'Install-UI4MEUiSkill'
)
