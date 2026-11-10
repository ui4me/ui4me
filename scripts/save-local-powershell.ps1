[CmdletBinding()]
param([Parameter(Mandatory)][string]$Feed, [Parameter(Mandatory)][string]$Destination, [Parameter(Mandatory)][string]$Version)
$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.PSResourceGet -MinimumVersion 1.1.0 -ErrorAction Stop
$repository = 'ui4me-test-' + [guid]::NewGuid().ToString('N')
try {
    Register-PSResourceRepository -Name $repository -Uri $Feed -Trusted -ErrorAction Stop
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Save-PSResource -Name Ui4me -Version $Version -Repository $repository -Path $Destination -TrustRepository -AcceptLicense -ErrorAction Stop
    $manifest = Join-Path (Join-Path (Join-Path $Destination 'Ui4me') $Version) 'Ui4me.psd1'
    if (-not (Test-Path -LiteralPath $manifest)) { throw "Saved package layout is unexpected: $manifest" }
} finally {
    if (Get-PSResourceRepository -Name $repository -ErrorAction SilentlyContinue) {
        Unregister-PSResourceRepository -Name $repository -ErrorAction Stop
    }
}
