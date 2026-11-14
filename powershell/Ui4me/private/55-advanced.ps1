# UI4ME 2.1 — additional high-value, Python-parity presentation and input controls.
# This file is dot-sourced by Ui4me.psm1. No compiled code, JS or Python runtime.

function New-UI4MEShell {
    <# .SYNOPSIS Semantic desktop application shell; place New-UI4MESidebar/Content/Header inside. #>
    [CmdletBinding()] param([Parameter(Mandatory)][scriptblock]$Content)
    return (Invoke-UiContainer 'div' 'u4-shell' '' $Content)
}
function New-UI4MESidebar {
    [CmdletBinding()] param([Parameter(Mandatory)][scriptblock]$Content, [string]$Title)
    $prefix = if ($Title) { '<h3 class="u4-sidebar-title">{0}</h3>' -f (ConvertTo-UiHtml $Title) } else { '' }
    return (Invoke-UiContainer 'aside' 'u4-sidebar u4-column u4-gap-sm' '' $Content $null $null $prefix)
}
function New-UI4MEContent {
    [CmdletBinding()] param([Parameter(Mandatory)][scriptblock]$Content)
    return (Invoke-UiContainer 'section' 'u4-content u4-column u4-gap-md' '' $Content)
}
function New-UI4MEHeader {
    [CmdletBinding()] param([Parameter(Mandatory)][scriptblock]$Content)
    return (Invoke-UiContainer 'header' 'u4-header u4-row u4-align-center u4-gap-md' '' $Content)
}
function New-UI4MEFooter {
    [CmdletBinding()] param([Parameter(Mandatory)][scriptblock]$Content)
    return (Invoke-UiContainer 'footer' 'u4-footer u4-row u4-gap-sm' '' $Content)
}
function New-UI4MEStatusBar {
    [CmdletBinding()] param([Parameter(Mandatory)][scriptblock]$Content)
    return (Invoke-UiContainer 'div' 'u4-statusbar u4-row u4-align-center' '' $Content $null @{ role = 'status' })
}
function New-UI4MEFieldset {
    <# .SYNOPSIS Group related fields under an accessible legend. #>
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Legend, [Parameter(Mandatory)][scriptblock]$Content)
    if (-not $Legend.Trim()) { throw 'Fieldset legend is required' }
    $prefix = '<legend class="u4-fieldset-legend">{0}</legend>' -f (ConvertTo-UiHtml $Legend)
    return (Invoke-UiContainer 'fieldset' 'u4-fieldset u4-column u4-gap-sm' '' $Content $null $null $prefix)
}
function New-UI4MEMetric {
    <# .SYNOPSIS Accessible reactive statistic / KPI card; -Value can be a state. #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Label, [AllowNull()][object]$Value, [string]$Detail = '')
    $id = New-UiId 'metric'
    $initial = Get-UiValue $Value
    Add-UiMarkup ('<section class="u4-metric" aria-label="{0}"><span class="u4-metric-label">{0}</span><strong id="{1}" class="u4-metric-value">{2}</strong><small class="u4-metric-detail">{3}</small></section>' -f (ConvertTo-UiHtml $Label), $id, (ConvertTo-UiHtml $initial), (ConvertTo-UiHtml $Detail))
    if (Test-UiState $Value) { $null = Register-UiBinding $Value $id 'Set-UiTextBinding' }
    return $id
}

function New-UI4MEEmpty {
    <# .SYNOPSIS Accessible empty state; -Action can display a button with a callback. #>
    [CmdletBinding()] param([string]$Title = 'Nothing here yet', [string]$Description = '', [string]$ActionLabel, [scriptblock]$OnAction)
    $id = New-UiId 'empty'
    Add-UiMarkup ('<section id="{0}" class="u4-state u4-empty"><h3>{1}</h3><p>{2}</p>' -f $id, (ConvertTo-UiHtml $Title), (ConvertTo-UiHtml $Description))
    if ($ActionLabel -and $OnAction) { $null = New-UI4MEButton -Text $ActionLabel -OnClick $OnAction }
    Add-UiMarkup '</section>'
    return $id
}
function New-UI4MELoading {
    <# .SYNOPSIS A status region with a spinner and an accessible loading message. #>
    [CmdletBinding()] param([string]$Text = 'Loading...')
    $id = New-UiId 'loading'
    Add-UiMarkup ('<div id="{0}" class="u4-state u4-loading" role="status"><span class="u4-spinner" aria-hidden="true"></span><span>{1}</span></div>' -f $id, (ConvertTo-UiHtml $Text))
    return $id
}

