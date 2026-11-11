# Core-only data viewer (UI4ME 1.0), the PowerShell twin of examples/python/data_viewer.py.
# 20 000 generated rows (or -Csv PATH) in a paged table (200 DOM rows), a live filter, sorting by
# clicking a column header, row selection by mouse or keyboard (Up/Down/PageUp/PageDown/Home/End,
# Enter opens the detail window), one detail window per row, background loading/filtering/sorting
# (App.RunInBackground) and an export of the current page to PDF (Window.ExportPdf).
# -StatePath rewrites a small JSON file after visible changes (for tests/native/data_journey.py);
# the state keys match the Python app. The page is built in this file: only the Ui4me module is used.
param([string] $Csv, [int] $Rows = 20000, [string] $StatePath, [string] $ExportDir, [double] $Seconds = 0, [string] $Backend = 'native')
if (-not (Get-Module Ui4me)) { Import-Module Ui4me -ErrorAction Stop }
if ($StatePath) { $StatePath = [IO.Path]::GetFullPath($StatePath) }
if (-not $ExportDir) { $ExportDir = [IO.Path]::GetTempPath() }
if ($Csv) { $Csv = [IO.Path]::GetFullPath($Csv) }
$pageHtml = @'
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>UI4ME data viewer</title>
<style>
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.35 sans-serif; color: #1d2330; background: #f3f5f9; }
header { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; padding: 8px 10px; background: #24324a; color: #fff; }
header h1 { font-size: 15px; margin: 0 auto 0 0; }
#filter { width: 220px; padding: 3px 6px; }
#app { padding: 8px; }
#summary, #status { font-size: 12px; color: #55607a; margin: 2px 2px 6px; }
#head { width: 100%; table-layout: fixed; border-collapse: collapse; background: #dfe5f0; }
#head th { text-align: left; padding: 4px 8px; font-size: 12px; cursor: pointer; border-bottom: 1px solid #b9c3d6; }
#scroller { height: calc(100vh - 190px); min-height: 120px; overflow: auto; background: #fff; border: 1px solid #ccd3df; }
#grid { width: 100%; table-layout: fixed; border-collapse: collapse; }
#grid td { padding: 2px 8px; height: 22px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; border-bottom: 1px solid #eef1f6; }
#grid tr.sel td { background: #cfe0ff; }
.num { text-align: right; }
#pager { display: flex; gap: 8px; align-items: center; margin-top: 6px; }
@media print {
  header, #pager, #head, #status { display: none; }
  #scroller { height: auto; overflow: visible; border: 0; }
  #grid td { height: auto; }
}
</style></head>
<body id="page">
<header>
  <h1>UI4ME data viewer</h1>
  <label>Filter <input id="filter" placeholder="type to filter rows"></label>
  <button id="detail">Details</button>
  <button id="export">Export PDF</button>
  <button id="copy">Copy selection</button>
</header>
<div id="app">
  <div id="summary">Loading...</div>
  <table id="head"><colgroup><col style="width:12%"><col style="width:30%"><col style="width:22%"><col style="width:18%"><col style="width:18%"></colgroup>
  <tr><th id="h-0">id</th><th id="h-1">name</th><th id="h-2">city</th><th id="h-3">amount</th><th id="h-4">score</th></tr></table>
  <div id="scroller" tabindex="0"><table id="grid"><colgroup><col style="width:12%"><col style="width:30%"><col style="width:22%"><col style="width:18%"><col style="width:18%"></colgroup><tbody id="rows"></tbody></table></div>
  <div id="pager"><button id="prev">Prev</button><span id="pageinfo">-</span><button id="next">Next</button></div>
  <div id="status">Ready.</div>
</div>
</body></html>
'@
$detailHtml = @'
<!doctype html><html><head><meta charset="utf-8"><style>
body { margin: 0; padding: 12px; font: 14px/1.4 sans-serif; background: #fff; color: #1d2330; }
h2 { font-size: 16px; margin: 0 0 8px; } dl { margin: 0 0 10px; } dt { font-size: 12px; color: #55607a; } dd { margin: 0 0 6px; }
</style></head><body id="d"><h2 id="dtitle">Row {row}</h2><dl>{fields}</dl><button id="dclose">Close</button></body></html>
'@
Invoke-Ui4meApp -Backend $Backend -ArgumentList @($pageHtml, $detailHtml, $Csv, $Rows, $StatePath, $ExportDir, $Seconds) {
    param($app, $pageHtml, $detailHtml, $csv, $rowCount, $statePath, $exportDir, $seconds)
    $PAGE = 200
    $state = @{ loaded = $false; total = 0; matched = 0; filter = ''; sort = @{ col = -1; desc = $false }; page = 0; pages = 0
        dom_rows = 0; selected = $null; details_open = @(); details_opened = 0; details_closed = 0
        exports = [Collections.Generic.List[object]]::new(); resized = [Collections.Generic.List[object]]::new(); closed = $false
        errors = [Collections.Generic.List[object]]::new(); tasks = 0; summary = ''; keydowns = 0; copied = $null }
    $data = @{ columns = @('id', 'name', 'city', 'amount', 'score'); rows = @(); view = [int[]]@(); generation = 0 }
    $details = @{}
    $window = $app.Open($pageHtml, 'UI4ME data viewer', 1000, 700)

    $rect = { param($e) try { $window.GetRect($e) } catch { $null } }.GetNewClosure()
    $save = {
        if (-not $statePath -or $window.IsClosed) { return }
        $snapshot = @{} + $state
        $snapshot.details_open = @($details.Keys | Sort-Object)
        $rects = @{}
        foreach ($n in 'page', 'filter', 'export', 'copy', 'detail', 'scroller', 'rows', 'prev', 'next', 'h-0', 'h-1', 'h-2', 'h-3', 'h-4', 'summary') { $rects[$n] = & $rect $n }
        $snapshot.rects = $rects
        $ids = @($window.Query('#rows tr', 210))
        $snapshot.dom_rows = $ids.Count
        $snapshot.row_ids = @($ids | Select-Object -First 3) + @($ids | Select-Object -Last 2)
        $snapshot.row_rects = @($ids | Select-Object -First 6 | ForEach-Object { & $rect $_ })
        $snapshot.selected_rect = if ($null -ne $state.selected) { & $rect "r$($state.selected)" } else { $null }
        $snapshot.filter_value = $window.GetValue('filter')
        $snapshot.scroll = $window.GetScroll('scroller')
        $snapshot.selection = $window.GetSelection()
        $snapshot.clipboard = try { $window.GetClipboardText() } catch { "<unavailable: $($_.Exception.Message)>" }
        $snapshot.focus = @($window.Query(':focus'))
        [IO.File]::WriteAllText("$statePath.tmp", ($snapshot | ConvertTo-Json -Depth 6 -Compress), [Text.UTF8Encoding]::new($false))
        # Windows refuses to replace a file another process is reading: retry briefly, else skip.
        foreach ($attempt in 1..20) {
            try { Move-Item -Force -LiteralPath "$statePath.tmp" -Destination $statePath -ErrorAction Stop; break }
            catch [System.IO.IOException], [System.UnauthorizedAccessException] { Start-Sleep -Milliseconds (10 * $attempt) }
        }
    }.GetNewClosure()
    $status = { param($text) $window.SetText('status', $text) }.GetNewClosure()
    $cell = { param($v) if ($v -is [double]) { $v.ToString('F2', [Globalization.CultureInfo]::InvariantCulture) } else { [string]$v } }.GetNewClosure()

    $renderPage = {
        $view = $data.view
        $pages = [Math]::Max(1, [int][Math]::Ceiling($view.Count / $PAGE))
        $state.page = [Math]::Min($state.page, $pages - 1)
        $state.pages = $pages
        $start = $state.page * $PAGE
        $sb = [Text.StringBuilder]::new()
        for ($k = $start; $k -lt [Math]::Min($view.Count, $start + $PAGE); $k++) {
            $i = $view[$k]
            $r = $data.rows[$i]
            $cls = if ($i -eq $state.selected) { ' class="sel"' } else { '' }
            $null = $sb.Append("<tr id=""r$i""$cls>")
            foreach ($v in $r) {
                $text = [Net.WebUtility]::HtmlEncode((& $cell $v))
                if ($v -is [double] -or $v -is [int] -or $v -is [long]) { $null = $sb.Append("<td class=""num"">$text</td>") } else { $null = $sb.Append("<td>$text</td>") }
            }
            $null = $sb.Append('</tr>')
        }
        $window.ReplaceChildrenHtml('rows', $sb.ToString())
        $window.SetText('pageinfo', "Page $($state.page + 1) / $pages")
        $window.SetText('summary', $state.summary)
    }.GetNewClosure()

    # Closures are created at this level only: a closure made inside another closure loses the outer
    # variables. Per-request values travel in $request and in the work's result.
    $request = @{ reset = $true }
    $work = {
        param($rows, $query, $col, $desc, $generation)
        $needle = $query.ToLowerInvariant()
        $keep = [Collections.Generic.List[int]]::new()
        for ($i = 0; $i -lt $rows.Count; $i++) {
            if ($needle -eq '') { $keep.Add($i); continue }
            if ((($rows[$i] -join ' ').ToLowerInvariant()).Contains($needle)) { $keep.Add($i) }
        }
        $indices = $keep.ToArray()
        if ($col -ge 0 -and $indices.Count -gt 1) {
            if ($col -eq 0 -or $col -eq 3 -or $col -eq 4) {
                $keys = [double[]]::new($indices.Count)
                for ($k = 0; $k -lt $indices.Count; $k++) { $keys[$k] = [double]$rows[$indices[$k]][$col] }
            }
            else {
                $keys = [string[]]::new($indices.Count)
                for ($k = 0; $k -lt $indices.Count; $k++) { $keys[$k] = ([string]$rows[$indices[$k]][$col]).ToLowerInvariant() }
            }
            [Array]::Sort($keys, $indices)
            if ($desc) { [Array]::Reverse($indices) }
        }
        $sum = 0.0
        foreach ($i in $indices) { $sum += [double]$rows[$i][3] }
        @{ indices = $indices; sum = $sum; count = $indices.Count; generation = $generation; col = $col; desc = $desc }
    }
    $done = {
        param($result)
        if ($result.generation -ne $data.generation -or $window.IsClosed) { return }
        try {
            $data.view = [int[]]$result.indices
            $state.matched = $result.count
            $state.tasks++
            $text = "$($result.count) of $($state.total) rows"
            if ($result.count -gt 0) { $text += (' - total {0:N2}, average {1:N2}' -f $result.sum, ($result.sum / $result.count)) }
            $state.summary = $text
            if ($request.reset) { $state.page = 0 }
            & $renderPage
            for ($p = 0; $p -lt 5; $p++) {
                $mark = if ($p -eq $result.col) { if ($result.desc) { [string][char]0x25BC } else { [string][char]0x25B2 } } else { '' }
                $window.SetText("h-$p", ("$($data.columns[$p]) $mark").Trim())
            }
            & $status "Showing $($result.count) rows."
            & $save
        }
        catch { $state.errors.Add("refresh: $($_ | Out-String)"); & $save }
    }.GetNewClosure()
    $failed = { param($err) $state.errors.Add("$err"); & $status "Error: $err"; & $save }.GetNewClosure()
    $refresh = {
        param([bool] $resetPage)
        $data.generation++
        $request.reset = $resetPage
        $null = $app.RunInBackground($work, $done, $failed, @(, $data.rows) + @($state.filter, $state.sort.col, $state.sort.desc, $data.generation))
    }.GetNewClosure()

    $selectPosition = {
        param([int] $position)
        $view = $data.view
        if ($view.Count -eq 0) { return }
        $position = [Math]::Max(0, [Math]::Min($view.Count - 1, $position))
        $old = $state.selected
        $state.selected = $view[$position]
        $newPage = [int][Math]::Floor($position / $PAGE)
        if ($newPage -ne $state.page) { $state.page = $newPage; & $renderPage }
        else {
            if ($null -ne $old -and $window.HasElement("r$old")) { $window.RemoveClass("r$old", 'sel') }
            $window.AddClass("r$($state.selected)", 'sel')
        }
        $window.ScrollIntoView("r$($state.selected)", 'nearest')
        & $status "Selected row $($state.selected) (position $($position + 1) of $($view.Count))."
        & $save
    }.GetNewClosure()
    $selectedPosition = { if ($null -eq $state.selected) { -1 } else { [Array]::IndexOf($data.view, [int]$state.selected) } }.GetNewClosure()

    $openDetail = {
        $index = $state.selected
        if ($null -eq $index) { & $status 'Select a row first.'; & $save; return }
        $existing = $details[[int]$index]
        if ($existing -and -not $existing.IsClosed) { $null = $existing.Activate(); return }
        $row = $data.rows[$index]
        $fields = for ($n = 0; $n -lt $row.Count; $n++) { "<dt>$([Net.WebUtility]::HtmlEncode([string]$data.columns[$n]))</dt><dd id=""f$n"">$([Net.WebUtility]::HtmlEncode((& $cell $row[$n])))</dd>" }
        $html = $detailHtml.Replace('{row}', "$index").Replace('{fields}', ($fields -join ''))
        $details[[int]$index] = $app.Open($html, "UI4ME row $index", 360, 300)
        $state.details_opened++
        & $save
    }.GetNewClosure()

    $export = {
        $path = Join-Path $exportDir ("data-view-{0}.pdf" -f ($state.exports.Count + 1))
        try {
            $result = $window.ExportPdf($path, 'A4', 150, 'UI4ME data viewer') | ConvertFrom-Json
            $state.exports.Add(@{ path = $path; pages = $result.pages; bytes = (Get-Item -LiteralPath $path).Length })
            & $status "Exported $($result.pages) page(s) to $([IO.Path]::GetFileName($path))."
        }
        catch { $state.errors.Add("export: $($_.Exception.Message)"); & $status "Export failed: $($_.Exception.Message)" }
        & $save
    }.GetNewClosure()

    $sortBy = {
        param([int] $col)
        $cur = $state.sort
        $state.sort = @{ col = $col; desc = if ($cur.col -eq $col) { -not $cur.desc } else { $false } }
        & $refresh $true
    }.GetNewClosure()

    $null = $app.On('click', {
        param($e)
        $element = $e.Element
        if ($e.Window -ne $window.Id) {
            if ($element -eq 'dclose') { foreach ($d in @($details.Values)) { if ($d.Id -eq $e.Window) { $d.Close() } } }
            return
        }
        if ($element -match '^r(\d+)$') {
            $index = [int]$Matches[1]
            $position = [Array]::IndexOf($data.view, $index)
            if ($position -ge 0) { & $selectPosition $position }
            $window.Focus('scroller')
        }
        elseif ($element -match '^h-(\d)$') { & $sortBy ([int]$Matches[1]) }
        elseif ($element -eq 'next') { $state.page = [Math]::Min($state.pages - 1, $state.page + 1); & $renderPage; & $save }
        elseif ($element -eq 'prev') { $state.page = [Math]::Max(0, $state.page - 1); & $renderPage; & $save }
        elseif ($element -eq 'detail') { & $openDetail }
        elseif ($element -eq 'export') { & $export }
        elseif ($element -eq 'copy') {
            $state.copied = $window.CopySelection()
            & $status $(if ($state.copied) { "Copied $($state.copied.Length) characters." } else { 'Nothing selected.' })
            & $save
        }
    }.GetNewClosure())
    $null = $app.On('keydown', {
        param($e)
        if ($e.Window -eq $window.Id) {
            $state.keydowns++
            $position = & $selectedPosition
            switch ($e.Key) {
                'ArrowDown' { & $selectPosition ($position + 1) }
                'ArrowUp' { & $selectPosition $(if ($position -ge 0) { [Math]::Max(0, $position - 1) } else { 0 }) }
                'PageDown' { & $selectPosition ($position + 10) }
                'PageUp' { & $selectPosition ([Math]::Max(0, $position - 10)) }
                'Home' { if ($e.Element -ne 'filter') { & $selectPosition 0 } }
                'End' { if ($e.Element -ne 'filter') { & $selectPosition ($data.view.Count - 1) } }
                'Enter' { & $openDetail }
                'Escape' { if ($window.GetValue('filter')) { $window.SetValue('filter', ''); $state.filter = ''; & $refresh $true } }
            }
        }
        elseif ($e.Key -eq 'Escape') { foreach ($d in @($details.Values)) { if ($d.Id -eq $e.Window) { $d.Close() } } }
    }.GetNewClosure())
    $null = $app.On('input', {
        param($e)
        if ($e.Window -eq $window.Id -and $e.Element -eq 'filter') { $state.filter = $window.GetValue('filter'); & $refresh $true }
    }.GetNewClosure())
    $null = $app.On('closed', {
        param($e)
        if ($e.Window -eq $window.Id) {
            $state.closed = $true
            foreach ($d in @($details.Values)) { if (-not $d.IsClosed) { $d.Close() } }
            $app.Stop()
        }
        else {
            foreach ($k in @($details.Keys)) { if ($details[$k].Id -eq $e.Window) { $details.Remove($k); $state.details_closed++; & $save } }
        }
    }.GetNewClosure())
    $null = $app.On('resized', {
        param($e)
        if ($e.Window -eq $window.Id) {
            $state.resized.Add(@($e.Width, $e.Height))
            if ($state.resized.Count -gt 50) { $state.resized.RemoveAt(0) }
            & $save
        }
    }.GetNewClosure())
    $null = $window.On('mouseup', { & $save }.GetNewClosure())
    $null = $window.On('keyup', { & $save }.GetNewClosure())
    $null = $window.On('scroll', { & $save }.GetNewClosure(), 'scroller')
    $null = $app.On('started', { & $save }.GetNewClosure())
    if ($seconds -gt 0) { $null = $app.Timer([int]($seconds * 1000), { $app.Stop() }.GetNewClosure(), $false) }
    $null = $app.On('stopped', {
        if ($statePath) {
            $final = if (Test-Path -LiteralPath $statePath) { Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json -AsHashtable } else { @{} }
            foreach ($k in 'closed', 'details_opened', 'details_closed', 'exports', 'errors', 'total') { $final[$k] = $state[$k] }
            $final.exited = $true
            [IO.File]::WriteAllText($statePath, ($final | ConvertTo-Json -Depth 6 -Compress), [Text.UTF8Encoding]::new($false))
        }
    }.GetNewClosure())

    & $status 'Loading rows in the background...'
    $loadWork = {
        param($csv, $count)
        $list = [Collections.Generic.List[object]]::new()
        if ($csv) {
            $lines = [IO.File]::ReadAllLines($csv)
            foreach ($row in ($lines | Select-Object -Skip 1 -First 200000 | ConvertFrom-Csv -Header c1, c2, c3, c4, c5)) {
                $list.Add(@([long]$row.c1, [string]$row.c2, [string]$row.c3, [double]$row.c4, [long]$row.c5))
            }
        }
        else {
            $cities = 'Praha', 'Brno', 'Ostrava', ([string][char]0x50 + 'lze' + [char]0x148), 'Liberec', 'Olomouc', 'Hradec', 'Pardubice', 'Zlin', 'Jihlava', 'Tabor', 'Kladno'
            for ($i = 0; $i -lt $count; $i++) {
                $list.Add(@([long]$i, ('Name {0:D5}' -f $i), $cities[$i % $cities.Count], ([double](($i * 7919) % 100000) / 100.0), [long](($i * 31) % 101)))
            }
        }
        , $list.ToArray()
    }
    $null = $app.RunInBackground($loadWork, {
        param($rows)
        try {
            $data.rows = $rows
            $state.loaded = $true
            $state.total = $rows.Count
            & $refresh $true
        }
        catch { $state.errors.Add("load: $($_ | Out-String)"); & $save }
    }.GetNewClosure(), { param($err) $state.errors.Add("$err"); & $status "Load failed: $err"; & $save }.GetNewClosure(), @($csv, $rowCount))
}
