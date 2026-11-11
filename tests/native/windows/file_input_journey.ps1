# Real-input journey for <input type=file> on Windows (Core 0.6 F0606), twin of
# tests/native/kwin/file_input_journey.py. Run INSIDE an interactive desktop session.
#   pwsh -File file_input_journey.ps1 -Out DIR -Exe <python> -Arguments <file_input_app.py --state {state} --root {root}>
# A SendInput click on the input opens the IFileDialog: Escape cancels; the typed Unicode path +
# Enter chooses the file; Space on the focused multiple input reopens it. Automated, not a person.
param(
    [Parameter(Mandatory)][string] $Out,
    [Parameter(Mandatory)][string] $Exe,
    [Parameter(Mandatory)][string[]] $Arguments
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$statePath = Join-Path $Out 'state.json'
$root = Join-Path $Out 'files'
Remove-Item -LiteralPath $statePath -ErrorAction SilentlyContinue

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Fi {
    [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] struct MOUSEINPUT { public int dx, dy; public uint data, flags, time; public IntPtr extra; }
    [StructLayout(LayoutKind.Sequential)] struct KEYBDINPUT { public ushort vk, scan; public uint flags, time; public IntPtr extra; }
    [StructLayout(LayoutKind.Explicit)] struct UNION { [FieldOffset(0)] public MOUSEINPUT mi; [FieldOffset(0)] public KEYBDINPUT ki; }
    [StructLayout(LayoutKind.Sequential)] struct INPUT { public uint type; public UNION u; }
    [DllImport("user32.dll", SetLastError = true)] static extern uint SendInput(uint n, INPUT[] inputs, int size);
    [DllImport("user32.dll")] static extern int GetSystemMetrics(int i);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    static void Send(INPUT i) { if (SendInput(1, new[] { i }, Marshal.SizeOf<INPUT>()) != 1) throw new InvalidOperationException("SendInput failed"); System.Threading.Thread.Sleep(15); }
    public static void Move(int x, int y) {
        int vx = GetSystemMetrics(76), vy = GetSystemMetrics(77), vw = GetSystemMetrics(78), vh = GetSystemMetrics(79);
        var i = new INPUT { type = 0 };
        i.u.mi.dx = (int)Math.Round((x - vx) * 65535.0 / (vw - 1)); i.u.mi.dy = (int)Math.Round((y - vy) * 65535.0 / (vh - 1));
        i.u.mi.flags = 0x0001 | 0x8000 | 0x4000; Send(i);
    }
    public static void Button(bool down) { var i = new INPUT { type = 0 }; i.u.mi.flags = down ? 0x0002u : 0x0004u; Send(i); }
    public static void Key(ushort vk, bool down) { var i = new INPUT { type = 1 }; i.u.ki.vk = vk; i.u.ki.flags = down ? 0u : 0x0002u; Send(i); }
    public static void Text(string s) {
        foreach (var c in s) foreach (var up in new[] { false, true }) { var i = new INPUT { type = 1 }; i.u.ki.scan = c; i.u.ki.flags = 0x0004u | (up ? 0x0002u : 0u); Send(i); }
    }
}
'@
function Read-State {
    try {
        $stream = [IO.FileStream]::new($statePath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]'ReadWrite, Delete')
        try { $text = [IO.StreamReader]::new($stream, [Text.Encoding]::UTF8).ReadToEnd() } finally { $stream.Dispose() }
        $text | ConvertFrom-Json -AsHashtable
    } catch { @{} }
}
function Wait-State([scriptblock] $predicate, [double] $seconds = 15) {
    $deadline = [DateTime]::UtcNow.AddSeconds($seconds)
    while ([DateTime]::UtcNow -lt $deadline) { $s = Read-State; if ($s.Count) { try { if (& $predicate $s) { return $s } } catch { } }; Start-Sleep -Milliseconds 150 }
    throw "condition not reached: $predicate"
}
function Wait-Window([string] $title, [double] $seconds = 20) {
    $deadline = [DateTime]::UtcNow.AddSeconds($seconds)
    while ([DateTime]::UtcNow -lt $deadline) { $h = [Fi]::FindWindow([NullString]::Value, $title); if ($h -ne [IntPtr]::Zero) { return $h }; Start-Sleep -Milliseconds 200 }
    throw "window '$title' did not appear"
}
function Press([ushort] $vk) { [Fi]::Key($vk, $true); [Fi]::Key($vk, $false) }
function Click-Element([string] $element) {
    $r = (Read-State).rects[$element]
    $p = [Fi+POINT]::new(); $null = [Fi]::ClientToScreen($script:hwnd, [ref] $p)
    [Fi]::Move([int]($p.X + $r.x + $r.width / 2), [int]($p.Y + $r.y + $r.height / 2)); Start-Sleep -Milliseconds 50
    [Fi]::Button($true); [Fi]::Button($false); Start-Sleep -Milliseconds 100
}
function Events($kind, $element) { @((Read-State).events | Where-Object { $_.type -eq $kind -and $_.element -eq $element }) }
$cases = [Collections.Generic.List[object]]::new()
function Case([string] $id, [scriptblock] $action) {
    try { $cases.Add([ordered]@{ id = $id; status = 'passed'; details = (& $action) }) }
    catch { $cases.Add([ordered]@{ id = $id; status = 'failed'; details = $_.Exception.Message }) }
}
$arguments = @($Arguments | ForEach-Object { $_.Replace('{state}', $statePath).Replace('{root}', $root) })
$quoted = $arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }
$app = Start-Process -FilePath $Exe -ArgumentList ($quoted -join ' ') -PassThru -RedirectStandardOutput (Join-Path $Out 'app.out.log') -RedirectStandardError (Join-Path $Out 'app.err.log')
try {
    Case 'P00-window-shown' {
        $null = Wait-State { param($s) $s.rects.pick } 60
        $script:hwnd = Wait-Window 'ui4me file input probe'
        $null = [Fi]::SetForegroundWindow($script:hwnd); Start-Sleep -Milliseconds 500
        @{ ok = $true }
    }
    Case 'P01-click-opens-picker-escape-cancels' {
        Click-Element 'pick'
        $d = Wait-Window 'Open'
        Start-Sleep -Milliseconds 1000
        Press 0x1B
        $null = Wait-State { param($s) @($s.events | Where-Object { $_.type -eq 'cancel' -and $_.element -eq 'pick' }).Count -eq 1 }
        @{ dialog = [int64]$d }
    }
    Case 'P02-choose-unicode-path' {
        Click-Element 'pick'
        $null = Wait-Window 'Open'
        Start-Sleep -Milliseconds 1200
        $expected = (Read-State).expected
        [Fi]::Text($expected); Press 0x0D
        $s = Wait-State { param($s) @($s.files.pick).Count -eq 1 } 20
        if ($s.files.pick[0] -cne $expected) { throw "files $($s.files.pick -join ',') expected $expected" }
        $commit = @($s.events | Where-Object { $_.type -eq 'commit' -and $_.element -eq 'pick' })
        if (-not $commit -or $commit[-1].files[0] -cne $expected) { throw 'no commit event with the files' }
        @{ files = @($s.files.pick) }
    }
    Case 'P03-keyboard-space-multiple' {
        $n = @(Events 'cancel' 'many').Count
        Click-Element 'many'
        $null = Wait-Window 'Open'
        Start-Sleep -Milliseconds 1000
        Press 0x1B
        $null = Wait-State { param($s) @($s.events | Where-Object { $_.type -eq 'cancel' -and $_.element -eq 'many' }).Count -eq ($n + 1) }
        Start-Sleep -Milliseconds 500
        Press 0x20
        $null = Wait-Window 'Open'
        Start-Sleep -Milliseconds 1200
        $expected = (Read-State).expected
        [Fi]::Text($expected); Press 0x0D
        $s = Wait-State { param($s) @($s.files.many).Count -eq 1 } 20
        if ($s.files.many[0] -cne $expected) { throw "files $($s.files.many -join ',')" }
        @{ files = @($s.files.many); focus = @($s.focus) }
    }
} finally {
    if (-not $app.HasExited) { Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue }
}
$status = if ($cases.Count -and -not ($cases | Where-Object { $_.status -ne 'passed' })) { 'passed' } else { 'failed' }
[IO.File]::WriteAllText((Join-Path $Out 'journey.json'), (ConvertTo-Json -InputObject ([ordered]@{ kind = 'file-input-journey'; status = $status; cases = $cases; environment = "Windows interactive session $env:USERNAME, SendInput + IFileDialog (automated, not a person)" }) -Depth 6), [Text.UTF8Encoding]::new($false))
foreach ($c in $cases) { '{0,-7} {1}  {2}' -f $c.status, $c.id, (ConvertTo-Json -InputObject $c.details -Compress -Depth 4) }
'done' | Set-Content (Join-Path $Out 'done.txt')
