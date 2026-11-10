[CmdletBinding()]
param([switch]$InstallTools)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if ($InstallTools) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'WinGet is required for -InstallTools; otherwise install prerequisites manually.' }
    foreach ($id in @('Python.Python.3.12', 'Rustlang.Rustup', 'Microsoft.DotNet.SDK.10', 'Microsoft.PowerShell')) {
        & winget install --id $id --exact --source winget --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) { throw "Installation failed for $id. Inspect WinGet output; restart the terminal after installation." }
    }
    Write-Host 'Install Visual Studio 2022 Build Tools with Desktop development with C++ and Windows SDK; use its x64 developer shell.'
    Write-Host 'Restart the terminal so newly installed executables are on PATH, then run this script without -InstallTools.'
    return
}
& py -3.12 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required by this convenience bootstrap; repository tooling supports Python 3.11+.' }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip setup failed' }
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Development dependency installation failed' }
Write-Host 'Next: .\.venv\Scripts\Activate.ps1, then python dev.py doctor.'
Write-Host 'First reconstruction setup: python dev.py lock; review and commit Cargo.lock and packages.lock.json before building or CI.'
