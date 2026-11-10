[CmdletBinding()]
param([Parameter(Mandatory)][string]$PackagePath)
$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.PSResourceGet -MinimumVersion 1.1.0 -ErrorAction Stop
if (-not $env:PSGALLERY_API_KEY) { throw 'Set PSGALLERY_API_KEY securely in the publication environment.' }
if (-not (Test-Path -LiteralPath $PackagePath -PathType Leaf)) { throw 'Package file does not exist.' }
Publish-PSResource -NupkgPath $PackagePath -Repository PSGallery -ApiKey $env:PSGALLERY_API_KEY -ErrorAction Stop
