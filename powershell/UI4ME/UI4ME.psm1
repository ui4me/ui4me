# UI4ME 2.0 component layer for PowerShell on UI4ME.Core 1.x.
# Pure PowerShell (5.1 and 7.2+): no compiled assembly, no Python, no second native host.
# Every native operation goes through documented UI4ME.Core commands.
Set-StrictMode -Version 2.0

$script:UiBuilder = $null
$script:AssetPath = Join-Path $PSScriptRoot 'assets'
$script:BlockedTags = @('script', 'style', 'iframe', 'object', 'embed')

# ------------------------------------------------------------------------------ helpers --

function ConvertTo-UiHtml {
    param([AllowNull()][object] $Value)
    if ($null -eq $Value) { return '' }
    return [System.Net.WebUtility]::HtmlEncode([string] $Value)
}

function Assert-UiBuilder {
    if ($null -eq $script:UiBuilder) {
        throw 'UI4ME components must be created inside Invoke-UI4MEApp -Content { ... } (or one of its callbacks).'
    }
    return $script:UiBuilder
}

function New-UiId {
    param([string]$Prefix = 'u')
    $ctx = Assert-UiBuilder
    $ctx.Sequence = [int]$ctx.Sequence + 1
    return ('u4ps-{0}-{1}' -f $Prefix, $ctx.Sequence)
}

function Add-UiMarkup {
    param([string]$Markup)
    $ctx = Assert-UiBuilder
    [void]$ctx.Target.Markup.Append($Markup)
}

function Add-UiSetup {
    # Runs once the element exists in the live document (immediately for runtime content).
    param($Initializer)
    $ctx = Assert-UiBuilder
    [void]$ctx.Target.Setups.Add($Initializer)
}

function Get-UiClassAttr {
    param([string]$Base, [string]$Extra)
    return ('class="{0}"' -f (ConvertTo-UiHtml ((@($Base, $Extra) | Where-Object { $_ }) -join ' ')))
}

function Test-UiState {
    param([AllowNull()][object]$Value)
    return ($null -ne $Value -and $Value.PSObject.TypeNames -contains 'UI4ME.UiState')
}

function Get-UiValue {
    # A plain value, or the current value of a state/computed.
    param([AllowNull()][object]$Value)
    if (Test-UiState $Value) { return $Value.Value }
    return $Value
}

function Invoke-UiBuild {
    # Dot-source a build block so variables it defines stay visible to later callbacks.
    param([scriptblock]$Content)
    if ($null -ne $Content) { $null = . $Content }
}

function Invoke-UiContainer {
    param([string]$Tag, [string]$Class, [string]$Style, [scriptblock]$Content, [AllowNull()][object]$Visible,
          [hashtable]$Attributes, [string]$Prefix)
    if ($Tag -notmatch '^[a-z][a-z0-9-]*$' -or $script:BlockedTags -contains $Tag) { throw "Invalid container tag '$Tag'" }
    $id = New-UiId 'box'
    $attrs = ''
    if ($Attributes) {
        foreach ($key in $Attributes.Keys) {
            if ($key -notmatch '^[a-zA-Z_:][-a-zA-Z0-9_:.]*$' -or $key -match '^on') { throw "Invalid attribute '$key'" }
            $attrs += (' {0}="{1}"' -f $key, (ConvertTo-UiHtml $Attributes[$key]))
        }
    }
    $styleAttr = if ($Style) { ' style="{0}"' -f (ConvertTo-UiHtml $Style) } else { '' }
    Add-UiMarkup ('<{0} id="{1}" {2}{3}{4}{5}>' -f $Tag, $id, (Get-UiClassAttr '' $Class), $styleAttr, $attrs,
                  (Get-UiHiddenAttr $Visible))
    if ($Prefix) { Add-UiMarkup $Prefix }
    try { Invoke-UiBuild $Content }
    finally { Add-UiMarkup "</$Tag>" }
    Register-UiVisibility $id $Visible
    return $id
}

function Get-UiHiddenAttr {
    param([AllowNull()][object]$Visible)
    if ($null -eq $Visible) { return '' }
    if ([bool](Get-UiValue $Visible)) { return '' }
    return ' hidden'
}

function Register-UiVisibility {
    param([string]$Id, [AllowNull()][object]$Visible)
    if (-not (Test-UiState $Visible)) { return }
    $null = Register-UiBinding $Visible $Id 'Set-UiHiddenBinding' 
}

# --------------------------------------------------------------- context and events --

function New-UiContext {
    param([string]$Title, [string]$Theme, [string]$Css, [string]$Assets, [scriptblock]$OnError)
    $root = [pscustomobject]@{ Markup = (New-Object System.Text.StringBuilder); Setups = (New-Object System.Collections.ArrayList) }
    return [pscustomobject]@{
        App = $null; Window = $null; Document = $null; Title = $Title
        Sequence = 0; Target = $root; Root = $root
        Handlers = @{}; Subscriptions = @{}; Bindings = (New-Object System.Collections.ArrayList)
        Timers = (New-Object System.Collections.ArrayList); Tasks = (New-Object System.Collections.ArrayList)
        ThemeSheet = $null; VisualCss = $null; Css = $Css; Theme = $Theme; Assets = $Assets
        CloseRequest = (New-Object System.Collections.ArrayList); Closed = (New-Object System.Collections.ArrayList)
        OnError = $OnError; ErrorCount = 0; LastError = $null; Running = $false; Stopping = $false
        Owners = @{}; CurrentOwner = $null
    }
}

function Write-UiError {
    param($ErrorRecord, [string]$Context)
    $ctx = $script:UiBuilder
    if ($null -eq $ctx) { Write-Warning "UI4ME: $Context failed: $ErrorRecord"; return }
    $ctx.ErrorCount = [int]$ctx.ErrorCount + 1
    $ctx.LastError = "$Context`: $ErrorRecord"
    if ($ctx.OnError) {
        try { $null = & $ctx.OnError $ErrorRecord $Context } catch { Write-Warning "UI4ME: OnError handler failed: $_" }
        return
    }
    [Console]::Error.WriteLine("UI4ME: error in $Context`: $ErrorRecord")
    if ($ctx.Document -and -not $ctx.Stopping) {
        try { Show-UI4MEUiToast -Text "$Context`: $($ErrorRecord.Exception.Message)" -Tone danger -Seconds 8 } catch { }
    }
}

function Invoke-UiHandler {
    param($Handler, [object[]]$Arguments, [string]$Context)
    try {
        $null = Invoke-UiCallable $Handler $Arguments
    } catch {
        Write-UiError $_ $Context
    }
}

function New-UiCallable {
    # Internal callback: a module function name plus captured data. Unlike .GetNewClosure()
    # blocks, these keep access to module-private functions and state.
    param([string]$Fn, $Data)
    return [pscustomobject]@{ Fn = $Fn; Data = $Data }
}

function Invoke-UiCallable {
    param($Callable, [object[]]$Arguments = @())
    if ($Callable -is [scriptblock]) { return (& $Callable @Arguments) }
    return (& $Callable.Fn $Callable.Data @Arguments)
}

function Register-UiHandler {
    # Delegated routing: one Core subscription per event type, dispatched along the event path.
    param([string]$Element, [string]$Type, $Handler)
    $ctx = Assert-UiBuilder
    if (-not $ctx.Handlers.ContainsKey($Type)) { $ctx.Handlers[$Type] = @{} }
    $byElement = $ctx.Handlers[$Type]
    if (-not $byElement.ContainsKey($Element)) { $byElement[$Element] = New-Object System.Collections.ArrayList }
    $entry = [pscustomobject]@{ Element = $Element; Type = $Type; Handler = $Handler; Owner = $ctx.CurrentOwner }
    [void]$byElement[$Element].Add($entry)
    if ($null -ne $ctx.CurrentOwner) { [void]$ctx.CurrentOwner.Handlers.Add($entry) }
    if ($null -ne $ctx.Document) { Initialize-UiSubscription $Type }
    return $entry
}

function Initialize-UiSubscription {
    param([string]$Type)
    $ctx = $script:UiBuilder
    if ($ctx.Subscriptions.ContainsKey($Type)) { return }
    $ctx.Subscriptions[$Type] = Register-UI4MEDocumentEvent -Document $ctx.Document -Type $Type -Callback {
        param($evt)
        Invoke-UiDispatch $evt
    }
}

function Invoke-UiDispatch {
    param($evt)
    $ctx = $script:UiBuilder
    if ($null -eq $ctx -or $ctx.Stopping) { return }
    $type = [string]$evt.type
    if (-not $ctx.Handlers.ContainsKey($type)) { return }
    $byElement = $ctx.Handlers[$type]
    $targets = New-Object System.Collections.ArrayList
    if ($evt.PSObject.Properties['element'] -and $evt.element) { [void]$targets.Add([string]$evt.element) }
    if ($evt.PSObject.Properties['path'] -and $evt.path) {
        foreach ($p in @($evt.path)) { if ($p -and -not $targets.Contains([string]$p)) { [void]$targets.Add([string]$p) } }
    }
    foreach ($target in $targets) {
        if (-not $byElement.ContainsKey($target)) { continue }
        foreach ($entry in @($byElement[$target])) {
            if ($null -ne $entry.Owner -and $entry.Owner.Disposed) { continue }
            $previous = $ctx.CurrentOwner
            $ctx.CurrentOwner = $entry.Owner
            try { Invoke-UiHandler $entry.Handler @($evt) "$type on #$target" }
            finally { $ctx.CurrentOwner = $previous }
        }
    }
}

function Remove-UiOwner {
    # Dispose runtime content: its handlers, bindings, timers and tasks stop.
    param($Owner)
    $ctx = $script:UiBuilder
    if ($null -eq $Owner -or $Owner.Disposed) { return }
    $Owner.Disposed = $true
    foreach ($entry in @($Owner.Handlers)) {
        if ($ctx.Handlers.ContainsKey($entry.Type) -and $ctx.Handlers[$entry.Type].ContainsKey($entry.Element)) {
            $list = $ctx.Handlers[$entry.Type][$entry.Element]
            [void]$list.Remove($entry)
            if ($list.Count -eq 0) { [void]$ctx.Handlers[$entry.Type].Remove($entry.Element) }
        }
    }
    foreach ($cleanup in @($Owner.Cleanups)) { try { $null = Invoke-UiCallable $cleanup } catch { } }
    foreach ($child in @($Owner.Children)) { Remove-UiOwner $child }
}

function New-UiOwner {
    param([AllowNull()]$Parent)
    $owner = [pscustomobject]@{ Handlers = (New-Object System.Collections.ArrayList)
        Cleanups = (New-Object System.Collections.ArrayList); Children = (New-Object System.Collections.ArrayList)
        Disposed = $false }
    if ($null -ne $Parent) { [void]$Parent.Children.Add($owner) }
    return $owner
}

function Register-UiBinding {
    # Apply $Apply (param($ctx, $element, $value)) whenever $State changes, once the document exists.
    # $Apply: module function name taking ($ctx, $element, $value, $data).
    param($State, [string]$Element, [string]$Apply, $Data)
    $ctx = Assert-UiBuilder
    $binding = [pscustomobject]@{ State = $State; Element = $Element; Apply = $Apply; Data = $Data; Owner = $ctx.CurrentOwner; Token = $null }
    $binding.Token = $State.Subscribe((New-UiCallable 'Invoke-UiBinding' $binding))
    [void]$ctx.Bindings.Add($binding)
    if ($null -ne $ctx.CurrentOwner) {
        [void]$ctx.CurrentOwner.Cleanups.Add((New-UiCallable 'Remove-UiBinding' $binding))
    }
    return $binding
}

function Invoke-UiBinding {
    param($Binding, $Value)
    $c = $script:UiBuilder
    if ($null -eq $c -or $null -eq $c.Document -or $c.Stopping) { return }
    if ($null -ne $Binding.Owner -and $Binding.Owner.Disposed) { return }
    # Content rebuilt by this binding (When/Each) belongs to the binding's owner.
    $previous = $c.CurrentOwner
    $c.CurrentOwner = $Binding.Owner
    try { & $Binding.Apply $c $Binding.Element $Value $Binding.Data }
    finally { $c.CurrentOwner = $previous }
}

function Remove-UiBinding {
    param($Binding)
    $Binding.State.Unsubscribe($Binding.Token)
    [void]$script:UiBuilder.Bindings.Remove($Binding)
}

function Set-UiTextBinding { param($ctx, $element, $value, $data)
    Set-UI4MEDocumentText -Document $ctx.Document -Element $element -Text ([string]$value) }
