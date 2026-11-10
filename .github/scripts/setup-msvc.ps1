$ErrorActionPreference = 'Stop'
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path $vswhere)) { throw 'Visual Studio Installer / vswhere is required for the external C SDK consumer.' }
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if ($LASTEXITCODE -ne 0 -or -not $installation) { throw 'MSVC x64 build tools were not found.' }
$setup = Join-Path $installation.Trim() 'VC\Auxiliary\Build\vcvars64.bat'
if (-not (Test-Path $setup)) { throw 'vcvars64.bat was not found.' }
$environmentLines = & $env:ComSpec /d /s /c "`"$setup`" >nul && set"
if ($LASTEXITCODE -ne 0) { throw 'MSVC environment setup failed.' }
$keep = @('PATH','INCLUDE','LIB','LIBPATH','WINDOWSSDKDIR','VCTOOLSINSTALLDIR','VSINSTALLDIR','VCINSTALLDIR','VSCMD_ARG_TGT_ARCH')
foreach ($line in $environmentLines) {
    $separator = $line.IndexOf('=')
    if ($separator -lt 1) { continue }
    $name = $line.Substring(0, $separator)
    $value = $line.Substring($separator + 1)
    if ($name.ToUpperInvariant() -in $keep) {
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        if ($env:GITHUB_ENV) { Add-Content -LiteralPath $env:GITHUB_ENV -Value "$name=$value" -Encoding utf8 }
    }
}
Write-Host 'MSVC x64 environment prepared for subsequent steps.'
