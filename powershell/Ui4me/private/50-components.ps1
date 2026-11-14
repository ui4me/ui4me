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
          [scriptblock]$OnChange, [switch]$Horizontal, [string]$Class = '')
    $id = New-UiId 'radio'
    $opts = ConvertTo-UiOptions $Options
    $initial = if ($null -ne $Bind) { [string](Get-UiValue $Bind) } else { '' }
    $cls = if ($Horizontal) { 'u4-radio-group u4-horizontal' } else { 'u4-radio-group' }
    if ($Class) { $cls += ' ' + $Class }
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
                  $id, (ConvertTo-UiHtml $Label), (ConvertTo-UiHtml $cls), $sb.ToString())
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
