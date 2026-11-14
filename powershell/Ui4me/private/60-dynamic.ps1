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
