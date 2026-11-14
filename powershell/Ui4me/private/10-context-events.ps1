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
    # Drop the disposed owner from its parent: a long-lived item whose When branch is rebuilt
    # repeatedly must not accumulate disposed children.
    if ($null -ne $Owner.Parent -and -not $Owner.Parent.Disposed) { [void]$Owner.Parent.Children.Remove($Owner) }
}

function New-UiOwner {
    param([AllowNull()]$Parent)
    $owner = [pscustomobject]@{ Handlers = (New-Object System.Collections.ArrayList)
        Cleanups = (New-Object System.Collections.ArrayList); Children = (New-Object System.Collections.ArrayList)
        Disposed = $false; Parent = $Parent }
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
