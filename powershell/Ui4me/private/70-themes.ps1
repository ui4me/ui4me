# --------------------------------------------------------------------- styles --

function Add-UI4MEUiCss {
    <# .SYNOPSIS Adds trusted application CSS after the theme (before or after the window opens). #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Css)
    $ctx = Assert-UiBuilder
    if ($null -ne $ctx.Document) { return (Add-UI4MEStylesheet -Document $ctx.Document -Css $Css) }
    $ctx.Css = [string]$ctx.Css + "`n" + $Css
}

function Set-UI4MEUiTheme {
    <#
    .SYNOPSIS
    -Css replaces the whole visual theme (structural CSS stays); -ColorScheme picks light/dark/system;
    -Reset restores the bundled theme.
    #>
    [CmdletBinding(DefaultParameterSetName = 'Css')]
    param([Parameter(ParameterSetName = 'Css', Mandatory)][string]$Css,
          [Parameter(ParameterSetName = 'Scheme', Mandatory)][ValidateSet('light', 'dark', 'system')][string]$ColorScheme,
          [Parameter(ParameterSetName = 'Reset', Mandatory)][switch]$Reset)
    $ctx = Assert-UiBuilder
    if ($PSCmdlet.ParameterSetName -eq 'Scheme') {
        $ctx.Theme = $ColorScheme
        if ($ctx.Document) {
            Enter-UiThemeSwitch $ctx
            $null = Set-UI4MEEnvironment -Document $ctx.Document -ColorScheme $ColorScheme
        }
        return
    }
    $visual = if ($Reset) { Get-Content -LiteralPath (Join-Path $script:AssetPath 'theme.css') -Raw -Encoding UTF8 } else { $Css }
    if ($null -eq $ctx.Document) { $ctx.VisualCss = $visual }
    else {
        Enter-UiThemeSwitch $ctx
        $null = Set-UI4MEStylesheet -Document $ctx.Document -Sheet $ctx.ThemeSheet -Css $visual
    }
}

function Enter-UiThemeSwitch {
    # UI4ME.Core 1.x forwards every DOM event (including transitionrun/start/end) to the
    # script. Restyling every control at once must not start a transition on each of them:
    # the host disconnects an application that falls behind its bounded event queue.
    param($ctx)
    Invoke-UI4MEBatch -Document $ctx.Document -Operations @(@{ op = 'add_class'; element = 'u4ps-main'; name = 'u4-theme-switching' })
    # App-owned timer: the restore must run even if the caller's content is disposed.
    $owner = $ctx.CurrentOwner
    $ctx.CurrentOwner = $null
    try { $null = Start-UI4MEUiTimer -Milliseconds 250 -Action (New-UiCallable 'Exit-UiThemeSwitch' $ctx) }
    finally { $ctx.CurrentOwner = $owner }
}

function Exit-UiThemeSwitch {
    param($ctx)
    if ($ctx.Document -and -not ($ctx.Window -and $ctx.Window.Closed)) {
        Invoke-UI4MEBatch -Document $ctx.Document -Operations @(@{ op = 'remove_class'; element = 'u4ps-main'; name = 'u4-theme-switching' })
    }
}