function Set-UiHiddenBinding { param($ctx, $element, $value, $data)
    if ([bool]$value) { Set-UI4MEDocumentAttribute -Document $ctx.Document -Element $element -Name hidden -Remove }
    else { Set-UI4MEDocumentAttribute -Document $ctx.Document -Element $element -Name hidden -Value '' } }
function Set-UiDisabledBinding { param($ctx, $element, $value, $data)
    if ([bool]$value) { Set-UI4MEDocumentAttribute -Document $ctx.Document -Element $element -Name disabled -Value '' }
    else { Set-UI4MEDocumentAttribute -Document $ctx.Document -Element $element -Name disabled -Remove } }
function Set-UiValueBinding { param($ctx, $element, $value, $data)
    # Never echo a value that came from the control itself: the user may already have typed
    # further characters, and writing the older value back would erase them.
    if ($null -ne $data -and $data.HasShadow -and (Test-UiSameValue $value $data.Shadow)) { return }
    $text = if ($null -eq $value) { '' } elseif ($value -is [double] -or $value -is [int]) {
        [System.Convert]::ToString($value, [System.Globalization.CultureInfo]::InvariantCulture) } else { [string]$value }
    if ($null -ne $data) { $data.Shadow = $value; $data.HasShadow = $true }
    Set-UI4MEDocumentValue -Document $ctx.Document -Element $element -Value $text }

function Test-UiSameValue {
    param($a, $b)
    if ($null -eq $a -or $null -eq $b) { return ($null -eq $a -and $null -eq $b) }
    return ([string]$a -ceq [string]$b)
}
function Set-UiCheckedBinding { param($ctx, $element, $value, $data)
    Set-UI4MEChecked -Document $ctx.Document -Element $element -Checked ([bool]$value) }

function Invoke-UiSetups {
    param($Setups)
    $ctx = $script:UiBuilder
    foreach ($setup in @($Setups)) {
        try { $null = Invoke-UiCallable $setup @($ctx) } catch { Write-UiError $_ 'component setup' }
    }
    foreach ($type in @($ctx.Handlers.Keys)) { Initialize-UiSubscription $type }
}

# -------------------------------------------------------------------------- application --

function Invoke-UI4MEApp {
    <#
    .SYNOPSIS
    Builds one native window from UI4ME components and runs it until the host shuts down.
    .DESCRIPTION
    Must run inside a backend process launched by the UI4ME.Core host (Start-UI4MEUiScript or
    Start-UI4MEHost -Manifest app.toml). The -Content block is dot-sourced, so variables it defines
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
    $resolvedAppId = $AppId
    if (-not $resolvedAppId) {
        $slug = ($Title.ToLowerInvariant() -replace '[^a-z0-9]+', '-').Trim('-')
        if ($slug.Length -gt 60) { $slug = $slug.Substring(0, 60) }
        if (-not $slug) { $slug = 'app' }
        $resolvedAppId = "org.ui4me.app.$slug"
    }
    if ($resolvedAppId -cnotmatch '^[A-Za-z][A-Za-z0-9_.-]{0,127}$') { throw 'AppId may contain only letters, digits, dots, hyphens and underscores' }
    Import-Module UI4ME.Core -ErrorAction Stop
    if ($Assets -and -not (Test-Path -LiteralPath $Assets -PathType Container)) { throw "Assets folder not found: $Assets" }
    $ctx = New-UiContext -Title $Title -Theme $Theme -Css $Css -Assets $Assets -OnError $OnError
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
        $ctx.App = Connect-UI4ME
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

# ----------------------------------------------------------------------------- state --

function New-UI4MEState {
    <#
    .SYNOPSIS
    Observable value. Read .Value, change with .Set(new) or .Update({ param($old) ... }); bound components follow.
    #>
    [CmdletBinding()]
    param([AllowNull()][object]$Value)
    $state = [pscustomobject]@{ Value = $Value; Subscribers = (New-Object System.Collections.ArrayList); Next = 0 }
    $state.PSObject.TypeNames.Insert(0, 'UI4ME.UiState')
    $state | Add-Member -MemberType ScriptMethod -Name Set -Value {
        param([AllowNull()][object]$NewValue)
        if ($null -eq $NewValue -and $null -eq $this.Value) { return }
        if ($null -ne $NewValue -and $null -ne $this.Value -and -not ($NewValue -is [System.Collections.IEnumerable] -and
                -not ($NewValue -is [string])) -and [object]::Equals($this.Value, $NewValue)) { return }
        $this.Value = $NewValue
        foreach ($subscriber in @($this.Subscribers)) {
            try { $null = Invoke-UiCallable $subscriber.Callback @(, $NewValue) }
            catch { Write-UiError $_ 'state subscriber' }
        }
    }
    $state | Add-Member -MemberType ScriptMethod -Name Update -Value {
        param([scriptblock]$Transform)
        $this.Set((& $Transform $this.Value))
    }
    $state | Add-Member -MemberType ScriptMethod -Name Subscribe -Value {
        param($Callback)
        $this.Next = [int]$this.Next + 1
        [void]$this.Subscribers.Add([pscustomobject]@{ Token = $this.Next; Callback = $Callback })
        return $this.Next
    }
    $state | Add-Member -MemberType ScriptMethod -Name Unsubscribe -Value {
        param([int]$Token)
        foreach ($subscriber in @($this.Subscribers)) { if ($subscriber.Token -eq $Token) { [void]$this.Subscribers.Remove($subscriber) } }
    }
    return $state
}

function New-UI4MEComputed {
    <#
    .SYNOPSIS
    A read-only state whose value is -Expression, recomputed whenever any -DependsOn state changes.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object[]]$DependsOn, [Parameter(Mandatory)][scriptblock]$Expression)
    $computed = New-UI4MEState -Value (& $Expression)
    $data = [pscustomobject]@{ Target = $computed; Expression = $Expression }
    foreach ($dependency in $DependsOn) {
        if (-not (Test-UiState $dependency)) { throw '-DependsOn takes states from New-UI4MEState/New-UI4MEComputed' }
        $null = $dependency.Subscribe((New-UiCallable 'Update-UiComputed' $data))
    }
    return $computed
}

function Update-UiComputed {
    param($Data, $ignored)
    $Data.Target.Set((& $Data.Expression))
}

# ------------------------------------------------------------------------ components --

function New-UI4METext {
    <# .SYNOPSIS Text (escaped). -Bind shows a state's value and follows its changes. #>
    [CmdletBinding()]
    param([AllowNull()][object]$Text = '', [AllowNull()][object]$Bind,
          [ValidateSet('default', 'muted', 'info', 'success', 'warning', 'danger')][string]$Tone = 'default',
          [string]$Class = '', [string]$Style = '', [AllowNull()][object]$Visible)
    $id = New-UiId 'text'
    $value = if ($null -ne $Bind) { Get-UiValue $Bind } else { Get-UiValue $Text }
    $toneClass = if ($Tone -ne 'default') { "u4-tone-$Tone" } else { '' }
    $styleAttr = if ($Style) { ' style="{0}"' -f (ConvertTo-UiHtml $Style) } else { '' }
    Add-UiMarkup ('<span id="{0}" {1}{2}{3}>{4}</span>' -f $id, (Get-UiClassAttr 'u4-text' "$toneClass $Class".Trim()), $styleAttr,
                  (Get-UiHiddenAttr $Visible), (ConvertTo-UiHtml $value))
    $source = if ($null -ne $Bind) { $Bind } elseif (Test-UiState $Text) { $Text } else { $null }
    if ($null -ne $source) {
        if (-not (Test-UiState $source)) { throw '-Bind takes a state from New-UI4MEState or New-UI4MEComputed' }
        $null = Register-UiBinding $source $id 'Set-UiTextBinding'
    }
    Register-UiVisibility $id $Visible
    return $id
}

function New-UI4MEHeading {
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowNull()][object]$Text, [ValidateRange(1, 6)][int]$Level = 2, [string]$Class = '')
    $id = New-UiId 'heading'
    Add-UiMarkup ('<h{0} id="{1}" {2}>{3}</h{0}>' -f $Level, $id, (Get-UiClassAttr "u4-heading u4-h$Level" $Class),
                  (ConvertTo-UiHtml (Get-UiValue $Text)))
    if (Test-UiState $Text) {
        $null = Register-UiBinding $Text $id 'Set-UiTextBinding'
    }
    return $id
}

function New-UI4MEButton {
    <# .SYNOPSIS A button. -OnClick receives the native event. -Disabled may be a state. #>
    [CmdletBinding()]
    param([AllowNull()][object]$Text = 'Button', [scriptblock]$OnClick,
          [ValidateSet('primary', 'secondary', 'outline', 'ghost', 'danger')][string]$Variant = 'primary',
          [ValidateSet('sm', 'md', 'lg')][string]$Size = 'md',
          [AllowNull()][object]$Disabled = $false, [string]$Class = '', [string]$Tooltip, [AllowNull()][object]$Visible)
    $id = New-UiId 'button'
    $disabledAttr = if ([bool](Get-UiValue $Disabled)) { ' disabled' } else { '' }
    $title = if ($Tooltip) { ' title="{0}"' -f (ConvertTo-UiHtml $Tooltip) } else { '' }
    $classes = "u4-btn-$Variant"
    if ($Size -ne 'md') { $classes += " u4-btn-$Size" }
    Add-UiMarkup ('<button type="button" id="{0}" {1}{2}{3}{4}>{5}</button>' -f $id, (Get-UiClassAttr "u4-btn $classes" $Class),
                  $disabledAttr, $title, (Get-UiHiddenAttr $Visible), (ConvertTo-UiHtml (Get-UiValue $Text)))
    if ($OnClick) { $null = Register-UiHandler $id 'click' $OnClick }
    if (Test-UiState $Text) {
        $null = Register-UiBinding $Text $id 'Set-UiTextBinding'
    }
    if (Test-UiState $Disabled) {
        $null = Register-UiBinding $Disabled $id 'Set-UiDisabledBinding' 
    }
    Register-UiVisibility $id $Visible
    return $id
}

function Add-UiField {
    # Shared label/help chrome around a control; returns nothing (markup only).
    param([string]$Id, [string]$Label, [string]$Description, [string]$ControlMarkup)
    $help = if ($Description) { '<p class="u4-help" id="{0}-help">{1}</p>' -f $Id, (ConvertTo-UiHtml $Description) } else { '' }
    Add-UiMarkup ('<div class="u4-field" id="{0}-field"><label class="u4-label" for="{0}">{1}</label>{2}{3}<p class="u4-error" id="{0}-error" role="alert" hidden></p></div>' -f
                  $Id, (ConvertTo-UiHtml $Label), $ControlMarkup, $help)
}

function Register-UiValueControl {
    # Two-way binding between a state and a control value; events: input (text) / change (selects).
    param([string]$Id, [AllowNull()]$Bind, [scriptblock]$OnChange, [string]$EventType, [scriptblock]$Convert)
    $data = [pscustomobject]@{ State = $Bind; Callback = $OnChange; Convert = $Convert; Id = $Id
        Shadow = $(if ($null -ne $Bind) { $Bind.Value } else { $null }); HasShadow = ($null -ne $Bind) }
    if ($null -ne $Bind) {
        if (-not (Test-UiState $Bind)) { throw '-Bind takes a state from New-UI4MEState' }
        $null = Register-UiBinding $Bind $Id 'Set-UiValueBinding' $data
    }
    if ($null -ne $Bind -or $OnChange) {
        $null = Register-UiHandler $Id $EventType (New-UiCallable 'Invoke-UiValueEvent' $data)
    }
}

function Invoke-UiValueEvent {
    param($Data, $evt)
    $raw = if ($evt.PSObject.Properties['value'] -and $null -ne $evt.value) { [string]$evt.value } else {
        [string](Get-UI4MEValue -Document $script:UiBuilder.Document -Element $Data.Id) }
    $value = if ($Data.Convert) { & $Data.Convert $raw } else { $raw }
    $Data.Shadow = $value; $Data.HasShadow = $true
    if ($null -ne $Data.State) { $Data.State.Set($value) }
    if ($Data.Callback) { $null = & $Data.Callback $value }
}