$script:UiIconPaths = @{
    plus='M12 5v14M5 12h14'; minus='M5 12h14'; check='M20 6 9 17l-5-5'
    x='M18 6 6 18M6 6l12 12'; search='m21 21-4.35-4.35M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16'
    menu='M4 7h16M4 12h16M4 17h16'; 'chevron-down'='m6 9 6 6 6-6'
    'chevron-right'='m9 18 6-6-6-6'; folder='M3 6h6l2 3h10v11H3V6'
    home='m3 10 9-7 9 7v10H3V10m6 10v-7h6v7'
    refresh='M20 11a8 8 0 1 0-2 6m2-5v-6m0 6h-6'
    info='M12 17v-5m0-5h.01M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20'
    warning='m12 2 10 19H2L12 2m0 7v5m0 4h.01'
    download='M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4'
    settings='M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7M12 2v2M12 20v2M2 12h2M20 12h2'
}
function Get-UiSvgIcon {
    param([Parameter(Mandatory)][string]$Icon, [int]$Size = 18, [string]$Label)
    if (-not $script:UiIconPaths.ContainsKey($Icon)) { throw "Unknown UI4ME icon '$Icon'" }
    if ($Size -lt 8 -or $Size -gt 128) { throw 'Icon size must be between 8 and 128 px' }
    $attributes = if ($Label) { 'role="img" aria-label="{0}"' -f (ConvertTo-UiHtml $Label) } else { 'role="presentation" aria-hidden="true"' }
    return ('<svg class="u4-icon" viewBox="0 0 24 24" width="{0}" height="{0}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" {1}><path d="{2}"></path></svg>' -f $Size, $attributes, $script:UiIconPaths[$Icon])
}
function New-UI4MEIcon {
    <# .SYNOPSIS Inline SVG icon, no external font or network requests. #>
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Name, [ValidateRange(8, 128)][int]$Size = 18, [string]$Label)
    $id = New-UiId 'icon'
    Add-UiMarkup ('<span id="{0}" class="u4-inline-icon">{1}</span>' -f $id, (Get-UiSvgIcon $Name $Size $Label))
    return $id
}
function New-UI4MEIconButton {
    <# .SYNOPSIS Icon-only button; -Label is mandatory for accessibility. #>
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Icon, [Parameter(Mandatory)][string]$Label,
      [scriptblock]$OnClick, [ValidateSet('primary', 'secondary', 'outline', 'ghost', 'danger')][string]$Variant = 'ghost',
      [AllowNull()][object]$Disabled = $false)
    if (-not $Label.Trim()) { throw 'An icon button needs a nonempty accessible -Label' }
    $id = New-UiId 'iconbutton'
    $disabledAttr = if ([bool](Get-UiValue $Disabled)) { ' disabled' } else { '' }
    Add-UiMarkup ('<button type="button" class="u4-btn u4-btn-{0} u4-icon-button" id="{1}" aria-label="{2}"{3}>{4}</button>' -f $Variant, $id, (ConvertTo-UiHtml $Label), $disabledAttr, (Get-UiSvgIcon $Icon 18 $null))
    if ($OnClick) { $null = Register-UiHandler $id 'click' $OnClick }
    Register-UiDisabled $id $Disabled
    return $id
}
function New-UI4METooltip {
    <# .SYNOPSIS CSS hover and focus tooltip for an included focusable trigger. #>
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Text, [Parameter(Mandatory)][scriptblock]$Content)
    if (-not $Text.Trim()) { throw 'Tooltip text must not be empty' }
    $id = New-UiId 'tip'
    # The trigger region is described by the tip, so assistive technology announces it.
    Add-UiMarkup ('<span class="u4-tooltip-root" id="{0}"><span class="u4-tooltip-trigger" aria-describedby="{0}-text">' -f $id)
    try { Invoke-UiBuild $Content }
    finally { Add-UiMarkup ('</span><span role="tooltip" id="{0}-text" class="u4-tooltip-text">{1}</span></span>' -f $id, (ConvertTo-UiHtml $Text)) }
    return $id
}
function New-UI4MEBreadcrumbs {
    <# .SYNOPSIS Readable path navigation label; items are displayed as text, not unsafe raw links. #>
    [CmdletBinding()] param([Parameter(Mandatory)][string[]]$Items)
    $id = New-UiId 'crumbs'
    Add-UiMarkup ('<nav id="{0}" aria-label="Breadcrumb"><ol class="u4-breadcrumbs">' -f $id)
    $index = 0
    foreach ($label in $Items) {
        $index++
        $current = if ($index -eq $Items.Count) { ' aria-current="page"' } else { '' }
        Add-UiMarkup ('<li{0}>{1}</li>' -f $current, (ConvertTo-UiHtml $label))
    }
    Add-UiMarkup '</ol></nav>'
    return $id
}

