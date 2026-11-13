# App side of the native test channel for PowerShell UI4ME apps (see channel.py).
# Dot-source this file. Waiting for the driver pumps UI events, timers and tasks
# through Wait-UI4MEUi, so the window stays live while real input arrives.
$script:ChannelDir = $env:UI4ME_TEST_CHANNEL
if (-not $script:ChannelDir) { throw 'UI4ME_TEST_CHANNEL is not set; run this app through a native driver' }
$script:ChannelNext = 0
$script:ChannelFailures = 0

function Write-ChannelRecord([string]$Name, [hashtable]$Record) {
    $line = ($Record | ConvertTo-Json -Compress -Depth 8)
    [System.IO.File]::AppendAllText((Join-Path $script:ChannelDir $Name), $line + "`n", (New-Object System.Text.UTF8Encoding($false)))
}

function Send-ChannelRequest([string]$Action, [hashtable]$Fields = @{}) {
    # Queue a driver action without waiting (for input that must happen while a callback blocks).
    $script:ChannelNext++
    $record = @{ kind = 'request'; id = $script:ChannelNext; action = $Action }
    foreach ($k in $Fields.Keys) { $record[$k] = $Fields[$k] }
    Write-ChannelRecord 'requests.jsonl' $record
    return $script:ChannelNext
}

function Request-Channel([string]$Action, [hashtable]$Fields = @{}, [int]$TimeoutSeconds = 45) {
    $id = Send-ChannelRequest $Action $Fields
    return (Receive-ChannelAck $id $Action $TimeoutSeconds)
}

function Receive-ChannelAck([int]$id, [string]$Action = 'request', [int]$TimeoutSeconds = 45) {
    $acks = Join-Path $script:ChannelDir 'acks.jsonl'
    $holder = @{ found = $null }
    $ok = Wait-UI4MEUi -Milliseconds ($TimeoutSeconds * 1000) -Until {
        if (-not (Test-Path -LiteralPath $acks)) { return $false }
        foreach ($line in [System.IO.File]::ReadAllLines($acks)) {
            if (-not $line.Trim()) { continue }
            try { $r = $line | ConvertFrom-Json } catch { continue }
            if ($r.ack -eq $id) { $holder.found = $r; return $true }
        }
        return $false
    }
    $found = $holder.found
    if ($null -eq $found) { throw "driver did not acknowledge $Action #$id" }
    if ($found.PSObject.Properties['ok'] -and -not $found.ok) { throw "driver could not $Action`: $($found.error)" }
    return $found
}

function Write-Check([string]$Name, $Ok, $Detail = $null) {
    $passed = [bool]$Ok
    if (-not $passed) { $script:ChannelFailures++ }
    Write-ChannelRecord 'results.jsonl' @{ kind = 'check'; name = $Name; status = $(if ($passed) { 'passed' } else { 'failed' }); detail = $Detail }
}

function Write-ChannelFatal([string]$Message) { Write-ChannelRecord 'results.jsonl' @{ kind = 'fatal'; message = $Message } }
function Write-ChannelDone { Write-ChannelRecord 'results.jsonl' @{ kind = 'done'; failures = $script:ChannelFailures } }

function Wait-Until([scriptblock]$Condition, [int]$TimeoutSeconds = 10) {
    return (Wait-UI4MEUi -Milliseconds ($TimeoutSeconds * 1000) -Until $Condition)
}

function Get-Center([string]$Element) {
    $doc = (Get-UI4MEUiContext).Document
    $r = (Invoke-UI4MEDocumentCommand -Document $doc -Operation get_rect -Parameters @{ element = $Element }).rect
    if ($null -eq $r) { throw "element $Element has no layout box" }
    return @{ x = [double]$r.x + [Math]::Min([double]$r.width / 2, 40); y = [double]$r.y + [double]$r.height / 2 }
}

function Invoke-Click([string]$Window, [string]$Element) {
    $c = Get-Center $Element
    $null = Request-Channel 'click' @{ window = $Window; x = $c.x; y = $c.y }
}
