# Native PowerShell journey for the UI4ME 2.1 additions, started directly (pwsh -File / powershell.exe -File).
# Covers metric binding, multi-select, segmented (radio), adjustable split (keyboard), tooltip (focus),
# copy button + native clipboard, log with hostile text, escaping of user-supplied text, colour-scheme
# switch without transition floods, owner-disposed timers, and a user close -> clean shutdown.
$ErrorActionPreference = 'Stop'
Import-Module UI4ME
. (Join-Path $PSScriptRoot '..\Channel.ps1')

$Title = 'UI4ME PS 2.1 journey'
$script:closedRuns = 0
$script:log = New-Object System.Collections.ArrayList
$script:Hostile = '<b>bold</b> & "quotes"'

Invoke-UI4MEApp -Title $Title -Width 1000 -Height 860 -Content {
    $jobs = New-UI4MEState -Value 4
    $features = New-UI4MEState -Value @('alpha')
    $mode = New-UI4MEState -Value 'list'
    $label = New-UI4MEState -Value 'plain'
    $showTicker = New-UI4MEState -Value $false

    New-UI4MERow -Content {
        $script:metric = New-UI4MEMetric -Label 'Pending jobs' -Value $jobs -Detail 'queue'
        $script:more = New-UI4MEButton -Text 'More jobs' -OnClick { $jobs.Set([int]$jobs.Value + 1) }
        $script:tip = New-UI4METooltip -Text 'Copies the sample text' -Content {
            $script:copy = New-UI4MECopyButton -Text 'Sample PS ✓ text' -Label 'Copy sample'
        }
    }
    $script:fs = New-UI4MEFieldset -Legend 'Options' -Content {
        $script:multi = New-UI4MEMultiSelect -Label 'Features' -Options @('alpha', 'beta', 'gamma') -Bind $features
    }
    $script:seg = New-UI4MESegmented -Label 'View' -Options @('list', 'grid', 'table') -Bind $mode
    $script:split = New-UI4MEResizableSplit -Percent 30 -Label 'Pane size' -Side { New-UI4METext -Text 'side' } -Main { New-UI4METext -Text 'main' }
    $script:userText = New-UI4METext -Bind $label
    $script:logView = New-UI4MELog -MaxLines 3 -Label 'Events'
    New-UI4MEWhen -Condition $showTicker -Content {
        $null = Start-UI4MEUiTimer -Milliseconds 40 -Repeat -Action { [void]$script:log.Add('tick') }
    }
    $script:state = [pscustomobject]@{ Jobs = $jobs; Features = $features; Mode = $mode; Label = $label; Ticker = $showTicker }
} -OnClose {
    $script:closedRuns++
    Write-Check 'window.on_close_once' ($script:closedRuns -eq 1) $script:closedRuns
    Write-ChannelDone
} -OnReady {
    try {
        $ctx = Get-UI4MEUiContext
        $doc = $ctx.Document
        $st = $script:state
        # 1. Metric follows a real click.
        Invoke-Click $Title $script:more
        $ok = Wait-Until { [int]$st.Jobs.Value -eq 5 }
        Write-Check 'metric.click_updates' ($ok -and (Get-UI4MEDocumentText -Document $doc -Element $script:metric) -eq '5') $st.Jobs.Value
        # 2. Multi-select: check beta, uncheck alpha; programmatic set reaches the DOM.
        Invoke-Click $Title "$($script:multi)-2"
        Invoke-Click $Title "$($script:multi)-1"
        $ok = Wait-Until { (@($st.Features.Value) -join ',') -eq 'beta' }
        Write-Check 'multiselect.clicks' $ok (@($st.Features.Value) -join ',')
        $st.Features.Set(@('gamma'))
        Write-Check 'multiselect.state_to_dom' ((Get-UI4MEChecked -Document $doc -Element "$($script:multi)-3") -and -not (Get-UI4MEChecked -Document $doc -Element "$($script:multi)-2")) $null
        # 3. Segmented (radio group) by click.
        Invoke-Click $Title "$($script:seg)-2"
        Write-Check 'segmented.click' (Wait-Until { $st.Mode.Value -eq 'grid' }) $st.Mode.Value
        # 4. Split with the keyboard.
        Set-UI4MEFocus -Document $doc -Element "$($script:split)-slider"
        foreach ($i in 1..3) { $null = Request-Channel 'key' @{ key = 'right' } }
        $ok = Wait-Until { (Invoke-UI4MEDocumentCommand -Document $doc -Operation get_attribute -Parameters @{ element = $script:split; name = 'style' }).value -eq '--u4-split:33%' } 5
        Write-Check 'split.keyboard_resizes' $ok (Invoke-UI4MEDocumentCommand -Document $doc -Operation get_attribute -Parameters @{ element = $script:split; name = 'style' }).value
        # 5. Tooltip appears on keyboard focus (focus-within) and is linked for assistive technology.
        $tipText = "$($script:tip)-text"
        $before = (Get-UI4MEComputedStyle -Document $doc -Element $tipText -Properties visibility).properties.visibility.value
        Set-UI4MEFocus -Document $doc -Element $script:copy
        $null = Wait-UI4MEUi -Milliseconds 300
        $after = (Get-UI4MEComputedStyle -Document $doc -Element $tipText -Properties visibility).properties.visibility.value
        Write-Check 'tooltip.focus_within_shows' ($before -eq 'hidden' -and $after -eq 'visible') "$before -> $after"
        # 6. Copy button -> native clipboard (read back through Core).
        Invoke-Click $Title $script:copy
        $ok = Wait-Until { (Get-UI4MEClipboard -Application $ctx.App) -eq 'Sample PS ✓ text' } 5
        Write-Check 'copy_button.clipboard_roundtrip' $ok (Get-UI4MEClipboard -Application $ctx.App)
        # 7. User-supplied text is never markup: bound text and log lines stay literal.
        $st.Label.Set($script:Hostile)
        $shown = Get-UI4MEDocumentText -Document $doc -Element $script:userText
        foreach ($n in 1..5) { Add-UI4MELogLine -Element $script:logView -Text "line $n $($script:Hostile)" }
        $logText = Get-UI4MEDocumentText -Document $doc -Element $script:logView
        $lines = ([regex]::Matches($logText, 'line \d')).Count
        $bold = @((Find-UI4MEElement -Document $doc -Selector 'b').ids).Count
        Write-Check 'escaping.user_text_literal' ($shown -eq $script:Hostile -and $bold -eq 0) "$shown / <b> elements: $bold"
        Write-Check 'log.bounded_and_literal' ($lines -eq 3 -and $logText -like "*line 5 $($script:Hostile)*" -and $logText -notlike '*line 2 *') "$lines lines: $logText"
        # 8. Colour scheme switch: transitions suspended during the switch, colours change, class removed.
        $c1 = (Get-UI4MEComputedStyle -Document $doc -Element $script:more -Properties color).properties.color.value
        Set-UI4MEUiTheme -ColorScheme dark
        $switching = @((Find-UI4MEElement -Document $doc -Selector '#u4ps-main.u4-theme-switching').ids).Count
        $null = Wait-UI4MEUi -Milliseconds 600
        $after = @((Find-UI4MEElement -Document $doc -Selector '#u4ps-main.u4-theme-switching').ids).Count
        $dark = (Get-UI4MEComputedStyle -Document $doc -Element $script:userText -Properties color).properties.color.value
        Set-UI4MEUiTheme -ColorScheme light
        $null = Wait-UI4MEUi -Milliseconds 600
        $light = (Get-UI4MEComputedStyle -Document $doc -Element $script:userText -Properties color).properties.color.value
        Write-Check 'theme.scheme_switch' ($switching -eq 1 -and $after -eq 0 -and $dark -ne $light) "switching=$switching after=$after dark=$dark light=$light first=$c1"
        # 9. Timers stop with their owner content.
        $st.Ticker.Set($true)
        $null = Wait-Until { $script:log -contains 'tick' }
        $st.Ticker.Set($false)
        $ticks = @($script:log | Where-Object { $_ -eq 'tick' }).Count
        $null = Wait-UI4MEUi -Milliseconds 800
        $diag = Get-UI4MEUiDiagnostics
        Write-Check 'timer.owner_dispose_stops' (@($script:log | Where-Object { $_ -eq 'tick' }).Count -le $ticks + 1) ($diag | ConvertTo-Json -Compress)
        Write-Check 'no.errors' ($diag.Errors -eq 0) $diag.LastError
        $null = Send-ChannelRequest 'native-close' @{ window = $Title }
    } catch {
        Write-ChannelFatal ("$_`n" + $_.ScriptStackTrace)
        Write-ChannelDone
        Stop-UI4MEUiApp
    }
}
