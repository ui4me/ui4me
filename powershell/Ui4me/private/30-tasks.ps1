# ---------------------------------------------------------------------- timers and tasks --

function Get-UiTimerWait {
    param($ctx, [int]$Maximum)
    $wait = $Maximum
    $now = [DateTime]::UtcNow
    foreach ($timer in @($ctx.Timers)) {
        $ms = [int][Math]::Ceiling(($timer.Due - $now).TotalMilliseconds)
        if ($ms -lt $wait) { $wait = [Math]::Max(0, $ms) }
    }
    if (@($ctx.Tasks).Count -gt 0 -and $wait -gt 20) { $wait = 20 }
    return $wait
}

function Invoke-UiOwned {
    # Run a UI4ME-owned callback (timer, task completion) like a Core event callback:
    # Core defers host notifications until it returns, so event handlers never run
    # nested inside it, and content it creates belongs to $Owner.
    param($ctx, $Owner, $Handler, [object[]]$Arguments, [string]$Context)
    $app = $ctx.App
    $wasDispatching = $false
    if ($null -ne $app) { $wasDispatching = [bool]$app.Dispatching; $app.Dispatching = $true }
    $previous = $ctx.CurrentOwner
    $ctx.CurrentOwner = $Owner
    try { Invoke-UiHandler $Handler $Arguments $Context }
    finally {
        $ctx.CurrentOwner = $previous
        if ($null -ne $app) { $app.Dispatching = $wasDispatching }
    }
}

function Invoke-UiTimers {
    param($ctx)
    $now = [DateTime]::UtcNow
    foreach ($timer in @($ctx.Timers)) {
        if (-not $ctx.Timers.Contains($timer)) { continue }  # already handled by a nested pump
        if ($timer.Cancelled -or ($null -ne $timer.Owner -and $timer.Owner.Disposed)) { [void]$ctx.Timers.Remove($timer); continue }
        if ($timer.Due -gt $now) { continue }
        if ($timer.Repeat) { $timer.Due = $now.AddMilliseconds($timer.Interval) } else { [void]$ctx.Timers.Remove($timer) }
        Invoke-UiOwned $ctx $timer.Owner $timer.Action @() 'timer'
    }
}

function Start-UI4MEUiTimer {
    <#
    .SYNOPSIS
    Runs -Action after -Milliseconds (repeatedly with -Repeat) on the UI runspace. Returns a timer handle.
    .DESCRIPTION
    Timers created while rendering runtime content (New-UI4MEEach/-When items) stop when that content is removed.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][ValidateRange(1, 86400000)][int]$Milliseconds, [Parameter(Mandatory)]$Action,
          [switch]$Repeat)
    $ctx = Assert-UiBuilder
    $timer = [pscustomobject]@{ Due = [DateTime]::UtcNow.AddMilliseconds($Milliseconds); Interval = $Milliseconds
        Repeat = [bool]$Repeat; Action = $Action; Cancelled = $false; Owner = $ctx.CurrentOwner }
    $timer.PSObject.TypeNames.Insert(0, 'UI4ME.UiTimer')
    [void]$ctx.Timers.Add($timer)
    return $timer
}

function Stop-UI4MEUiTimer {
    <# .SYNOPSIS Cancels a timer from Start-UI4MEUiTimer. #>
    [CmdletBinding()] param([Parameter(Mandatory)]$Timer)
    $Timer.Cancelled = $true
}

function Start-UI4MEUiTask {
    <#
    .SYNOPSIS
    Runs -Work in a separate PowerShell runspace; -OnDone/-OnError run later on the UI runspace.
    .DESCRIPTION
    -Work cannot see your script's variables or call UI4ME commands: pass inputs with -ArgumentList
    and return a result. Stop-UI4MEUiTask cancels it (the pipeline is stopped; completion callbacks
    are skipped). Tasks started inside runtime content are cancelled when that content is removed.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][scriptblock]$Work, [object[]]$ArgumentList = @(),
          [scriptblock]$OnDone, [scriptblock]$OnError, [scriptblock]$OnCancel)
    $ctx = Assert-UiBuilder
    $ps = [System.Management.Automation.PowerShell]::Create()
    $null = $ps.AddScript($Work.ToString())
    foreach ($argument in $ArgumentList) { $null = $ps.AddArgument($argument) }
    $task = [pscustomobject]@{ PowerShell = $ps; Async = $null; OnDone = $OnDone; OnError = $OnError; OnCancel = $OnCancel
        State = 'running'; Owner = $ctx.CurrentOwner; Result = $null; Error = $null }
    $task.PSObject.TypeNames.Insert(0, 'UI4ME.UiTask')
    $task.Async = $ps.BeginInvoke()
    [void]$ctx.Tasks.Add($task)
    if ($null -ne $ctx.CurrentOwner) {
        [void]$ctx.CurrentOwner.Cleanups.Add((New-UiCallable 'Stop-UiTaskQuiet' $task))
    }
    return $task
}

function Stop-UI4MEUiTask {
    <# .SYNOPSIS Cancels a running Start-UI4MEUiTask task. Its OnDone/OnError do not run. #>
    [CmdletBinding()] param([Parameter(Mandatory)]$Task, [switch]$Quiet)
    if ($Task.State -ne 'running') { return }
    $Task.State = 'cancelled'
    try { $null = $Task.PowerShell.BeginStop($null, $null) } catch { }
    $ctx = $script:UiBuilder
    if (-not $Quiet -and $Task.OnCancel -and $ctx -and -not $ctx.Stopping) { Invoke-UiHandler $Task.OnCancel @() 'task cancel' }
}

function Stop-UiTaskQuiet { param($Task) Stop-UI4MEUiTask -Task $Task -Quiet }

function Update-UiTasks {
    param($ctx)
    foreach ($task in @($ctx.Tasks)) {
        if (-not $ctx.Tasks.Contains($task)) { continue }  # already handled by a nested pump
        if ($task.State -eq 'cancelled') {
            if ($task.Async.IsCompleted) { [void]$ctx.Tasks.Remove($task); try { $task.PowerShell.Dispose() } catch { } }
            continue
        }
        if (-not $task.Async.IsCompleted) { continue }
        [void]$ctx.Tasks.Remove($task)
        try {
            $output = $task.PowerShell.EndInvoke($task.Async)
            if ($task.PowerShell.HadErrors -and $task.PowerShell.Streams.Error.Count -gt 0) {
                throw $task.PowerShell.Streams.Error[0].Exception
            }
            $task.State = 'succeeded'
            $value = if ($output.Count -eq 1) { $output[0] } else { @($output) }
            $task.Result = $value
            if ($task.OnDone -and ($null -eq $task.Owner -or -not $task.Owner.Disposed)) { Invoke-UiOwned $ctx $task.Owner $task.OnDone @(, $value) 'task' }
        } catch {
            $task.State = 'failed'
            $task.Error = $_
            if ($null -ne $task.Owner -and $task.Owner.Disposed) { }
            elseif ($task.OnError) { Invoke-UiOwned $ctx $task.Owner $task.OnError @($_) 'task error' }
            else { Write-UiError $_ 'background task' }
        } finally {
            try { $task.PowerShell.Dispose() } catch { }
        }
    }
}

function Stop-UiTasks {
    param($ctx)
    foreach ($task in @($ctx.Tasks)) { Stop-UI4MEUiTask -Task $task -Quiet }
    $ctx.Tasks.Clear()
}
