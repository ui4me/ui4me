# Keyboard/IME probe app for native input journeys (Core 0.5 F0501/F0502/F0507), PowerShell twin of
# input_probe.py: the same page, the same event log and the same command file protocol.
#   pwsh input_probe.ps1 -StatePath STATE.json -CommandsPath COMMANDS.jsonl [-Seconds N]
# Automated; not a person.
param(
    [Parameter(Mandatory)][string] $StatePath,
    [Parameter(Mandatory)][string] $CommandsPath,
    [double] $Seconds = 300
)
if (-not (Get-Module Ui4me)) { Import-Module Ui4me -ErrorAction Stop }
$StatePath = [IO.Path]::GetFullPath($StatePath)
$CommandsPath = [IO.Path]::GetFullPath($CommandsPath)
$page = @'
<!doctype html><html><head><style>
body { font: 18px sans-serif; margin: 16px; }
input, textarea { display: block; width: 520px; font-size: 20px; margin: 10px 0; padding: 4px; }
textarea { height: 120px; }
</style></head><body>
<label for=a>First</label><input id=a>
<label for=b>Second</label><input id=b>
<label for=t>Notes</label><textarea id=t></textarea>
<button id=go>Go</button>
</body></html>
'@
Invoke-Ui4meApp -ArgumentList @($page, $StatePath, $CommandsPath, $Seconds) {
    param($app, $page, $statePath, $commandsPath, $seconds)
    $fields = @('a', 'b', 't')
    $log = [Collections.Generic.List[object]]::new()
    $read = @{ offset = 0 }
    $window = $app.Open($page, 'ui4me input probe', 640, 460)

    $save = {
        if ($window.IsClosed) { return }
        $values = [ordered]@{}
        foreach ($f in $fields) { $values[$f] = $window.GetValue($f) }
        $rects = [ordered]@{}
        foreach ($e in @($fields + 'go')) { $rects[$e] = $window.GetRect($e) }
        $state = [ordered]@{ log = $log; values = $values; focus = @($window.Query(':focus')); rects = $rects; commands = $read.offset }
        $tmp = "$statePath.tmp"
        [IO.File]::WriteAllText($tmp, (ConvertTo-Json -InputObject $state -Depth 6 -Compress), [Text.UTF8Encoding]::new($false))
        Move-Item -Force -LiteralPath $tmp -Destination $statePath
    }.GetNewClosure()

    $record = {
        param($e)
        $j = $e.Json | ConvertFrom-Json
        $kind = $j.type
        if ($kind -eq 'keydown' -or $kind -eq 'keyup') {
            $entry = @($kind, $j.key, $j.code, [bool]$j.ctrl, [bool]$j.alt, [bool]$j.shift, [bool]$j.repeat)
        } elseif ($kind -eq 'input') {
            $entry = @($kind, $j.element, $j.input_type, $j.data, [bool]$j.is_composing)
        } elseif ($kind.StartsWith('composition')) {
            $entry = @($kind, $j.element, $j.data)
        } else {
            $entry = @($kind, $j.element)
        }
        $log.Add($entry)
        & $save
    }.GetNewClosure()
    foreach ($kind in 'keydown', 'keyup', 'input', 'compositionstart', 'compositionupdate', 'compositionend', 'focus', 'blur') {
        $null = $window.On($kind, $record)
    }

    $poll = {
        if (-not [IO.File]::Exists($commandsPath)) { return }
        $bytes = [IO.File]::ReadAllBytes($commandsPath)
        if ($bytes.Length -le $read.offset -or $bytes[$bytes.Length - 1] -ne 10) { return }
        $chunk = [Text.Encoding]::UTF8.GetString($bytes, $read.offset, $bytes.Length - $read.offset)
        $read.offset = $bytes.Length
        foreach ($line in $chunk -split "`n") {
            if (-not $line.Trim()) { continue }
            $c = $line | ConvertFrom-Json
            switch ($c.op) {
                'focus' { $window.Focus($c.element) }
                'set_value' { $window.SetValue($c.element, $c.value) }
                'clear' { $log.Clear(); foreach ($f in $fields) { $window.SetValue($f, '') } }
                'close' { $window.Close(); return }
                'stop' { $app.Stop(); return }
            }
        }
        & $save
    }.GetNewClosure()

    $null = $app.On('closed', { $app.Stop() }.GetNewClosure())
    $null = $app.Timer(50, $poll, $true)
    $null = $app.Timer([int]($seconds * 1000), { $app.Stop() }.GetNewClosure())
    & $save
}