function New-UI4MEInput {
    <# .SYNOPSIS Labelled text input. -Bind keeps a state in sync both ways; -OnSubmit runs on Enter. #>
    [CmdletBinding()]
    param([string]$Label = '', [AllowNull()][object]$Value = '', [AllowNull()][object]$Bind,
          [string]$Placeholder = '', [scriptblock]$OnChange, [scriptblock]$OnSubmit, [string]$Description,
          # date/time/month/week/color inputs are refused by UI4ME.Core 1.x (no native pickers):
          # use New-UI4MEDate, New-UI4METime and New-UI4MEColor instead.
          [ValidateSet('text', 'password', 'email', 'search', 'url', 'tel')]
          [string]$Type = 'text', [switch]$Required, [AllowNull()][object]$Disabled = $false, [int]$MaxLength = 0,
          [string]$Class = '', [string]$Name)
    $id = New-UiId 'input'
    $initial = if ($null -ne $Bind) { Get-UiValue $Bind } else { Get-UiValue $Value }
    $flags = ''
    if ($Required) { $flags += ' required aria-required="true"' }
    if ([bool](Get-UiValue $Disabled)) { $flags += ' disabled' }
    if ($MaxLength -gt 0) { $flags += (' maxlength="{0}"' -f $MaxLength) }
    if ($Placeholder) { $flags += (' placeholder="{0}"' -f (ConvertTo-UiHtml $Placeholder)) }
    if ($Name) { $flags += (' name="{0}"' -f (ConvertTo-UiHtml $Name)) }
    if ($Description) { $flags += (' aria-describedby="{0}-help"' -f $id) }
    $control = '<input id="{0}" type="{1}" {2} value="{3}"{4}>' -f $id, $Type, (Get-UiClassAttr 'u4-input' $Class), (ConvertTo-UiHtml $initial), $flags
    Add-UiField $id $Label $Description $control
    Register-UiValueControl $id $Bind $OnChange 'input' $null
    if ($OnSubmit) {
        $null = Register-UiHandler $id 'keydown' (New-UiCallable 'Invoke-UiSubmitKey' ([pscustomobject]@{ Id = $id; Submit = $OnSubmit }))
    }
    Register-UiDisabled $id $Disabled
    return $id
}

function Invoke-UiSubmitKey {
    param($Data, $evt)
    if ([string]$evt.key -ne 'Enter') { return }
    if ($evt.PSObject.Properties['shift'] -and $evt.shift) { return }
    $v = Get-UI4MEValue -Document $script:UiBuilder.Document -Element $Data.Id
    $null = & $Data.Submit $v
}

function Register-UiDisabled {
    param([string]$Id, [AllowNull()][object]$Disabled)
    if (-not (Test-UiState $Disabled)) { return }
    $null = Register-UiBinding $Disabled $Id 'Set-UiDisabledBinding' 
}

function Set-UiFieldError {
    param($ctx, [string]$Id, [string]$Message)
    $errorId = "$Id-error"
    Set-UI4MEDocumentText -Document $ctx.Document -Element $errorId -Text $Message
    if ($Message) {
        Set-UI4MEDocumentAttribute -Document $ctx.Document -Element $errorId -Name hidden -Remove
        Set-UI4MEDocumentAttribute -Document $ctx.Document -Element $Id -Name aria-invalid -Value 'true'
    } else {
        Set-UI4MEDocumentAttribute -Document $ctx.Document -Element $errorId -Name hidden -Value ''
        Set-UI4MEDocumentAttribute -Document $ctx.Document -Element $Id -Name aria-invalid -Remove
    }
}

function Invoke-UiParsedEvent {
    # input event of a parsed field: text -> value, or show the parse error under the field.
    param($Data, $evt)
    $raw = if ($evt.PSObject.Properties['value'] -and $null -ne $evt.value) { [string]$evt.value } else {
        [string](Get-UI4MEValue -Document $script:UiBuilder.Document -Element $Data.Id) }
    $parsed = & $Data.Parse $Data $raw
    if ($parsed.ContainsKey('Error')) { Set-UiFieldError $script:UiBuilder $Data.Id $parsed['Error']; return }
    Set-UiFieldError $script:UiBuilder $Data.Id ''
    Set-UiParsedValue $Data $parsed['Value'] $false
}

function Set-UiParsedValue {
    param($Data, $Value, [bool]$WriteControl)
    $Data.Shadow = $Value; $Data.HasShadow = $true
    if ($WriteControl) {
        Set-UI4MEDocumentValue -Document $script:UiBuilder.Document -Element $Data.Id -Value (& $Data.Format $Value)
    }
    if ($null -ne $Data.State) { $Data.State.Set($Value) }
    if ($Data.Callback) { $null = Invoke-UiCallable $Data.Callback @(, $Value) }
}

function Set-UiParsedBinding { param($ctx, $element, $value, $data)
    if ($data.HasShadow -and (Test-UiSameValue $value $data.Shadow)) { return }
    $data.Shadow = $value; $data.HasShadow = $true
    Set-UI4MEDocumentValue -Document $ctx.Document -Element $element -Value (& $data.Format $value) }

function New-UiParsedField {
    param([string]$Prefix, [string]$Label, $Initial, $Bind, [scriptblock]$OnChange, [string]$Placeholder,
          [scriptblock]$Parse, [scriptblock]$Format, [string]$Extra = '', [hashtable]$More = @{})
    $id = New-UiId $Prefix
    $data = [pscustomobject]@{ Id = $id; State = $Bind; Callback = $OnChange; Parse = $Parse; Format = $Format
        Shadow = $Initial; HasShadow = $true }
    foreach ($k in $More.Keys) { $data | Add-Member -NotePropertyName $k -NotePropertyValue $More[$k] }
    $control = ('<input id="{0}" type="text" class="u4-input" inputmode="numeric" autocomplete="off" spellcheck="false" placeholder="{1}" value="{2}">{3}' -f
                $id, (ConvertTo-UiHtml $Placeholder), (ConvertTo-UiHtml (& $Format $Initial)), $Extra)
    Add-UiField $id $Label $null $control
    if ($null -ne $Bind) {
        if (-not (Test-UiState $Bind)) { throw '-Bind takes a state from New-UI4MEState' }
        $null = Register-UiBinding $Bind $id 'Set-UiParsedBinding' $data
    }
    $null = Register-UiHandler $id 'input' (New-UiCallable 'Invoke-UiParsedEvent' $data)
    return $data
}

function New-UI4MEDate {
    <#
    .SYNOPSIS
    Date field (YYYY-MM-DD) with an in-window calendar. -Bind holds a [datetime] (date part) or $null.
    .DESCRIPTION
    UI4ME.Core 1.x has no native date picker, so this is a validated text input plus a keyboard-usable
    calendar inside the window (arrow keys move, Escape closes).
    #>
    [CmdletBinding()]
    param([string]$Label = 'Date', [AllowNull()][object]$Value, [AllowNull()][object]$Bind, [scriptblock]$OnChange,
          [AllowNull()][Nullable[datetime]]$Min, [AllowNull()][Nullable[datetime]]$Max)
    $initial = if ($null -ne $Bind) { Get-UiValue $Bind } else { $Value }
    if ($initial -is [string] -and $initial) { $initial = [datetime]::ParseExact($initial, 'yyyy-MM-dd', [System.Globalization.CultureInfo]::InvariantCulture) }
    if ($null -ne $initial) { $initial = ([datetime]$initial).Date }
    $minDate = if ($null -ne $Min) { ([datetime]$Min).Date } else { $null }   # bounds are whole days
    $maxDate = if ($null -ne $Max) { ([datetime]$Max).Date } else { $null }
    $ctx = Assert-UiBuilder
    $peek = [int]$ctx.Sequence + 1
    $panel = "u4ps-date-$peek-cal"
    $extra = ('<button type="button" id="{0}-toggle" class="u4-btn u4-btn-ghost u4-btn-sm u4-picker-toggle" aria-expanded="false" aria-haspopup="dialog" aria-label="Choose date from calendar">Calendar</button><div id="{0}" class="u4-calendar" role="dialog" aria-label="Calendar" hidden></div>' -f $panel)
    $shown = if ($null -ne $initial) { $initial } else { [datetime]::Today }
    $data = New-UiParsedField 'date' $Label $initial $Bind $OnChange 'YYYY-MM-DD' {
        param($d, $raw)
        $raw = $raw.Trim()
        if (-not $raw) { return @{ Value = $null } }
        $parsed = [datetime]::MinValue
        if (-not [datetime]::TryParseExact($raw.Replace('/', '-'), 'yyyy-MM-dd', [System.Globalization.CultureInfo]::InvariantCulture, [System.Globalization.DateTimeStyles]::None, [ref]$parsed)) {
            return @{ Error = 'Enter a date as YYYY-MM-DD' }
        }
        if ($null -ne $d.Min -and $parsed -lt $d.Min) { return @{ Error = 'Must be on or after ' + $d.Min.ToString('yyyy-MM-dd') } }
        if ($null -ne $d.Max -and $parsed -gt $d.Max) { return @{ Error = 'Must be on or before ' + $d.Max.ToString('yyyy-MM-dd') } }
        return @{ Value = $parsed }
    } {
        param($v)
        if ($null -eq $v) { '' } else { ([datetime]$v).ToString('yyyy-MM-dd', [System.Globalization.CultureInfo]::InvariantCulture) }
    } $extra @{ Panel = $panel; Shown = (New-Object datetime $shown.Year, $shown.Month, 1); Min = $minDate; Max = $maxDate; Open = $false }
    if ($data.Id -ne "u4ps-date-$peek") { throw 'internal id mismatch' }
    $null = Register-UiHandler "$panel-toggle" 'click' (New-UiCallable 'Switch-UiCalendar' $data)
    $null = Register-UiHandler $panel 'click' (New-UiCallable 'Invoke-UiCalendarClick' $data)
    $null = Register-UiHandler $panel 'keydown' (New-UiCallable 'Invoke-UiCalendarKey' $data)
    return $data.Id
}

function Get-UiDayId { param($Data, [datetime]$Day) return ('{0}-d{1}' -f $Data.Panel, $Day.ToString('yyyyMMdd')) }

function Switch-UiCalendar {
    param($Data, $evt, [Nullable[bool]]$Open)
    $ctx = $script:UiBuilder
    $want = if ($null -ne $Open) { [bool]$Open } else { -not $Data.Open }
    if ($want) {
        if ($null -ne $Data.Shadow) { $Data.Shown = New-Object datetime ([datetime]$Data.Shadow).Year, ([datetime]$Data.Shadow).Month, 1 }
        Update-UiCalendar $Data
        Set-UI4MEDocumentAttribute -Document $ctx.Document -Element $Data.Panel -Name hidden -Remove
    } else {
        Set-UI4MEDocumentAttribute -Document $ctx.Document -Element $Data.Panel -Name hidden -Value ''
    }
    Set-UI4MEDocumentAttribute -Document $ctx.Document -Element "$($Data.Panel)-toggle" -Name aria-expanded -Value $(if ($want) { 'true' } else { 'false' })
    $Data.Open = $want
    if ($want) {
        $focusDay = if ($null -ne $Data.Shadow -and ([datetime]$Data.Shadow).Month -eq $Data.Shown.Month -and ([datetime]$Data.Shadow).Year -eq $Data.Shown.Year) { [datetime]$Data.Shadow } else { $Data.Shown }
        Set-UI4MEFocus -Document $ctx.Document -Element (Get-UiDayId $Data $focusDay)
    }
}

function Update-UiCalendar {
    param($Data)
    $inv = [System.Globalization.CultureInfo]::InvariantCulture
    $first = $Data.Shown
    $offset = (([int]$first.DayOfWeek) + 6) % 7  # Monday first
    $start = $first.AddDays(-$offset)
    $sb = New-Object System.Text.StringBuilder
    foreach ($name in @('Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su')) { [void]$sb.Append('<span class="u4-calendar-head" aria-hidden="true">' + $name + '</span>') }
    $weeks = [Math]::Ceiling(($offset + [datetime]::DaysInMonth($first.Year, $first.Month)) / 7)
    for ($i = 0; $i -lt $weeks * 7; $i++) {
        $day = $start.AddDays($i)
        $cls = 'u4-calendar-day'
        if ($day.Month -ne $first.Month) { $cls += ' u4-muted' }
        if ($day -eq [datetime]::Today) { $cls += ' u4-today' }
        $attrs = ''
        if ($null -ne $Data.Shadow -and $day -eq [datetime]$Data.Shadow) { $cls += ' u4-selected'; $attrs += ' aria-pressed="true"' }
        if (($null -ne $Data.Min -and $day -lt $Data.Min) -or ($null -ne $Data.Max -and $day -gt $Data.Max)) { $attrs += ' disabled' }
        [void]$sb.Append(('<button type="button" id="{0}" class="{1}" aria-label="{2}"{3}>{4}</button>' -f
            (Get-UiDayId $Data $day), $cls, $day.ToString('dddd d MMMM yyyy', $inv), $attrs, $day.Day))
    }
    $p = $Data.Panel
    $html = ('<div class="u4-calendar-nav"><button type="button" id="{0}-prev" class="u4-btn u4-btn-ghost u4-btn-sm" aria-label="Previous month">&#8249;</button><strong aria-live="polite">{1}</strong><button type="button" id="{0}-next" class="u4-btn u4-btn-ghost u4-btn-sm" aria-label="Next month">&#8250;</button></div><div class="u4-calendar-grid" role="grid">{2}</div><div class="u4-calendar-foot"><button type="button" id="{0}-today" class="u4-btn u4-btn-ghost u4-btn-sm">Today</button><button type="button" id="{0}-clear" class="u4-btn u4-btn-ghost u4-btn-sm">Clear</button></div>' -f
             $p, $first.ToString('MMMM yyyy', $inv), $sb.ToString())
    Set-UI4MEDocumentHtml -Document $script:UiBuilder.Document -Element $p -Html $html
}

