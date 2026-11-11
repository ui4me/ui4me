# Real-input keyboard-layout and IME journey on Windows (Core 0.5 F0501/F0502), twin of
# tests/native/kwin/input_journey.py. Run INSIDE an interactive desktop session.
#   pwsh -File input_journey.ps1 -Out DIR -Exe <program> -Arguments <args with {state} and {commands}>
# Keys are SendInput scan codes, so the window's active keyboard layout (US, Czech, US-International,
# German) and the Microsoft Japanese/Korean IMEs (TSF) produce the text. The probe app is
# tests/native/input_probe.py or input_probe.ps1. Automation, not a person; label evidence
# accordingly. The ja-JP and ko-KR input methods must be in the user's language list for the IME cases.
param(
    [Parameter(Mandatory)][string] $Out,
    [Parameter(Mandatory)][string] $Exe,
    [Parameter(Mandatory)][string[]] $Arguments,
    [switch] $NoIme,
    [string] $Only = '.'
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$statePath = Join-Path $Out 'state.json'
$commandsPath = Join-Path $Out 'commands.jsonl'
Remove-Item -LiteralPath $statePath -ErrorAction SilentlyContinue
[IO.File]::WriteAllText($commandsPath, '')

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Kb {
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
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr LoadKeyboardLayout(string klid, uint flags);
    [DllImport("user32.dll")] public static extern IntPtr GetKeyboardLayout(uint thread);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern uint MapVirtualKey(uint code, uint type);
    public static void VkScan(ushort vk, bool down) { var i = new INPUT { type = 1 }; i.u.ki.vk = vk; i.u.ki.scan = (ushort)MapVirtualKey(vk, 0); i.u.ki.flags = down ? 0u : 0x0002u; Send(i); }
    static void Send(INPUT i) { if (SendInput(1, new[] { i }, Marshal.SizeOf<INPUT>()) != 1) throw new InvalidOperationException("SendInput failed " + Marshal.GetLastWin32Error()); System.Threading.Thread.Sleep(15); }
    public static void Move(int x, int y) {
        int vx = GetSystemMetrics(76), vy = GetSystemMetrics(77), vw = GetSystemMetrics(78), vh = GetSystemMetrics(79);
        var i = new INPUT { type = 0 };
        i.u.mi.dx = (int)Math.Round((x - vx) * 65535.0 / (vw - 1)); i.u.mi.dy = (int)Math.Round((y - vy) * 65535.0 / (vh - 1));
        i.u.mi.flags = 0x0001 | 0x8000 | 0x4000; Send(i);
    }
    public static void Button(bool down) { var i = new INPUT { type = 0 }; i.u.mi.flags = down ? 0x0002u : 0x0004u; Send(i); }
    // A hardware-like key: a set-1 scan code (extended for E0 keys); the active layout maps it.
    public static void Scan(ushort scan, bool extended, bool down) {
        var i = new INPUT { type = 1 }; i.u.ki.scan = scan;
        i.u.ki.flags = 0x0008u | (extended ? 0x0001u : 0u) | (down ? 0u : 0x0002u); Send(i);
    }
    public static void Vk(ushort vk, bool down) { var i = new INPUT { type = 1 }; i.u.ki.vk = vk; i.u.ki.flags = down ? 0u : 0x0002u; Send(i); }
    public static string LayoutOf(IntPtr h) { uint pid; return GetKeyboardLayout(GetWindowThreadProcessId(h, out pid)).ToInt64().ToString("X8"); }
}
'@

# Set-1 scan codes by US key name (the same physical keys as the Linux evdev table).
$K = @{ '1' = 2; '2' = 3; '5' = 6; '6' = 7; '8' = 9; minus = 12; equal = 13; bs = 14; tab = 15
    q = 16; w = 17; e = 18; r = 19; t = 20; y = 21; u = 22; i = 23; o = 24; p = 25; lbracket = 26; enter = 28
    lctrl = 29; a = 30; s = 31; d = 32; f = 33; g = 34; h = 35; j = 36; k = 37; l = 38; semicolon = 39
    apostrophe = 40; grave = 41; lshift = 42; z = 44; x = 45; c = 46; v = 47; b = 48; n = 49; m = 50
    lalt = 56; space = 57; esc = 1; ralt = 'E038'; home = 'E047'; end = 'E04F' }
function Key-Event([string] $name, [bool] $down) {
    $v = $K[$name]
    if ($v -is [string]) { [Kb]::Scan([Convert]::ToUInt16($v.Substring(2), 16), $true, $down) }
    else { [Kb]::Scan([uint16]$v, $false, $down) }
}
function Keys([string[]] $seq) {
    foreach ($item in $seq) {
        if ($item.StartsWith('+')) { Key-Event $item.Substring(1) $true }
        elseif ($item.StartsWith('-')) { Key-Event $item.Substring(1) $false }
        else { Key-Event $item $true; Key-Event $item $false }
    }
}
function Type-Letters([string] $text) {
    foreach ($ch in $text.ToCharArray()) {
        $name = [string]$ch
        if ($ch -eq ' ') { $name = 'space' }
        if ([char]::IsUpper($ch)) { Keys @('+lshift', $name.ToLower(), '-lshift') } else { Keys @($name) }
    }
}

function Read-State {
    try {
        $stream = [IO.FileStream]::new($statePath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]'ReadWrite, Delete')
        try { $text = [IO.StreamReader]::new($stream, [Text.Encoding]::UTF8).ReadToEnd() } finally { $stream.Dispose() }
        $text | ConvertFrom-Json -AsHashtable
    } catch { @{} }
}
function Wait-State([scriptblock] $predicate, [double] $seconds = 10) {
    $deadline = [DateTime]::UtcNow.AddSeconds($seconds)
    $s = @{}
    while ([DateTime]::UtcNow -lt $deadline) {
        $s = Read-State
        if ($s.Count) { try { if (& $predicate $s) { return $s } } catch { } }
        Start-Sleep -Milliseconds 100
    }
    $tail = if ($s.log) { ($s.log | Select-Object -Last 10 | ForEach-Object { $_ -join '|' }) -join '; ' } else { '' }
    throw "condition not reached: $predicate; values $($s.values | ConvertTo-Json -Compress) log $tail"
}
function Host-Op([hashtable] $op, [bool] $ack = $true) {
    [IO.File]::AppendAllText($commandsPath, (ConvertTo-Json -InputObject $op -Compress) + "`n", [Text.UTF8Encoding]::new($false))
    $n = (Get-Item -LiteralPath $commandsPath).Length
    if ($ack) { $null = Wait-State { param($s) $s.commands -ge $n } }
}
function Values($s) { "a=$($s.values.a)|b=$($s.values.b)|t=$($s.values.t)" }
function Typed([string] $element, [string] $expected, [double] $seconds = 6) {
    $null = Wait-State { param($s) $s.values[$element] -ceq $expected } $seconds
    Start-Sleep -Milliseconds 500
    $s = Read-State
    if ($s.values[$element] -cne $expected) { throw "late change: $(Values $s)" }
    $s
}
function Inputs($s) { @($s.log | Where-Object { $_[0] -eq 'input' }) }
function Click-Element([string] $element) {
    $s = Read-State
    $r = $s.rects[$element]
    $p = [Kb+POINT]::new()
    $null = [Kb]::ClientToScreen($script:hwnd, [ref] $p)
    [Kb]::Move([int]($p.X + $r.x + 20), [int]($p.Y + $r.y + $r.height / 2)); Start-Sleep -Milliseconds 40
    [Kb]::Button($true); [Kb]::Button($false); Start-Sleep -Milliseconds 80
}
function Fresh([string] $element = 'a') {
    Host-Op @{ op = 'clear' }
    Click-Element $element
    $null = Wait-State { param($s) @($s.focus) -join ',' -eq $element }
    Host-Op @{ op = 'clear' }
}
$KLID = @{ us = '00000409'; cz = '00000405'; intl = '00020409'; de = '00000407'; ja = '00000411'; ko = '00000412' }
function Use-Layout([string] $name) {
    $hkl = [Kb]::LoadKeyboardLayout($KLID[$name], 0)
    if ($hkl -eq [IntPtr]::Zero) { throw "LoadKeyboardLayout $name failed" }
    $null = [Kb]::SetForegroundWindow($script:hwnd)
    $null = [Kb]::PostMessage($script:hwnd, 0x0050, [IntPtr]1, $hkl)  # WM_INPUTLANGCHANGEREQUEST
    $want = $KLID[$name].Substring(4)
    for ($i = 0; $i -lt 50; $i++) {
        $got = [Kb]::LayoutOf($script:hwnd)
        if ($got.EndsWith($want) -or $got.StartsWith($want)) { Start-Sleep -Milliseconds 200; return $got }
        Start-Sleep -Milliseconds 100
    }
    throw "layout $name not active (window has $([Kb]::LayoutOf($script:hwnd)))"
}

