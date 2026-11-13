# Native PowerShell journey: events, binding, computed, keyed list, When/disposal, tabs,
# CSS replacement, toast timer, background task + cancel, native save dialog, close veto,
# and user close -> clean shutdown. Run: Start-UI4MEUiScript -Path ps_basic.ps1 (via a driver).
$ErrorActionPreference = 'Stop'
Import-Module UI4ME
. (Join-Path $PSScriptRoot '..\Channel.ps1')

$Title = 'UI4ME PS journey'
$script:allowClose = $false
$script:closeRequests = 0
$script:closedRuns = 0
$script:log = New-Object System.Collections.ArrayList

Invoke-UI4MEApp -Title $Title -Width 900 -Height 760 -Content {
    $clicks = New-UI4MEState -Value 0
    $name = New-UI4MEState -Value ''
    $agree = New-UI4MEState -Value $false
    $color = New-UI4MEState -Value 'red'
    $showWorker = New-UI4MEState -Value $false
    $items = New-UI4MEState -Value @(1..5 | ForEach-Object { [pscustomobject]@{ id = $_; label = "Item $_" } })
    $greeting = New-UI4MEComputed -DependsOn $name -Expression { "Hello $(if ($name.Value) { $name.Value } else { 'nobody' })" }
    $saved = New-UI4MEState -Value 'none'
    $taskResult = New-UI4MEState -Value 'none'

    New-UI4MERow -Content {
        $script:btn = New-UI4MEButton -Text 'Press me' -OnClick { $clicks.Set([int]$clicks.Value + 1) }
        $script:count = New-UI4METext -Bind $clicks
    }
    $script:field = New-UI4MEInput -Label 'Name' -Bind $name -OnSubmit { param($v) [void]$script:log.Add("submit:$v") }
    $script:greet = New-UI4METext -Bind $greeting
    $script:box = New-UI4MECheckbox -Label 'I agree' -Bind $agree
    $script:sel = New-UI4MESelect -Label 'Color' -Options @('red', 'green', 'blue') -Bind $color
    $script:tabs = New-UI4METabs -Tabs ([ordered]@{
        'First' = { New-UI4METext -Text 'first panel' }
        'Second' = { $script:secondText = New-UI4METext -Text 'second panel' }
    })
    $script:styled = New-UI4METext -Text 'styled' -Class 'probe-styled'
    $when = New-UI4MEState -Value ([datetime]'2026-02-14')
    $colour = New-UI4MEState -Value '#2563eb'
    New-UI4MERow -Content {
        $script:dateId = New-UI4MEDate -Label 'When' -Bind $when
        $script:colorId = New-UI4MEColor -Label 'Colour' -Bind $colour
    }
    $script:saveBtn = New-UI4MEButton -Text 'Save as' -OnClick {
        $path = Show-UI4MEUiFileDialog -Kind Save -Title 'UI4ME PS save probe' -FileName 'ps-probe.txt'
        $saved.Set("save:$path")
    }
    New-UI4MEWhen -Condition $showWorker -Content {
        New-UI4METext -Text 'worker'
        $null = Start-UI4MEUiTimer -Milliseconds 50 -Repeat -Action { [void]$script:log.Add('tick') }
        $null = Start-UI4MEUiTask -Work { Start-Sleep -Seconds 3; 'late' } -OnDone { param($r) [void]$script:log.Add("task:$r") }
    }
    $script:list = New-UI4MEEach -Items $items -Key id -Template {
        param($item)
        New-UI4MERow -Content {
            New-UI4METext -Text $item.label
            $null = New-UI4MEInput -Label "note $($item.id)" -Class "note-$($item.id)"
        }
    }
} -OnCloseRequest {
    $script:closeRequests++
    $script:allowClose
} -OnClose {
    $script:closedRuns++
    Write-Check 'window.on_close_once' ($script:closedRuns -eq 1) $script:closedRuns
    Write-ChannelDone
} -OnReady {
    try {
        $ctx = Get-UI4MEUiContext
        $doc = $ctx.Document
        # 1. Real click -> handler -> state -> bound text.
        Invoke-Click $Title $script:btn
        $ok = Wait-Until { $clicks.Value -eq 1 }
        Write-Check 'button.click' ($ok -and (Get-UI4MEDocumentText -Document $doc -Element $script:count) -eq '1') $clicks.Value
        # 2. Typing -> bound state -> computed text; Enter -> OnSubmit.
        Invoke-Click $Title $script:field
        $null = Request-Channel 'type' @{ text = 'Ada' }
        $ok = Wait-Until { $name.Value -eq 'Ada' }
        Write-Check 'input.type.binds' ($ok -and (Get-UI4MEDocumentText -Document $doc -Element $script:greet) -eq 'Hello Ada') $name.Value
        $null = Request-Channel 'key' @{ key = 'enter' }
        Write-Check 'input.enter.submit' (Wait-Until { $script:log -contains 'submit:Ada' }) ($script:log -join ',')
        $name.Set('Grace')
        Write-Check 'input.state_to_dom' ((Get-UI4MEValue -Document $doc -Element $script:field) -eq 'Grace') $null
        # 3. Checkbox click.
        Invoke-Click $Title $script:box
        Write-Check 'checkbox.click' (Wait-Until { $agree.Value -eq $true }) $agree.Value
        # 4. Select with keyboard.
        Set-UI4MEFocus -Document $doc -Element $script:sel
        $null = Request-Channel 'key' @{ key = 'down' }
        Write-Check 'select.keyboard' (Wait-Until { $color.Value -eq 'green' } 5) $color.Value
        # 5. Tabs.
        Invoke-Click $Title "$($script:tabs)-2-tab"
        $hidden = (Invoke-UI4MEDocumentCommand -Document $doc -Operation get_attribute -Parameters @{ element = "$($script:tabs)-2-panel"; name = 'hidden' }).value
        Write-Check 'tabs.click' ($null -eq $hidden) $hidden
        # 6. Keyed list: typed value and node identity survive reorder; removed rows release handlers.
        $note3 = (Find-UI4MEElement -Document $doc -Selector '.note-3').ids[0]
        Invoke-Click $Title $note3
        $null = Request-Channel 'type' @{ text = 'keep' }
        $null = Wait-Until { (Get-UI4MEValue -Document $doc -Element $note3) -eq 'keep' }
        $nodeBefore = (Get-UI4MENode -Document $doc -Element $note3).Id
        $before = Get-UI4MEUiDiagnostics
        $new = @($items.Value | Sort-Object id -Descending | Where-Object { $_.id -ne 2 }) + [pscustomobject]@{ id = 9; label = 'Item 9' }
        $items.Set($new)
        $order = @((Find-UI4MEElement -Document $doc -Selector "#$($script:list) .u4-text").ids | ForEach-Object { Get-UI4MEDocumentText -Document $doc -Element $_ })
        $nodeAfter = (Get-UI4MENode -Document $doc -Element $note3).Id
        Write-Check 'each.reorder.preserves_dom' ($nodeBefore -eq $nodeAfter -and (Get-UI4MEValue -Document $doc -Element $note3) -eq 'keep') "$nodeBefore -> $nodeAfter"
        Write-Check 'each.order' (($order -join ',') -eq 'Item 5,Item 4,Item 3,Item 1,Item 9') ($order -join ',')
        Write-Check 'each.remove' (@((Find-UI4MEElement -Document $doc -Selector '.note-2').ids).Count -eq 0) $null
        $after = Get-UI4MEUiDiagnostics
        Write-Check 'each.subscriptions_shared' ($after.CoreSubscriptions -le 6) ($after | ConvertTo-Json -Compress)
        # 7. When: disposing content stops its timer and task.
        $showWorker.Set($true)
        $null = Wait-Until { $script:log -contains 'tick' }
        $showWorker.Set($false)
        $ticks = @($script:log | Where-Object { $_ -eq 'tick' }).Count
        $null = Wait-UI4MEUi -Milliseconds 3800
        Write-Check 'when.dispose_stops_timer' (@($script:log | Where-Object { $_ -eq 'tick' }).Count -le $ticks + 1) $ticks
        Write-Check 'when.dispose_skips_task' (-not ($script:log -contains 'task:late')) (($script:log | Where-Object { $_ -ne 'tick' }) -join ',')
        # 8. Background task + cancellation outside components.
        $t1 = Start-UI4MEUiTask -Work { param($a) $a * 2 } -ArgumentList 21 -OnDone { param($r) $taskResult.Set("done:$r") }
        Write-Check 'task.done' (Wait-Until { $taskResult.Value -eq 'done:42' }) $taskResult.Value
        $script:cancelled = $false
        $t2 = Start-UI4MEUiTask -Work { Start-Sleep 5; 'x' } -OnDone { $taskResult.Set('should-not') } -OnCancel { $script:cancelled = $true }
        Stop-UI4MEUiTask -Task $t2
        $null = Wait-UI4MEUi -Milliseconds 600
        Write-Check 'task.cancel' ($script:cancelled -and $taskResult.Value -eq 'done:42' -and $t2.State -eq 'cancelled') $t2.State
        # 9. CSS replacement twice.
        $sheets = @(Get-UI4MEStylesheets -Document $doc).Count
        Set-UI4MEUiTheme -Css '.probe-styled { color: rgb(1, 2, 3); }'
        $c1 = (Get-UI4MEComputedStyle -Document $doc -Element $script:styled -Properties color).properties.color.value
        Set-UI4MEUiTheme -Css '.probe-styled { color: rgb(200, 10, 20); }'
        $c2 = (Get-UI4MEComputedStyle -Document $doc -Element $script:styled -Properties color).properties.color.value
        Write-Check 'css.replace' ($c1 -eq 'rgb(1, 2, 3)' -and $c2 -eq 'rgb(200, 10, 20)') "$c1 / $c2"
        Write-Check 'css.no_sheet_leak' (@(Get-UI4MEStylesheets -Document $doc).Count -eq $sheets) $sheets
        Set-UI4MEUiTheme -Reset
        # 10. Toast auto-dismiss.
        $toast = Show-UI4MEUiToast -Text 'hello' -Seconds 0.5
        $gone = Wait-Until { @((Find-UI4MEElement -Document $doc -Selector "#$toast").ids).Count -eq 0 } 5
        Write-Check 'toast.auto_dismiss' $gone $toast
        # 10b. In-window calendar and swatches with real clicks.
        Invoke-Click $Title "$($script:dateId)-cal-toggle"
        $opened = Wait-Until { (Invoke-UI4MEDocumentCommand -Document $doc -Operation get_attribute -Parameters @{ element = "$($script:dateId)-cal"; name = 'hidden' }).value -eq $null }
        Invoke-Click $Title "$($script:dateId)-cal-d20260220"
        Write-Check 'date.calendar.click_day' ($opened -and (Wait-Until { $when.Value -eq [datetime]'2026-02-20' })) "$($when.Value)"
        Write-Check 'date.calendar.writes_text' ((Get-UI4MEValue -Document $doc -Element $script:dateId) -eq '2026-02-20') (Get-UI4MEValue -Document $doc -Element $script:dateId)
        Invoke-Click $Title "$($script:colorId)-swatches-6"
        Write-Check 'color.swatch_click' (Wait-Until { $colour.Value -eq '#16a34a' }) $colour.Value
        # 11. Native save dialog from a click handler (handler blocks; input is queued first).
        $c = Get-Center $script:saveBtn
        $a = Send-ChannelRequest 'click' @{ window = $Title; x = $c.x; y = $c.y }
        $b = Send-ChannelRequest 'dialog-key' @{ window = 'UI4ME PS save probe'; key = 'enter' }
        $null = Receive-ChannelAck $a
        $ack = Receive-ChannelAck $b 'dialog-key' 60
        $ok = Wait-Until { $saved.Value -like 'save:*ps-probe.txt' } 15
        Write-Check 'dialog.save' ($ok -and $null -ne $ack.window) $saved.Value
        # 12. Close veto, then allowed close.
        $null = Request-Channel 'native-close' @{ window = $Title }
        $null = Wait-Until { $script:closeRequests -ge 1 } 5
        $null = Wait-UI4MEUi -Milliseconds 800
        $wins = (Request-Channel 'windows').windows
        Write-Check 'close.veto' (@($wins | Where-Object { $_.caption -like "*$Title*" }).Count -eq 1 -and $script:closeRequests -eq 1) $script:closeRequests
        Write-Check 'no.errors' ((Get-UI4MEUiDiagnostics).Errors -eq 0) (Get-UI4MEUiDiagnostics).LastError
        $script:allowClose = $true
        $null = Send-ChannelRequest 'native-close' @{ window = $Title }
    } catch {
        Write-ChannelFatal ("$_`n" + $_.ScriptStackTrace)
        Write-ChannelDone
        Stop-UI4MEUiApp
    }
}