function Select-UiCalendarDay {
    param($Data, $Day)
    Set-UiFieldError $script:UiBuilder $Data.Id ''
    Set-UiParsedValue $Data $Day $true
    Switch-UiCalendar $Data $null $false
    Set-UI4MEFocus -Document $script:UiBuilder.Document -Element $Data.Id
}

function Invoke-UiCalendarClick {
    param($Data, $evt)
    $target = [string]$evt.element
    $p = $Data.Panel
    switch -Regex ($target) {
        "^$([regex]::Escape($p))-prev$" { $Data.Shown = $Data.Shown.AddMonths(-1); Update-UiCalendar $Data; return }
        "^$([regex]::Escape($p))-next$" { $Data.Shown = $Data.Shown.AddMonths(1); Update-UiCalendar $Data; return }
        "^$([regex]::Escape($p))-today$" { Select-UiCalendarDay $Data ([datetime]::Today); return }
        "^$([regex]::Escape($p))-clear$" { Select-UiCalendarDay $Data $null; return }
        "^$([regex]::Escape($p))-d(\d{8})$" {
            $day = [datetime]::ParseExact($Matches[1], 'yyyyMMdd', [System.Globalization.CultureInfo]::InvariantCulture)
            if (($null -ne $Data.Min -and $day -lt $Data.Min) -or ($null -ne $Data.Max -and $day -gt $Data.Max)) { return }
            Select-UiCalendarDay $Data $day
        }
    }
}

function Invoke-UiCalendarKey {
    param($Data, $evt)
    $key = [string]$evt.key
    if ($key -eq 'Escape') { Switch-UiCalendar $Data $null $false; Set-UI4MEFocus -Document $script:UiBuilder.Document -Element $Data.Id; return }
    $steps = @{ ArrowLeft = -1; ArrowRight = 1; ArrowUp = -7; ArrowDown = 7 }
    if (-not $steps.ContainsKey($key)) { return }
    if ([string]$evt.element -notmatch ('^' + [regex]::Escape($Data.Panel) + '-d(\d{8})$')) { return }
    $day = [datetime]::ParseExact($Matches[1], 'yyyyMMdd', [System.Globalization.CultureInfo]::InvariantCulture).AddDays($steps[$key])
    if ($day.Month -ne $Data.Shown.Month -or $day.Year -ne $Data.Shown.Year) { $Data.Shown = New-Object datetime $day.Year, $day.Month, 1; Update-UiCalendar $Data }
    Set-UI4MEFocus -Document $script:UiBuilder.Document -Element (Get-UiDayId $Data $day)
}

function New-UI4METime {
    <# .SYNOPSIS 24-hour time field (HH:MM). -Bind holds a [timespan] or $null. #>
    [CmdletBinding()]
    param([string]$Label = 'Time', [AllowNull()][object]$Value, [AllowNull()][object]$Bind, [scriptblock]$OnChange)
    $initial = if ($null -ne $Bind) { Get-UiValue $Bind } else { $Value }
    if ($initial -is [string] -and $initial) { $initial = [timespan]::Parse($initial) }
    $data = New-UiParsedField 'time' $Label $initial $Bind $OnChange 'HH:MM' {
        param($d, $raw)
        $raw = $raw.Trim()
        if (-not $raw) { return @{ Value = $null } }
        if ($raw -notmatch '^(\d{1,2}):(\d{2})$' -or [int]$Matches[1] -gt 23 -or [int]$Matches[2] -gt 59) { return @{ Error = 'Enter a 24-hour time as HH:MM' } }
        return @{ Value = New-Object timespan ([int]$Matches[1]), ([int]$Matches[2]), 0 }
    } {
        param($v)
        if ($null -eq $v) { '' } else { '{0:00}:{1:00}' -f ([timespan]$v).Hours, ([timespan]$v).Minutes }
    }
    return $data.Id
}

function New-UI4MEColor {
    <# .SYNOPSIS Hex colour field (#rrggbb) with live preview and in-window swatches. -Bind holds the string. #>
    [CmdletBinding()]
    param([string]$Label = 'Color', [AllowNull()][string]$Value = '#2563eb', [AllowNull()][object]$Bind, [scriptblock]$OnChange,
          [string[]]$Palette = @('#2563eb', '#7c3aed', '#db2777', '#dc2626', '#ea580c', '#ca8a04', '#16a34a', '#0d9488', '#475569', '#111827'))
    $normalize = {
        param($t)
        $t = ([string]$t).Trim()
        if ($t -notmatch '^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$') { return $null }
        $h = $Matches[1].ToLowerInvariant()
        if ($h.Length -eq 3) { $h = -join ($h.ToCharArray() | ForEach-Object { "$_$_" }) }
        return "#$h"
    }
    $initial = if ($null -ne $Bind) { Get-UiValue $Bind } else { $Value }
    if ($initial) { $n = & $normalize $initial; if (-not $n) { throw "Not a hex colour: $initial" }; $initial = $n }
    $ctx = Assert-UiBuilder
    $peek = [int]$ctx.Sequence + 1
    $swatchId = "u4ps-color-$peek-swatches"
    $sw = New-Object System.Text.StringBuilder
    $swatchColours = @($Palette | ForEach-Object { & $normalize $_ })
    for ($i = 0; $i -lt $swatchColours.Count; $i++) {
        [void]$sw.Append(('<button type="button" id="{0}-{1}" class="u4-swatch" style="background:{2}" aria-label="{2}" title="{2}"></button>' -f $swatchId, $i, $swatchColours[$i]))
    }
    $extra = ('<span id="u4ps-color-{0}-preview" class="u4-swatch u4-swatch-preview" aria-hidden="true" style="background:{1}"></span><div id="{2}" class="u4-swatches" role="group" aria-label="Colour presets">{3}</div>' -f
              $peek, $(if ($initial) { $initial } else { 'transparent' }), $swatchId, $sw.ToString())
    $data = New-UiParsedField 'color' $Label $initial $Bind $OnChange '#rrggbb' {
        param($d, $raw)
        if (-not $raw.Trim()) { return @{ Value = $null } }
        $n = & $d.Normalize $raw
        if (-not $n) { return @{ Error = 'Enter a colour as #rrggbb' } }
        return @{ Value = $n }
    } { param($v) if ($null -eq $v) { '' } else { [string]$v } } $extra @{ Normalize = $normalize; Palette = $swatchColours; Swatches = $swatchId }
    if ($data.Id -ne "u4ps-color-$peek") { throw 'internal id mismatch' }
    $preview = New-UI4MEState -Value $initial
    $data | Add-Member -NotePropertyName Preview -NotePropertyValue $preview
    $userCallback = $data.Callback
    $data.Callback = $null
    $data | Add-Member -NotePropertyName UserCallback -NotePropertyValue $userCallback
    $data.Callback = (New-UiCallable 'Invoke-UiColorChanged' $data)
    $null = Register-UiBinding $preview "$($data.Id)-preview" 'Set-UiColorPreview'
    if ($null -ne $Bind) { $null = $Bind.Subscribe((New-UiCallable 'Sync-UiColorPreview' $data)) }
    $null = Register-UiHandler $swatchId 'click' (New-UiCallable 'Invoke-UiSwatchClick' $data)
    return $data.Id
}

function Invoke-UiColorChanged { param($Data, $Value) $Data.Preview.Set($Value); if ($Data.UserCallback) { $null = & $Data.UserCallback $Value } }
function Sync-UiColorPreview { param($Data, $Value) $Data.Preview.Set($Value) }
function Set-UiColorPreview { param($ctx, $element, $value, $data)
    Set-UI4MEDocumentAttribute -Document $ctx.Document -Element $element -Name style -Value ('background:' + $(if ($value) { $value } else { 'transparent' })) }

function Invoke-UiSwatchClick {
    param($Data, $evt)
    if ([string]$evt.element -notmatch ('^' + [regex]::Escape($Data.Swatches) + '-(\d+)$')) { return }
    Set-UiFieldError $script:UiBuilder $Data.Id ''
    Set-UiParsedValue $Data $Data.Palette[[int]$Matches[1]] $true
}

function New-UI4MENumber {
    <# .SYNOPSIS Numeric input bound to a [double] state ($null when empty or invalid). #>
    [CmdletBinding()]
    param([string]$Label = '', [AllowNull()][object]$Value, [AllowNull()][object]$Bind, [double]$Min = [double]::NaN,
          [double]$Max = [double]::NaN, [double]$Step = 1, [scriptblock]$OnChange, [string]$Class = '')
    $id = New-UiId 'number'
    $initial = if ($null -ne $Bind) { Get-UiValue $Bind } else { Get-UiValue $Value }
    $attrs = ' step="{0}"' -f [System.Convert]::ToString($Step, [System.Globalization.CultureInfo]::InvariantCulture)
    if (-not [double]::IsNaN($Min)) { $attrs += ' min="{0}"' -f [System.Convert]::ToString($Min, [System.Globalization.CultureInfo]::InvariantCulture) }
    if (-not [double]::IsNaN($Max)) { $attrs += ' max="{0}"' -f [System.Convert]::ToString($Max, [System.Globalization.CultureInfo]::InvariantCulture) }
    $text = if ($null -eq $initial) { '' } else { [System.Convert]::ToString($initial, [System.Globalization.CultureInfo]::InvariantCulture) }
    Add-UiField $id $Label $null ('<input id="{0}" type="number" {1} value="{2}"{3}>' -f $id, (Get-UiClassAttr 'u4-input u4-num' $Class), (ConvertTo-UiHtml $text), $attrs)
    $convert = { param($raw)
        $parsed = 0.0
        if ([double]::TryParse($raw, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$parsed)) { $parsed } else { $null } }
    Register-UiValueControl $id $Bind $OnChange 'input' $convert
    return $id
}

function New-UI4METextArea {
    [CmdletBinding()]
    param([string]$Label = '', [AllowNull()][object]$Value = '', [AllowNull()][object]$Bind,
          [ValidateRange(1, 100)][int]$Rows = 4, [scriptblock]$OnChange, [string]$Placeholder = '', [string]$Class = '')
    $id = New-UiId 'textarea'
    $initial = if ($null -ne $Bind) { Get-UiValue $Bind } else { Get-UiValue $Value }
    $ph = if ($Placeholder) { ' placeholder="{0}"' -f (ConvertTo-UiHtml $Placeholder) } else { '' }
    Add-UiField $id $Label $null ('<textarea id="{0}" {1} rows="{2}"{3}>{4}</textarea>' -f $id, (Get-UiClassAttr 'u4-input u4-textarea' $Class), $Rows, $ph, (ConvertTo-UiHtml $initial))
    Register-UiValueControl $id $Bind $OnChange 'input' $null
    return $id
}

function New-UI4MECheckbox {
    <# .SYNOPSIS Labelled checkbox (or -Switch toggle) bound to a [bool] state. #>
    [CmdletBinding()]
    param([string]$Label = '', [bool]$Checked = $false, [AllowNull()][object]$Bind,
          [scriptblock]$OnChange, [switch]$Switch, [AllowNull()][object]$Disabled = $false, [string]$Class = '')
    $id = New-UiId 'check'
    $isChecked = if ($null -ne $Bind) { [bool](Get-UiValue $Bind) } else { $Checked }
    $flags = ''
    if ($isChecked) { $flags += ' checked' }
    if ([bool](Get-UiValue $Disabled)) { $flags += ' disabled' }
    if ($Switch) { $flags += ' role="switch"' }
    $extra = if ($Switch) { "u4-switch $Class" } else { $Class }
    Add-UiMarkup ('<label {0}><input id="{1}" type="checkbox"{2}><span>{3}</span></label>' -f (Get-UiClassAttr 'u4-check' $extra), $id, $flags, (ConvertTo-UiHtml $Label))
    if ($null -ne $Bind) {
        if (-not (Test-UiState $Bind)) { throw '-Bind takes a state from New-UI4MEState' }
        $null = Register-UiBinding $Bind $id 'Set-UiCheckedBinding'
    }
    if ($null -ne $Bind -or $OnChange) {
        $handler = New-UiCallable 'Invoke-UiCheckEvent' ([pscustomobject]@{ Id = $id; State = $Bind; Callback = $OnChange; Last = $isChecked })
        $null = Register-UiHandler $id 'input' $handler
        $null = Register-UiHandler $id 'change' $handler
    }
    Register-UiDisabled $id $Disabled
    return $id
}

