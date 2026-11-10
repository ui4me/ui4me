[CmdletBinding()]
param([Parameter(Mandatory)][string]$ModulePath)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $ModulePath 'Ui4me.psd1') -ErrorAction Stop
$info = Get-Ui4meInfo
$state = [hashtable]::Synchronized(@{})
try {
Invoke-Ui4meApp -ArgumentList @(,$state) {
    param($app, $state)
    $window = New-Ui4meWindow '<p id="status">Owner test</p>'
    $null = $app.Timer(10000, { throw 'Native ownership probe timed out' }, $false)
    $owner = [Environment]::CurrentManagedThreadId
    $state.owner = $owner
    $null = $app.On('started', {
        try { Invoke-Ui4meApp {}; throw 'nested run was accepted' }
        catch { if ($_.Exception.ToString() -notmatch 'Only one Ui4me application') { throw }; $state.nested = 'rejected' }
        $post = $app.Post({ $state.postOwner = [Environment]::CurrentManagedThreadId })
        try { $null = $post.GetResult(); throw 'owner wait was accepted' }
        catch { if ($_.Exception.ToString() -notmatch 'Do not wait') { throw }; $state.wait = 'rejected' }
        if ($post.IsCompleted) { throw 'post executed before callback returned' }
        $state.deferred = $true
        $null = $app.Work({
            param($target)
            try { $target.SetText('status','wrong thread'); return 'incorrectly accepted' }
            catch { return $_.Exception.ToString() }
        }, @($window), {
            param($values, $error)
            if ($error) { throw $error }
            $state.wrongThread = [string]$values[0]
            $state.workOwner = [Environment]::CurrentManagedThreadId
            $app.Stop()
        })
    })
}
} catch { $state | ConvertTo-Json -Depth 6 | Write-Host; throw }
if ($state.nested -ne 'rejected' -or $state.wait -ne 'rejected' -or -not $state.deferred) { throw 'Nested run, owner wait or deferred assertion failed' }
if ($state.wrongThread -notmatch 'owner|thread') { throw ('Wrong thread was not rejected: '+$state.wrongThread) }
if (-not $state.postOwner -or $state.postOwner -ne $state.workOwner -or $state.workOwner -ne $state.owner) { throw 'Worker completion did not execute on post owner' }
$failureCaptured = $false
try {
    Invoke-Ui4meApp {
        param($app)
        $null = New-Ui4meWindow '<p>Callback failure</p>'
        $null = $app.Timer(10000, { throw 'Callback failure probe timed out' }, $false)
        $null = $app.On('started', { throw 'deliberate owner callback failure' })
    }
} catch {
    if ($_.Exception.ToString() -notmatch 'deliberate owner callback failure') { throw }
    $failureCaptured = $true
}
if (-not $failureCaptured) { throw 'Callback failure did not propagate' }
$state.failurePropagated = $true
Invoke-Ui4meApp -ArgumentList @(,$state) {
    param($app, $state)
    $null = New-Ui4meWindow '<p>Session after callback failure</p>'
    $null = $app.Timer(10000, { throw 'Session reuse probe timed out' }, $false)
    $null = $app.On('started', { $state.afterFailure = $true; $app.Stop() })
}
if (-not $state.afterFailure) { throw 'Application did not restart after callback failure' }
@{build_info=$info;checks=$state} | ConvertTo-Json -Depth 8
