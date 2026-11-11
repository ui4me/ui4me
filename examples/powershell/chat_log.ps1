# Core-only chat and log demo (UI4ME 0.3). Uses only the public Ui4me module.
# Enter sends, Shift+Enter adds a line. Drag to select text, then Ctrl+C or "Copy selection".
# -StatePath rewrites a small JSON file after user-visible changes (for automated desktop journeys).
param(
    [ValidateSet('native', 'headless')][string] $Backend = 'native',
    [string] $StatePath,
    [double] $Seconds = 0
)
if (-not (Get-Module Ui4me)) { Import-Module Ui4me -ErrorAction Stop }
$page = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../foundation/chat.html'))
if ($StatePath) { $StatePath = [IO.Path]::GetFullPath($StatePath) }
Invoke-Ui4meApp -Backend $Backend -ArgumentList @($page, $StatePath, $Seconds) {
    param($app, $page, $statePath, $seconds)
    $logKeep = 400
    $reply = ('Streaming reply {n}: UI4ME Core appends each token with AppendText, keeps the ' +
        'conversation at its end unless you scroll away, and leaves your draft, focus and ' +
        'selection alone while it updates. Příliš žluťoučký kůň úpěl ďábelské ódy.').Split(' ')
    $state = @{ sent = [Collections.Generic.List[string]]::new(); copied = $null; lines = 0; replies = 0
        paused = $false; closed = $false; resized = [Collections.Generic.List[object]]::new(); keydowns = 0 }
    $stream = @{ tokens = [Collections.Generic.Queue[string]]::new(); target = $null; count = 0 }
    $window = $app.OpenFile($page, 'UI4ME chat demo', 1000, 700)
    $window.SetScrollFollow('msgs', $true)
    $window.SetScrollFollow('log', $true)
    $window.SetDefaultAction('composer', 'keydown', $true, 'Enter', $false)

    # Helpers are closures; event handlers are captured by the binding when registered.
    $save = {
        if (-not $statePath -or $window.IsClosed) { return }
        $rects = @{}
        foreach ($e in 'compose', 'send', 'copy', 'msgs', 'log', 'search', 'm0') { $rects[$e] = $window.GetRect($e) }
        $snapshot = @{} + $state
        $snapshot.rects = $rects
        $snapshot.compose = $window.GetValue('compose')
        $snapshot.search = $window.GetValue('search')
        $snapshot.selection = $window.GetSelection()
        $snapshot.clipboard = try { $window.GetClipboardText() } catch { "<unavailable: $($_.Exception.Message)>" }
        $snapshot.focus = @($window.Query(':focus'))
        $snapshot.msgs_scroll = $window.GetScroll('msgs')
        $snapshot.log_scroll = $window.GetScroll('log')
        $temporary = "$statePath.tmp"
        [IO.File]::WriteAllText($temporary, ($snapshot | ConvertTo-Json -Depth 5 -Compress), [Text.UTF8Encoding]::new($false))
        Move-Item -Force -LiteralPath $temporary -Destination $statePath
    }.GetNewClosure()
    $send = {
        $text = $window.GetValue('compose').Trim()
        if (-not $text) { return }
        $state.sent.Add($text)
        $n = $state.sent.Count
        $window.SetValue('compose', '')
        $body = ($text -split "`n" | ForEach-Object { [Net.WebUtility]::HtmlEncode($_) }) -join '<br>'
        $stream.count++
        $id = "r$($stream.count)"
        $window.Batch(@(
            @{ op = 'insert_html'; element = 'msgs'; position = 'beforeend'; html = "<p class=""msg me"" id=""u$n""><b>you</b>$body</p><p class=""msg"" id=""$id""><b>assistant</b></p>" },
            @{ op = 'trim_children'; element = 'msgs'; keep = 200 }
        ))
        $stream.tokens.Clear()
        foreach ($t in $reply) { $stream.tokens.Enqueue($t.Replace('{n}', [string]$n)) }
        $stream.target = $id
        $window.SetText('status', "Sent message $n.")
        & $save
    }.GetNewClosure()

    $null = $window.On('keydown', {
        param($e)
        $state.keydowns++
        if ($e.Key -eq 'Enter' -and $e.DefaultPrevented) { & $send }
    }, 'compose')
    $null = $window.On('click', { & $send }, 'send')
    $null = $window.On('click', {
        $state.copied = $window.CopySelection()
        $window.SetText('status', $(if ($state.copied) { "Copied $($state.copied.Length) characters." } else { 'Nothing selected.' }))
        & $save
    }, 'copy')
    $null = $window.On('click', {
        $state.paused = -not $state.paused
        $window.SetText('pause', $(if ($state.paused) { 'Resume stream' } else { 'Pause stream' }))
        & $save
    }, 'pause')
    $null = $window.On('click', { $app.Stop() }, 'quit')
    $null = $window.On('keyup', { & $save })
    $null = $window.On('mouseup', { & $save })
    $null = $app.On('resized', { param($e) $state.resized.Add(@($e.Width, $e.Height)); & $save })
    $null = $app.On('closed', { $state.closed = $true; $app.Stop() })
    $null = $app.On('started', { & $save })
    $null = $app.Timer(40, {
        if ($state.paused -or $window.IsClosed) { return }
        $state.lines++
        $i = $state.lines
        $query = $window.GetValue('search').Trim()
        $text = '{0:D5} worker-{1} processed item {2} ✓' -f $i, ($i % 7), ($i * 37 % 1000)
        $class = if ($query -and $text.Contains($query)) { ' class="hit"' } else { '' }
        $window.Batch(@(
            @{ op = 'insert_html'; element = 'log'; position = 'beforeend'; html = "<div$class>$([Net.WebUtility]::HtmlEncode($text))</div>" },
            @{ op = 'trim_children'; element = 'log'; keep = $logKeep }
        ))
        if ($stream.tokens.Count -gt 0 -and $window.HasElement($stream.target)) {
            $window.AppendText($stream.target, $stream.tokens.Dequeue() + ' ')
            if ($stream.tokens.Count -eq 0) { $state.replies++ }
        }
        if ($i % 25 -eq 0) { & $save }
    }, $true)
    if ($seconds -gt 0) { $null = $app.Timer([int]($seconds * 1000), { $app.Stop() }, $false) }
    $null = $app.On('stopped', {
        if ($statePath) {
            $final = if (Test-Path -LiteralPath $statePath) { Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json -AsHashtable } else { @{} }
            foreach ($k in 'sent', 'copied', 'lines', 'replies', 'closed', 'resized') { $final[$k] = $state[$k] }
            $final.exited = $true
            [IO.File]::WriteAllText($statePath, ($final | ConvertTo-Json -Depth 5 -Compress), [Text.UTF8Encoding]::new($false))
        }
    })
}
