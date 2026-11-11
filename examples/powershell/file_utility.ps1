# Core-only file utility (UI4ME 0.4). Uses only the public Ui4me module.
# Native open/save/folder dialogs, a text editor, a folder listing, clipboard, a modal settings
# <dialog> with a <select>, a second "Details" window and responsive layout.
# -StatePath rewrites a small JSON file after visible changes (for automated journeys).
param([string] $Start, [string] $StatePath)
if (-not (Get-Module Ui4me)) { Import-Module Ui4me -ErrorAction Stop }
$page = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../foundation/files.html'))
if ($StatePath) { $StatePath = [IO.Path]::GetFullPath($StatePath) }
if ($Start) { $Start = [IO.Path]::GetFullPath($Start) }
Invoke-Ui4meApp -ArgumentList @($page, $Start, $StatePath) {
    param($app, $page, $start, $statePath)
    $state = @{ file = $null; folder = $null; entries = @(); saved = $null; cancelled = 0; copied = $null
        theme = 'light'; details_open = $false; details_closed = 0; resized = [Collections.Generic.List[object]]::new(); closed = $false }
    $details = @{ window = $null }
    $window = $app.OpenFile($page, 'UI4ME file utility', 900, 640)

    $save = {
        if (-not $statePath -or $window.IsClosed) { return }
        $snapshot = @{} + $state
        $rects = @{}
        foreach ($e in 'open', 'save', 'folder', 'copy', 'details', 'settings', 'editor', 'theme', 'prefs-close', 'entries') { $rects[$e] = $window.GetRect($e) }
        $snapshot.rects = $rects
        $snapshot.editor = $window.GetValue('editor')
        $snapshot.focus = @($window.Query(':focus'))
        $snapshot.dialog = $window.GetDialog('prefs')
        $snapshot.layout = if ($window.GetRect('entries').Width -gt 400) { 'column' } else { 'row' }
        $snapshot.clipboard = try { $window.GetClipboardText() } catch { "<unavailable: $($_.Exception.Message)>" }
        [IO.File]::WriteAllText("$statePath.tmp", ($snapshot | ConvertTo-Json -Depth 6 -Compress), [Text.UTF8Encoding]::new($false))
        Move-Item -Force -LiteralPath "$statePath.tmp" -Destination $statePath
    }.GetNewClosure()
    $status = { param($text) $window.SetText('status', $text); & $save }.GetNewClosure()
    $startDir = {
        if ($state.folder) { return $state.folder }
        if ($state.file) { return [IO.Path]::GetDirectoryName($state.file) }
        $start
    }.GetNewClosure()

    $null = $window.On('click', {
        $null = $window.OpenFileDialog({
            param($e)
            if ($null -eq $e.Paths) { $state.cancelled++; & $status $(if ($e.Error) { "Open failed: $($e.Error)" } else { 'Open cancelled.' }); return }
            $path = $e.Paths[0]
            try {
                if ((Get-Item -LiteralPath $path).Length -gt 1MB) { & $status 'That file is larger than 1 MiB.'; return }
                $text = [IO.File]::ReadAllText($path, [Text.UTF8Encoding]::new($false, $true))
            }
            catch { & $status "Cannot open ${path}: $($_.Exception.Message)"; return }
            $state.file = $path
            $window.SetValue('editor', $text)
            $window.SetText('path', $path)
            & $status "Opened $([IO.Path]::GetFileName($path)) ($($text.Length) characters)."
        }, 'Open text file', (& $startDir), @{ Text = @('txt', 'md', 'log') }, $false)
    }, 'open')
    $null = $window.On('click', {
        $name = if ($state.file) { [IO.Path]::GetFileName($state.file) } else { 'untitled.txt' }
        $null = $window.SaveFileDialog({
            param($e)
            if ($null -eq $e.Paths) { $state.cancelled++; & $status 'Save cancelled.'; return }
            $path = $e.Paths[0]
            try { [IO.File]::WriteAllText($path, $window.GetValue('editor'), [Text.UTF8Encoding]::new($false)) }
            catch { & $status "Cannot save: $($_.Exception.Message)"; return }
            $state.saved = $path; $state.file = $path
            $window.SetText('path', $path)
            & $status "Saved $([IO.Path]::GetFileName($path))."
        }, 'Save text file', (& $startDir), $name, $null)
    }, 'save')
    $null = $window.On('click', {
        $null = $window.FolderDialog({
            param($e)
            if ($null -eq $e.Paths) { $state.cancelled++; & $status 'No folder chosen.'; return }
            $folder = $e.Paths[0]
            try { $names = @(Get-ChildItem -LiteralPath $folder -Force | Sort-Object Name | Select-Object -First 500 | ForEach-Object { $_.Name + $(if ($_.PSIsContainer) { '/' } else { '' }) }) }
            catch { & $status "Cannot list ${folder}: $($_.Exception.Message)"; return }
            $state.folder = $folder; $state.entries = $names
            $html = ($names | ForEach-Object { '<li>' + [Net.WebUtility]::HtmlEncode($_) + '</li>' }) -join ''
            $window.ReplaceChildrenHtml('entries', $(if ($html) { $html } else { '<li>(empty)</li>' }))
            & $status "$($names.Count) entries in $([IO.Path]::GetFileName($folder))."
        }, 'Choose folder', (& $startDir))
    }, 'folder')
    $null = $window.On('click', {
        $text = if ($state.file) { $state.file } else { '' }
        $window.SetClipboardText($text)
        $state.copied = $text
        & $status $(if ($text) { 'Copied path.' } else { 'No file path to copy.' })
    }, 'copy')
    $null = $window.On('click', {
        if ($details.window -and -not $details.window.IsClosed) { $null = $details.window.Activate(); return }
        $info = if ($state.file) { $state.file } else { 'No file open' }
        $w = $app.Open("<h3>Details</h3><p id=""info"">$([Net.WebUtility]::HtmlEncode($info))</p><button id=""close"">Close</button>", 'UI4ME file details', 420, 220)
        $null = $w.On('click', { $w.Close() }.GetNewClosure(), 'close')
        $details.window = $w
        $state.details_open = $true
        & $save
    }, 'details')
    $null = $window.On('click', { $window.ShowDialog('prefs', $true); & $save }, 'settings')
    $null = $window.On('click', { $window.CloseDialog('prefs', 'closed') }, 'prefs-close')
    $null = $window.On('close', { & $save }, 'prefs')
    $null = $window.On('commit', {
        param($e)
        $state.theme = $e.Value
        if ($state.theme -eq 'dark') { $window.AddClass('page', 'dark') } else { $window.RemoveClass('page', 'dark') }
        & $save
    }, 'theme')
    $null = $window.On('keyup', { & $save })
    $null = $window.On('mouseup', { & $save })
    $null = $app.On('resized', { param($e) $state.resized.Add(@($e.Width, $e.Height)); & $save })
    $null = $app.On('closed', {
        param($e)
        if ($details.window -and $e.Window -eq $details.window.Id) {
            $state.details_open = $false; $state.details_closed++; $details.window = $null; & $save
        }
        elseif ($e.Window -eq $window.Id) { $state.closed = $true; $app.Stop() }
    })
    $null = $app.On('started', { & $save })
    $null = $app.On('stopped', {
        if ($statePath) {
            $final = if (Test-Path -LiteralPath $statePath) { Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json -AsHashtable } else { @{} }
            foreach ($k in 'file', 'saved', 'closed', 'details_closed', 'theme') { $final[$k] = $state[$k] }
            $final.exited = $true
            [IO.File]::WriteAllText($statePath, ($final | ConvertTo-Json -Depth 6 -Compress), [Text.UTF8Encoding]::new($false))
        }
    })
}
