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
        if ($identity.version -ne $identity.binding_version -or $identity.abi -ne 1 -or $identity.product -ne 'ui4me') { throw 'Version/ABI mismatch' }
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
    Test-Case 'PS15_caught_nested_app_error' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $state = @{ rejected = $false }
            $null = $app.On('started', {
                try { Invoke-Ui4meApp -Backend headless {}; throw 'Nested app was accepted' }
                catch {
                    if ($_.Exception.ToString() -notmatch 'Only one Ui4me application') { throw }
                    $state.rejected = $true
                }
                $app.Stop()
            })
            $null = $app.On('stopped', { if (-not $state.rejected) { throw 'Nested application was not rejected' } })
        }
    }
    Test-Case 'PS16_unhandled_initializer_error' {
        $failed = $false
        try { Invoke-Ui4meApp -Backend headless { throw 'Deliberate initializer failure' } }
        catch {
            if ($_.Exception.ToString() -notmatch 'Deliberate initializer failure') { throw }
            $failed = $true
        }
        if (-not $failed) { throw 'Initializer error was swallowed' }
    }

    Test-Case 'PS17_transactional_registration' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            foreach ($i in 1..6) {
                $failed = $false
                try { $null = $app.Work($null, @(), {}) } catch { $failed = $true }
                if (-not $failed) { throw 'Null work script accepted' }
                $failed = $false
                try { $null = $app.Timer(1, $null, $true) } catch { $failed = $true }
                if (-not $failed) { throw 'Null timer handler accepted' }
            }
            if (($app.StatsJson() | ConvertFrom-Json).timers -ne 0) { throw 'Failed timer registrations leaked' }
            $null = $app.Work({ 42 }, @(), { param($values, $error)
                if ($error -or $values[0] -ne 42) { throw 'Worker capacity leaked after rejected calls' }
                $app.Stop()
            })
            $null = $app.Timer(5000, { throw 'Valid work after failure timed out' }, $false)
        }
    }
    Test-Case 'PS18_completion_survives_post_saturation' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $state = @{completed=0}
            foreach ($i in 1..512) { $null = $app.Post({}) }
            $worker = $app.Work({ 42 }, @(), { param($values, $error)
                if ($error -or $values[0] -ne 42) { throw 'Reserved completion returned wrong result' }
                $state.completed++
                $app.Stop()
            })
            $deadline = [DateTime]::UtcNow.AddSeconds(5)
            while (-not $worker.IsExecutionCompleted -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 5 }
            if (-not $worker.IsExecutionCompleted) { throw 'Background execution did not finish before run' }
            if ($worker.GetResult()[0] -ne 42) { throw 'Work handle did not preserve result' }
            $null = $app.Timer(5000, { throw 'Reserved completion timed out with full post queue' }, $false)
            $null = $app.On('stopped', { if ($state.completed -ne 1) { throw 'Completion was lost or duplicated' } })
        }
    }
    Test-Case 'PS19_background_failure_is_observable' {
        $worker = Invoke-Ui4meApp -Backend headless {
            param($app)
            $worker = $app.Work({ throw 'Observable worker failure' }, @(), { param($values, $error)
                if ($null -eq $error -or $error.ToString() -notmatch 'Observable worker failure') { throw 'Worker error missing' }
                $app.Stop()
            })
            $null = $app.Timer(5000, { throw 'Worker failure callback timed out' }, $false)
            Write-Output -NoEnumerate $worker
        }
        if ($worker.Status -ne 'failed' -or $null -eq $worker.Error -or -not $worker.IsExecutionCompleted) { throw 'Work failure state missing' }
        $failed = $false
        try { $null = $worker.GetResult() } catch { $failed = $true }
        if (-not $failed) { throw 'Failed Work.GetResult did not throw' }
    }
    Test-Case 'PS20_subscription_reentry_and_terminal_guard' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $state = @{later=$null; guarded=$false}
            $null = $app.On('started', { $state.later.Dispose() })
            $state.later = $app.On('started', { throw 'Removed listener ran in current dispatch' })
            $null = $app.On('started', { $app.Stop() })
            $null = $app.On('stopped', {
                try { $app.Dispose() } catch { $state.guarded = $true }
                if (-not $state.guarded) { throw 'Dispose was allowed inside active run' }
            })
        }
    }
    Test-Case 'PS21_document_updates' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $window = $app.Open('<div id="rows"><p id="old">One</p></div><input id="name" value="Keep"><input id="flag" type="checkbox">')
            $window.SetValue('name', 'Příliš žluťoučký')
            $window.SetChecked('flag', $true)
            if (-not $window.GetChecked('flag')) { throw 'Checked state not updated' }
            $window.SetAttribute('rows', 'class', 'list')
            $window.AddClass('rows', 'active')
            $window.RemoveClass('rows', 'list')
            $window.ReplaceChildrenHtml('rows', '<p id="new">Two</p>')
            $window.SetText('new', 'Updated')
            if ($window.GetValue('name') -ne 'Příliš žluťoučký') { throw 'Subtree update erased unrelated input' }
            $null = $app.On('started', { $app.Stop() })
        }
    }
    Test-Case 'PS21b_dom_insert_remove_move_read' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $window = $app.Open('<ul id="list"><li id="b" data-k="v">B</li></ul><input id="edit" value="keep">')
            $window.PrependHtml('list', '<li id="a">A</li>')
            $window.AppendHtml('list', '<li id="d">D</li>')
            $window.InsertHtmlAfter('b', '<li id="c">Č</li>')
            $window.InsertHtmlBefore('list', '<p id="title">Title</p>')
            if (($window.Query('#list > li') -join ',') -ne 'a,b,c,d') { throw 'Insert order is wrong' }
            if ($window.GetText('list') -ne 'ABČD') { throw 'Text read is wrong' }
            if ($window.GetAttribute('b', 'data-k') -ne 'v') { throw 'Attribute read is wrong' }
            if ($null -ne $window.GetAttribute('b', 'title')) { throw 'Missing attribute is not null' }
            if ($window.GetAttributes('b').Count -ne 2) { throw 'Attribute map is wrong' }
            $rejected = $false
            try { $window.AppendHtml('list', '<li id="e">E</li><li id="a">dup</li>') } catch { $rejected = $true }
            if (-not $rejected -or $window.HasElement('e')) { throw 'Duplicate fragment was not atomic' }
            $window.Focus('edit')
            $window.MoveElement('edit', 'c')
            if (($window.Query('#c > input:focus') -join ',') -ne 'edit') { throw 'Move lost focus' }
            if ($window.GetValue('edit') -ne 'keep') { throw 'Move lost value' }
            $window.RemoveElement('c')
            if ($window.HasElement('edit')) { throw 'Removed subtree is still addressable' }
            $null = $app.On('started', { $app.Stop() })
        }
    }
    Test-Case 'PS21c_batch_and_default_action' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $window = $app.Open('<ul id="log"><li id="l1">one</li></ul><form id="f"><textarea id="msg"></textarea></form>')
            $window.Batch(@(
                @{ op = 'insert_html'; element = 'log'; position = 'beforeend'; html = '<li id="l2">two</li>' },
                @{ op = 'move_element'; element = 'l2'; target = 'l1'; position = 'beforebegin' }
            ))
            if (($window.Query('#log > li') -join ',') -ne 'l2,l1') { throw 'Batch order is wrong' }
            $rejected = $false
            try { $window.Batch(@(@{ op = 'remove_element'; element = 'l1' }, @{ op = 'set_text'; element = 'missing'; text = 'x' })) } catch { $rejected = $_.Exception.Message -match 'batch operation 1' }
            if (-not $rejected -or -not $window.HasElement('l1')) { throw 'Failed batch was not rolled back' }
            $window.SetDefaultAction('f', 'keydown', $true, 'Enter', $false)
            $window.SetDefaultAction('f', 'keydown', $false, 'Enter', $false)
            $null = $app.On('started', { $app.Stop() })
        }
    }
    Test-Case 'PS22_cancel_completed_work_before_delivery' {
        $worker = Invoke-Ui4meApp -Backend headless {
            param($app)
            $worker = $app.Work({ 42 }, @(), { throw 'Cancelled completion was delivered' })
            $deadline = [DateTime]::UtcNow.AddSeconds(5)
            while (-not $worker.IsExecutionCompleted -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 5 }
            if (-not $worker.IsExecutionCompleted) { throw 'Work did not finish before cancellation' }
            $worker.Cancel()
            $null = $app.Timer(20, { $app.Stop() }, $false)
            Write-Output -NoEnumerate $worker
        }
        if (-not $worker.IsCancellationRequested -or $worker.CompletionDelivered -or -not $worker.IsDeliveryCompleted) { throw 'Cancelled delivery state is incorrect' }
        if ($worker.GetResult()[0] -ne 42) { throw 'Late cancellation erased an already completed result' }
    }
    Test-Case 'PS23_cancel_active_work_is_observable' {
        $worker = Invoke-Ui4meApp -Backend headless {
            param($app)
            $worker = $app.Work({ Start-Sleep -Seconds 3; 42 }, @(), { throw 'Cancelled active work was delivered' })
            $worker.Cancel()
            if (-not $worker.IsCancelled) { throw 'Cancellation did not settle work outcome' }
            $null = $app.Timer(20, { $app.Stop() }, $false)
            Write-Output -NoEnumerate $worker
        }
        $deadline = [DateTime]::UtcNow.AddSeconds(5)
        while (-not $worker.IsExecutionCompleted -and [DateTime]::UtcNow -lt $deadline) { Start-Sleep -Milliseconds 5 }
        if (-not $worker.IsExecutionCompleted -or -not $worker.IsCancelled -or $worker.CompletionDelivered) { throw 'Cancelled execution did not settle and leave' }
        $failed = $false
        try { $null = $worker.GetResult() } catch { $failed = $true }
        if (-not $failed) { throw 'Cancelled Work.GetResult did not throw' }
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