function New-UI4MESegmented {
    <# .SYNOPSIS Accessible horizontal radio group styled as segmented choices. #>
    [CmdletBinding()] param([string]$Label = 'Choose', [Parameter(Mandatory)][object[]]$Options,
      [AllowNull()][object]$Bind, [scriptblock]$OnChange)
    return (New-UI4MERadio -Label $Label -Options $Options -Bind $Bind -OnChange $OnChange -Horizontal -Class 'u4-segmented')
}

function New-UI4MEMultiSelect {
    <# .SYNOPSIS A fieldset of labelled checkboxes with state holding an array of selected values. #>
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Label, [Parameter(Mandatory)][object[]]$Options,
      [AllowNull()][object]$Bind, [object[]]$Values = @(), [scriptblock]$OnChange)
    if ($null -ne $Bind -and -not (Test-UiState $Bind)) { throw '-Bind expects New-UI4MEState' }
    $optionsData = ConvertTo-UiOptions $Options
    $initial = if ($null -ne $Bind) { @(Get-UiValue $Bind) } else { @($Values) }
    $id = New-UiId 'multi'
    $map = @{}; $last = @{}
    Add-UiMarkup ('<fieldset class="u4-fieldset u4-multiselect" id="{0}"><legend class="u4-fieldset-legend">{1}</legend><div class="u4-multiselect-options">' -f $id, (ConvertTo-UiHtml $Label))
    $index = 0
    foreach ($option in $optionsData) {
        $index++
        $eid = "$id-$index"
        $map[$eid] = $option.Value
        $selected = @($initial) -contains $option.Value
        $last[$eid] = $selected
        $checked = if ($selected) { ' checked' } else { '' }
        Add-UiMarkup ('<label class="u4-check"><input type="checkbox" id="{0}"{1}><span>{2}</span></label>' -f $eid, $checked, (ConvertTo-UiHtml $option.Label))
    }
    Add-UiMarkup '</div></fieldset>'
    $state = if ($null -ne $Bind) { $Bind } else { New-UI4MEState -Value @($initial) }
    $data = [pscustomobject]@{ Map = $map; Last = $last; State = $state; Callback = $OnChange }
    $null = Register-UiBinding $state $id 'Set-UiMultiSelectBinding' $data
    foreach ($eid in $map.Keys) {
        $handler = New-UiCallable 'Invoke-UiMultiSelectEvent' ([pscustomobject]@{ Id = $eid; Data = $data })
        $null = Register-UiHandler $eid 'input' $handler
        $null = Register-UiHandler $eid 'change' $handler
    }
    return $id
}
function Set-UiMultiSelectBinding {
    param($ctx, $Element, $Value, $Data)
    $selected = @($Value)
    foreach ($id in $Data.Map.Keys) {
        $checked = $selected -contains $Data.Map[$id]
        if ($Data.Last[$id] -eq $checked) { continue }
        $Data.Last[$id] = $checked
        $null = Set-UI4MEChecked -Document $ctx.Document -Element $id -Checked $checked
    }
}
function Invoke-UiMultiSelectEvent {
    param($Item, $Event)
    $data = $Item.Data
    $checked = [bool](Get-UI4MEChecked -Document $script:UiBuilder.Document -Element $Item.Id)
    if ($data.Last[$Item.Id] -eq $checked) { return }
    $data.Last[$Item.Id] = $checked
    $value = $data.Map[$Item.Id]
    $selected = @($data.State.Value | Where-Object { $_ -ne $value })
    if ($checked) { $selected += $value }
    $data.State.Set(@($selected))
    if ($data.Callback) { $null = & $data.Callback @($selected) }
}

