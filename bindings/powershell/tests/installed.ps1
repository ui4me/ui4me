[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $ModulePath,
    [Parameter(Mandatory)][string] $ResultPath,
    [switch] $Native,
    [string] $CapturePath,
    [ValidateSet('all','F02','F03','F04','F05','F06','F07','F08','F10')][string] $Scenario = 'all'
)
$ErrorActionPreference = 'Stop'
$manifest = if (Test-Path -LiteralPath $ModulePath -PathType Container) { Join-Path $ModulePath 'Ui4me.psd1' } else { $ModulePath }
$moduleDirectory = Split-Path -Parent ([IO.Path]::GetFullPath($manifest))
$cases = [System.Collections.Generic.List[object]]::new()
$state = @{observations=[System.Collections.Generic.List[object]]::new(); posts=[System.Collections.Generic.List[object]]::new()}
$identity = $null
$fatal = $null

function Test-Case([string] $Id, [scriptblock] $Action, [string] $Details) {
    try { & $Action | Out-Null; $cases.Add(@{id=$Id; status='passed'; details=$Details}) }
    catch { $cases.Add(@{id=$Id; status='failed'; details=$_.Exception.ToString()}) }
}

try {
    Import-Module -Name $manifest -ErrorAction Stop
    $identity = Get-Ui4meInfo
    if (-not $Native) {
        Test-Case F01 {
            if ($env:UI4ME_NATIVE_LIB) { throw 'Installed consumers must not use UI4ME_NATIVE_LIB' }
            $relative = [IO.Path]::GetRelativePath($moduleDirectory, $identity.library_path)
            if ($relative.StartsWith('..') -or [IO.Path]::IsPathRooted($relative)) { throw 'Native library is outside the installed module' }
            Invoke-Ui4meApp -Backend headless {
                param($app)
                $null = $app.On('started', { param($event) $app.Stop() })
            }
        } 'Installed module resolves its native payload and completes a headless session'
        Test-Case F09 {
            if ($identity.abi -ne 1) { throw 'ABI mismatch' }
            $old = Invoke-Ui4meApp -Backend headless {
                param($app)
                $state = @{called=0}
                $window = New-Ui4meWindow '<p id="value">old</p>'
                $subscription = $app.On('started', { param($event) $state.called++; $app.Stop() })
                $null = $app.On('stopped', { if ($state.called -ne 1) { throw 'Callback lifetime check failed' } })
                [GC]::Collect()
                Write-Output -NoEnumerate @($window, $subscription)
            }
            Invoke-Ui4meApp -Backend headless -ArgumentList @(,$old) {
                param($app, $old)
                $rejected = $false
                try { $old[0].SetText('value', 'stale') } catch { $rejected = $true }
                if (-not $rejected) { throw 'Stale window accepted a mutation' }
                $state = @{called=0}
                $null = $app.On('started', { $state.called++; $app.Stop() })
                $old[1].Dispose()
                $null = $app.On('stopped', { if ($state.called -ne 1) { throw 'Old subscription removed a new callback' } })
            }
            $failed = $false
            try {
                Invoke-Ui4meApp -Backend headless {
                    param($app)
                    $null = $app.On('started', { throw 'F09 deliberate callback failure' })
                }
            } catch { $failed = $_.Exception.ToString() -match 'F09 deliberate callback failure' }
            if (-not $failed) { throw 'Callback failure did not reach the caller' }
        } 'ABI, callback roots, stale window and subscription identity, and callback error propagation'
        Test-Case F11 {
            $directory = Join-Path ([IO.Path]::GetTempPath()) ('ui4me space ž ' + [guid]::NewGuid().ToString('N'))
            $null = New-Item -ItemType Directory -Path $directory
            try {
                $path = Join-Path $directory 'form ü.html'
                Get-ChildItem -LiteralPath (Join-Path $moduleDirectory 'resources') | Copy-Item -Destination $directory -Recurse
                Move-Item -LiteralPath (Join-Path $directory 'index.html') -Destination $path
                Invoke-Ui4meApp -Backend headless -ArgumentList @($path) {
                    param($app, $path)
                    $window = New-Ui4meWindow -Path $path
                    if ((Get-Ui4meValue $window name) -ne 'Příliš žluťoučký kůň') { throw 'Resource value mismatch' }
                    $directory = [IO.Path]::GetDirectoryName($path)
                    $probeFile = Join-Path $directory 'assets ü.html'
                    @'
<!doctype html><html><head><link rel="stylesheet" href="style.css"></head><body>
<div id="paint" style="width:120px;height:120px;padding:0"></div>
<img id="asset" width="28" height="28" style="position:absolute;left:8px;top:8px;width:28px;height:28px">
</body></html>
'@ | Set-Content -LiteralPath $probeFile -Encoding utf8
                    $probe = $app.OpenFile($probeFile, 'Asset probe', 160, 160)
                    $capture = Join-Path $directory 'assets.png'
                    $null = $probe.Snapshot($capture)
                    $state = @{phase='css'; previous=[Convert]::ToBase64String([IO.File]::ReadAllBytes($capture))}
                    $probe.AddClass('paint', 'sidebar')
                    $null = $app.Timer(10, {
                        $null = $probe.Snapshot($capture)
                        $pixels = [Convert]::ToBase64String([IO.File]::ReadAllBytes($capture))
                        if ($pixels -eq $state.previous) { return }
                        $state.previous = $pixels
                        if ($state.phase -eq 'css') {
                            $state.phase = 'image'
                            $probe.SetAttribute('asset', 'src', 'icon.png')
                        }
                        else {
                            $diagnostics = $probe.DiagnosticsJson() | ConvertFrom-Json
                            if (@($diagnostics.diagnostics | Where-Object stage -eq 'resource').Count) { throw 'Local asset produced a resource error' }
                            $state.phase = 'done'
                            $app.Stop()
                        }
                    }, $true)
                    $null = $app.Timer(3000, { throw ('Local stylesheet/image did not change rendered pixels: ' + $state.phase) }, $false)
                    $null = $app.On('stopped', { if ($state.phase -ne 'done') { throw 'Local asset probe incomplete' } })
                }
                if (-not $identity.source_id) { throw 'Missing source identity' }
            }
            finally { Remove-Item -LiteralPath $directory -Recurse -Force }
        } 'Unicode/space document root; packaged CSS and asynchronous PNG change actual rendered pixels; resource diagnostics stay clear'
        Test-Case F12 {
            if ($identity.version -ne $identity.binding_version -or $identity.version -ne (Import-PowerShellDataFile -LiteralPath $manifest).ModuleVersion) { throw 'Version mismatch' }
            if (-not $identity.source_id -or -not (Test-Path -LiteralPath $identity.library_path)) { throw 'Missing candidate identity' }
            1..2 | ForEach-Object {
                Invoke-Ui4meApp -Backend headless {
                    param($app)
                    $null = $app.On('started', { param($event) $app.Stop() })
                }
            }
        } 'Local candidate version and fresh session; public upgrade is assessed separately'
    }
    else {
        Write-Host 'Use the labeled controls. Close session 1 to open session 2. Capture the actual desktop externally.'
        Write-Host 'Recorded observations require human review. Renderer PNGs cannot prove native desktop acceptance.'
        $count = if ($Scenario -in @('all','F08')) { 2 } else { 1 }
        foreach ($number in 1..$count) {
            try {
                Invoke-Ui4meApp -ArgumentList @($state, $number, $CapturePath) {
                    param($app, $state, $number, $capturePath)
                    $local = @{allow=$false}
                    $record = {
                        param($entry)
                        if ($state.observations.Count -lt 4096) { $state.observations.Add(@{session=$number; event=$entry}) }
                    }.GetNewClosure()
                    $html = @'
<h1>ui4me native acceptance</h1>
<input id="name" value="Edit me">
<button id="echo">Echo typed value</button>
<button id="second">Open another window</button>
<button id="resize">Resize this window</button>
<button id="allow">Allow normal close</button>
<button id="worker">Run background script</button>
<button id="bounds">Exercise timer capacity</button>
<button id="race">Queue work then force stop</button>
<button id="error">Raise a callback error</button>
<button id="stop">Force stop</button>
<p id="status">Close is vetoed until Allow or Force stop.</p>
'@
                    $window = New-Ui4meWindow $html -Title "ui4me native acceptance — session $number" -Width 760 -Height 740
                    foreach ($kind in @('started','stopped','resized','closed','click','change')) {
                        $null = $app.On($kind, { param($event) & $record ($event.Json | ConvertFrom-Json) })
                    }
                    $null = $app.On('stopped', { & $record @{type='terminal_stats'; stats=($app.StatsJson() | ConvertFrom-Json)} })
                    $null = Register-Ui4meEvent $window close_requested {
                        param($event)
                        & $record @{type='close_requested'; veto=(-not $local.allow)}
                        if (-not $local.allow) { $window.SetText('status','Close vetoed. Use Allow or Force stop.'); return $false }
                    }
                    $null = Register-Ui4meEvent $window click { $window.SetText('status', $window.GetValue('name')) } -Element echo
                    $null = Register-Ui4meEvent $window click { $null = New-Ui4meWindow '<p>Second window; close independently.</p>' -Title 'Second window' } -Element second
                    $null = Register-Ui4meEvent $window click { $window.Resize(860,780) } -Element resize
                    $null = Register-Ui4meEvent $window click { $local.allow=$true; $window.SetText('status','Normal close allowed') } -Element allow
                    $null = Register-Ui4meEvent $window click {
                        $owner = [Environment]::CurrentManagedThreadId
                        $null = $app.Work({ param($number) $number * 2 }, @(21), {
                            param($values,$error)
                            if ($null -ne $error) { throw $error }
                            & $record @{type='worker_dispatch'; owner_correct=([Environment]::CurrentManagedThreadId -eq $owner); result=$values[0]}
                            $window.SetText('status', ('Worker result on UI owner: ' + $values[0]))
                        })
                    } -Element worker
                    $null = Register-Ui4meEvent $window click {
                        $timers = [System.Collections.Generic.List[object]]::new()
                        $rejected = $false
                        try { foreach ($index in 1..129) { $timers.Add($app.Timer(60000, {}, $false)) } }
                        catch { $rejected=$true; & $record @{type='capacity_rejected'; registered=$timers.Count; message=$_.Exception.Message} }
                        finally { foreach ($timer in $timers) { $timer.Cancel() } }
                        $window.SetText('status', $(if ($rejected) {'Timer capacity rejection observed'} else {'ERROR: no capacity rejection'}))
                    } -Element bounds
                    $null = Register-Ui4meEvent $window click {
                        foreach ($index in 1..32) { $state.posts.Add($app.Post({ & $record @{type='queued_work_ran'} })) }
                        $app.Stop()
                    } -Element race
                    $null = Register-Ui4meEvent $window click { throw 'Deliberate native callback failure' } -Element error
                    $null = Register-Ui4meEvent $window click { $app.Stop() } -Element stop
                    $null = $app.Timer(1000, {
                        & $record @{type='runtime_stats'; stats=($app.StatsJson() | ConvertFrom-Json)}
                        if ($capturePath) {
                            $path = [IO.Path]::Combine([IO.Path]::GetDirectoryName($capturePath), ([IO.Path]::GetFileNameWithoutExtension($capturePath) + "-$number.png"))
                            & $record @{type='renderer_snapshot'; native_capture=$false; path=$path; result=($window.Snapshot($path) | ConvertFrom-Json)}
                        }
                    }, $false)
                }
            }
            catch {
                if ($_.Exception.ToString() -notmatch 'Deliberate native callback failure') { throw }
                $state.observations.Add(@{session=$number; event=@{type='callback_error_returned'; message=$_.Exception.ToString()}})
            }
        }
        $state.observations.Add(@{event=@{type='terminal_posts'; total=$state.posts.Count; settled=@($state.posts | Where-Object IsCompleted).Count; cancelled=@($state.posts | Where-Object IsCancelled).Count}})
    }
}
catch { $fatal = $_.Exception.ToString() }
finally {
    $path = [IO.Path]::GetFullPath($ResultPath)
    $null = New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($path)) -Force
    @{binding='powershell'; powershell_version=$PSVersionTable.PSVersion.ToString(); backend=$(if ($Native) {'native'} else {'headless'}); build_info=$identity;
      cases=@($cases.ToArray()); observations=@($state.observations.ToArray());
      manual_review_required=[bool]$Native; native_capture=$false; error=$fatal} |
        ConvertTo-Json -Depth 20 | Set-Content -LiteralPath $path -Encoding utf8
}
if ($fatal -or @($cases | Where-Object status -ne 'passed').Count -gt 0) { exit 1 }
exit 0
