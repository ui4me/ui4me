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
    Test-Case 'PS21e_validity' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $window = $app.Open('<form id="f"><input id="n" required><button id="go">Go</button></form>')
            $v = $window.GetValidityJson('n') | ConvertFrom-Json
            if ($v.valid -or -not $v.flags.valueMissing -or $v.message -ne 'Please fill out this field.') { throw 'Validity is wrong' }
            $c = $window.CheckValidityJson('f') | ConvertFrom-Json
            if ($c.valid -or $c.count -ne 1 -or $c.invalid[0] -ne 'n') { throw 'CheckValidity is wrong' }
            $window.SetValue('n', 'ok')
            if (-not ($window.CheckValidityJson('f') | ConvertFrom-Json).valid) { throw 'Valid form reported invalid' }
            $null = $app.On('started', { $app.Stop() })
        }
    }
    Test-Case 'PS21d_scroll_geometry_follow' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $rows = '<div class="r"></div>' * 4
            $window = $app.Open("<style>body{margin:0}.r{height:30px}</style><div id=""log"" style=""height:100px;overflow:auto""><div id=""r0"" class=""r""></div>$rows</div>", 'scroll', 400, 300)
            if ($window.GetScroll('log').MaxY -ne 50) { throw 'Scroll range is wrong' }
            if ($window.ScrollTo('log', $null, 1000).Y -ne 50) { throw 'scroll_to did not clamp' }
            if ($window.ScrollBy('log', 0, -20).Y -ne 30) { throw 'scroll_by is wrong' }
            $window.ScrollIntoView('r0', 'start', 'nearest')
            $instant = $window.ScrollBy('log', 0, 10, 'instant')
            if ($instant.Animating -or $instant.Y -ne 10) { throw 'scroll_by instant is wrong' }
            $smooth = $window.ScrollTo('log', $null, 0, 'smooth')
            if (-not $smooth.Animating) { throw 'smooth scroll_to did not animate' }
            Start-Sleep -Milliseconds 600
            if ($window.GetScroll('log').Animating -or $window.GetScroll('log').Y -ne 0) { throw 'smooth scroll did not finish' }
            $window.ScrollIntoView('r0', 'start', 'nearest')
            $rect = $window.GetRect('r0')
            if ($rect.Y -ne 0 -or $rect.Width -ne 400) { throw 'Rect is wrong' }
            $window.SetScrollFollow('log', $true)
            $window.AppendHtml('log', '<div class="r"></div>')
            if ($window.GetScroll('log').Y -ne 80) { throw 'Follow did not keep the end visible' }
            $null = $app.On('started', { $app.Stop() })
        }
    }
    Test-Case 'PS21e_selection_clipboard' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $window = $app.Open('<p id="a">Příliš žluťoučký</p><p id="b">кінь</p><input id="pw" type="password" value="secret">')
            $window.SelectText('a')
            if ($window.GetSelection() -ne 'Příliš žluťoučký') { throw 'Element selection is wrong' }
            if ($window.CopySelection() -ne 'Příliš žluťoučký' -or $window.GetClipboardText() -ne 'Příliš žluťoučký') { throw 'Copy failed' }
            $window.SelectText($null)
            if ($window.GetSelection() -ne "Příliš žluťoučký`nкінь") { throw 'Select all is wrong or leaked a control value' }
            $window.ClearSelection()
            if ($window.GetSelection() -ne '') { throw 'Clear failed' }
            $window.SetClipboardText('pasted ✓')
            if ($window.GetClipboardText() -ne 'pasted ✓') { throw 'Clipboard round trip failed' }
            $null = $app.On('started', { $app.Stop() })
        }
    }
    Test-Case 'PS21f_streaming_append_trim' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $window = $app.Open('<div id="log"></div><p id="msg"></p>')
            foreach ($i in 0..299) {
                $window.Batch(@(
                    @{ op = 'insert_html'; element = 'log'; position = 'beforeend'; html = "<div id=""l$i"">$i</div>" },
                    @{ op = 'trim_children'; element = 'log'; keep = 100 }
                ))
                $window.AppendText('msg', 'ž')
            }
            if ($window.Query('#log > div').Count -ne 100) { throw 'Trim did not bound the log' }
            if (($window.Query('#log > div:first-child') -join ',') -ne 'l200') { throw 'Trim removed the wrong end' }
            if ($window.GetText('msg') -ne ('ž' * 300)) { throw 'Streamed text is wrong' }
            $window.TrimChildren('log', 10, 'end')
            if (($window.Query('#log > div:last-child') -join ',') -ne 'l209') { throw 'Trim from end is wrong' }
            $null = $app.On('started', { $app.Stop() })
        }
    }
    Test-Case 'PS21g_dialog_select' {
        $closes = Invoke-Ui4meApp -Backend headless {
            param($app)
            $window = $app.Open('<button id="b">Open</button><dialog id="d"><input id="i"></dialog><select id="s"><option value="a">A</option><option value="b">B</option></select><select id="m" multiple><option value="x">X</option><option value="y">Y</option></select>')
            $seen = [Collections.Generic.List[string]]::new()
            $null = $window.On('close', { param($e) $seen.Add($e.ReturnValue) }, 'd')
            $window.ShowDialog('d', $true)
            $state = $window.GetDialog('d')
            if (-not $state.Open -or -not $state.Modal) { throw 'Dialog did not open modally' }
            if (($window.Query(':focus') -join ',') -ne 'i') { throw 'Dialog did not take focus' }
            $window.CloseDialog('d', 'done')
            $window.SetValue('s', 'b')
            if ($window.GetValue('s') -ne 'b') { throw 'Select value is wrong' }
            $window.SetSelectedValues('m', @('x', 'y'))
            if (@($window.GetOptions('m') | Where-Object Selected).Count -ne 2) { throw 'Multiple selection is wrong' }
            $null = $app.On('started', { $app.Stop() })
            Write-Output -NoEnumerate $seen
        }
        if (($closes -join ',') -ne 'done') { throw "Dialog close event return value: $($closes -join ',')" }
    }
    Test-Case 'PS21g2_popover' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $window = $app.Open('<button id="b" popovertarget="p">Open</button><div id="p" popover>x</div><div id="m" popover="manual">m</div>')
            if (-not (($window.GetPopoverJson('p') | ConvertFrom-Json).kind -eq 'auto')) { throw 'Popover kind is wrong' }
            if (($window.GetPopoverJson('m') | ConvertFrom-Json).kind -ne 'manual') { throw 'Manual popover kind is wrong' }
            $window.ShowPopover('p')
            if (-not ($window.GetPopoverJson('p') | ConvertFrom-Json).open) { throw 'Popover did not open' }
            if (($window.Query(':popover-open') -join ',') -ne 'p') { throw 'popover-open does not match' }
            if ($window.TogglePopover('p')) { throw 'Toggle did not close' }
            $null = $window.TogglePopover('p')
            $window.HidePopover('p')
            if (($window.GetPopoverJson('p') | ConvertFrom-Json).open) { throw 'Popover did not hide' }
            $null = $app.On('started', { $app.Stop() })
        }
    }
    Test-Case 'PS21g4_pagination_pdf' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $window = $app.Open('<style>@page{size:300px 200px;margin:20px} .b{break-before:page}</style><p id="a">one</p><p class="b" id="b">two</p>')
            if (($window.PaginateJson() | ConvertFrom-Json).count -ne 2) { throw 'page count' }
            if (($window.GetPageRectsJson('b') | ConvertFrom-Json)[0].page -ne 1) { throw 'page rects' }
            $pdf = Join-Path ([System.IO.Path]::GetTempPath()) "ui4me-ps-$PID.pdf"
            if (($window.ExportPdf($pdf, $null, 72, 'Doc') | ConvertFrom-Json).pages -ne 2) { throw 'pdf pages' }
            if ([System.Text.Encoding]::ASCII.GetString([System.IO.File]::ReadAllBytes($pdf), 0, 8) -ne '%PDF-1.4') { throw 'pdf header' }
            Remove-Item $pdf
            if (($window.PrintDocument() | ConvertFrom-Json).status -ne 'unavailable') { throw 'headless print' }
            $null = $app.On('started', { $app.Stop() })
        }
    }
    Test-Case 'PS21g3_pointer_capture' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $window = $app.Open('<div id="a">A</div>')
            if ($window.SetPointerCapture('a')) { throw 'Capture without a press was accepted' }
            $window.ReleasePointerCapture('a')
            if ($null -ne $window.GetPointerCapture()) { throw 'A capture is reported' }
            $null = $app.On('started', { $app.Stop() })
        }
    }
    Test-Case 'PS21i_rich_editing' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $window = $app.Open('<div id="ed" contenteditable><p>ab</p></div><p id="o">o</p>')
            if (-not $window.ExecEdit('ed', 'insert_text', 'c')) { throw 'insert_text changed nothing' }
            if (-not $window.ExecEdit('ed', 'bold')) { throw 'bold was refused' }
            if (-not ($window.GetEditStateJson('ed') | ConvertFrom-Json).bold) { throw 'pending bold not reported' }
            if (-not $window.ExecEdit('ed', 'undo')) { throw 'undo changed nothing' }
            $threw = $false
            try { $null = $window.ExecEdit('ed', 'link', 'javascript:alert(1)') } catch { $threw = $true }
            if (-not $threw) { throw 'A javascript: link was accepted' }
            $null = $app.On('started', { $app.Stop() })
        }
    }
    Test-Case 'PS21h_window_actions' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $window = $app.Open('<p>w</p>')
            if (-not $window.Maximize().Applied) { throw 'Maximize was not applied' }
            if (-not ($window.StateJson() | ConvertFrom-Json).maximized) { throw 'State does not report maximized' }
            $null = $window.Restore()
            $window.SetConstraints(300, 200, $null, $null, $false)
            $state = $window.StateJson() | ConvertFrom-Json
            if ($state.resizable -or $state.min_size[0] -ne 300) { throw 'Constraints were not recorded' }
            if ($app.MonitorsJson() -ne '[]') { throw 'Headless should report no monitors' }
            $caps = $app.CapabilitiesJson() | ConvertFrom-Json
            if ($caps.backend -ne 'headless' -or $caps.features.'window.focus'.status -ne 'unavailable' -or -not $caps.features.'window.focus'.reason) { throw "Headless capabilities: $($app.CapabilitiesJson())" }
            $doc = $app.Open('<div id=box><span>no id</span>žluť</div>')
            if ($doc.GetHtml('box', $null, $false) -ne '<span>no id</span>žluť') { throw "inner html: $($doc.GetHtml('box', $null, $false))" }
            $sheet = $doc.AddStylesheet('#box{width:77px}') | ConvertFrom-Json
            if ($doc.GetRect('box').Width -ne 77) { throw 'stylesheet not applied' }
            $doc.RemoveStylesheet($sheet.sheet)
            $kids = $doc.NodeChildrenJson($doc.NodeOf('box'), 0, 256) | ConvertFrom-Json
            if ($kids.total -ne 2 -or $kids.children[0].name -ne 'span') { throw "children: $($kids | ConvertTo-Json -Compress)" }
            if (($doc.NodeJson($kids.children[1].node) | ConvertFrom-Json).text -ne 'žluť') { throw 'text node' }
            $cs = ($doc.ComputedStyleJson('box', 'color', 'nope') | ConvertFrom-Json).properties
            if ($cs.color.status -ne 'supported' -or $cs.nope.status -ne 'invalid') { throw "computed style: $($cs | ConvertTo-Json -Compress)" }
            $app.SetLinkPolicy(@('https'), @('*.example.com'), $false)
            $refused = $false; try { $app.SetLinkPolicy(@('file'), $null, $false) } catch { $refused = $true }
            if (-not $refused) { throw 'file: scheme accepted' }
            if (($app.Notify('Hi', 'there', $null, $null, $null) | ConvertFrom-Json).status -ne 'unavailable') { throw 'notify in headless' }
            $menu = $doc.SetMenu(@(@{ label = 'File'; items = @(@{ id = 'save'; label = 'Save'; accelerator = 'Ctrl+S' }) })) | ConvertFrom-Json
            if (-not $menu.accelerators) { throw "set_menu: $($menu | ConvertTo-Json -Compress)" }
            if (($app.RegisterHotkey('k', 'Ctrl+Alt+K') | ConvertFrom-Json).status -ne 'unavailable') { throw 'hotkey in headless' }
            $picker = $app.Open('<input id=pick type=file>')
            if ($picker.GetFiles('pick').Count -ne 0) { throw 'file input starts empty' }
            $geo = $doc.TextRectsJson('box', $null, -1, -1) | ConvertFrom-Json
            if ($geo.length -ne 9 -or $geo.rects.Count -lt 1) { throw "text rects: $($geo | ConvertTo-Json -Compress)" }
            $styled = $app.Open('<style>#b{width:10px;height:5px}@media (prefers-color-scheme: dark){#b{width:20px}}</style><div id=b></div>')
            $env = $styled.SetEnvironment('dark', $null) | ConvertFrom-Json
            if ($env.color_scheme -ne 'dark' -or $env.color_scheme_source -ne 'app' -or $styled.GetRect('b').Width -ne 20) { throw "Dark override: $($styled.EnvironmentJson())" }
            $null = $styled.SetEnvironment('system', $null)
            if ($styled.GetRect('b').Width -ne 10) { throw 'system did not restore the default scheme' }
            $null = $app.On('started', { $app.Stop() })
        }
    }
    Test-Case 'PS21i_file_dialog_headless' {
        $seen = Invoke-Ui4meApp -Backend headless {
            param($app)
            $window = $app.Open('<p>f</p>')
            $results = [Collections.Generic.List[string]]::new()
            $null = $window.OpenFileDialog({ param($e) $results.Add($(if ($null -eq $e.Paths) { 'cancel' } else { 'paths' })) }, 'Pick', $null, @{ Text = @('txt') }, $false)
            $null = $window.SaveFileDialog({ param($e) $results.Add($(if ($null -eq $e.Paths) { 'cancel' } else { 'paths' })) }, $null, $null, 'notes ž.txt', $null)
            $null = $app.Timer(50, { $app.Stop() }, $false)
            Write-Output -NoEnumerate $results
        }
        if (($seen -join ',') -ne 'cancel,cancel') { throw "Headless file dialogs: $($seen -join ',')" }
    }
    Test-Case 'PS21j_accessibility_tree' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $window = $app.Open('<button id="b">Save</button><label for="n">Name</label><input id="n">')
            $json = $window.AccessibilityTreeJson()
            if ($json -notmatch 'Save' -or $json -notmatch 'Name') { throw "Accessibility tree: $json" }
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

    Test-Case 'PSDG1_diagnostics_and_explain' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            $w = $app.Open('<style>#a{view-transition-name:x}</style><div id="a">x</div><span id="s">s</span>')
            try { $w.SetText('/home/someone/missing.css?token=SECRET', 't') } catch { }
            $r = $w.GetDiagnosticsJson() | ConvertFrom-Json
            if ($r.schema -ne 1 -or $r.items.Count -lt 1) { throw 'No diagnostics' }
            $raw = $w.GetDiagnosticsJson()
            if ($raw -match 'SECRET' -or $raw -match '/home/someone') { throw 'Diagnostics were not redacted' }
            if ($w.GetDiagnosticsJson($false) -notmatch 'SECRET') { throw 'redact=false lost the content' }
            $cursor = ($r.items | Measure-Object -Property seq -Maximum).Maximum
            if (@(($w.GetDiagnosticsJson($true, [uint64]$cursor) | ConvertFrom-Json).items).Count -ne 0) { throw 'since cursor ignored' }
            if (($w.ExplainJson('s', 'width') | ConvertFrom-Json).status -ne 'not_applicable') { throw 'inline width' }
            if (($w.ExplainJson('a', 'view-transition-name') | ConvertFrom-Json).status -ne 'unsupported') { throw 'unsupported' }
            if (($w.ExplainJson('gone', 'color') | ConvertFrom-Json).status -ne 'stale_reference') { throw 'stale' }
            $null = $app.On('started', { $app.Stop() })
        }
    }
    Test-Case 'PSBG1_fifty_background_tasks_settle_on_owner' {
        $r = Invoke-Ui4meApp -Backend headless {
            param($app)
            $rows = (0..1499 | ForEach-Object { "<li id=`"r$_`">row $_</li>" }) -join ''
            $window = New-Ui4meWindow "<ul>$rows</ul>"
            $state = @{ settled = [System.Collections.Generic.List[int]]::new(); threads = @{}; mutations = 0; tasks = [System.Collections.Generic.List[object]]::new() }
            $owner = [Environment]::CurrentManagedThreadId
            $null = $app.Timer(1, { $state.mutations++; $window.SetText("r$($state.mutations % 1500)", "changed $($state.mutations)") }, $true)
            $null = $app.Timer(10000, { $app.Stop() }, $false)
            foreach ($n in 0..49) {
                $state.tasks.Add($app.RunInBackground({ param($n) Start-Sleep -Milliseconds (2 * ($n % 7)); $n * $n },
                    { param($value)
                        $state.threads[[Environment]::CurrentManagedThreadId] = $true
                        $state.settled.Add([int]$value)
                        if ($state.settled.Count -eq 50) { $app.Stop() } },
                    { param($e) throw "unexpected error $e" }, @($n)))
            }
            $null = $app.On('stopped', {
                if ($state.settled.Count -ne 50) { throw "settled $($state.settled.Count)" }
                if ($state.threads.Count -ne 1 -or -not $state.threads.ContainsKey($owner)) { throw 'Settled off the owner thread' }
                $seq = @($state.settled | ForEach-Object { $state.tasks[[int][math]::Sqrt($_)].CompletionSequence })
                for ($i = 1; $i -lt $seq.Count; $i++) { if ($seq[$i] -le $seq[$i - 1]) { throw 'Not in completion order' } }
                if ((($state.settled | Sort-Object) -join ',') -ne (((0..49 | ForEach-Object { $_ * $_ }) | Sort-Object) -join ',')) { throw 'Wrong values' }
                if ($state.mutations -lt 1) { throw 'Owner did not render' }
            })
        }
    }
    Test-Case 'PSBG2_background_exception_cancel_and_stop' {
        # error path, cancel before start, stop with pending tasks
        $task = Invoke-Ui4meApp -Backend headless {
            param($app)
            $gate = [System.Threading.ManualResetEventSlim]::new($false)
            $state = @{ log = [System.Collections.Generic.List[string]]::new() }
            $null = $app.RunInBackground({ throw 'boom' }, { param($v) $state.log.Add('done') }, { param($e) $state.log.Add('error:' + $e.Message); $app.Stop() })
            $blockers = foreach ($i in 1..4) { $app.RunInBackground({ param($g) $null = $g.Wait(5000); 1 }, { param($v) $state.log.Add('blocker') }, $null, @($gate)) }
            $queued = $app.RunInBackground({ 2 }, { param($v) $state.log.Add('queued') }, $null)
            if (-not $queued.Cancel() -or $queued.Status -ne 'cancelled') { throw 'Pending task was not cancelled' }
            $failed = $false; try { $null = $queued.GetResult() } catch { $failed = $true }
            if (-not $failed) { throw 'Cancelled GetResult did not throw' }
            $null = $app.On('stopped', {
                $gate.Set()
                if ($state.log.Count -ne 1 -or $state.log[0] -ne 'error:boom') { throw ('log: ' + ($state.log -join ',')) }
            })
            $null = $app.Timer(5000, { $app.Stop() }, $false)
            Write-Output -NoEnumerate $blockers
        }
        foreach ($t in $task) {
            if ($t.Status -notin 'cancelled', 'succeeded') { throw "Pending task left in $($t.Status)" }
            if ($t.Delivered) { throw 'Callback delivered after stop' }
        }
        # a fresh App after the stop works
        $value = Invoke-Ui4meApp -Backend headless {
            param($app)
            $state = @{ v = $null }
            $null = $app.RunInBackground({ 40 + 2 }, { param($v) $state.v = $v; $app.Stop() }, { param($e) throw $e })
            $null = $app.Timer(5000, { $app.Stop() }, $false)
            Write-Output -NoEnumerate $state
        }
        if ($value.v -ne 42) { throw "Restart result $($value.v)" }
    }
    Test-Case 'PSBG3_background_survives_post_queue_pressure' {
        Invoke-Ui4meApp -Backend headless {
            param($app)
            foreach ($i in 1..512) { $null = $app.Post({}) }
            $state = @{ got = 0 }
            foreach ($n in 1..20) {
                $null = $app.RunInBackground({ param($n) $n }, { param($v) $state.got++; if ($state.got -eq 20) { $app.Stop() } }, { param($e) throw $e }, @($n))
            }
            $null = $app.Timer(10000, { $app.Stop() }, $false)
            $null = $app.On('stopped', { if ($state.got -ne 20) { throw "Only $($state.got) of 20 settled" } })
        }
    }

    Test-Case 'PS_contract_coverage' {
        # The managed layer exposes no hook to observe wire commands, so each declared op maps to
        # the public App/Window call that sends it; every call must complete on the headless
        # backend (an honest refusal is fine, a protocol error is not). The op set must equal the
        # profile's declaration, so a new op without a public method fails here.
        # cancel_completion is only sent when scheduling a Work item fails after reserve_completion
        # (an internal rollback with no public trigger); it shares Work with reserve_completion.
        $profilePath = Join-Path $PSScriptRoot '..' '..' '..' 'docs' 'SUPPORT_PROFILE_V1.json'
        $declared = @((Get-Content -Raw -LiteralPath $profilePath | ConvertFrom-Json).commands | Where-Object powershell | ForEach-Object op | Sort-Object)
        $calls = [ordered]@{
        'add_class' = '$w.AddClass("p","x")'
        'add_stylesheet' = '$w.AddStylesheet("p{color:red}")'
        'append_text' = '$w.AppendText("p","!")'
        'batch' = '$w.Batch(@(@{op="set_text";element="p";text="b"}))'
        'cancel_completion' = '$null = $app.Work({ 1 }, @(), { })'
        'cancel_timer' = '$app.Timer(10000, { }, $false).Cancel()'
        'capabilities' = '$app.CapabilitiesJson()'
        'check_validity' = '$w.CheckValidityJson("f")'
        'claim_instance' = '$app.ClaimInstance(@())'
        'clear_selection' = '$w.ClearSelection()'
        'close' = '$w.Close()'
        'close_dialog' = '$w.ShowDialog("dlg", $true); $w.CloseDialog("dlg", "r")'
        'close_notification' = '$app.CloseNotification(1)'
        'copy_selection' = '$w.CopySelection()'
        'diagnostics' = '$w.DiagnosticsJson()'
        'exec_edit' = '$w.ExecEdit("ed", "bold", $null)'
        'explain' = '$w.ExplainJson("p", "color")'
        'export_pdf' = '$w.ExportPdf((Join-Path $tmp "o.pdf"))'
        'file_dialog' = '$w.OpenFileDialog({ }, $null, $null, $null, $false)'
        'focus' = '$w.Focus("i")'
        'get_accessibility_tree' = '$w.AccessibilityTreeJson()'
        'get_attribute' = '$w.GetAttribute("p","id")'
        'get_attributes' = '$w.GetAttributes("p")'
        'get_checked' = '$w.GetChecked("chk")'
        'get_clipboard_html' = '$w.GetClipboardHtml($false)'
        'get_clipboard_text' = '$w.GetClipboardText()'
        'get_computed_style' = '$w.ComputedStyleJson("p", "color")'
        'get_diagnostics' = '$w.GetDiagnosticsJson()'
        'get_dialog' = '$w.GetDialog("dlg")'
        'get_edit_state' = '$w.GetEditStateJson("ed")'
        'get_environment' = '$w.EnvironmentJson()'
        'get_files' = '$w.GetFiles("file")'
        'get_html' = '$w.GetHtml("p", $null, $false)'
        'get_node' = '$w.NodeJson($w.NodeOf("p"))'
        'get_options' = '$w.GetOptions("sel")'
        'get_page_rects' = '$null = $w.PaginateJson(); $w.GetPageRectsJson("p")'
        'get_pointer_capture' = '$w.GetPointerCapture()'
        'get_popover' = '$w.GetPopoverJson("pop")'
        'get_rect' = '$w.GetRect("box")'
        'get_scroll' = '$w.GetScroll("scroller")'
        'get_selection' = '$w.GetSelection()'
        'get_text' = '$w.GetText("p")'
        'get_validity' = '$w.GetValidityJson("i")'
        'get_value' = '$w.GetValue("i")'
        'get_window_state' = '$w.StateJson()'
        'has_element' = '$w.HasElement("p")'
        'hide_popover' = '$w.HidePopover("pop")'
        'insert_html' = '$w.AppendHtml("list", "<li>d</li>")'
        'list_monitors' = '$app.MonitorsJson()'
        'list_stylesheets' = '$w.StylesheetsJson()'
        'move_element' = '$w.MoveElement("a", "list", "beforeend")'
        'node_children' = '$w.NodeChildrenJson($w.NodeOf("list"), 0, 256)'
        'node_of' = '$w.NodeOf("p")'
        'notify' = '$app.Notify("t", "b", $null, $null, $null)'
        'open' = '$app.Open("<p>x</p>", "t", 100, 100)'
        'open_file' = '$app.OpenFile((Join-Path $tmp "doc.html"), "t", 100, 100)'
        'paginate' = '$w.PaginateJson()'
        'print' = '$w.PrintDocument()'
        'query' = '$w.Query("li", 1024)'
        'register_hotkey' = '$app.RegisterHotkey("h", "Ctrl+Alt+K")'
        'remove_attribute' = '$w.RemoveAttribute("p", "title")'
        'remove_class' = '$w.RemoveClass("p", "x")'
        'remove_element' = '$w.RemoveElement("s")'
        'remove_stylesheet' = '$w.RemoveStylesheet(($w.AddStylesheet("p{color:red}") | ConvertFrom-Json).sheet)'
        'remove_tray' = '$app.RemoveTray()'
        'render_page' = '$null = $w.PaginateJson(); $w.RenderPage(0, (Join-Path $tmp "p.png"), 96)'
        'replace_children_html' = '$w.ReplaceChildrenHtml("list", "<li>z</li>")'
        'replace_stylesheet' = '$w.ReplaceStylesheet(($w.AddStylesheet("p{color:red}") | ConvertFrom-Json).sheet, "p{color:blue}")'
        'reserve_completion' = '$null = $app.Work({ 1 }, @(), { })'
        'resize' = '$w.Resize(320, 240)'
        'scroll_by' = '$w.ScrollBy("scroller", 0, 5, $null)'
        'scroll_into_view' = '$w.ScrollIntoView("c", "nearest", "nearest", $null)'
        'scroll_to' = '$w.ScrollTo("scroller", $null, 5, $null)'
        'select_text' = '$w.SelectText("p")'
        'set_attribute' = '$w.SetAttribute("p", "title", "t")'
        'set_checked' = '$w.SetChecked("chk", $true)'
        'set_clipboard_html' = '$w.SetClipboardHtml("<b>x</b>", "x")'
        'set_clipboard_text' = '$w.SetClipboardText("x")'
        'set_default_action' = '$w.SetDefaultAction("p", "click")'
        'set_environment' = '$w.SetEnvironment("dark", $null)'
        'set_link_policy' = '$app.SetLinkPolicy(@("https"), $null, $false)'
        'set_menu' = '$w.SetMenu(@(@{ id = "m"; label = "M" }))'
        'set_pointer_capture' = '$w.SetPointerCapture("box", 1)'
        'set_pointer_grab' = '$w.SetPointerGrab("none", $true)'
        'set_scroll_follow' = '$w.SetScrollFollow("scroller", $true)'
        'set_selected_values' = '$w.SetSelectedValues("sel", @("2"))'
        'set_text' = '$w.SetText("p", "t")'
        'set_title' = '$w.SetTitle("T")'
        'set_tray' = '$app.SetTray($null, "t", $null)'
        'set_value' = '$w.SetValue("i", "x")'
        'set_window_constraints' = '$w.SetConstraints(100, 100, $null, $null, $true)'
        'set_window_icon' = '$w.SetIcon($null)'
        'show_context_menu' = '$w.ShowContextMenu(1, 1, @(@{ id = "c"; label = "C" }))'
        'show_dialog' = '$w.ShowDialog("dlg", $true)'
        'show_popover' = '$w.ShowPopover("pop")'
        'snapshot' = '$w.Snapshot((Join-Path $tmp "s.png"))'
        'stats' = '$app.StatsJson()'
        'text_at_point' = '$w.TextAtPointJson(5, 5)'
        'text_rects' = '$w.TextRectsJson("p", $null, -1, -1)'
        'timer' = '$app.Timer(10000, { }, $false)'
        'toggle_popover' = '$w.TogglePopover("pop")'
        'trim_children' = '$w.TrimChildren("list", 1, "start")'
        'unregister_hotkey' = '$app.UnregisterHotkey("h")'
        'window_action' = '$w.WindowAction("show")'
        }
        $table = @($calls.Keys | Sort-Object)
        $diff = Compare-Object $declared $table
        if ($diff) { throw ('Op table differs from the profile: ' + (($diff | ForEach-Object { "$($_.InputObject) ($($_.SideIndicator))" }) -join ', ')) }
        $html = '<style>#box{width:40px;height:20px}</style><div id="root"><p id="p">hello world</p><span id="s">x</span><div id="box">box</div><div id="scroller" style="height:30px;overflow:auto"><div style="height:300px">tall</div></div><ul id="list"><li id="a">a</li><li id="b">b</li><li id="c">c</li></ul><form id="f"><input id="i" value="v" required><input id="chk" type="checkbox"><select id="sel"><option value="1">one</option><option value="2">two</option></select></form><div id="ed" contenteditable="true">edit</div><dialog id="dlg">dialog</dialog><div id="pop" popover>pop</div><input id="file" type="file"></div>'
        $tmp = Join-Path ([IO.Path]::GetTempPath()) ('ui4me-contract-' + [guid]::NewGuid())
        $null = New-Item -ItemType Directory -Path $tmp
        $failures = [System.Collections.Generic.List[string]]::new()
        try {
            Set-Content -LiteralPath (Join-Path $tmp 'doc.html') -Value '<p>doc</p>' -Encoding utf8
            foreach ($op in $table) {
                $result = Invoke-Ui4meApp -Backend headless -ArgumentList @($calls[$op], $html, $tmp) {
                    param($app, $text, $html, $tmp)
                    $w = $app.Open($html)
                    $outcome = 'ok'
                    try { $null = & ([scriptblock]::Create($text)) }
                    catch {
                        # Only a refusal from the native layer is an acceptable result; a missing
                        # method or a binding exception is a contract failure.
                        $native = $_.Exception
                        while ($native -and $native -isnot [Ui4me.Managed.Ui4meException]) { $native = $native.InnerException }
                        $outcome = if ($native) { 'refused: ' + $native.Message } else { 'error: ' + $_.Exception.Message }
                    }
                    Write-Output $outcome
                    $null = $app.On('started', { param($event) $app.Stop() })
                }
                if ("$result" -match '^refused: .*(unknown|unsupported op|unrecognized|invalid command|protocol|missing field|unknown variant)') { $failures.Add("${op}: $result") }
                elseif ("$result" -notmatch '^(ok|refused: )') { $failures.Add("${op}: no outcome ($result)") }
            }
        }
        finally { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue }
        if ($failures.Count) { throw ($failures -join "`n") }
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
