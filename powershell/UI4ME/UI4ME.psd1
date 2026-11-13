@{
    RootModule = 'UI4ME.psm1'
    ModuleVersion = '2.0.0'
    GUID = 'cf797c5d-35fd-48a5-9cfa-661a0c63f723'
    Author = 'UI4ME Contributors'
    CompanyName = 'UI4ME'
    Copyright = '(c) 2026 UI4ME contributors. MIT license.'
    Description = 'Native desktop GUI components, state binding, keyed lists, timers, background tasks and themes for PowerShell, on the UI4ME.Core 1.x native host. No browser, Python or web server.'
    PowerShellVersion = '5.1'
    DotNetFrameworkVersion = '4.7.2'
    CompatiblePSEditions = @('Desktop', 'Core')
    RequiredModules = @(@{ModuleName = 'UI4ME.Core'; ModuleVersion = '1.0.0'})
    FunctionsToExport = @(
        'Invoke-UI4MEApp',
        'Stop-UI4MEUiApp',
        'Wait-UI4MEUi',
        'Get-UI4MEUiContext',
        'Get-UI4MEUiDiagnostics',
        'New-UI4MEState',
        'New-UI4MEComputed',
        'Start-UI4MEUiTimer',
        'Stop-UI4MEUiTimer',
        'Start-UI4MEUiTask',
        'Stop-UI4MEUiTask',
        'New-UI4METext',
        'New-UI4MEHeading',
        'New-UI4MEButton',
        'New-UI4MEInput',
        'New-UI4MENumber',
        'New-UI4METextArea',
        'New-UI4MECheckbox',
        'New-UI4MESelect',
        'New-UI4MERadio',
        'New-UI4MESlider',
        'New-UI4MEDate',
        'New-UI4METime',
        'New-UI4MEColor',
        'New-UI4MERow',
        'New-UI4MEColumn',
        'New-UI4MECard',
        'New-UI4MEGrid',
        'New-UI4METoolbar',
        'New-UI4MEScroll',
        'New-UI4MEForm',
        'New-UI4MEDivider',
        'New-UI4MESpacer',
        'New-UI4MEBadge',
        'New-UI4MEHtml',
        'New-UI4MEImage',
        'New-UI4MELink',
        'New-UI4MECode',
        'New-UI4MEAlert',
        'New-UI4MEProgress',
        'New-UI4MESpinner',
        'New-UI4MEAccordion',
        'New-UI4METabs',
        'New-UI4MEList',
        'New-UI4METable',
        'New-UI4MEDialog',
        'Show-UI4MEUiDialog',
        'Close-UI4MEUiDialog',
        'Show-UI4MEUiToast',
        'Add-UI4MEUiContent',
        'Remove-UI4MEUiContent',
        'New-UI4MEWhen',
        'New-UI4MEEach',
        'Add-UI4MEUiCss',
        'Set-UI4MEUiTheme',
        'Show-UI4MEUiFileDialog',
        'Start-UI4MEUiScript',
        'Get-UI4MEUiSetting',
        'Set-UI4MEUiSetting'
    )
    CmdletsToExport = @()
    AliasesToExport = @()
    VariablesToExport = @()
    PrivateData = @{PSData = @{Tags = @('UI','GUI','Native','Desktop','PowerShell','Linux','Windows');
        ProjectUri = 'https://github.com/ui4me/ui4me';
        LicenseUri = 'https://github.com/ui4me/ui4me/blob/main/LICENSE'}}
}
