# PowerShell settings example; run directly: pwsh -File ./examples/powershell/settings.ps1
$ErrorActionPreference = 'Stop'
Import-Module UI4ME

Invoke-UI4MEApp -Title 'UI4ME Settings' -Width 720 -Height 650 -Content {
    $name = New-UI4MEState -Value (Get-UI4MEUiSetting -Name DisplayName -Default 'Operator')
    $theme = New-UI4MEState -Value (Get-UI4MEUiSetting -Name Theme -Default 'system')
    New-UI4MEHeading -Text 'Settings' -Level 1
    New-UI4MEFieldset -Legend 'User' -Content {
        New-UI4MEInput -Label 'Display name' -Bind $name -Required
        New-UI4MESelect -Label 'Theme' -Options @('system', 'light', 'dark') -Bind $theme
    }
    New-UI4MERow -Content {
        New-UI4MEButton -Text 'Save settings' -OnClick {
            Set-UI4MEUiSetting -Name DisplayName -Value $name.Value
            Set-UI4MEUiSetting -Name Theme -Value $theme.Value
            Set-UI4MEUiTheme -ColorScheme $theme.Value
            Show-UI4MEUiToast -Text 'Saved preferences' -Tone success
        }
        New-UI4MEButton -Text 'Quit' -Variant secondary -OnClick { Stop-UI4MEUiApp }
    }
}
