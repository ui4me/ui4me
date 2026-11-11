# Automated real-input desktop journey for the Core chat/log demo on Windows.
# Run INSIDE an interactive desktop session (an SSH or service session has no input desktop).
#   pwsh -File chat_journey.ps1 -Out DIR -Exe <program> -Arguments <args with {state}>
# Input is synthesized with SendInput, the OS input path. It is automation, not a person;
# label evidence accordingly. The result is DIR\journey.json.
param(
    [Parameter(Mandatory)][string] $Out,
    [Parameter(Mandatory)][string] $Exe,
    [Parameter(Mandatory)][string[]] $Arguments
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$statePath = Join-Path $Out 'state.json'
Remove-Item -LiteralPath $statePath -ErrorAction SilentlyContinue

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Win {
    [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
    [StructLayout(LayoutKind.Sequential)] struct MOUSEINPUT { public int dx, dy; public uint data, flags, time; public IntPtr extra; }
    [StructLayout(LayoutKind.Sequential)] struct KEYBDINPUT { public ushort vk, scan; public uint flags, time; public IntPtr extra; }
    [StructLayout(LayoutKind.Explicit)] struct UNION { [FieldOffset(0)] public MOUSEINPUT mi; [FieldOffset(0)] public KEYBDINPUT ki; }
    [StructLayout(LayoutKind.Sequential)] struct INPUT { public uint type; public UNION u; }
    [DllImport("user32.dll", SetLastError = true)] static extern uint SendInput(uint n, INPUT[] inputs, int size);
    [DllImport("user32.dll")] static extern int GetSystemMetrics(int i);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string cls, string title);
    [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
    [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr h, int cmd);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
    static void Send(INPUT i) { if (SendInput(1, new[] { i }, Marshal.SizeOf<INPUT>()) != 1) throw new InvalidOperationException("SendInput failed " + Marshal.GetLastWin32Error()); System.Threading.Thread.Sleep(12); }
    public static void Move(int x, int y) {
        int vx = GetSystemMetrics(76), vy = GetSystemMetrics(77), vw = GetSystemMetrics(78), vh = GetSystemMetrics(79);
        var i = new INPUT { type = 0 };
        i.u.mi.dx = (int)Math.Round((x - vx) * 65535.0 / (vw - 1)); i.u.mi.dy = (int)Math.Round((y - vy) * 65535.0 / (vh - 1));
        i.u.mi.flags = 0x0001 | 0x8000 | 0x4000; Send(i);
    }
    public static void Button(bool down) { var i = new INPUT { type = 0 }; i.u.mi.flags = down ? 0x0002u : 0x0004u; Send(i); }
    public static void Wheel(int notches) { var i = new INPUT { type = 0 }; i.u.mi.flags = 0x0800; i.u.mi.data = unchecked((uint)(notches * 120)); Send(i); }
    public static void Key(ushort vk, bool down) { var i = new INPUT { type = 1 }; i.u.ki.vk = vk; i.u.ki.flags = down ? 0u : 0x0002u; Send(i); }
    public static void Text(string s) {
        foreach (var c in s) {
            if (c == ' ') { Key(0x20, true); Key(0x20, false); continue; }
            foreach (var up in new[] { false, true }) { var i = new INPUT { type = 1 }; i.u.ki.scan = c; i.u.ki.flags = 0x0004u | (up ? 0x0002u : 0u); Send(i); }
        }
    }
}
'@

function Read-State {
    try { Get-Content -Raw -LiteralPath $statePath -Encoding utf8 | ConvertFrom-Json -AsHashtable } catch { @{} }
}
function Get-Field($s, [string[]] $names) {
    foreach ($n in $names) { if ($null -ne $s -and $s.ContainsKey($n)) { return $s[$n] } }
    $null
}
function Get-Rect($s, $element) {
    $r = $s.rects[$element]
    @{ x = (Get-Field $r 'x', 'X'); y = (Get-Field $r 'y', 'Y'); w = (Get-Field $r 'width', 'Width'); h = (Get-Field $r 'height', 'Height') }
}
function Get-Scroll($s, $name) {
    $v = $s[$name]
    @{ y = (Get-Field $v 'y', 'Y'); max = (Get-Field $v 'max_y', 'MaxY') }
}
function Wait-State([scriptblock] $predicate, [double] $seconds = 10) {
    $deadline = [DateTime]::UtcNow.AddSeconds($seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $s = Read-State
        if ($s.Count) { try { if (& $predicate $s) { return $s } } catch { } }
        Start-Sleep -Milliseconds 100
    }
    throw "condition not reached: $predicate"
}
$script:origin = $null
$script:hwnd = [IntPtr]::Zero
function Update-Origin {
    $p = [Win+POINT]::new()
    if (-not [Win]::ClientToScreen($script:hwnd, [ref] $p)) { throw 'ClientToScreen failed' }
    $script:origin = $p
}
function At($s, $element, [double] $fx = 0.5, [double] $fy = 0.5, [double] $dx = 0) {
    $r = Get-Rect $s $element
    @([int]($script:origin.X + $r.x + $r.w * $fx + $dx), [int]($script:origin.Y + $r.y + $r.h * $fy))
}
function Click($xy) { [Win]::Move($xy[0], $xy[1]); Start-Sleep -Milliseconds 40; [Win]::Button($true); [Win]::Button($false); Start-Sleep -Milliseconds 60 }
function Chord([ushort] $modifier, [ushort] $vk) { [Win]::Key($modifier, $true); [Win]::Key($vk, $true); [Win]::Key($vk, $false); [Win]::Key($modifier, $false) }
function Press([ushort] $vk) { [Win]::Key($vk, $true); [Win]::Key($vk, $false) }

$cases = [Collections.Generic.List[object]]::new()
function Case([string] $id, [scriptblock] $action) {
    $started = [DateTime]::UtcNow
    try {
        $detail = & $action
        $cases.Add([ordered]@{ id = $id; status = 'passed'; details = $detail; seconds = [math]::Round(([DateTime]::UtcNow - $started).TotalSeconds, 2) })
    }
    catch { $cases.Add([ordered]@{ id = $id; status = 'failed'; details = $_.Exception.Message }) }
}

$arguments = $Arguments | ForEach-Object { $_.Replace('{state}', $statePath) }
$app = Start-Process -FilePath $Exe -ArgumentList $arguments -PassThru -RedirectStandardOutput (Join-Path $Out 'app.out.log') -RedirectStandardError (Join-Path $Out 'app.err.log')
try {
    Case 'J01_window_shown' {
        $s = Wait-State { param($s) $s.rects.compose } 60
        $deadline = [DateTime]::UtcNow.AddSeconds(20)
        while ($script:hwnd -eq [IntPtr]::Zero -and [DateTime]::UtcNow -lt $deadline) { $script:hwnd = [Win]::FindWindow($null, 'UI4ME chat demo'); Start-Sleep -Milliseconds 200 }
        if ($script:hwnd -eq [IntPtr]::Zero) { throw 'window not found' }
        [void][Win]::SetForegroundWindow($script:hwnd)
        Update-Origin
        @{ client = @($script:origin.X, $script:origin.Y); compose = (Get-Rect $s 'compose') }
    }
    Case 'J02_type_enter_sends' {
        Click (At (Read-State) 'compose'); [Win]::Text('hello core'); Press 0x0D
        $s = Wait-State { param($s) (@($s.sent) -join '|') -eq 'hello core' -and $s.compose -eq '' }
        @{ sent = @($s.sent); focus = @($s.focus) }
    }
    Case 'J03_shift_enter_newline' {
        [Win]::Text('line one'); Chord 0x10 0x0D; [Win]::Text('line two'); Press 0x0D
        $s = Wait-State { param($s) @($s.sent).Count -eq 2 }
        if (@($s.sent)[1] -ne "line one`nline two") { throw "Shift+Enter: $(@($s.sent)[1])" }
        @{ sent = @($s.sent)[1] }
    }
    Case 'J04_search_field_survives_stream' {
        Click (At (Read-State) 'search'); [Win]::Text('worker')
        $s = Wait-State { param($s) $s.search -eq 'worker' }
        $lines = $s.lines
        Start-Sleep -Milliseconds 1500
        $s = Wait-State { param($s) $s.lines -gt $lines + 10 }
        if ($s.search -ne 'worker' -or (@($s.focus) -join ',') -ne 'search') { throw "search $($s.search) focus $(@($s.focus) -join ',')" }
        @{ search = $s.search; focus = @($s.focus); lines_during = $s.lines - $lines }
    }
    Case 'J05_drag_select_document_text' {
        $s = Read-State
        $a = At $s 'm0' 0 0.75 12; $b = At $s 'm0' 0.98 0.75
        [Win]::Move($a[0], $a[1]); [Win]::Button($true)
        [Win]::Move([int](($a[0] + $b[0]) / 2), $b[1]); [Win]::Move($b[0], $b[1]); [Win]::Button($false)
        $s = Wait-State { param($s) ([string]$s.selection).Length -gt 10 }
        if (-not ([string]$s.selection).Contains('Type below')) { throw "selection $($s.selection)" }
        @{ selection = $s.selection }
    }
    Case 'J06_copy_button_os_clipboard' {
        $s = Read-State; $selected = $s.selection
        Click (At $s 'copy')
        $s = Wait-State { param($s) $s.copied -eq $selected -and $s.clipboard -eq $selected }
        @{ copied = $s.copied; os_clipboard = $s.clipboard; get_clipboard = (Get-Clipboard -Raw) }
    }
    Case 'J07_ctrl_c_then_ctrl_v_into_control' {
        $s = Read-State
        Click (At $s 'm0' 0 0.25 12); Start-Sleep -Milliseconds 600
        $w = At $s 'm0' 0 0.25 20
        Click $w; Click $w
        $s = Wait-State { param($s) $s.selection -eq 'assistant' }
        Chord 0x11 0x43
        $s = Wait-State { param($s) $s.clipboard -eq 'assistant' }
        $os = Get-Clipboard -Raw
        Click (At $s 'compose'); Chord 0x11 0x56
        $s = Wait-State { param($s) $s.compose -eq 'assistant' }
        Chord 0x11 0x41; Press 0x08
        $null = Wait-State { param($s) $s.compose -eq '' }
        @{ os_clipboard = $os; pasted = $s.compose }
    }
    Case 'J08_wheel_scroll_away_stops_follow' {
        $s = Read-State
        $xy = At $s 'log'; [Win]::Move($xy[0], $xy[1])
        1..5 | ForEach-Object { [Win]::Wheel(3) }
        $s = Wait-State { param($s) $v = Get-Scroll $s 'log_scroll'; $v.y -lt $v.max - 50 } 5
        Start-Sleep -Milliseconds 1500
        $s = Read-State; $v = Get-Scroll $s 'log_scroll'
        if ($v.y -ge $v.max - 50) { throw 'follow yanked the reader back to the end' }
        @{ log_scroll = $v }
    }
    Case 'J09_resize_relayout' {
        $s = Read-State; $before = (Get-Rect $s 'log').w
        [void][Win]::ShowWindowAsync($script:hwnd, 3)  # maximize through the window manager
        $s = Wait-State { param($s) @($s.resized).Count -gt 0 -and (Get-Rect $s 'log').w -gt $before + 20 }
        Update-Origin
        @{ resized = @($s.resized)[-1]; log_width = @($before, (Get-Rect $s 'log').w) }
    }
    Case 'J10_close_exits_cleanly' {
        [void][Win]::PostMessage($script:hwnd, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)  # WM_CLOSE, as the title-bar button
        if (-not $app.WaitForExit(15000)) { throw 'app did not exit' }
        $s = Read-State
        if ($app.ExitCode -ne 0 -or -not $s.exited -or -not $s.closed) { throw "exit $($app.ExitCode) exited=$($s.exited) closed=$($s.closed)" }
        @{ exit_code = $app.ExitCode }
    }
}
finally {
    if (-not $app.HasExited) { $app.Kill(); $app.WaitForExit(5000) | Out-Null }
}
$status = if (@($cases | Where-Object status -ne 'passed').Count) { 'failed' } else { 'passed' }
$result = [ordered]@{ schema = 1; kind = 'desktop-journey'; environment = "Windows interactive session $env:USERNAME, SendInput (automated, not a person)"; command = @($Exe) + $arguments; status = $status; cases = $cases }
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Out 'journey.json') -Encoding utf8
$status | Set-Content -LiteralPath (Join-Path $Out 'done.txt')
