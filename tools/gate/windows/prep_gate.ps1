# Stage the Windows gate (Core 1.0, F1107): install the candidate wheel into a fresh venv and
# expand the candidate module stage under $Root, copy the harnesses, examples and probes, and
# write the PowerShell wrappers that import the installed module. Run as the administrator after
# `dev.py package` built the candidate in $Src\dist\win-x64. Fails (nonzero) on any staging error.
param(
    [string] $Src = 'C:\Users\Administrator\ui4me-dev',
    [string] $Root = 'C:\Users\Public\ui4me-gui\gate',
    [string] $Python = 'C:\Users\Public\ui4me-gui\python\python.exe',
    [string] $PyDeps = 'C:\Users\Public\ui4me-gui\r05in\pydeps'
)
$ErrorActionPreference = 'Stop'
$version = (Get-Content "$Src\VERSION").Trim()
# Only a directory this script created (it holds the .ui4me-gate marker) or an empty one is
# replaced; anything else is refused, never deleted.
$Root = [IO.Path]::GetFullPath($Root)
$marker = Join-Path $Root '.ui4me-gate'
$protected = @([IO.Path]::GetPathRoot($Root), $env:USERPROFILE, $env:PUBLIC, $env:SystemRoot, [IO.Path]::GetFullPath($Src)) | Where-Object { $_ } | ForEach-Object { $_.TrimEnd('\') }
if ($protected -contains $Root.TrimEnd('\') -or ([IO.Path]::GetFullPath($Src).TrimEnd('\') + '\').StartsWith($Root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing gate root ${Root}: use a dedicated directory"
}
if (Test-Path -LiteralPath $Root) {
    $item = Get-Item -LiteralPath $Root -Force
    if (-not $item.PSIsContainer -or $item.LinkType) { throw "Refusing gate root ${Root}: not a plain directory" }
    if (Test-Path -LiteralPath $marker -PathType Leaf) {
        Remove-Item -LiteralPath $Root -Recurse -Force
    } elseif (@(Get-ChildItem -LiteralPath $Root -Force).Count -eq 0) {
        Remove-Item -LiteralPath $Root -Force
    } else {
        throw "Refusing gate root ${Root}: exists and is not a gate directory (no .ui4me-gate marker)"
    }
}
New-Item -ItemType Directory -Force $Root, "$Root\results", "$Root\mod" | Out-Null
'ui4me gate output; tools/gate/windows/prep_gate.ps1 may delete this directory' | Set-Content -LiteralPath $marker
& $Python -m venv "$Root\venv"
if ($LASTEXITCODE) { throw "venv creation failed ($LASTEXITCODE)" }
& "$Root\venv\Scripts\python.exe" -m pip install -q (Get-ChildItem "$Src\dist\win-x64\ui4me-$version-*.whl").FullName
if ($LASTEXITCODE) { throw "wheel installation failed ($LASTEXITCODE)" }
Expand-Archive "$Src\dist\win-x64\Ui4me-$version-win-x64-stage.zip" -DestinationPath "$Root\mod"
Copy-Item -Recurse "$Src\examples" "$Root\examples"
# Shared probes first, then the Windows harnesses: a Windows file of the same name wins.
Copy-Item "$Src\tests\native\*" $Root -Include *.py, *.ps1, *.lua
Get-ChildItem "$Src\tests\native\windows" -File | Copy-Item -Destination $Root
Copy-Item -Recurse "$Src\tests\packaging" "$Root\packaging"
Copy-Item "$Src\docs\reference\PLATFORM_CAPABILITIES_V1.json" "$Root\PLATFORM_CAPABILITIES_V1.json"
if (Test-Path $PyDeps) { Copy-Item -Recurse $PyDeps "$Root\pydeps" }
# The LuaJIT binding (pure Lua) and the LuaJIT built by bindings\lua\tools\build_luajit.cmd (the gate
# fails its lua step without it).
Copy-Item -Recurse "$Src\bindings\lua" "$Root\lua"
Copy-Item "$Src\tests\lua\test_ui4me.lua" $Root
if (Test-Path "$Src\build\luajit\src\luajit.exe") {
    New-Item -ItemType Directory -Force "$Root\luajit" | Out-Null
    Copy-Item "$Src\build\luajit\src\luajit.exe", "$Src\build\luajit\src\lua51.dll" "$Root\luajit"
}
$mod = "$Root\mod\Ui4me\Ui4me.psd1"
@{
    'run-chat-ps.ps1'  = "param([string] `$StatePath) Import-Module '$mod' -ErrorAction Stop; & '$Root\examples\powershell\chat_log.ps1' -StatePath `$StatePath"
    'run-files-ps.ps1' = "param([string] `$Start, [string] `$StatePath) Import-Module '$mod' -ErrorAction Stop; & '$Root\examples\powershell\file_utility.ps1' -Start `$Start -StatePath `$StatePath"
    'run-input-ps.ps1' = "param([string] `$StatePath, [string] `$CommandsPath) Import-Module '$mod' -ErrorAction Stop; & '$Root\input_probe.ps1' -StatePath `$StatePath -CommandsPath `$CommandsPath"
}.GetEnumerator() | ForEach-Object { Set-Content -Path (Join-Path $Root $_.Key) -Value $_.Value -Encoding UTF8 }
icacls $Root /grant 'ui4me_test:(OI)(CI)M' /T /Q | Out-Null
(Get-FileHash (Get-ChildItem "$Src\dist\win-x64\ui4me-$version-*.whl").FullName).Hash
& "$Root\venv\Scripts\python.exe" -c "import ui4me; print(ui4me.__file__, ui4me.__version__)"
git -C $Src log --oneline -1
