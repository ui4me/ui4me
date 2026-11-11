# Windows native release gate (Core 1.0, F1107), run in the interactive ui4me_test session (through
# task.ps1) against the INSTALLED candidate staged by prep_gate.ps1: the wheel in $root\venv and the
# module stage in $root\mod. Automated input, not a person.
param([string] $Root = 'C:\Users\Public\ui4me-gui\gate')
$root = $Root
$out = "$root\results"
New-Item -ItemType Directory -Force $out | Out-Null
$pwsh = 'C:\Program Files\PowerShell\7\pwsh.exe'
$py = "$root\venv\Scripts\python.exe"
Remove-Item Env:PYTHONPATH, Env:UI4ME_NATIVE_LIB -ErrorAction SilentlyContinue
$env:UI4ME_INSTALLED = '1'
"user=$env:USERNAME session=$((Get-Process -Id $PID).SessionId) $(Get-Date -Format o)" | Set-Content "$out\context.txt"
& $py -c "import ui4me, sys; print(ui4me.__file__, ui4me.__version__)" *> "$out\python-identity.txt"
$only = if (Test-Path "$root\only.txt") { (Get-Content "$root\only.txt").Trim() } else { 'chat,files,window,input,uia,env,fileinput,services,animation,print,capabilities,data,lua,nvda' }
function Ps([string] $script) { "param([string]`$A, [string]`$B, [string]`$C, [string]`$D) Import-Module '$root\mod\Ui4me\Ui4me.psd1' -ErrorAction Stop; & '$script' @args" }
if ($only -match 'chat') {
  & $pwsh -NoLogo -NoProfile -Command "& '$root\chat_journey.ps1' -Out '$out\chat-python' -Exe '$py' -Arguments @('-I', '$root\examples\python\chat_log.py', '--state', '{state}')" *> "$out\chat-python.log"
  & $pwsh -NoLogo -NoProfile -Command "& '$root\chat_journey.ps1' -Out '$out\chat-powershell' -Exe '$pwsh' -Arguments @('-NoLogo', '-NoProfile', '-File', '$root\run-chat-ps.ps1', '-StatePath', '{state}')" *> "$out\chat-powershell.log"
}
if ($only -match 'files') {
  & $pwsh -NoLogo -NoProfile -Command "& '$root\files_journey.ps1' -Out '$out\files-python' -Exe '$py' -Arguments @('-I', '$root\examples\python\file_utility.py', '--start', '{start}', '--state', '{state}')" *> "$out\files-python.log"
  & $pwsh -NoLogo -NoProfile -Command "& '$root\files_journey.ps1' -Out '$out\files-powershell' -Exe '$pwsh' -Arguments @('-NoLogo', '-NoProfile', '-File', '$root\run-files-ps.ps1', '-Start', '{start}', '-StatePath', '{state}')" *> "$out\files-powershell.log"
}
if ($only -match 'window') {
  New-Item -ItemType Directory -Force "$out\window-probe" | Out-Null
  & $py -I "$root\window_probe.py" --out "$out\window-probe\probe.json" *> "$out\window-probe\command.log"
}
if ($only -match 'input') {
  & $pwsh -NoLogo -NoProfile -Command "& '$root\input_journey.ps1' -Out '$out\input-python' -Exe '$py' -Arguments @('-I', '$root\input_probe.py', '--state', '{state}', '--commands', '{commands}')" *> "$out\input-python.log"
  & $pwsh -NoLogo -NoProfile -Command "& '$root\input_journey.ps1' -Out '$out\input-powershell' -Exe '$pwsh' -Arguments @('-NoLogo', '-NoProfile', '-File', '$root\run-input-ps.ps1', '-StatePath', '{state}', '-CommandsPath', '{commands}')" *> "$out\input-powershell.log"
}
if ($only -match 'uia') {
  $env:PYTHONPATH = "$root\pydeps"  # comtypes for the native COM client only (the venv provides ui4me)
  & $pwsh -NoLogo -NoProfile -File "$root\uia_probe.ps1" -Python $py -Out "$out\uia" -NativeClient "$root\uia_native_text.py" *> "$out\uia.log"
  Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
}
if ($only -match 'env') {
  New-Item -ItemType Directory -Force "$out\environment" | Out-Null
  & $py -I "$root\environment_probe.py" --out "$out\environment\env.json" *> "$out\environment\command.log"
}
if ($only -match 'fileinput') {
  & $pwsh -NoLogo -NoProfile -Command "& '$root\file_input_journey.ps1' -Out '$out\file-input' -Exe '$py' -Arguments @('$root\file_input_app.py', '--state', '{state}', '--root', '{root}')" *> "$out\file-input.log"
}
if ($only -match 'services') {
  New-Item -ItemType Directory -Force "$out\services" | Out-Null
  & $py -I "$root\services_probe.py" --out "$out\services\services.json" *> "$out\services\command.log"
}
if ($only -match 'animation') {
  New-Item -ItemType Directory -Force "$out\animation" | Out-Null
  & $py -I "$root\animation_probe.py" --out "$out\animation\animation.json" *> "$out\animation\command.log"
}
if ($only -match 'print') {
  New-Item -ItemType Directory -Force "$out\print" | Out-Null
  & $py -I "$root\print_probe.py" --out "$out\print\print.json" *> "$out\print\command.log"
}
if ($only -match 'capabilities') {
  New-Item -ItemType Directory -Force "$out\capabilities" | Out-Null
  & $py -I "$root\capabilities_probe.py" --profile "$root\PLATFORM_CAPABILITIES_V1.json" --out "$out\capabilities\caps.json" *> "$out\capabilities\command.log"
}
if (($only -match 'data') -and (Test-Path "$root\data_journey.py")) {
  New-Item -ItemType Directory -Force "$out\data-app" | Out-Null
  & $py -I "$root\data_journey.py" --app "$root\examples\python\data_viewer.py" --out "$out\data-app\data.json" *> "$out\data-app\command.log"
}
if (($only -match 'lua') -and (Test-Path "$root\lua_probe.lua") -and (Test-Path "$root\luajit\luajit.exe")) {
  New-Item -ItemType Directory -Force "$out\lua" | Out-Null
  $env:UI4ME_NATIVE_LIB = (Get-ChildItem -Recurse "$root\venv\Lib\site-packages\ui4me" -Filter ui4me_core.dll | Select-Object -First 1).FullName
  $env:LUA_PATH = "$root\lua\?.lua;;"
  & "$root\luajit\luajit.exe" "$root\lua_probe.lua" --out "$out\lua\lua.json" *> "$out\lua\command.log"
  Remove-Item Env:UI4ME_NATIVE_LIB, Env:LUA_PATH -ErrorAction SilentlyContinue
}
$nvda = 'C:\Users\Public\ui4me-gui\nvda\portable\nvda.exe'  # a portable NVDA 2024.4.2 (nvaccess.org)
if (($only -match 'nvda') -and (Test-Path $nvda)) {
  New-Item -ItemType Directory -Force "$out\nvda" | Out-Null
  & $py -I "$root\nvda_journey.py" --nvda $nvda --out "$out\nvda\nvda.json" *> "$out\nvda\command.log"
}
'done' | Set-Content "$out\all-done.txt"
