@{
    RootModule = 'Ui4me.psm1'
    ModuleVersion = '0.1.0'
    GUID = '5a6ad4f3-5fc3-4bfd-a4bb-06c48b842af2'
    Author = 'ui4me contributors'
    CompanyName = 'ui4me'
    Copyright = '(c) ui4me contributors. MIT license.'
    Description = 'Small native UI runtime for PowerShell. Reconstructed v0.1 foundation source.'
    PowerShellVersion = '7.4'
    CompatiblePSEditions = @('Core')
    FunctionsToExport = @('Invoke-Ui4meApp', 'Get-Ui4meInfo', 'New-Ui4meWindow', 'Register-Ui4meEvent', 'Set-Ui4meText', 'Get-Ui4meValue', 'Stop-Ui4meApp')
    CmdletsToExport = @()
    VariablesToExport = @()
    AliasesToExport = @()
    PrivateData = @{
        PSData = @{
            Tags = @('ui4me', 'GUI', 'Windows', 'Linux')
            LicenseUri = 'https://github.com/ui4me/ui4me/blob/main/LICENSE'
            ProjectUri = 'https://ui4me.github.io/'
            ReleaseNotes = 'Foundation 0.1.0. See release qualification evidence before relying on platform support.'
        }
    }
}
