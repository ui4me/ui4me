# Run an unmodified PowerShell example natively, screenshot it and smoke its keyboard focus.
#   python3 tests/native/linux/vkwin.py --out DIR -- pwsh -NoProfile -File tests/native/apps/ps_showcase.ps1 examples/powershell/gallery.ps1
# An alias routes the example's Invoke-UI4MEApp to Invoke-ShowcaseApp (an alias outranks the function the
# example's own Import-Module re-imports). It adds an -OnReady scenario and calls the module's
# Invoke-UI4MEApp from THIS script, so Core relaunches this wrapper with the same arguments.
param([Parameter(Mandatory)][string]$Example)
$ErrorActionPreference = 'Stop'
Import-Module UI4ME
. (Join-Path $PSScriptRoot '..\Channel.ps1')
$script:Example = (Resolve-Path -LiteralPath $Example).ProviderPath
$script:Shot = if ($env:UI4ME_SHOWCASE_SHOT) { $env:UI4ME_SHOWCASE_SHOT } else { [IO.Path]::GetFileNameWithoutExtension($script:Example) + '.png' }

function Invoke-ShowcaseApp {
    # Untyped parameters on purpose: the example's -Content block is dot-sourced into this
    # function's scope (its own session state), so `$theme = New-UI4MEState ...` there would be
    # coerced to [string] by a typed $Theme parameter (PowerShell variables are case-insensitive).
    param($Content, $Title = 'UI4ME', $Width, $Height, $Theme, $Css, $Assets, $OnReady, $OnCloseRequest,
          $OnClose, $OnError, $AppId)
    $script:ShowTitle = $Title
    $script:UserReady = $OnReady
    $params = @{} + $PSBoundParameters
    $params.OnReady = {
        if ($script:UserReady) { & $script:UserReady }
        try {
            $null = Request-Channel 'wait-window' @{ window = $script:ShowTitle; timeout = 20 }
            $null = Request-Channel 'move' @{ window = $script:ShowTitle; x = 4; y = 4 }  # no hover styles in the shot
            $null = Wait-UI4MEUi -Milliseconds 1500
            $shot = Request-Channel 'screenshot' @{ window = $script:ShowTitle; name = $script:Shot }
            Write-Check 'showcase.screenshot' ([bool]$shot.path) $shot
            $doc = (Get-UI4MEUiContext).Document
            $seen = New-Object Collections.ArrayList
            foreach ($i in 1..8) {
                $null = Request-Channel 'key' @{ key = 'tab'; settle = 0.15 }
                [void]$seen.Add([string](Get-UI4MEFocusedElement -Document $doc).element)
            }
            $distinct = @($seen | Where-Object { $_ } | Sort-Object -Unique).Count
            Write-Check 'showcase.tab_moves_focus' ($distinct -ge 1) ($seen -join ',')
            $diag = Get-UI4MEUiDiagnostics
            Write-Check 'showcase.no_errors' ($diag.Errors -eq 0) $diag.LastError
            Write-ChannelDone
            $null = Send-ChannelRequest 'native-close' @{ window = $script:ShowTitle }
        } catch {
            Write-ChannelFatal ("$_`n" + $_.ScriptStackTrace)
            Write-ChannelDone
            Stop-UI4MEUiApp
        }
    }
    UI4ME\Invoke-UI4MEApp @params
}

Set-Alias -Name Invoke-UI4MEApp -Value Invoke-ShowcaseApp -Scope Script
Set-Location -LiteralPath (Split-Path -Parent $script:Example)
. $script:Example
