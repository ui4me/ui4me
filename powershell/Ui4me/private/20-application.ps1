# -------------------------------------------------------------------------- application --

function Invoke-UI4MEApp {
    <#
    .SYNOPSIS
    Builds one native window from UI4ME components and runs it until the host shuts down.
    .DESCRIPTION
    Run this function directly from a normal app.ps1, using pwsh -File app.ps1
    (or powershell.exe -File app.ps1 on Windows). UI4ME.Core 1.0.1 automatically
    launches the native host and supervised PowerShell backend.
    The -Content block is dot-sourced, so variables it defines
    (states, helper scriptblocks) remain visible to event callbacks without .GetNewClosure().
    Callbacks, timers and task completions all run on this runspace, one at a time.
    .PARAMETER OnCloseRequest
    Runs when the user asks to close the window; return $false to keep it open.
    .PARAMETER OnReady
    Runs once after the window is shown (for example to start loading data).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][scriptblock]$Content,
          [string]$Title = 'UI4ME', [ValidateRange(120, 16384)][int]$Width = 960, [ValidateRange(120, 16384)][int]$Height = 680,
          [ValidateSet('light', 'dark', 'system')][string]$Theme = 'system',
          [string]$Css, [string]$Assets,
          [scriptblock]$OnReady, [scriptblock]$OnCloseRequest, [scriptblock]$OnClose, [scriptblock]$OnError,
          [string]$AppId)
    if ($script:UiBuilder) { throw 'Nested UI4ME applications are not supported.' }
    if ($AppId) {
        # Only a caller-supplied id goes to Core, so only it must be a dotted identity.
        if ($AppId.Length -gt 128 -or $AppId -cnotmatch '^[A-Za-z][A-Za-z0-9_-]*(\.[A-Za-z][A-Za-z0-9_-]*)+$') { throw 'AppId may contain only letters, digits, dots, hyphens and underscores' }
        $resolvedAppId = $AppId
    } else {
        # Derived id names the settings folder only (same rule as Python's _derived_app_id).
        $resolvedAppId = Get-UiDerivedAppId $Title
        if ($resolvedAppId -cnotmatch '^[A-Za-z][A-Za-z0-9_.-]{0,127}$') { throw "Cannot derive a settings id from title '$Title'; pass -AppId" }
    }
    Import-Module UI4ME.Core -ErrorAction Stop
    if ($Assets -and -not (Test-Path -LiteralPath $Assets -PathType Container)) { throw "Assets folder not found: $Assets" }
    # Delegate script startup and native host supervision to UI4ME.Core.
    # The call does not return in the first (launcher) process; in the host's
    # backend it connects and returns the application's Core object.
    $startOptions = @{ Name = $Title }
    if ($AppId) { $startOptions.AppId = $AppId }
    if ($MyInvocation.PSCommandPath) { $startOptions.ScriptPath = $MyInvocation.PSCommandPath }
    $coreApp = Start-UI4MEScript @startOptions
    $ctx = New-UiContext -Title $Title -Theme $Theme -Css $Css -Assets $Assets -OnError $OnError
    $ctx.App = $coreApp
    $ctx | Add-Member -NotePropertyName AppId -NotePropertyValue $resolvedAppId
    $ctx | Add-Member -NotePropertyName Settings -NotePropertyValue $null
    if ($OnCloseRequest) { [void]$ctx.CloseRequest.Add($OnCloseRequest) }
    if ($OnClose) { [void]$ctx.Closed.Add($OnClose) }
    $script:UiBuilder = $ctx
    try {
        Invoke-UiBuild $Content
        $functional = Get-Content -LiteralPath (Join-Path $script:AssetPath 'functional.css') -Raw -Encoding UTF8
        $visual = if ($null -ne $ctx.VisualCss) { [string]$ctx.VisualCss } else {
            Get-Content -LiteralPath (Join-Path $script:AssetPath 'theme.css') -Raw -Encoding UTF8 }
        $html = '<!doctype html><html><head><meta charset="utf-8"><title>' + (ConvertTo-UiHtml $Title) + '</title>' +
                '<style>' + $functional + '</style></head><body class="u4-body">' +
                '<div class="u4-app"><main id="u4ps-main" class="u4-main u4-column u4-gap-md">' +
                $ctx.Root.Markup.ToString() + '</main><div id="u4ps-toasts" class="u4-toasts" aria-live="polite"></div></div></body></html>'
        try {
            $ctx.Window = New-UI4MEWindow -Application $ctx.App -Title $Title -Width $Width -Height $Height
            if ($Assets) { $ctx.Document = Open-UI4MEHtml -Window $ctx.Window -Html $html -AssetRoot $Assets }
            else { $ctx.Document = Open-UI4MEHtml -Window $ctx.Window -Html $html }
            $ctx.ThemeSheet = (Add-UI4MEStylesheet -Document $ctx.Document -Css $visual).sheet
            if ($ctx.Css) { $null = Add-UI4MEStylesheet -Document $ctx.Document -Css $ctx.Css }
            if ($Theme -ne 'system') { $null = Set-UI4MEEnvironment -Document $ctx.Document -ColorScheme $Theme }
            Set-UI4MEBeforeClose -Window $ctx.Window -Callback { Test-UiCloseAllowed }
            Register-UI4MENotification -Application $ctx.App -Method 'window.event' -Callback {
                param($params)
                Invoke-UiWindowEvent $params
            }
            Invoke-UiSetups $ctx.Root.Setups
            $null = Set-UI4MEReady -Application $ctx.App
            $ctx.Running = $true
            if ($env:UI4ME_UI_SMOKE) {
                # Unattended example check: stop after N seconds; errors make the script fail.
                $null = Start-UI4MEUiTimer -Milliseconds ([int]([double]::Parse($env:UI4ME_UI_SMOKE, [System.Globalization.CultureInfo]::InvariantCulture) * 1000)) -Action (New-UiCallable 'Stop-UiSmoke' $ctx)
            }
            if ($OnReady) { Invoke-UiHandler $OnReady @() 'OnReady' }
            Invoke-UiLoop $ctx
            if ($env:UI4ME_UI_SMOKE -and $ctx.ErrorCount) { throw "UI4ME smoke run reported $($ctx.ErrorCount) error(s); last: $($ctx.LastError)" }
        } finally {
            $ctx.Running = $false
            $ctx.Stopping = $true
            Stop-UiTasks $ctx
            if (-not $ctx.Window -or -not $ctx.Window.Closed) { Invoke-UiClosed $ctx }
            if ($ctx.App) { Close-UI4ME -Application $ctx.App }
        }
    } finally {
        $script:UiBuilder = $null
    }
}