function New-UI4MEResizableSplit {
    <# .SYNOPSIS Two responsive panes; a native range input adjusts the width via CSS. #>
    [CmdletBinding()] param([Parameter(Mandatory)][scriptblock]$Side, [Parameter(Mandatory)][scriptblock]$Main,
      [ValidateRange(15, 85)][int]$Percent = 35, [string]$Label = 'Resize panels')
    $id = New-UiId 'split'
    Add-UiMarkup ('<section class="u4-adjustable"><div class="u4-adjustable-controls"><label for="{0}-slider">{1}</label><input id="{0}-slider" type="range" min="15" max="85" value="{2}" aria-label="{1}"></div><div class="u4-resizable-panes" id="{0}" style="--u4-split:{2}%"><div class="u4-resizable-side">' -f $id, (ConvertTo-UiHtml $Label), $Percent)
    try { Invoke-UiBuild $Side }
    finally { Add-UiMarkup '</div><div class="u4-resizable-main">' }
    try { Invoke-UiBuild $Main }
    finally { Add-UiMarkup '</div></div></section>' }
    $data = [pscustomobject]@{ Id = $id }
    $null = Register-UiHandler "$id-slider" 'input' (New-UiCallable 'Invoke-UiResizeSplit' $data)
    return $id
}
function Invoke-UiResizeSplit {
    param($Data, $Event)
    $n = 35
    if (-not [int]::TryParse([string]$Event.value, [ref]$n)) { return }
    $n = [Math]::Max(15, [Math]::Min(85, $n))
    $null = Set-UI4MEDocumentAttribute -Document $script:UiBuilder.Document -Element $Data.Id -Name style -Value ("--u4-split:$n%")
}

function New-UI4MELog {
    <# .SYNOPSIS A bounded accessible log view. Append from the app runspace with Add-UI4MELogLine. #>
    [CmdletBinding()] param([ValidateRange(1, 5000)][int]$MaxLines = 500, [string]$Label = 'Application log')
    $ctx = Assert-UiBuilder
    $id = New-UiId 'log'
    if (-not $ctx.PSObject.Properties['UiLogs']) { $ctx | Add-Member -NotePropertyName UiLogs -NotePropertyValue @{} }
    $ctx.UiLogs[$id] = [pscustomobject]@{ Max = $MaxLines; Lines = (New-Object Collections.Generic.List[string]) }
    if ($null -ne $ctx.CurrentOwner) { [void]$ctx.CurrentOwner.Cleanups.Add((New-UiCallable 'Remove-UiLog' $id)) }
    Add-UiMarkup ('<div id="{0}" class="u4-log" role="log" aria-label="{1}" aria-live="polite" aria-relevant="additions text"></div>' -f $id, (ConvertTo-UiHtml $Label))
    return $id
}
function Remove-UiLog { param($Id) $ctx = $script:UiBuilder; if ($null -ne $ctx -and $ctx.PSObject.Properties['UiLogs']) { [void]$ctx.UiLogs.Remove($Id) } }
function Add-UI4MELogLine {
    [CmdletBinding()] param([Parameter(Mandatory)][string]$Element, [Parameter(Mandatory)][AllowEmptyString()][string]$Text,
      [ValidateSet('info', 'success', 'warning', 'danger')][string]$Level = 'info')
    $ctx = Assert-UiBuilder
    if (-not $ctx.PSObject.Properties['UiLogs'] -or -not $ctx.UiLogs.ContainsKey($Element)) { throw "Unknown UI4ME log '$Element'" }
    $log = $ctx.UiLogs[$Element]
    $line = '<div class="u4-log-line u4-log-{0}">{1}</div>' -f $Level, (ConvertTo-UiHtml $Text)
    $log.Lines.Add($line)
    if ($log.Lines.Count -gt $log.Max) { $log.Lines.RemoveAt(0) }
    if ($ctx.Document) {
        $null = Set-UI4MEDocumentHtml -Document $ctx.Document -Element $Element -Html ($log.Lines -join '')
    }
}

function New-UI4MECopyButton {
    <# .SYNOPSIS Copy plain text through the native Core clipboard; needs user interaction on Wayland. #>
    [CmdletBinding()] param([Parameter(Mandatory)][AllowEmptyString()][string]$Text, [string]$Label = 'Copy')
    $data = [pscustomobject]@{ Text = $Text }
    $id = New-UiId 'copy'
    Add-UiMarkup ('<button id="{0}" type="button" class="u4-btn u4-btn-secondary">{1}</button>' -f $id, (ConvertTo-UiHtml $Label))
    $null = Register-UiHandler $id 'click' (New-UiCallable 'Invoke-UiCopyButton' $data)
    return $id
}
function Invoke-UiCopyButton {
    param($Data, $Event)
    $ctx = Assert-UiBuilder
    $null = Set-UI4MEClipboard -Application $ctx.App -Text ([string]$Data.Text)
}