$cases = [Collections.Generic.List[object]]::new()
function Case([string] $id, [scriptblock] $action) {
    if ($id -notmatch $Only -and $id -ne 'W00-window-shown') { return }
    $started = [DateTime]::UtcNow
    try {
        $detail = & $action
        $cases.Add([ordered]@{ id = $id; status = 'passed'; details = $detail; seconds = [math]::Round(([DateTime]::UtcNow - $started).TotalSeconds, 2) })
    } catch { $cases.Add([ordered]@{ id = $id; status = 'failed'; details = $_.Exception.Message }) }
}

$arguments = @($Arguments | ForEach-Object { $_.Replace('{state}', $statePath).Replace('{commands}', $commandsPath) })
$app = Start-Process -FilePath $Exe -ArgumentList $arguments -PassThru -RedirectStandardOutput (Join-Path $Out 'app.out.log') -RedirectStandardError (Join-Path $Out 'app.err.log')
$script:hwnd = [IntPtr]::Zero
try {
    Case 'W00-window-shown' {
        $null = Wait-State { param($s) $s.rects.a } 40
        for ($i = 0; $i -lt 100 -and $script:hwnd -eq [IntPtr]::Zero; $i++) { $script:hwnd = [Kb]::FindWindow([NullString]::Value, 'ui4me input probe'); Start-Sleep -Milliseconds 100 }
        if ($script:hwnd -eq [IntPtr]::Zero) { throw 'probe window not found' }
        $null = [Kb]::SetForegroundWindow($script:hwnd); Start-Sleep -Milliseconds 500
        $null = Use-Layout 'us'
        @{ foreground = ([Kb]::GetForegroundWindow() -eq $script:hwnd); layout = [Kb]::LayoutOf($script:hwnd) }
    }
    Case 'K01-us-baseline' {
        $l = Use-Layout 'us'; Fresh
        Type-Letters 'Hello world'
        $s = Typed 'a' 'Hello world'
        @{ layout = $l; value = $s.values.a; inputs = (Inputs $s).Count }
    }
    Case 'K02-czech-dead-altgr' {
        $l = Use-Layout 'cz'; Fresh
        Keys @('2', '5', '6', '8', 'y', 'z', 'semicolon', 'equal', 'e', '+lshift', 'equal', '-lshift', 'c', 'equal', 'u', '+ralt', 'q', 'v', 'e', '-ralt')
        $s = Typed 'a' 'ěřžázyůéčú\@€'
        $n = (Inputs $s).Count
        if ($n -ne 13) { throw "$n input events for 13 characters" }
        @{ layout = $l; value = $s.values.a; inputs = $n }
    }
    Case 'K03-us-intl-dead' {
        $l = Use-Layout 'intl'; Fresh
        Keys @('apostrophe', 'e', '+lshift', 'apostrophe', '-lshift', 'u', 'grave', 'a', 'apostrophe', 'space', '+ralt', 's', '-ralt')
        $s = Typed 'a' "éüà'ß"
        @{ layout = $l; value = $s.values.a; inputs = (Inputs $s).Count }
    }
    Case 'K04-german' {
        $l = Use-Layout 'de'; Fresh
        Keys @('y', 'z', 'semicolon', 'apostrophe', 'lbracket', 'minus', '+ralt', 'q', '-ralt', 'grave', 'o', 'equal', 'e')
        $s = Typed 'a' 'zyöäüß@ôé'
        @{ layout = $l; value = $s.values.a }
    }
    Case 'K05-shortcuts-not-text' {
        $null = Use-Layout 'cz'; Fresh
        Type-Letters 'abc'; $null = Typed 'a' 'abc'
        Keys @('+lctrl', 'a', '-lctrl', 'x'); $null = Typed 'a' 'x'
        Keys @('+lctrl', 'y', '-lctrl')  # Czech: this key is Z -> undo
        $null = Typed 'a' 'abc'
        Keys @('+lctrl', '+lalt', 't', '-lalt', '-lctrl')  # Ctrl+Alt+T: no AltGr character on T
        Keys @('+lalt', 'd', '-lalt')
        $s = Typed 'a' 'abc'
        # The window keeps the keyboard focus and still takes clicks (no menu loop after Alt).
        Click-Element 'b'
        $s = Wait-State { param($s) @($s.focus) -join ',' -eq 'b' } 5
        @{ value = $s.values.a; focus_after_click = @($s.focus) }
    }
    Case 'K06-key-repeat' {
        $null = Use-Layout 'us'; Fresh
        # Hardware typematic repeat: repeated make codes without a break code.
        for ($i = 0; $i -lt 8; $i++) { Key-Event 'a' $true; Start-Sleep -Milliseconds 40 }
        Key-Event 'a' $false
        $s = Typed 'a' 'aaaaaaaa'
        $downs = @($s.log | Where-Object { $_[0] -eq 'keydown' -and $_[1] -eq 'a' })
        $repeats = @($downs | Where-Object { $_[6] })
        if ($downs.Count -ne 8 -or $repeats.Count -ne 7) { throw "keydowns $($downs.Count), repeat-flagged $($repeats.Count)" }
        @{ keydowns = $downs.Count; repeat_flagged = $repeats.Count }
    }
    if (-not $NoIme) {
        function Ime-On([string] $lang) {
            $l = Use-Layout $lang
            if ($lang -eq 'ja') {
                [Kb]::Vk(0x16, $true); [Kb]::Vk(0x16, $false)  # VK_IME_ON
                Start-Sleep -Milliseconds 300
                return $l
            }
            # Korean starts in English mode; find the Hangul toggle this IME accepts (VK_HANGUL with
            # its scan code, or Right Alt on a 101-key keyboard) by typing a probe consonant.
            $focus = @((Read-State).focus) -join ','
            foreach ($method in 'vk', 'ralt', 'vkonly') {
                switch ($method) {
                    'vk' { [Kb]::VkScan(0x15, $true); [Kb]::VkScan(0x15, $false) }
                    'ralt' { Keys @('ralt') }
                    'vkonly' { [Kb]::Vk(0x15, $true); [Kb]::Vk(0x15, $false) }
                }
                Start-Sleep -Milliseconds 300
                Keys @('g')
                Start-Sleep -Milliseconds 800
                $v = (Read-State).values[$focus]
                Host-Op @{ op = 'clear' }
                if ($v -eq [string][char]0x314E) { return "$l/$method" }
                if ($v -ne 'g') { throw "Hangul probe typed '$v'" }
            }
            throw 'no Hangul mode toggle worked'
        }
        function Check-Once($s, [string] $element, [string] $final) {
            $comp = @($s.log | Where-Object { $_[0] -like 'composition*' -and $_[1] -eq $element })
            $starts = @($comp | Where-Object { $_[0] -eq 'compositionstart' }).Count
            $ends = @($comp | Where-Object { $_[0] -eq 'compositionend' } | ForEach-Object { $_[2] })
            $commits = @(Inputs $s | Where-Object { $_[2] -eq 'insertFromComposition' } | ForEach-Object { $_[3] })
            @{ starts = $starts; ends = $ends; commits = $commits; inserts = @(Inputs $s | Where-Object { $_[2] -eq 'insertText' } | ForEach-Object { $_[3] }) }
        }
        Case 'I02-japanese-once' {
            Fresh 'a'; $l = Ime-On 'ja'
            Type-Letters 'nihonn'  # romaji: a final n needs nn
            $null = Wait-State { param($s) $s.values.a -eq 'にほん' }
            Keys @('space')
            $s = Wait-State { param($s) $s.values.a -ne 'にほん' -and $s.values.a.Length -gt 0 }
            $converted = $s.values.a
            Keys @('enter')
            $s = Typed 'a' $converted
            $c = Check-Once $s 'a' $converted
            if ($c.starts -ne 1 -or $c.ends.Count -ne 1 -or $c.ends[0] -ne $converted -or $c.commits.Count -ne 1 -or $c.inserts.Count -ne 0) { throw "not exactly once: $($c | ConvertTo-Json -Compress)" }
            @{ layout = $l; value = $converted; once = $c }
        }
        Case 'I04-korean' {
            Fresh 'a'; $l = Ime-On 'ko'
            Type-Letters 'gksrmf'  # 2-beolsik: ㅎㅏㄴ ㄱㅡㄹ
            $null = Wait-State { param($s) $s.values.a -eq '한글' }
            Keys @('enter')
            $s = Typed 'a' '한글'
            $c = Check-Once $s 'a' '한글'
            @{ layout = $l; value = $s.values.a; detail = $c }
        }
        Case 'I06-cancel' {
            Fresh 'a'; $null = Ime-On 'ja'
            Type-Letters 'kana'
            $null = Wait-State { param($s) $s.values.a -eq 'かな' }
            # The first Esc closes the prediction list, the next cancels the composition.
            for ($i = 0; $i -lt 3 -and (Read-State).values.a -ne ''; $i++) { Keys @('esc'); Start-Sleep -Milliseconds 400 }
            $s = Typed 'a' ''
            $ends = @($s.log | Where-Object { $_[0] -eq 'compositionend' } | ForEach-Object { $_[2] })
            if ($ends.Count -ne 1 -or $ends[0] -ne '') { throw "compositionend $($ends -join ',')" }
            @{ value = $s.values.a }
        }
        Case 'I07-host-focus-move' {
            Fresh 'a'; $null = Ime-On 'ja'
            Type-Letters 'toukyou'
            $null = Wait-State { param($s) $s.values.a -eq 'とうきょう' }
            Host-Op @{ op = 'focus'; element = 'b' }
            $null = Wait-State { param($s) @($s.focus) -join ',' -eq 'b' }
            Start-Sleep -Milliseconds 1000
            $s = Read-State
            if ($s.values.a -ne 'とうきょう' -or $s.values.b -ne '') { throw "after focus move $(Values $s)" }
            Type-Letters 'ka'; Keys @('enter')
            $s = Typed 'b' 'か'
            if ($s.values.a -ne 'とうきょう') { throw "a changed: $(Values $s)" }
            @{ values = (Values $s) }
        }
        Case 'I08-click-during-preedit' {
            Fresh 'a'; $null = Ime-On 'ja'
            Type-Letters 'oosa'
            $null = Wait-State { param($s) $s.values.a -eq 'おおさ' }
            Click-Element 't'
            $null = Wait-State { param($s) @($s.focus) -join ',' -eq 't' }
            Start-Sleep -Milliseconds 1000
            $s = Read-State
            if ($s.values.a -ne 'おおさ' -or $s.values.t -ne '') { throw "after click $(Values $s)" }
            Type-Letters 'ka'; Keys @('enter')
            $s = Typed 't' 'か'
            @{ values = (Values $s) }
        }
        Case 'I09-host-write-during-preedit' {
            Fresh 'a'; $null = Ime-On 'ja'
            Type-Letters 'saku'
            $null = Wait-State { param($s) $s.values.a -eq 'さく' }
            Host-Op @{ op = 'set_value'; element = 'a'; value = 'replaced' }
            Start-Sleep -Milliseconds 1000
            $s = Read-State
            if ($s.values.a -ne 'replaced') { throw "after host write $(Values $s)" }
            Type-Letters 'ka'; Keys @('enter')
            $s = Typed 'a' 'replacedか'
            @{ value = $s.values.a }
        }
        Case 'I10-close-during-preedit' {
            Fresh 'a'; $null = Ime-On 'ja'
            Type-Letters 'ka'
            $null = Wait-State { param($s) $s.values.a -eq 'か' }
            Host-Op @{ op = 'close' } $false
            if (-not $app.WaitForExit(10000)) { throw 'probe did not exit after close' }
            @{ exit = $app.ExitCode }
        }
    }
} finally {
    try { $null = Use-Layout 'us' } catch { }
    if (-not $app.HasExited) { Host-Op @{ op = 'stop' } $false; if (-not $app.WaitForExit(10000)) { Stop-Process -Id $app.Id -Force } }
}
$status = if ($cases.Count -and -not ($cases | Where-Object { $_.status -ne 'passed' })) { 'passed' } else { 'failed' }
$result = [ordered]@{ journey = 'input'; status = $status; cases = $cases; label = 'automated SendInput scan codes with Windows layouts and Microsoft IMEs in an interactive session; not a person' }
[IO.File]::WriteAllText((Join-Path $Out 'journey.json'), (ConvertTo-Json -InputObject $result -Depth 8), [Text.UTF8Encoding]::new($false))
foreach ($c in $cases) { '{0,-7} {1}  {2}' -f $c.status, $c.id, (ConvertTo-Json -InputObject $c.details -Compress -Depth 5) }
'done' | Set-Content (Join-Path $Out 'done.txt')