function Invoke-UiCheckEvent {
    param($Data, $evt)
    $value = [bool](Get-UI4MEChecked -Document $script:UiBuilder.Document -Element $Data.Id)
    if ($value -eq $Data.Last) { return }  # input + change for one toggle
    $Data.Last = $value
    if ($null -ne $Data.State) { $Data.State.Set($value) }
    if ($Data.Callback) { $null = & $Data.Callback $value }
}

function ConvertTo-UiOptions {
    param([object[]]$Options)
    $result = New-Object System.Collections.ArrayList
    foreach ($option in $Options) {
        if ($option -is [System.Collections.IDictionary]) {
            [void]$result.Add([pscustomobject]@{ Value = [string]$option['Value']; Label = [string]$(if ($option.Contains('Label')) { $option['Label'] } else { $option['Value'] }) })
        } else {
            [void]$result.Add([pscustomobject]@{ Value = [string]$option; Label = [string]$option })
        }
    }
    $values = @($result | ForEach-Object { $_.Value })
    if (@($values | Select-Object -Unique).Count -ne $values.Count) { throw 'Option values must be unique' }
    return , $result
}

function New-UI4MESelect {
    <# .SYNOPSIS Drop-down choice. -Options are strings or @{Value=..;Label=..}. -Bind holds the chosen value. #>
    [CmdletBinding()]
    param([string]$Label = '', [object[]]$Options = @(), [AllowNull()][object]$Bind, [AllowNull()][object]$Value,
          [scriptblock]$OnChange, [string]$Class = '')
    $id = New-UiId 'select'
    $opts = ConvertTo-UiOptions $Options
    $initial = if ($null -ne $Bind) { [string](Get-UiValue $Bind) } elseif ($null -ne $Value) { [string]$Value } elseif ($opts.Count) { $opts[0].Value } else { '' }
    $sb = New-Object System.Text.StringBuilder
    foreach ($option in $opts) {
        $selected = if ($option.Value -eq $initial) { ' selected' } else { '' }
        [void]$sb.Append(('<option value="{0}"{1}>{2}</option>' -f (ConvertTo-UiHtml $option.Value), $selected, (ConvertTo-UiHtml $option.Label)))
    }
    Add-UiField $id $Label $null ('<select id="{0}" {1}>{2}</select>' -f $id, (Get-UiClassAttr 'u4-select' $Class), $sb.ToString())
    Register-UiValueControl $id $Bind $OnChange 'change' $null
    return $id
}

function New-UI4MERadio {
    <# .SYNOPSIS Radio group bound to the chosen option value. #>
    [CmdletBinding()]
    param([string]$Label = '', [Parameter(Mandatory)][object[]]$Options, [AllowNull()][object]$Bind,
          [scriptblock]$OnChange, [switch]$Horizontal)
    $id = New-UiId 'radio'
    $opts = ConvertTo-UiOptions $Options
    $initial = if ($null -ne $Bind) { [string](Get-UiValue $Bind) } else { '' }
    $cls = if ($Horizontal) { 'u4-radio-group u4-horizontal' } else { 'u4-radio-group' }
    $sb = New-Object System.Text.StringBuilder
    $ids = @{}
    $index = 0
    foreach ($option in $opts) {
        $index++
        $rid = "$id-$index"
        $ids[$rid] = $option.Value
        $checked = if ($option.Value -eq $initial) { ' checked' } else { '' }
        [void]$sb.Append(('<label class="u4-check"><input type="radio" id="{0}" name="{1}" value="{2}"{3}><span>{4}</span></label>' -f
                          $rid, $id, (ConvertTo-UiHtml $option.Value), $checked, (ConvertTo-UiHtml $option.Label)))
    }
    Add-UiMarkup ('<fieldset class="u4-field" id="{0}"><legend class="u4-label">{1}</legend><div class="{2}" role="radiogroup">{3}</div></fieldset>' -f
                  $id, (ConvertTo-UiHtml $Label), $cls, $sb.ToString())
    $data = [pscustomobject]@{ Map = $ids; State = $Bind; Callback = $OnChange; Last = $initial }
    if ($null -ne $Bind) { $null = Register-UiBinding $Bind $id 'Set-UiRadioBinding' $data }
    foreach ($rid in $ids.Keys) {
        $handler = New-UiCallable 'Invoke-UiRadioEvent' ([pscustomobject]@{ Group = $data; Value = $ids[$rid] })
        $null = Register-UiHandler $rid 'input' $handler
        $null = Register-UiHandler $rid 'change' $handler
    }
    return $id
}

function Set-UiRadioBinding { param($ctx, $element, $value, $data)
    $data.Last = [string]$value
    foreach ($rid in $data.Map.Keys) { Set-UI4MEChecked -Document $ctx.Document -Element $rid -Checked ($data.Map[$rid] -eq [string]$value) } }

function Invoke-UiRadioEvent {
    param($Data, $evt)
    $group = $Data.Group
    if ($group.Last -eq $Data.Value) { return }
    $group.Last = $Data.Value
    if ($null -ne $group.State) { $group.State.Set($Data.Value) }
    if ($group.Callback) { $null = & $group.Callback $Data.Value }
}

function New-UI4MESlider {
    [CmdletBinding()]
    param([string]$Label = '', [double]$Min = 0, [double]$Max = 100, [double]$Step = 1, [double]$Value = 0,
          [AllowNull()][object]$Bind, [scriptblock]$OnChange)
    $id = New-UiId 'slider'
    $initial = if ($null -ne $Bind) { Get-UiValue $Bind } else { $Value }
    $inv = [System.Globalization.CultureInfo]::InvariantCulture
    Add-UiField $id $Label $null ('<input id="{0}" type="range" class="u4-slider" min="{1}" max="{2}" step="{3}" value="{4}">' -f
        $id, [System.Convert]::ToString($Min, $inv), [System.Convert]::ToString($Max, $inv), [System.Convert]::ToString($Step, $inv),
        [System.Convert]::ToString($initial, $inv))
    $convert = { param($raw) [double]::Parse($raw, [System.Globalization.CultureInfo]::InvariantCulture) }
    Register-UiValueControl $id $Bind $OnChange 'input' $convert
    return $id
}

function New-UI4MERow {
    [CmdletBinding()]
    param([Parameter(Mandatory)][scriptblock]$Content, [ValidateSet('none', 'xs', 'sm', 'md', 'lg', 'xl')][string]$Gap = 'md',
          [switch]$Wrap, [string]$Class = '', [string]$Style = '', [AllowNull()][object]$Visible)
    $cls = "u4-row u4-gap-$Gap u4-align-center"
    if ($Wrap) { $cls += ' u4-wrap' }
    Invoke-UiContainer 'div' "$cls $Class" $Style $Content $Visible
}
function New-UI4MEColumn {
    [CmdletBinding()]
    param([Parameter(Mandatory)][scriptblock]$Content, [ValidateSet('none', 'xs', 'sm', 'md', 'lg', 'xl')][string]$Gap = 'md',
          [string]$Class = '', [string]$Style = '', [AllowNull()][object]$Visible)
    Invoke-UiContainer 'div' "u4-column u4-gap-$Gap $Class" $Style $Content $Visible
}
function New-UI4MECard {
    [CmdletBinding()]
    param([Parameter(Mandatory)][scriptblock]$Content, [string]$Title,
          [ValidateSet('outlined', 'elevated', 'filled', 'plain')][string]$Variant = 'outlined',
          [string]$Class = '', [string]$Style = '', [AllowNull()][object]$Visible)
    $prefix = if ($Title) { '<h3 class="u4-heading u4-h3">{0}</h3>' -f (ConvertTo-UiHtml $Title) } else { '' }
    Invoke-UiContainer 'section' "u4-card u4-card-$Variant u4-column u4-gap-md u4-pad-lg $Class" $Style $Content $Visible $null $prefix
}
function New-UI4MEGrid {
    [CmdletBinding()]
    param([Parameter(Mandatory)][scriptblock]$Content, [ValidateRange(1, 12)][int]$Columns = 2, [string]$MinWidth,
          [string]$Class = '', [string]$Style = '')
    $template = if ($MinWidth) { "grid-template-columns: repeat(auto-fit, minmax($MinWidth, 1fr));" } else { "grid-template-columns: repeat($Columns, minmax(0, 1fr));" }
    Invoke-UiContainer 'div' "u4-grid u4-gap-md $Class" ($template + $Style) $Content
}
function New-UI4METoolbar {
    [CmdletBinding()]
    param([Parameter(Mandatory)][scriptblock]$Content, [string]$Class = '')
    Invoke-UiContainer 'div' "u4-toolbar u4-row u4-gap-sm $Class" '' $Content $null @{ role = 'toolbar' }
}
function New-UI4MEScroll {
    [CmdletBinding()]
    param([Parameter(Mandatory)][scriptblock]$Content, [string]$Height = '300px')
    if ($Height -notmatch '^[0-9.]+(px|em|rem|vh|%)$') { throw 'Height must be a CSS length such as 300px' }
    Invoke-UiContainer 'div' 'u4-scroll u4-column u4-gap-sm' "max-height:$Height;" $Content
}
function New-UI4MEForm {
    <# .SYNOPSIS A form; -OnSubmit receives the form data (native validation runs first). #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][scriptblock]$Content, [scriptblock]$OnSubmit)
    $id = Invoke-UiContainer 'form' 'u4-form u4-column u4-gap-md' '' $Content
    if ($OnSubmit) {
        Add-UiSetup (New-UiCallable 'Initialize-UiPrevent' ([pscustomobject]@{ Id = $id; Event = 'submit' }))
        $null = Register-UiHandler $id 'submit' (New-UiCallable 'Invoke-UiFormSubmit' ([pscustomobject]@{ Id = $id; Submit = $OnSubmit }))
    }
    return $id
}
function Initialize-UiPrevent { param($Data, $ctx)
    $null = Set-UI4MEPreventDefault -Document $ctx.Document -Element $Data.Id -EventType $Data.Event }

function Invoke-UiFormSubmit {
    param($Data, $evt)
    $form = Get-UI4MEFormData -Document $script:UiBuilder.Document -Form $Data.Id
    $null = & $Data.Submit $form $evt
}

function New-UI4MEDivider {
    [CmdletBinding()] param([switch]$Vertical)
    $id = New-UiId 'divider'
    $cls = if ($Vertical) { 'u4-divider u4-divider-vertical' } else { 'u4-divider' }
    Add-UiMarkup ('<hr id="{0}" class="{1}">' -f $id, $cls)
    return $id
}
function New-UI4MESpacer {
    [CmdletBinding()] param()
    $id = New-UiId 'spacer'
    Add-UiMarkup ('<div class="u4-spacer" id="{0}" aria-hidden="true"></div>' -f $id)
    return $id
}
function New-UI4MEBadge {
    [CmdletBinding()]
    param([AllowNull()][object]$Text, [ValidateSet('default', 'info', 'success', 'warning', 'danger')][string]$Tone = 'default')
    $id = New-UiId 'badge'
    $toneClass = if ($Tone -ne 'default') { " u4-tone-$Tone" } else { '' }
    Add-UiMarkup ('<span id="{0}" class="u4-badge{1}">{2}</span>' -f $id, $toneClass, (ConvertTo-UiHtml (Get-UiValue $Text)))
    if (Test-UiState $Text) {
        $null = Register-UiBinding $Text $id 'Set-UiTextBinding'
    }
    return $id
}
function New-UI4MEHtml {
    <# .SYNOPSIS Inserts TRUSTED markup verbatim. Never pass user input; use New-UI4METext for that. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Markup)
    Add-UiMarkup $Markup
}
function New-UI4MEImage {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Source, [string]$Alt = '', [string]$Width, [string]$Height, [string]$Class = '')
    $id = New-UiId 'image'
    $size = ''
    if ($Width) { $size += ' width="{0}"' -f (ConvertTo-UiHtml $Width) }
    if ($Height) { $size += ' height="{0}"' -f (ConvertTo-UiHtml $Height) }
    Add-UiMarkup ('<img id="{0}" src="{1}" alt="{2}" {3}{4}>' -f $id, (ConvertTo-UiHtml $Source), (ConvertTo-UiHtml $Alt), (Get-UiClassAttr 'u4-image' $Class), $size)
    return $id
}
function New-UI4MELink {
    <# .SYNOPSIS A link. -Href opens in the OS default handler (http/https/mailto/file); -OnClick runs in-app. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Text, [string]$Href, [scriptblock]$OnClick)
    $id = New-UiId 'link'
    $hrefAttr = if ($Href) { ' href="{0}"' -f (ConvertTo-UiHtml $Href) } else { ' href="#"' }
    Add-UiMarkup ('<a id="{0}" class="u4-link"{1}>{2}</a>' -f $id, $hrefAttr, (ConvertTo-UiHtml $Text))
    Add-UiSetup (New-UiCallable 'Initialize-UiPrevent' ([pscustomobject]@{ Id = $id; Event = 'click' }))
    $null = Register-UiHandler $id 'click' (New-UiCallable 'Invoke-UiLink' ([pscustomobject]@{ Href = $Href; Callback = $OnClick }))
    return $id
}
function Invoke-UiLink {
    param($Data, $evt)
    if ($Data.Callback) { $null = & $Data.Callback $evt }
    elseif ($Data.Href) { $null = Open-UI4MEExternal -Application $script:UiBuilder.App -Target $Data.Href -Window $script:UiBuilder.Window }
}

