# Automated real-input journey for the Core-only file utility on Windows (Core 0.4 gate).
# Run INSIDE an interactive desktop session:
#   pwsh -File files_journey.ps1 -Out DIR -Exe <program> -Arguments <args with {state} and {start}>
# Answers the Windows file dialogs (IFileDialog) with SendInput. Automated, not a person.
param(
    [Parameter(Mandatory)][string] $Out,
    [Parameter(Mandatory)][string] $Exe,
    [Parameter(Mandatory)][string[]] $Arguments
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$statePath = Join-Path $Out 'state.json'
Remove-Item -LiteralPath $statePath -ErrorAction SilentlyContinue
$start = Join-Path $Out 'files\ünïcødé složka'
New-Item -ItemType Directory -Force -Path $start | Out-Null
[IO.File]::WriteAllText((Join-Path $start 'notes.txt'), 'Hello from ui4me', [Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $start 'žluťoučký.md'), '# Unicode name', [Text.UTF8Encoding]::new($false))
Remove-Item -LiteralPath (Join-Path $start 'copy.txt') -ErrorAction SilentlyContinue

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
    [DllImport("user32.dll")] public static extern bool IsZoomed(IntPtr h);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    public static int ScreenWidth() { return GetSystemMetrics(0); }
    public static int ScreenHeight() { return GetSystemMetrics(1); }
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


function Wait-Window([string] $title, [double] $seconds = 20) {
    $deadline = [DateTime]::UtcNow.AddSeconds($seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $h = [Win]::FindWindow([NullString]::Value, $title)
        if ($h -ne [IntPtr]::Zero) { return $h }
        Start-Sleep -Milliseconds 200
    }
    throw "window '$title' did not appear"
}
function Click-Element($element) { Click (At (Read-State) $element) }

$arguments = $Arguments | ForEach-Object { $_.Replace('{state}', $statePath).Replace('{start}', $start) }
# Start-Process joins arguments with spaces and does not quote them.
$quoted = $arguments | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }
$app = Start-Process -FilePath $Exe -ArgumentList ($quoted -join ' ') -PassThru -RedirectStandardOutput (Join-Path $Out 'app.out.log') -RedirectStandardError (Join-Path $Out 'app.err.log')
try {
    Case 'G01_window_shown' {
        $null = Wait-State { param($s) $s.rects.open } 60
        $script:hwnd = Wait-Window 'UI4ME file utility'
        [void][Win]::SetForegroundWindow($script:hwnd)
        Start-Sleep -Milliseconds 500
        Update-Origin
        $s = Read-State
        @{ client = @($script:origin.X, $script:origin.Y); layout = $s.layout; screen = @([Win]::ScreenWidth(), [Win]::ScreenHeight()) }
    }
    Case 'G02_open_dialog_cancel' {
        Click-Element 'open'
        $d = Wait-Window 'Open text file'
        Start-Sleep -Milliseconds 800
        Press 0x1B
        $s = Wait-State { param($s) $s.cancelled -eq 1 }
        @{ cancelled = $s.cancelled; dialog = [int64]$d }
    }
    Case 'G03_folder_dialog_unicode_listing' {
        Click-Element 'folder'
        $null = Wait-Window 'Choose folder'
        Start-Sleep -Milliseconds 1000
        Press 0x0D
        $s = Wait-State { param($s) $s.folder -eq $start }
        if (@($s.entries) -notcontains 'žluťoučký.md' -or @($s.entries) -notcontains 'notes.txt') { throw "listing $(@($s.entries) -join ',')" }
        @{ folder = $s.folder; entries = @($s.entries) }
    }
    Case 'G04_open_dialog_reads_file' {
        Click-Element 'open'
        $null = Wait-Window 'Open text file'
        Start-Sleep -Milliseconds 1000
        [Win]::Text('notes.txt'); Press 0x0D
        $s = Wait-State { param($s) $s.file -eq (Join-Path $start 'notes.txt') -and $s.editor -eq 'Hello from ui4me' }
        @{ file = $s.file; editor = $s.editor }
    }
    Case 'G05_edit_and_save_dialog_writes' {
        Click-Element 'editor'; Chord 0x11 0x23; [Win]::Text(' edited')
        $null = Wait-State { param($s) ([string]$s.editor).EndsWith(' edited') }
        Click-Element 'save'
        $null = Wait-Window 'Save text file'
        Start-Sleep -Milliseconds 1000
        Chord 0x11 0x41; [Win]::Text('copy.txt'); Press 0x0D
        $target = Join-Path $start 'copy.txt'
        $s = Wait-State { param($s) $s.saved -eq $target }
        $content = [IO.File]::ReadAllText($target)
        if ($content -ne 'Hello from ui4me edited') { throw "saved content $content" }
        @{ saved = $s.saved; content = $content }
    }
    Case 'G06_copy_path_os_clipboard' {
        Click-Element 'copy'
        $target = Join-Path $start 'copy.txt'
        $s = Wait-State { param($s) $s.clipboard -eq $target }
        @{ app_clipboard = $s.clipboard; os_clipboard = (Get-Clipboard -Raw) }
    }
    Case 'G07_settings_modal_select_escape' {
        Click-Element 'settings'
        $s = Wait-State { param($s) (Get-Field $s.dialog 'open', 'Open') -and (Get-Field $s.dialog 'modal', 'Modal') }
        if ((@($s.focus) -join ',') -ne 'theme') { throw "modal focus $(@($s.focus) -join ',')" }
        Press 0x28
        $s = Wait-State { param($s) $s.theme -eq 'dark' }
        Press 0x1B
        $s = Wait-State { param($s) -not (Get-Field $s.dialog 'open', 'Open') }
        if ((@($s.focus) -join ',') -ne 'settings') { throw "focus not restored: $(@($s.focus) -join ',')" }
        @{ theme = $s.theme; focus = @($s.focus) }
    }
    Case 'G08_second_window_lifetime' {
        Click-Element 'details'
        $d = Wait-Window 'UI4ME file details'
        $null = Wait-State { param($s) $s.details_open }
        [void][Win]::PostMessage($d, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
        $s = Wait-State { param($s) $s.details_closed -eq 1 -and -not $s.details_open }
        @{ details_closed = $s.details_closed; main_still = $s.editor }
    }
    Case 'G09_responsive_resize' {
        $r = [Win+RECT]::new(); [void][Win]::GetWindowRect($script:hwnd, [ref] $r)
        $y = [int](($r.T + $r.B) / 2)
        # A real drag of the right border (cross-thread SetWindowPos is avoided).
        [Win]::Move($r.R - 3, $y); Start-Sleep -Milliseconds 150; [Win]::Button($true)
        foreach ($step in 1..10) { [Win]::Move($r.R - 3 - $step * 30, $y); Start-Sleep -Milliseconds 30 }
        [Win]::Button($false)
        $s = Wait-State { param($s) $s.layout -eq 'column' -and @($s.resized).Count -gt 0 }
        Update-Origin
        @{ layout = $s.layout; resized = @(@($s.resized)[-1]) }
    }
    Case 'G10_close_exits_cleanly' {
        [void][Win]::PostMessage($script:hwnd, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
        if (-not $app.WaitForExit(20000)) { throw 'app did not exit' }
        $s = Read-State
        if ($app.ExitCode -ne 0 -or -not $s.exited -or -not $s.closed) { throw "exit $($app.ExitCode) exited=$($s.exited) closed=$($s.closed)" }
        @{ exit_code = $app.ExitCode }
    }
}
finally {
    if (-not $app.HasExited) { $app.Kill(); $app.WaitForExit(5000) | Out-Null }
}
$status = if (@($cases | Where-Object status -ne 'passed').Count) { 'failed' } else { 'passed' }
$result = [ordered]@{ schema = 1; kind = 'file-utility-journey'; environment = "Windows interactive session $env:USERNAME, SendInput + IFileDialog (automated, not a person)"; command = @($Exe) + $arguments; status = $status; cases = $cases }
$result | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Out 'journey.json') -Encoding utf8
$status | Set-Content -LiteralPath (Join-Path $Out 'done.txt')