function Get-UiDerivedAppId {
    # 'My App' -> org.ui4me.app.my-app; a title without ASCII letters/digits gets a short
    # SHA-256 of its UTF-8 bytes so unrelated apps never share a settings folder.
    param([string]$Title)
    $slug = ($Title.ToLowerInvariant() -creplace '[^a-z0-9]+', '-').Trim('-')
    if ($slug.Length -gt 60) { $slug = $slug.Substring(0, 60) }
    if (-not $slug) {
        $sha = [System.Security.Cryptography.SHA256]::Create()
        try { $hash = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Title)) } finally { $sha.Dispose() }
        $slug = 'app-' + (-join ($hash[0..5] | ForEach-Object { $_.ToString('x2') }))
    }
    return "org.ui4me.app.$slug"
}

function Stop-UiSmoke { param($ctx) if (-not $ctx.App.ShutdownRequested) { $null = Request-UI4MEQuit -Application $ctx.App } }

function Test-UiCloseAllowed {
    $ctx = $script:UiBuilder
    if ($null -eq $ctx) { return $true }
    foreach ($handler in @($ctx.CloseRequest)) {
        try {
            $answer = @(& $handler)
            if ($answer.Count -gt 0 -and $answer[-1] -eq $false) { return $false }
        } catch {
            Write-UiError $_ 'OnCloseRequest'
            return $false  # fail closed: never discard work because a handler failed
        }
    }
    return $true
}

