# UI Automation probe of a Core window (screen-reader bridge, Core 0.4 + 0.5 F0504 text cases).
# Run INSIDE an interactive desktop session:
#   pwsh -File uia_probe.ps1 -Python <python.exe> -Out DIR
# The python must import the ui4me package under test. Reads the tree as a screen reader does,
# invokes a button, then reads text, moves the selection and sets a value through TextPattern and
# ValuePattern. Writes DIR\uia.json. Automated; not a person.
param(
    [Parameter(Mandatory)][string] $Python,
    [Parameter(Mandatory)][string] $Out
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$app = @'
import json, sys
from ui4me import App
state = {"clicks": 0, "values": {}}
def save():
    open(sys.argv[1], "w", encoding="utf-8").write(json.dumps(state))
with App(app_id="org.ui4me.uiaprobe") as app:
    w = app.open("""<h1>Probe heading</h1><button id="go">Press me</button>
      <label for="name">Your name</label><input id="name" value="Ada">
      <label for="notes">Notes</label><textarea id="notes" style="width:300px;height:80px">Line one
line two</textarea>
      <label><input id="ok" type="checkbox" checked> Agree</label><a href="#x">A link</a>
      <button aria-expanded="false">Menu</button><p style="display:none">Hidden text</p>""", title="ui4me uia probe", width=500, height=360)
    def click(_):
        state["clicks"] += 1
        save()
    def edited(e):
        state["values"][e["element"]] = e.get("value")
        save()
    w.on("click", click, element="go")
    w.on("input", edited)
    app.timer(60000, lambda _: app.stop())
    app.run()
'@
$script = Join-Path $Out 'uia_app.py'; $statePath = Join-Path $Out 'uia_state.json'
Remove-Item $statePath -ErrorAction SilentlyContinue
Set-Content -LiteralPath $script -Value $app -Encoding utf8
$p = Start-Process -FilePath $Python -ArgumentList @($script, $statePath) -PassThru -RedirectStandardError (Join-Path $Out 'uia_app.err.log')
$cases = [ordered]@{}
$details = [ordered]@{}
function State { try { Get-Content -Raw -Encoding utf8 $statePath | ConvertFrom-Json -AsHashtable } catch { @{} } }
function Poll([scriptblock] $get, $want, [double] $seconds = 5) {
    $deadline = [DateTime]::UtcNow.AddSeconds($seconds); $got = $null
    while ([DateTime]::UtcNow -lt $deadline) { try { $got = & $get } catch { $got = "error: $($_.Exception.Message)" }; if ($got -ceq $want) { return $got }; Start-Sleep -Milliseconds 200 }
    $got
}
try {
    $A = [System.Windows.Automation.AutomationElement]; $T = [System.Windows.Automation.TreeScope]
    $TP = [System.Windows.Automation.TextPattern]; $Unit = [System.Windows.Automation.Text.TextUnit]
    $End = [System.Windows.Automation.Text.TextPatternRangeEndpoint]
    $window = $null
    foreach ($i in 1..60) {
        $window = $A::RootElement.FindFirst($T::Children, [System.Windows.Automation.PropertyCondition]::new($A::NameProperty, 'ui4me uia probe'))
        if ($window) { $found = $window.FindAll($T::Descendants, [System.Windows.Automation.Condition]::TrueCondition); if ($found.Count -gt 3) { break } }
        Start-Sleep -Milliseconds 500
    }
    $all = @($window.FindAll($T::Descendants, [System.Windows.Automation.Condition]::TrueCondition))
    $items = $all | ForEach-Object { [ordered]@{ type = $_.Current.ControlType.ProgrammaticName; name = $_.Current.Name } }
    $has = { param($type, $name) @($items | Where-Object { $_.type -eq $type -and $_.name -eq $name }).Count -gt 0 }
    $cases.U01_window = [bool]$window
    $cases.U02_heading = @($items | Where-Object name -eq 'Probe heading').Count -gt 0
    $cases.U03_button = & $has 'ControlType.Button' 'Press me'
    $cases.U04_edit = & $has 'ControlType.Edit' 'Your name'
    $cases.U05_checkbox = & $has 'ControlType.CheckBox' 'Agree'
    $check = @($all | Where-Object { $_.Current.Name -eq 'Agree' })[0]
    $cases.U06_checked = $check -and $check.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Current.ToggleState -eq 'On'
    $cases.U07_link = & $has 'ControlType.Hyperlink' 'A link'
    $cases.U08_hidden_excluded = @($items | Where-Object { $_.name -like '*Hidden*' }).Count -eq 0
    $menu = @($all | Where-Object { $_.Current.Name -eq 'Menu' })[0]
    $cases.U09_expand_collapse = $menu -and $menu.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Current.ExpandCollapseState -eq 'Collapsed'
    $button = @($all | Where-Object { $_.Current.Name -eq 'Press me' })[0]
    $button.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
    foreach ($i in 1..20) { if ((State).clicks) { break }; Start-Sleep -Milliseconds 250 }
    $cases.U10_invoke_clicks = [bool](State).clicks

    # Text (0.5 F0504).
    $edit = @($all | Where-Object { $_.Current.Name -eq 'Your name' -and $_.Current.ControlType.ProgrammaticName -eq 'ControlType.Edit' })[0]
    $notes = @($all | Where-Object { $_.Current.Name -eq 'Notes' -and $_.Current.ControlType.ProgrammaticName -eq 'ControlType.Edit' })[0]
    $tp = $edit.GetCurrentPattern($TP::Pattern)
    $ntp = $notes.GetCurrentPattern($TP::Pattern)
    $details.U11 = $tp.DocumentRange.GetText(-1)
    $cases.U11_edit_text = $details.U11 -ceq 'Ada'
    $details.U12 = $ntp.DocumentRange.GetText(-1)
    $cases.U12_textarea_text = ($details.U12 -replace "`r", '') -ceq "Line one`nline two"
    # A range over characters 1..3 ("da"), selected through the pattern.
    $r = $tp.DocumentRange.Clone()
    $null = $r.MoveEndpointByRange($End::End, $r, $End::Start)
    $null = $r.MoveEndpointByUnit($End::End, $Unit::Character, 3)
    $null = $r.MoveEndpointByUnit($End::Start, $Unit::Character, 1)
    $details.U13_range = $r.GetText(-1)
    $r.Select()
    $details.U13 = Poll { @($tp.GetSelection())[0].GetText(-1) } 'da'
    $cases.U13_select_range = $details.U13_range -ceq 'da' -and $details.U13 -ceq 'da'
    $boxes = @($r.GetBoundingRectangles())
    $details.U14 = @($boxes | ForEach-Object { "$($_.X),$($_.Y),$($_.Width),$($_.Height)" })
    $cases.U14_bounding_rectangles = $boxes.Count -ge 1 -and $boxes[0].Width -gt 0 -and $boxes[0].Height -gt 0
    # Line navigation in the textarea: the second line by moving one Line unit.
    $l = $ntp.DocumentRange.Clone()
    $null = $l.MoveEndpointByRange($End::End, $l, $End::Start)
    $null = $l.Move($Unit::Line, 1)
    $null = $l.ExpandToEnclosingUnit($Unit::Line)
    $details.U15 = $l.GetText(-1)
    $cases.U15_line_navigation = ($details.U15 -replace "[`r`n]", '') -ceq 'line two'
    $edit.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue('Grace')
    $details.U16 = Poll { (State).values.name } 'Grace'
    $cases.U16_value_set = $details.U16 -ceq 'Grace' -and (Poll { $tp.DocumentRange.GetText(-1) } 'Grace') -ceq 'Grace'
    $result = [ordered]@{ status = $(if (@($cases.Values | Where-Object { -not $_ }).Count) { 'failed' } else { 'passed' }); cases = $cases; details = $details; items = $items }
}
catch { $result = [ordered]@{ status = 'failed'; error = $_.Exception.Message; at = $_.InvocationInfo.PositionMessage; cases = $cases; details = $details } }
finally { if (-not $p.HasExited) { $p.Kill() } }
[IO.File]::WriteAllText((Join-Path $Out 'uia.json'), ($result | ConvertTo-Json -Depth 5), [Text.UTF8Encoding]::new($false))
foreach ($k in $cases.Keys) { '{0,-7} {1}' -f $(if ($cases[$k]) { 'passed' } else { 'failed' }), $k }
'done' | Set-Content (Join-Path $Out 'done.txt')
