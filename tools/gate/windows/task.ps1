# Run a script in the interactive ui4me_test session (an administrator over SSH starts it as a
# scheduled task in that session) and wait for its marker file.
param([Parameter(Mandatory)][string] $Script, [Parameter(Mandatory)][string] $Marker, [int] $Seconds = 900, [string] $Exe = 'C:\Program Files\PowerShell\7\pwsh.exe')
$name = 'ui4me-gate-' + [IO.Path]::GetFileNameWithoutExtension($Script)
Remove-Item -LiteralPath $Marker -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute $Exe -Argument "-NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$Script`""
$principal = New-ScheduledTaskPrincipal -UserId 'ui4me_test' -LogonType Interactive
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds $Seconds) -AllowStartIfOnBatteries
Register-ScheduledTask -TaskName $name -Action $action -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $name
$deadline = (Get-Date).AddSeconds($Seconds)
while ((Get-Date) -lt $deadline -and -not (Test-Path $Marker)) { Start-Sleep -Seconds 2 }
$ok = Test-Path $Marker
Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
if (-not $ok) { Write-Output "TIMEOUT waiting for $Marker"; exit 1 }
Write-Output "marker present"