function New-UI4MECode {
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Text)
    $id = New-UiId 'code'
    Add-UiMarkup ('<pre id="{0}" class="u4-code u4-mono"><code>{1}</code></pre>' -f $id, (ConvertTo-UiHtml $Text))
    return $id
}
function New-UI4MEAlert {
    [CmdletBinding()]
    param([Parameter(Mandatory)][AllowNull()][object]$Text, [string]$Title,
          [ValidateSet('info', 'success', 'warning', 'danger')][string]$Tone = 'info', [AllowNull()][object]$Visible)
    $id = New-UiId 'alert'
    $titleMarkup = if ($Title) { '<div class="u4-alert-title">{0}</div>' -f (ConvertTo-UiHtml $Title) } else { '' }
    Add-UiMarkup ('<div id="{0}" class="u4-alert u4-alert-{1}" role="alert"{2}>{3}<div id="{0}-body">{4}</div></div>' -f
                  $id, $Tone, (Get-UiHiddenAttr $Visible), $titleMarkup, (ConvertTo-UiHtml (Get-UiValue $Text)))
    if (Test-UiState $Text) {
        $null = Register-UiBinding $Text "$id-body" 'Set-UiTextBinding'
    }
    Register-UiVisibility $id $Visible
    return $id
}
function New-UI4MEProgress {
    <# .SYNOPSIS Progress bar; -Value may be a state (0..-Max). Omit -Value for an indeterminate bar. #>
    [CmdletBinding()]
    param([AllowNull()][object]$Value, [double]$Max = 100, [string]$Label = '')
    $id = New-UiId 'progress'
    $inv = [System.Globalization.CultureInfo]::InvariantCulture
    $current = Get-UiValue $Value
    $valueAttr = if ($null -ne $current) { ' value="{0}"' -f [System.Convert]::ToString([double]$current, $inv) } else { '' }
    Add-UiMarkup ('<div class="u4-field"><label class="u4-label" for="{0}">{1}</label><progress class="u4-progress" id="{0}" max="{2}"{3}></progress></div>' -f
                  $id, (ConvertTo-UiHtml $Label), [System.Convert]::ToString($Max, $inv), $valueAttr)
    if (Test-UiState $Value) {
        $null = Register-UiBinding $Value $id 'Set-UiProgressBinding' 
    }
    return $id
}
function Set-UiProgressBinding { param($ctx, $element, $value, $data)
    if ($null -eq $value) { Set-UI4MEDocumentAttribute -Document $ctx.Document -Element $element -Name value -Remove; return }
    Set-UI4MEDocumentAttribute -Document $ctx.Document -Element $element -Name value -Value ([System.Convert]::ToString([double]$value, [System.Globalization.CultureInfo]::InvariantCulture)) }

function New-UI4MESpinner {
    [CmdletBinding()] param([string]$Label = 'Loading')
    $id = New-UiId 'spinner'
    Add-UiMarkup ('<span id="{0}" class="u4-spinner" role="status" aria-label="{1}"></span>' -f $id, (ConvertTo-UiHtml $Label))
    return $id
}
function New-UI4MEAccordion {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Title, [Parameter(Mandatory)][scriptblock]$Content, [switch]$Open)
    $id = New-UiId 'details'
    $openAttr = if ($Open) { ' open' } else { '' }
    Add-UiMarkup ('<details id="{0}" class="u4-disclosure"{1}><summary class="u4-disclosure-title">{2}</summary><div class="u4-disclosure-body u4-column u4-gap-sm">' -f
                  $id, $openAttr, (ConvertTo-UiHtml $Title))
    try { Invoke-UiBuild $Content } finally { Add-UiMarkup '</div></details>' }
    return $id
}
function New-UI4METabs {
    <#
    .SYNOPSIS
    Tabs from an ordered hashtable: [ordered]@{ 'General' = { ... }; 'Advanced' = { ... } }. -Bind holds the selected tab name.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][System.Collections.IDictionary]$Tabs, [AllowNull()][object]$Bind, [scriptblock]$OnChange)
    $id = New-UiId 'tabs'
    $names = @($Tabs.Keys)
    if ($names.Count -eq 0) { throw '-Tabs needs at least one tab' }
    $selected = if ($null -ne $Bind -and $names -contains [string](Get-UiValue $Bind)) { [string](Get-UiValue $Bind) } else { [string]$names[0] }
    $tabIds = @{}
    Add-UiMarkup ('<div class="u4-tabs u4-column u4-gap-md" id="{0}"><div class="u4-tab-list u4-row u4-gap-xs" role="tablist">' -f $id)
    $i = 0
    foreach ($name in $names) {
        $i++
        $tabIds[[string]$name] = "$id-$i"
        $isSel = ([string]$name -eq $selected)
        Add-UiMarkup ('<button type="button" class="u4-tab{0}" role="tab" id="{1}-tab" aria-controls="{1}-panel" aria-selected="{2}">{3}</button>' -f
                      $(if ($isSel) { ' u4-selected' } else { '' }), "$id-$i", $(if ($isSel) { 'true' } else { 'false' }), (ConvertTo-UiHtml $name))
    }
    Add-UiMarkup '</div>'
    foreach ($name in $names) {
        $panel = $tabIds[[string]$name]
        Add-UiMarkup ('<div class="u4-tab-panel u4-column u4-gap-md" role="tabpanel" id="{0}-panel" aria-labelledby="{0}-tab"{1}>' -f
                      $panel, $(if ([string]$name -ne $selected) { ' hidden' } else { '' }))
        try { Invoke-UiBuild $Tabs[$name] } finally { Add-UiMarkup '</div>' }
    }
    Add-UiMarkup '</div>'
    $current = New-UI4MEState -Value $selected
    $data = [pscustomobject]@{ Map = $tabIds; Current = $current; Bound = $Bind; Callback = $OnChange }
    if ($null -ne $Bind) { $null = $Bind.Subscribe((New-UiCallable 'Sync-UiTabs' $data)) }
    $null = Register-UiBinding $current $id 'Set-UiTabsBinding' $data
    foreach ($name in $names) {
        $null = Register-UiHandler "$($tabIds[[string]$name])-tab" 'click' (New-UiCallable 'Invoke-UiTabClick' ([pscustomobject]@{ Tabs = $data; Name = [string]$name }))
    }
    return $id
}
function Sync-UiTabs { param($Data, $value) if ($Data.Map.ContainsKey([string]$value)) { $Data.Current.Set([string]$value) } }

function Invoke-UiTabClick {
    param($Data, $evt)
    $Data.Tabs.Current.Set($Data.Name)
    if ($null -ne $Data.Tabs.Bound) { $Data.Tabs.Bound.Set($Data.Name) }
    if ($Data.Tabs.Callback) { $null = & $Data.Tabs.Callback $Data.Name }
}

function Set-UiTabsBinding { param($ctx, $element, $value, $data)
    $ops = New-Object System.Collections.ArrayList
    foreach ($tab in $data.Map.Keys) {
        $prefix = $data.Map[$tab]
        $on = ($tab -eq [string]$value)
        if ($on) {
            [void]$ops.Add(@{ op = 'remove_attribute'; element = "$prefix-panel"; name = 'hidden' })
            [void]$ops.Add(@{ op = 'add_class'; element = "$prefix-tab"; name = 'u4-selected' })
        } else {
            [void]$ops.Add(@{ op = 'set_attribute'; element = "$prefix-panel"; name = 'hidden'; value = '' })
            [void]$ops.Add(@{ op = 'remove_class'; element = "$prefix-tab"; name = 'u4-selected' })
        }
        [void]$ops.Add(@{ op = 'set_attribute'; element = "$prefix-tab"; name = 'aria-selected'; value = $(if ($on) { 'true' } else { 'false' }) })
    }
    Invoke-UI4MEBatch -Document $ctx.Document -Operations @($ops)
}

function New-UI4MEList {
    [CmdletBinding()]
    param([object[]]$Items = @())
    $id = New-UiId 'list'
    Add-UiMarkup ('<ul id="{0}" class="u4-list">' -f $id)
    foreach ($item in $Items) { Add-UiMarkup ('<li>{0}</li>' -f (ConvertTo-UiHtml $item)) }
    Add-UiMarkup '</ul>'
    return $id
}
function New-UI4METable {
    <# .SYNOPSIS Table of objects/hashtables. -Rows may be a state of rows; the body re-renders when it changes. #>
    [CmdletBinding()]
    param([string[]]$Columns = @(), [AllowNull()][object]$Rows = @(), [scriptblock]$OnRowClick, [string]$Key)
    $id = New-UiId 'table'
    Add-UiMarkup ('<div class="u4-table-wrap"><table id="{0}" class="u4-table"><thead><tr>' -f $id)
    foreach ($col in $Columns) { Add-UiMarkup ('<th scope="col" class="u4-th">{0}</th>' -f (ConvertTo-UiHtml $col)) }
    Add-UiMarkup ('</tr></thead><tbody id="{0}-body">{1}</tbody></table></div>' -f $id, (ConvertTo-UiTableBody $id $Columns @(Get-UiValue $Rows) $Key))
    $data = [pscustomobject]@{ Id = $id; Columns = $Columns; Rows = $Rows; Key = $Key; Callback = $OnRowClick }
    if (Test-UiState $Rows) { $null = Register-UiBinding $Rows "$id-body" 'Set-UiTableBinding' $data }
    if ($OnRowClick) { $null = Register-UiHandler "$id-body" 'click' (New-UiCallable 'Invoke-UiRowClick' $data) }
    return $id
}
function Set-UiTableBinding { param($ctx, $element, $value, $data)
    Set-UI4MEDocumentHtml -Document $ctx.Document -Element $element -Html (ConvertTo-UiTableBody $data.Id $data.Columns @($value) $data.Key) }

function Invoke-UiRowClick {
    param($Data, $evt)
    foreach ($p in @($evt.path)) {
        if ([string]$p -match ('^' + [regex]::Escape($Data.Id) + '-r(\d+)$')) {
            $row = @(Get-UiValue $Data.Rows)[[int]$Matches[1]]
            $null = & $Data.Callback $row $evt
            return
        }
    }
}

