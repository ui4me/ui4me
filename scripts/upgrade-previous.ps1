[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $Destination,
    [Parameter(Mandatory)][string] $Version,
    [Parameter(Mandatory)][string] $ResultPath
)
$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.PSResourceGet -MinimumVersion 1.1.0 -ErrorAction Stop
$null = New-Item -ItemType Directory -Path $Destination -Force
Save-PSResource -Name Ui4me -Version $Version -Repository PSGallery -Path $Destination -TrustRepository -AcceptLicense -ErrorAction Stop
$module = Join-Path (Join-Path (Join-Path $Destination 'Ui4me') $Version) 'Ui4me.psd1'
Import-Module -Name $module -ErrorAction Stop
$info = Get-Ui4meInfo
if ($info.version -ne $Version -or (Import-PowerShellDataFile -LiteralPath $module).ModuleVersion -ne $Version) { throw 'Previous public package identity mismatch' }
Invoke-Ui4meApp -Backend headless {
    param($app)
    $window = $app.Open('<input id="value" value="previous">')
    if ($window.GetValue('value') -ne 'previous') { throw 'Previous package did not operate' }
    $null = $app.On('started', { $app.Stop() })
}
$info | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $ResultPath -Encoding utf8
