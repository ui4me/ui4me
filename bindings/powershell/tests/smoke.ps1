[CmdletBinding()]
param(
    [Parameter(Mandatory)][string] $ModulePath,
    [Parameter(Mandatory)][string] $ResultPath
)
$ErrorActionPreference = 'Stop'
$cases = [System.Collections.Generic.List[object]]::new()
$manifest = if (Test-Path -LiteralPath $ModulePath -PathType Container) { Join-Path $ModulePath 'Ui4me.psd1' } else { $ModulePath }
$identity = $null

function Test-Case([string] $Id, [scriptblock] $Body) {
    try {
        & $Body | Out-Null
        $cases.Add(@{id=$Id; status='passed'; details='Actual headless binding check completed'})
    }
    catch { $cases.Add(@{id=$Id; status='failed'; details=$_.Exception.ToString()}) }
}

try {
    Import-Module -Name $manifest -ErrorAction Stop
    $identity = Get-Ui4meInfo
    Test-Case 'PS01_version_abi' {
        if ($identity.version -ne '0.1.0' -or $identity.abi -ne 1 -or $identity.product -ne 'ui4me') { throw 'Version/ABI mismatch' }
    }
    Test-Case 'PS02_session_cleanup' {
        1..2 | ForEach-Object {
            Invoke-Ui4meApp -Backend headless {
                param($app)
                $null = $app.On('started', { param($event) $app.Stop() })
            }
        }
    }
    Test-Case 'PS03_input_value' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $window = New-Ui4meWindow '<input id="name" value="Start">'
            Set-Ui4meText $window name 'Příliš žluťoučký'
            if ((Get-Ui4meValue $window name) -ne 'Příliš žluťoučký') { throw 'UTF8 value changed' }
            $null = $app.On('started', { param($event) $app.Stop() })
        }
    }
    Test-Case 'PS04_explicit_arguments' {
        $value = Invoke-Ui4meApp -Backend headless -ArgumentList @('Explicit argument') {
            param($app, $value)
            Write-Output $value
            $null = $app.On('started', { param($event) $app.Stop() })
        }
        if ($value -ne 'Explicit argument') { throw 'Argument transfer failed' }
    }
    Test-Case 'PS05_timer' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $state = @{count=0}
            $null = $app.Timer(1, { param($event) $state.count++; $app.Stop() }, $false)
            $null = $app.On('stopped', { param($event) if ($state.count -ne 1) { throw 'Timer did not run once' } })
        }
    }
    Test-Case 'PS06_cancel_timer' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $timer = $app.Timer(1, { throw 'Cancelled timer ran' }, $false)
            $timer.Cancel()
            $null = $app.Post({ $app.Stop() })
        }
    }
    Test-Case 'PS07_post_and_guard' {
        $work = Invoke-Ui4meApp -Backend headless {
            param($app)
            $work = $app.Post({ 42 })
            $blocked = $false
            try { $null = $work.GetResult() } catch { $blocked = $true }
            if (-not $blocked) { throw 'Owner wait was not rejected' }
            $null = $app.Post({ $app.Stop() })
            Write-Output -NoEnumerate $work
        }
        if ($work.GetResult() -ne 42) { throw 'Post result mismatch' }
    }
    Test-Case 'PS08_cancel_post' {
        $work = Invoke-Ui4meApp -Backend headless {
            param($app)
            $work = $app.Post({ throw 'Cancelled post ran' })
            if (-not $work.Cancel()) { throw 'Cancel rejected before execution' }
            $null = $app.Post({ $app.Stop() })
            Write-Output -NoEnumerate $work
        }
        if (-not $work.IsCancelled) { throw 'Posted work was not cancelled' }
    }
    Test-Case 'PS09_callback_error_cleanup' {
        $failed = $false
        try {
            Invoke-Ui4meApp -Backend headless {
                param($app)
                $null = $app.On('started', { throw 'Deliberate callback failure' })
            }
        }
        catch { $failed = $true }
        if (-not $failed) { throw 'Callback failure was swallowed' }
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $null = $app.On('started', { param($event) $app.Stop() })
        }
    }
    Test-Case 'PS10_subscription_lifetime' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $removed = $app.On('started', { throw 'Removed subscription ran' })
            $removed.Dispose()
            $null = $app.On('started', { param($event) $app.Stop() })
            [GC]::Collect()
        }
    }
    Test-Case 'PS11_terminal_pending_work' {
        $work = Invoke-Ui4meApp -Backend headless {
            param($app)
            $work = $app.Post({ 1 })
            $app.Stop()
            Write-Output -NoEnumerate $work
        }
        if (-not $work.IsCompleted) { throw 'Pending work did not settle' }
    }
    Test-Case 'PS12_background_completion' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $state = @{completed=$false}
            $null = $app.Work({ param($number) $number * 2 }, @(21), {
                param($values, $error)
                if ($null -ne $error) { throw $error }
                if ($values[0] -ne 42) { throw 'Background result mismatch' }
                $state.completed = $true
                $app.Stop()
            })
            $null = $app.Timer(5000, { throw 'Background completion timed out' }, $false)
            $null = $app.On('stopped', { if (-not $state.completed) { throw 'No completion callback' } })
        }
    }
    Test-Case 'PS13_cmdlet_callback_scope' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $state = @{received=0}
            $record = { param($value) $state.received = $value }.GetNewClosure()
            $window = New-Ui4meWindow '<p>Close interception</p>'
            $null = Register-Ui4meEvent $window close_requested {
                & $record 42
                $app.Stop()
                return $false
            }
            $null = $app.On('started', { $window.Close() })
            $null = $app.Timer(2000, { throw 'Close callback did not complete' }, $false)
            $null = $app.On('stopped', { if ($state.received -ne 42) { throw 'Callback lost its caller scope' } })
        }
    }
    Test-Case 'PS14_nested_background_callback_scope' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $state = @{received=0}
            $record = { param($value) $state.received = $value }.GetNewClosure()
            $window = New-Ui4meWindow '<p>Nested work</p>'
            $null = Register-Ui4meEvent $window close_requested {
                $owner = [Environment]::CurrentManagedThreadId
                $null = $app.Work({ 42 }, @(), {
                    param($values, $error)
                    if ($null -ne $error) { throw $error }
                    if ([Environment]::CurrentManagedThreadId -ne $owner) { throw 'Wrong completion thread' }
                    & $record $values[0]
                    $app.Stop()
                })
                return $false
            }
            $null = $app.On('started', { $window.Close() })
            $null = $app.Timer(5000, { throw 'Nested callback timed out' }, $false)
            $null = $app.On('stopped', { if ($state.received -ne 42) { throw 'Nested callback lost caller scope' } })
        }
    }
}
catch { $cases.Add(@{id='PS00_setup'; status='failed'; details=$_.Exception.ToString()}) }
finally {
    $directory = Split-Path -Parent ([IO.Path]::GetFullPath($ResultPath))
    $null = New-Item -ItemType Directory -Path $directory -Force
    @{binding='powershell'; backend='headless'; build_info=$identity; cases=@($cases.ToArray())} |
        ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $ResultPath -Encoding utf8
}
if (@($cases | Where-Object status -ne 'passed').Count -gt 0) { exit 1 }
exit 0