function ConvertTo-UiTableBody {
    param([string]$Id, [string[]]$Columns, [object[]]$Rows, [string]$Key)
    $sb = New-Object System.Text.StringBuilder
    if ($Rows.Count -eq 0) {
        [void]$sb.Append(('<tr><td class="u4-table-empty" colspan="{0}">No rows</td></tr>' -f [Math]::Max(1, $Columns.Count)))
        return $sb.ToString()
    }
    $index = 0
    foreach ($row in $Rows) {
        [void]$sb.Append(('<tr id="{0}-r{1}">' -f $Id, $index))
        foreach ($column in $Columns) {
            $v = $null
            if ($row -is [System.Collections.IDictionary]) { $v = $row[$column] }
            elseif ($null -ne $row -and $null -ne $row.PSObject.Properties[$column]) { $v = $row.$column }
            [void]$sb.Append(('<td>{0}</td>' -f (ConvertTo-UiHtml $v)))
        }
        [void]$sb.Append('</tr>')
        $index++
    }
    return $sb.ToString()
}
function New-UI4MEDialog {
    <# .SYNOPSIS An in-window <dialog>; open with Show-UI4MEUiDialog, close with Close-UI4MEUiDialog. #>
    [CmdletBinding()]
    param([string]$Title = '', [Parameter(Mandatory)][scriptblock]$Content, [scriptblock]$OnClose)
    $id = New-UiId 'dialog'
    Add-UiMarkup ('<dialog id="{0}" class="u4-dialog" aria-labelledby="{0}-title"><h2 class="u4-dialog-title" id="{0}-title">{1}</h2><div class="u4-dialog-body u4-column u4-gap-md">' -f
                  $id, (ConvertTo-UiHtml $Title))
    try { Invoke-UiBuild $Content } finally { Add-UiMarkup '</div></dialog>' }
    if ($OnClose) { $null = Register-UiHandler $id 'close' $OnClose }
    return $id
}
function Show-UI4MEUiDialog {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Element, [switch]$NonModal)
    $ctx = Assert-UiBuilder
    Show-UI4MEHtmlDialog -Document $ctx.Document -Element $Element -Modal (-not $NonModal)
}
function Close-UI4MEUiDialog {
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Element, [string]$ReturnValue = '')
    $ctx = Assert-UiBuilder
    Show-UI4MEHtmlDialog -Document $ctx.Document -Element $Element -Close -ReturnValue $ReturnValue
}
function Show-UI4MEUiToast {
    <# .SYNOPSIS An in-window notification that dismisses itself after -Seconds (0 = stays until closed). #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Text, [ValidateSet('info', 'success', 'warning', 'danger')][string]$Tone = 'info',
          [ValidateRange(0, 3600)][double]$Seconds = 4)
    $ctx = Assert-UiBuilder
    if (-not $ctx.Document) { throw 'Show-UI4MEUiToast needs a running application (call it from a callback or -OnReady).' }
    $ctx.Sequence = [int]$ctx.Sequence + 1
    $toast = 'u4ps-toast-{0}' -f $ctx.Sequence
    $html = '<div class="u4-toast u4-toast-{0}" id="{1}" role="status"><span>{2}</span><button type="button" class="u4-toast-close" id="{1}-close" aria-label="Close">&#215;</button></div>' -f
            $Tone, $toast, (ConvertTo-UiHtml $Text)
    Set-UI4MEDocumentHtml -Document $ctx.Document -Element 'u4ps-toasts' -Html $html -Position beforeend
    $data = [pscustomobject]@{ Id = $toast; Entry = $null; Removed = $false }
    $data.Entry = Register-UiHandler "$toast-close" 'click' (New-UiCallable 'Remove-UiToast' $data)
    if ($Seconds -gt 0) {
        $null = Start-UI4MEUiTimer -Milliseconds ([int]($Seconds * 1000)) -Action (New-UiCallable 'Remove-UiToast' $data)
    }
    return $toast
}
function Remove-UiToast {
    param($Data)
    if ($Data.Removed) { return }
    $Data.Removed = $true
    Remove-UiEntry $Data.Entry
    if (Find-UiElement $Data.Id) { Remove-UI4MEElement -Document $script:UiBuilder.Document -Element $Data.Id }
}

function Find-UiElement {
    param([string]$Id)
    $result = Find-UI4MEElement -Document $script:UiBuilder.Document -Selector "#$Id"
    return (@($result.ids).Count -gt 0)
}
function Remove-UiEntry {
    param($Entry)
    $ctx = $script:UiBuilder
    if ($ctx.Handlers.ContainsKey($Entry.Type) -and $ctx.Handlers[$Entry.Type].ContainsKey($Entry.Element)) {
        [void]$ctx.Handlers[$Entry.Type].Remove($Entry.Element)
    }
}

# --------------------------------------------------------------- dynamic content --

function Add-UI4MEUiContent {
    <#
    .SYNOPSIS
    Renders components at runtime into a container element (from a callback or -OnReady). Returns a handle for Remove-UI4MEUiContent.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Into, [Parameter(Mandatory)][scriptblock]$Content,
          [ValidateSet('beforeend', 'afterbegin', 'replace')][string]$Position = 'beforeend', [object[]]$ArgumentList = @())
    $ctx = Assert-UiBuilder
    if (-not $ctx.Document) { throw 'Add-UI4MEUiContent needs a running application.' }
    $handle = Invoke-UiRender $Content $ArgumentList
    if ($Position -eq 'replace') {
        Set-UI4MEDocumentHtml -Document $ctx.Document -Element $Into -Html $handle.Html
    } else {
        Set-UI4MEDocumentHtml -Document $ctx.Document -Element $Into -Html $handle.Html -Position $Position
    }
    Invoke-UiSetups $handle.Setups
    return $handle
}

function Invoke-UiRender {
    # Build markup for runtime content inside a fresh owner and wrapper element.
    param([scriptblock]$Content, [object[]]$ArgumentList, [string]$Tag = 'div', [string]$Class = 'u4-region')
    $ctx = Assert-UiBuilder
    $owner = New-UiOwner $ctx.CurrentOwner
    $target = [pscustomobject]@{ Markup = (New-Object System.Text.StringBuilder); Setups = (New-Object System.Collections.ArrayList) }
    $previousTarget = $ctx.Target; $previousOwner = $ctx.CurrentOwner
    $ctx.Target = $target; $ctx.CurrentOwner = $owner
    $ctx.Sequence = [int]$ctx.Sequence + 1
    $wrapper = 'u4ps-region-{0}' -f $ctx.Sequence
    try {
        Add-UiMarkup ('<{0} id="{1}" class="{2}">' -f $Tag, $wrapper, $Class)
        $null = & $Content @ArgumentList
        Add-UiMarkup "</$Tag>"
    } catch {
        Remove-UiOwner $owner
        throw
    } finally {
        $ctx.Target = $previousTarget; $ctx.CurrentOwner = $previousOwner
    }
    $handle = [pscustomobject]@{ Id = $wrapper; Owner = $owner; Html = $target.Markup.ToString(); Setups = $target.Setups }
    $handle.PSObject.TypeNames.Insert(0, 'UI4ME.UiContent')
    return $handle
}

function Remove-UI4MEUiContent {
    <# .SYNOPSIS Removes runtime content; its handlers, bindings, timers and tasks are released. #>
    [CmdletBinding()] param([Parameter(Mandatory)]$Handle)
    $ctx = Assert-UiBuilder
    if ($Handle.Owner.Disposed) { return }
    Remove-UiOwner $Handle.Owner
    if ($ctx.Document -and -not $ctx.Stopping) { Remove-UI4MEElement -Document $ctx.Document -Element $Handle.Id }
}

function New-UI4MEWhen {
    <#
    .SYNOPSIS
    Shows -Content while -Condition (a state) is true, else -Else. The visible branch is rebuilt each time it appears,
    and the hidden branch is disposed (its handlers, timers and tasks stop).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Condition, [Parameter(Mandatory)][scriptblock]$Content, [scriptblock]$Else)
    if (-not (Test-UiState $Condition)) { throw '-Condition takes a state from New-UI4MEState/New-UI4MEComputed' }
    $id = New-UiId 'when'
    $ctx = Assert-UiBuilder
    $region = [pscustomobject]@{ Current = $null }
    $branch = if ([bool]$Condition.Value) { $Content } else { $Else }
    $initial = ''
    if ($branch) {
        $region.Current = Invoke-UiRender $branch @()
        $initial = $region.Current.Html
        foreach ($setup in $region.Current.Setups) { [void]$ctx.Target.Setups.Add($setup) }
    }
    Add-UiMarkup ('<div id="{0}" class="u4-region">{1}</div>' -f $id, $initial)
    $region | Add-Member -NotePropertyName Then -NotePropertyValue $Content
    $region | Add-Member -NotePropertyName Otherwise -NotePropertyValue $Else
    $null = Register-UiBinding $Condition $id 'Set-UiWhenBinding' $region
    return $id
}

function Set-UiWhenBinding { param($ctx, $element, $value, $region)
    if ($region.Current) { Remove-UiOwner $region.Current.Owner; $region.Current = $null }
    $next = if ([bool]$value) { $region.Then } else { $region.Otherwise }
    if ($next) { $region.Current = Add-UI4MEUiContent -Into $element -Content $next -Position replace }
    else { Set-UI4MEDocumentHtml -Document $ctx.Document -Element $element -Html '' }
}

function New-UI4MEEach {
    <#
    .SYNOPSIS
    Keyed list: renders -Template once per item of -Items (a state holding an array). Items are matched by -Key:
    unchanged keys keep their DOM (focus, typed text, scroll); removed keys are disposed; reorders move nodes.
    .EXAMPLE
    New-UI4MEEach -Items $todos -Key id -Template { param($item) New-UI4METext -Text $item.title }
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object]$Items, [Parameter(Mandatory)][string]$Key,
          [Parameter(Mandatory)][scriptblock]$Template, [scriptblock]$Empty)
    if (-not (Test-UiState $Items)) { throw '-Items takes a state holding an array' }
    $id = New-UiId 'each'
    $ctx = Assert-UiBuilder
    $rendered = [ordered]@{}
    $sb = New-Object System.Text.StringBuilder
        foreach ($item in @($Items.Value)) {
        $k = [string](Get-UiItemKey $item $Key)
        if ($rendered.Contains($k)) { throw "Duplicate key '$k' in New-UI4MEEach" }
        $handle = Invoke-UiRender $Template @(, $item)
        $rendered[$k] = $handle
        [void]$sb.Append($handle.Html)
        foreach ($setup in $handle.Setups) { [void]$ctx.Target.Setups.Add($setup) }
    }
    $emptyId = "$id-empty"
    $emptyMarkup = ''
    if ($Empty) {
        $emptyHandle = Invoke-UiRender $Empty @()
        $emptyMarkup = '<div id="{0}"{1}>{2}</div>' -f $emptyId, $(if ($rendered.Count) { ' hidden' } else { '' }), $emptyHandle.Html
        foreach ($setup in $emptyHandle.Setups) { [void]$ctx.Target.Setups.Add($setup) }
    }
    Add-UiMarkup ('<div id="{0}" class="u4-column u4-gap-sm">{1}</div>{2}' -f $id, $sb.ToString(), $emptyMarkup)
    $data = [pscustomobject]@{ Rendered = $rendered; Key = $Key; Template = $Template; EmptyId = $(if ($Empty) { $emptyId } else { $null }) }
    $null = Register-UiBinding $Items $id 'Set-UiEachBinding' $data
    return $id
}

function Set-UiEachBinding { param($c, $element, $value, $data)
    $rendered = $data.Rendered
    $next = [ordered]@{}
    foreach ($item in @($value)) {
        $k = [string](Get-UiItemKey $item $data.Key)
        if ($next.Contains($k)) { throw "Duplicate key '$k' in New-UI4MEEach" }
        $next[$k] = $item
    }
    $ops = New-Object System.Collections.ArrayList
    foreach ($k in @($rendered.Keys)) {
        if (-not $next.Contains($k)) {
            Remove-UiOwner $rendered[$k].Owner
            [void]$ops.Add(@{ op = 'remove_element'; element = $rendered[$k].Id })
            $rendered.Remove($k)
        }
    }
    $setups = New-Object System.Collections.ArrayList
    foreach ($k in @($next.Keys)) {
        if (-not $rendered.Contains($k)) {
            $handle = Invoke-UiRender $data.Template @(, $next[$k])
            $rendered[$k] = $handle
            [void]$ops.Add(@{ op = 'insert_html'; element = $element; position = 'beforeend'; html = $handle.Html })
            foreach ($setup in $handle.Setups) { [void]$setups.Add($setup) }
        } else {
            [void]$ops.Add(@{ op = 'move_element'; element = $rendered[$k].Id; target = $element; position = 'beforeend' })
        }
    }
    # Keep the bookkeeping order equal to the DOM order.
    $ordered = [ordered]@{}
    foreach ($k in @($next.Keys)) { $ordered[$k] = $rendered[$k] }
    $rendered.Clear()
    foreach ($k in @($ordered.Keys)) { $rendered[$k] = $ordered[$k] }
    if ($data.EmptyId) {
        if ($next.Count) { [void]$ops.Add(@{ op = 'set_attribute'; element = $data.EmptyId; name = 'hidden'; value = '' }) }
        else { [void]$ops.Add(@{ op = 'remove_attribute'; element = $data.EmptyId; name = 'hidden' }) }
    }
    for ($i = 0; $i -lt $ops.Count; $i += 1000) {
        $last = [Math]::Min($ops.Count, $i + 1000) - 1
        Invoke-UI4MEBatch -Document $c.Document -Operations @($ops[$i..$last])
    }
    Invoke-UiSetups $setups
}

function Get-UiItemKey {
    param($Item, [string]$Key)
    if ($Item -is [System.Collections.IDictionary]) { return $Item[$Key] }
    if ($null -ne $Item -and $null -ne $Item.PSObject.Properties[$Key]) { return $Item.$Key }
    throw "Item has no key property '$Key'"
}

