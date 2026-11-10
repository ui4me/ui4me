Set-StrictMode -Version Latest

$managed = Join-Path $PSScriptRoot 'lib/Ui4me.Managed.dll'
if (-not (Test-Path -LiteralPath $managed -PathType Leaf)) {
    throw "Ui4me managed runtime missing: $managed. Install a packaged module or run the repository build."
}
if (-not ('Ui4me.Managed.Native' -as [type])) { Add-Type -Path $managed -ErrorAction Stop }
[Ui4me.Managed.Native]::Initialize($PSScriptRoot)

function Get-Ui4meInfo {
    <# .SYNOPSIS Returns native ABI, version, source identity and installed library path. #>
    [CmdletBinding()]
    param()
    [Ui4me.Managed.Native]::GetInfoJson() | ConvertFrom-Json
}

function Invoke-Ui4meApp {
    <#
    .SYNOPSIS Runs one application on the persistent native owner thread.
    .DESCRIPTION
    The initializer receives App as its first argument, followed by ArgumentList.
    Closures and the caller's local variables do not cross into the new runspace.
    Pass required data explicitly. Returns when the application has stopped.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position=0)][scriptblock] $ScriptBlock,
        [object[]] $ArgumentList = @(),
        [ValidateSet('native', 'headless')][string] $Backend = 'native'
    )
    $manifest = Join-Path $PSScriptRoot 'Ui4me.psd1'
    $operation = [Ui4me.Managed.Host]::Start($ScriptBlock.ToString(), $ArgumentList, $manifest, $Backend)
    function Send-Ui4meStreams {
        param($Items)
        foreach ($item in $Items) {
            switch ($item.Kind) {
                'output' { Write-Output -NoEnumerate $item.Value }
                'warning' { Write-Warning ([string]$item.Value) }
                'verbose' { Write-Verbose ([string]$item.Value) }
                'debug' { Write-Debug ([string]$item.Value) }
                'information' { Write-Information $item.Value.MessageData -Tags $item.Value.Tags }
                'error' { Write-Error -ErrorRecord $item.Value -ErrorAction Continue }
                'progress' { Write-Verbose ('Progress: ' + [string]$item.Value) }
            }
        }
    }
    try {
        while (-not $operation.Wait(50)) { Send-Ui4meStreams $operation.Drain() }
        Send-Ui4meStreams $operation.Drain()
        $operation.ThrowIfFailed()
    }
    finally {
        if (-not $operation.IsCompleted) {
            $operation.Cancel()
            if (-not $operation.Wait(5000)) {
                Write-Warning 'Ui4me stop was requested, but user code has not returned. This process cannot start another application yet.'
            }
        }
    }
}

function New-Ui4meWindow {
    <# .SYNOPSIS Opens a native window containing the foundation HTML subset. #>
    [CmdletBinding(DefaultParameterSetName='Html')]
    param(
        [Parameter(Mandatory, Position=0, ParameterSetName='Html')][string] $Html,
        [Parameter(Mandatory, ParameterSetName='File')][string] $Path,
        [string] $Title = 'ui4me',
        [int] $Width = 640,
        [int] $Height = 480,
        [Ui4me.Managed.App] $App = [Ui4me.Managed.App]::Current
    )
    if ($null -eq $App) { throw 'Call New-Ui4meWindow inside Invoke-Ui4meApp or pass an App explicitly.' }
    if ($PSCmdlet.ParameterSetName -eq 'File') { $App.OpenFile($ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Path), $Title, $Width, $Height) }
    else { $App.Open($Html, $Title, $Width, $Height) }
}

function Register-Ui4meEvent {
    <# .SYNOPSIS Registers an owner-thread callback. Return $false from close_requested to veto. #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position=0)][Ui4me.Managed.Window] $Window,
        [Parameter(Mandatory, Position=1)][string] $Event,
        [Parameter(Mandatory, Position=2)][scriptblock] $Action,
        [string] $Element
    )
    # The managed bridge captures the current PowerShell scope when On is
    # called. A module function has its own scope, so bring referenced caller
    # variables into it first. Otherwise callbacks registered through this
    # convenience command lose the initializer's local values.
    $__ui4me = @{ window = $Window; event = $Event; action = $Action
        element = $(if ($PSBoundParameters.ContainsKey('Element')) { $Element } else { $null }) }
    $__ui4meCaller = (Get-PSCallStack)[1].GetFrameVariables()
    $__ui4meNames = $__ui4me.action.Ast.FindAll({ param($node)
        $node -is [System.Management.Automation.Language.VariableExpressionAst]
    }, $true) | ForEach-Object { $_.VariablePath } | Where-Object { $_.IsUnqualified } |
        ForEach-Object { $_.UserPath } | Select-Object -Unique
    foreach ($__ui4meName in $__ui4meNames) {
        if ($__ui4meName -notmatch '^__ui4me' -and $__ui4meCaller.ContainsKey($__ui4meName)) {
            Set-Variable -Name $__ui4meName -Value $__ui4meCaller[$__ui4meName].Value -ErrorAction SilentlyContinue
        }
    }
    $__ui4me.window.On($__ui4me.event, $__ui4me.action, $__ui4me.element)
}

function Set-Ui4meText {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position=0)][Ui4me.Managed.Window] $Window,
        [Parameter(Mandatory, Position=1)][string] $Element,
        [Parameter(Mandatory, Position=2)][AllowEmptyString()][string] $Text
    )
    $Window.SetText($Element, $Text)
}

function Get-Ui4meValue {
    [CmdletBinding()]
    param([Parameter(Mandatory, Position=0)][Ui4me.Managed.Window] $Window,
          [Parameter(Mandatory, Position=1)][string] $Element)
    $Window.GetValue($Element)
}

function Stop-Ui4meApp {
    [CmdletBinding()]
    param([Ui4me.Managed.App] $App = [Ui4me.Managed.App]::Current)
    if ($null -eq $App) { throw 'No application is associated with this thread. Pass -App explicitly.' }
    $App.Stop()
}

Export-ModuleMember -Function Invoke-Ui4meApp, Get-Ui4meInfo, New-Ui4meWindow, Register-Ui4meEvent, Set-Ui4meText, Get-Ui4meValue, Stop-Ui4meApp
