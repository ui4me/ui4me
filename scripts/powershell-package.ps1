[CmdletBinding()]
param([Parameter(Mandatory)][string]$ModulePath, [Parameter(Mandatory)][string]$Destination)
$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.PSResourceGet -MinimumVersion 1.1.0 -ErrorAction Stop
$manifest = Join-Path $ModulePath 'Ui4me.psd1'
if (-not (Test-Path $manifest)) { throw "Missing module manifest: $manifest" }
Test-ModuleManifest $manifest -ErrorAction Stop | Out-Null
Compress-PSResource -Path $ModulePath -DestinationPath $Destination -ErrorAction Stop