function Invoke-UiWindowEvent {
    param($params)
    $ctx = $script:UiBuilder
    if ($null -eq $ctx -or $null -eq $ctx.Window) { return }
    if ([string]$params.window_id -ne [string]$ctx.Window.Id) { return }
    if ([string]$params.type -eq 'closed') { Invoke-UiClosed $ctx }
}

function Invoke-UiClosed {
    param($ctx)
    $handlers = @($ctx.Closed)
    $ctx.Closed.Clear()
    foreach ($handler in $handlers) { Invoke-UiHandler $handler @() 'OnClose' }
}

function Invoke-UiLoop {
    param($ctx)
    $app = $ctx.App
    while (-not $app.ShutdownRequested -and -not $app.Closed) {
        $wait = Get-UiTimerWait $ctx 50
        try { $null = Wait-UI4ME -Application $app -TimeoutMilliseconds $wait }
        catch [UI4ME.DisconnectedException] {
            if ($app.ShutdownRequested) { break }
            throw
        }
        Invoke-UiTimers $ctx
        Update-UiTasks $ctx
    }
}

function Wait-UI4MEUi {
    <#
    .SYNOPSIS
    Pumps native events, timers and task completions for a while (or until -Until returns true).
    .DESCRIPTION
    Use from -OnReady (or other code outside callbacks) to wait without blocking the window. Inside
    an event, timer or task callback, UI4ME.Core defers further events until the callback returns,
    so a condition that needs user input never becomes true there; split such work into callbacks
    instead. Returns $true when -Until became true, $false on timeout or shutdown.
    #>
    [CmdletBinding()]
    param([ValidateRange(0, 86400000)][int]$Milliseconds = 100, [scriptblock]$Until)
    $ctx = Assert-UiBuilder
    if ($null -eq $ctx.App) { throw 'Wait-UI4MEUi needs a running application.' }
    $deadline = [DateTime]::UtcNow.AddMilliseconds($Milliseconds)
    do {
        if ($Until -and (& $Until)) { return $true }
        if ($ctx.App.ShutdownRequested -or $ctx.App.Closed) { return $false }
        $left = [int][Math]::Max(0, ($deadline - [DateTime]::UtcNow).TotalMilliseconds)
        try { $null = Wait-UI4ME -Application $ctx.App -TimeoutMilliseconds ([Math]::Min($left, (Get-UiTimerWait $ctx 25))) }
        catch [UI4ME.DisconnectedException] { return $false }
        Invoke-UiTimers $ctx
        Update-UiTasks $ctx
    } while ([DateTime]::UtcNow -lt $deadline)
    if ($Until) { return [bool](& $Until) }
    return $false
}

function Stop-UI4MEUiApp {
    <# .SYNOPSIS Requests an orderly quit of the running UI4ME application. #>
    [CmdletBinding()] param()
    $ctx = Assert-UiBuilder
    if ($ctx.App -and -not $ctx.App.ShutdownRequested) { $null = Request-UI4MEQuit -Application $ctx.App }
}

function Get-UI4MEUiContext {
    <# .SYNOPSIS The running app's Core objects (App, Window, Document) for direct UI4ME.Core calls. #>
    [CmdletBinding()] param()
    return (Assert-UiBuilder)
}

function Get-UI4MEUiDiagnostics {
    <# .SYNOPSIS Counters for leaks and load: subscriptions, handlers, bindings, timers, tasks, errors. #>
    [CmdletBinding()] param()
    $ctx = Assert-UiBuilder
    $handlers = 0
    foreach ($type in $ctx.Handlers.Keys) { foreach ($list in $ctx.Handlers[$type].Values) { $handlers += $list.Count } }
    return [pscustomobject]@{
        CoreSubscriptions = $ctx.Subscriptions.Count; Handlers = $handlers
        Bindings = @($ctx.Bindings | Where-Object { $null -eq $_.Owner -or -not $_.Owner.Disposed }).Count
        Timers = @($ctx.Timers | Where-Object { -not $_.Cancelled }).Count
        Tasks = @($ctx.Tasks).Count; Errors = $ctx.ErrorCount; LastError = $ctx.LastError
    }
}