# --------------------------------------------------------------------- styles --

function Add-UI4MEUiCss {
    <# .SYNOPSIS Adds trusted application CSS after the theme (before or after the window opens). #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Css)
    $ctx = Assert-UiBuilder
    if ($null -ne $ctx.Document) { return (Add-UI4MEStylesheet -Document $ctx.Document -Css $Css) }
    $ctx.Css = [string]$ctx.Css + "`n" + $Css
}

function Set-UI4MEUiTheme {
    <#
    .SYNOPSIS
    -Css replaces the whole visual theme (structural CSS stays); -ColorScheme picks light/dark/system;
    -Reset restores the bundled theme.
    #>
    [CmdletBinding(DefaultParameterSetName = 'Css')]
    param([Parameter(ParameterSetName = 'Css', Mandatory)][string]$Css,
          [Parameter(ParameterSetName = 'Scheme', Mandatory)][ValidateSet('light', 'dark', 'system')][string]$ColorScheme,
          [Parameter(ParameterSetName = 'Reset', Mandatory)][switch]$Reset)
    $ctx = Assert-UiBuilder
    if ($PSCmdlet.ParameterSetName -eq 'Scheme') {
        $ctx.Theme = $ColorScheme
        if ($ctx.Document) { $null = Set-UI4MEEnvironment -Document $ctx.Document -ColorScheme $ColorScheme }
        return
    }
    $visual = if ($Reset) { Get-Content -LiteralPath (Join-Path $script:AssetPath 'theme.css') -Raw -Encoding UTF8 } else { $Css }
    if ($null -eq $ctx.Document) { $ctx.VisualCss = $visual }
    else { $null = Set-UI4MEStylesheet -Document $ctx.Document -Sheet $ctx.ThemeSheet -Css $visual }
}

# -------------------------------------------------------------------- settings --

function Get-UiSettingsFile {
    $ctx = Assert-UiBuilder
    $windows = ($PSVersionTable.PSEdition -eq 'Desktop') -or ((Get-Variable -Name IsWindows -ErrorAction SilentlyContinue) -and $IsWindows)
    if ($windows) {
        $base = if ($env:APPDATA) { $env:APPDATA } else { Join-Path $HOME 'AppData\Roaming' }
        $dir = Join-Path (Join-Path $base 'UI4ME') $ctx.AppId
    } else {
        $base = if ($env:XDG_CONFIG_HOME) { $env:XDG_CONFIG_HOME } else { Join-Path $HOME '.config' }
        $dir = Join-Path (Join-Path $base 'ui4me') $ctx.AppId
    }
    return (Join-Path $dir 'settings.json')
}

function Get-UiSettings {
    $ctx = Assert-UiBuilder
    if ($null -ne $ctx.Settings) { return $ctx.Settings }
    $table = [ordered]@{}
    $file = Get-UiSettingsFile
    if (Test-Path -LiteralPath $file) {
        try {
            if ((Get-Item -LiteralPath $file).Length -gt 1MB) { throw 'settings file is larger than 1 MiB' }
            $parsed = [System.IO.File]::ReadAllText($file) | ConvertFrom-Json -ErrorAction Stop
            if ($parsed -isnot [System.Management.Automation.PSCustomObject]) { throw 'settings file must contain a JSON object' }
            foreach ($p in $parsed.PSObject.Properties) { $table[$p.Name] = $p.Value }
        } catch {
            Move-Item -LiteralPath $file -Destination ($file + '.corrupt') -Force -ErrorAction SilentlyContinue
            Write-UiError $_ "settings $file"
        }
    }
    $ctx.Settings = $table
    return $table
}

function Get-UI4MEUiSetting {
    <#
    .SYNOPSIS
    Reads a persistent per-user setting of this app (same settings.json as Python's app.settings).
    .DESCRIPTION
    Stored in %APPDATA%\UI4ME\<AppId>\settings.json (Windows) or ~/.config/ui4me/<AppId>/settings.json (Linux).
    Invoke-UI4MEApp -AppId sets the folder (default: derived from -Title).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Name, [AllowNull()][object]$Default)
    $table = Get-UiSettings
    if ($table.Contains($Name)) { return $table[$Name] }
    return $Default
}

function Set-UI4MEUiSetting {
    <# .SYNOPSIS Stores a persistent setting (JSON-compatible value) atomically. -Remove deletes it. #>
    [CmdletBinding(DefaultParameterSetName = 'Set')]
    param([Parameter(Mandatory)][string]$Name, [Parameter(ParameterSetName = 'Set', Mandatory)][AllowNull()][object]$Value,
          [Parameter(ParameterSetName = 'Remove', Mandatory)][switch]$Remove)
    if (-not $Name -or $Name.Length -gt 200) { throw 'Setting names must be 1-200 characters' }
    $table = Get-UiSettings
    if ($Remove) { if (-not $table.Contains($Name)) { return }; $table.Remove($Name) } else { $table[$Name] = $Value }
    $json = ConvertTo-Json -InputObject ([pscustomobject]$table) -Depth 10
    if ([System.Text.Encoding]::UTF8.GetByteCount($json) -gt 1MB) { throw 'Settings are limited to 1 MiB' }
    $file = Get-UiSettingsFile
    $dir = Split-Path -Parent $file
    if (-not (Test-Path -LiteralPath $dir)) { $null = New-Item -ItemType Directory -Path $dir -Force }
    $tmp = Join-Path $dir ('.settings-' + [guid]::NewGuid().ToString('N') + '.tmp')
    [System.IO.File]::WriteAllText($tmp, $json, (New-Object System.Text.UTF8Encoding($false)))
    if (Test-Path -LiteralPath $file) { [System.IO.File]::Replace($tmp, $file, [NullString]::Value) }  # [NullString]: $null would become ""
    else { [System.IO.File]::Move($tmp, $file) }
}

# --------------------------------------------------------------------- desktop --

function Show-UI4MEUiFileDialog {
    <#
    .SYNOPSIS
    Native open/save/folder dialog. Returns a path (an array with -Multiple) or $null when cancelled.
    .DESCRIPTION
    The window stays responsive while the dialog is open; a user close still asks -OnCloseRequest.
    -Filters: @{ 'Images' = @('png','jpg') }.
    #>
    [CmdletBinding()]
    param([ValidateSet('Open', 'Save', 'Folder')][string]$Kind = 'Open', [string]$Title, [string]$Directory,
          [string]$FileName, [hashtable]$Filters, [switch]$Multiple)
    $ctx = Assert-UiBuilder
    if (-not $ctx.Window) { throw 'File dialogs need a running application.' }
    $params = @{ Window = $ctx.Window; Kind = @{ Open = 'OpenFiles'; Save = 'SaveFile'; Folder = 'ChooseFolder' }[$Kind] }
    if ($Title) { $params.Title = $Title }
    if ($Directory) { $params.Directory = $Directory }
    if ($FileName) { $params.FileName = $FileName }
    if ($Kind -eq 'Open') { $params.Multiple = [bool]$Multiple }
    if ($Filters -and $Kind -ne 'Folder') {
        $params.Filters = @($Filters.Keys | ForEach-Object { @{ name = [string]$_; extensions = @($Filters[$_]) } })
    }
    $result = Show-UI4MEFileDialog @params
    $paths = @()
    if ($null -ne $result -and $result.PSObject.Properties['paths'] -and $null -ne $result.paths) { $paths = @($result.paths) }
    if ($paths.Count -eq 0) { return $null }
    if ($Multiple) { return , $paths }
    return [string]$paths[0]
}

function Start-UI4MEUiScript {
    <#
    .SYNOPSIS
    Runs a PowerShell UI4ME script through the UI4ME.Core native host (writes a short-lived app manifest).
    .PARAMETER WindowsPowerShell
    On Windows, run the backend with Windows PowerShell 5.1 (powershell.exe) instead of this PowerShell.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path,
          [string]$Title, [string]$AppId = 'org.ui4me.UserApp', [switch]$WindowsPowerShell, [switch]$NoWait,
          [switch]$Headless)
    Import-Module UI4ME.Core -ErrorAction Stop
    $source = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    if ($AppId -notmatch '^[A-Za-z][A-Za-z0-9_.-]*$') { throw 'AppId may contain only ASCII letters, digits, dots, hyphens and underscores' }
    $appTitle = if ($Title) { $Title } else { [System.IO.Path]::GetFileNameWithoutExtension($source) }
    if ($WindowsPowerShell -or $PSVersionTable.PSEdition -eq 'Desktop') {
        if (-not (Test-Path -LiteralPath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'))) {
            throw 'Windows PowerShell 5.1 is not available'
        }
        # Bare name on purpose: UI4ME.Core 1.0 spawns an absolute program through its
        # canonical \\?\ path, from which Windows PowerShell 5.1 (.NET Framework) cannot start.
        $program = 'powershell.exe'
    } else {
        $program = (Get-Process -Id $PID).Path
    }
    if (-not $program) { throw 'Could not resolve the PowerShell executable' }
    $temp = Join-Path ([System.IO.Path]::GetTempPath()) ('ui4me-ps-' + [guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $temp -Force
    $manifest = Join-Path $temp 'app.toml'
    $q = { param($s) '"' + ([string]$s).Replace('\', '\\').Replace('"', '\"') + '"' }
    $toml = @(
        '[app]', ('id = ' + (& $q $AppId)), ('name = ' + (& $q $appTitle)), 'version = "2.0.0"', '',
        '[backend]', ('program = ' + (& $q $program)),
        ('args = ["-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ' + (& $q $source) + ']'),
        ('cwd = ' + (& $q (Split-Path -Parent $source))), '',
        '[host]', 'startup_timeout_ms = 30000', 'shutdown_timeout_ms = 5000', 'max_windows = 16', 'instance = "multiple"'
    ) -join "`n"
    if ($toml -match '[\x00-\x08\x0b-\x1f]') { throw 'Control characters are not allowed in the manifest values' }
    [System.IO.File]::WriteAllText($manifest, $toml + "`n", (New-Object System.Text.UTF8Encoding($false)))
    if ($Headless) {
        # Test mode: the real host without a desktop window (no native input, focus or dialogs).
        try {
            & (Get-UI4MEHostPath) run --headless --app $manifest
            if ($LASTEXITCODE -ne 0) { throw "UI4ME host exited with code $LASTEXITCODE" }
        } finally { Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue }
        return
    }
    if ($NoWait) { return (Start-UI4MEHost -Manifest $manifest -NoWait) }
    try { Start-UI4MEHost -Manifest $manifest }
    finally { Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue }
}

Export-ModuleMember -Function @(
    'Invoke-UI4MEApp', 'Stop-UI4MEUiApp', 'Wait-UI4MEUi', 'Get-UI4MEUiContext', 'Get-UI4MEUiDiagnostics',
    'New-UI4MEState', 'New-UI4MEComputed',
    'Start-UI4MEUiTimer', 'Stop-UI4MEUiTimer', 'Start-UI4MEUiTask', 'Stop-UI4MEUiTask',
    'New-UI4METext', 'New-UI4MEHeading', 'New-UI4MEButton', 'New-UI4MEInput', 'New-UI4MENumber', 'New-UI4METextArea',
    'New-UI4MECheckbox', 'New-UI4MESelect', 'New-UI4MERadio', 'New-UI4MESlider', 'New-UI4MEDate', 'New-UI4METime', 'New-UI4MEColor',
    'New-UI4MERow', 'New-UI4MEColumn', 'New-UI4MECard', 'New-UI4MEGrid', 'New-UI4METoolbar', 'New-UI4MEScroll',
    'New-UI4MEForm', 'New-UI4MEDivider', 'New-UI4MESpacer', 'New-UI4MEBadge', 'New-UI4MEHtml', 'New-UI4MEImage',
    'New-UI4MELink', 'New-UI4MECode', 'New-UI4MEAlert', 'New-UI4MEProgress', 'New-UI4MESpinner', 'New-UI4MEAccordion',
    'New-UI4METabs', 'New-UI4MEList', 'New-UI4METable', 'New-UI4MEDialog', 'Show-UI4MEUiDialog', 'Close-UI4MEUiDialog',
    'Show-UI4MEUiToast', 'Add-UI4MEUiContent', 'Remove-UI4MEUiContent', 'New-UI4MEWhen', 'New-UI4MEEach',
    'Add-UI4MEUiCss', 'Set-UI4MEUiTheme', 'Show-UI4MEUiFileDialog', 'Start-UI4MEUiScript',
    'Get-UI4MEUiSetting', 'Set-UI4MEUiSetting'
)
