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
