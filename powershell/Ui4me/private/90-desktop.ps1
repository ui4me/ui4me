# --------------------------------------------------------------------- desktop --

function Show-UI4MEUiFileDialog {
    <#
    .SYNOPSIS
    Native open/save/folder dialog. Returns a path (an array with -Multiple) or $null when cancelled.
    .DESCRIPTION
    The window stays responsive while the dialog is open; a user close still asks -OnCloseRequest.
    -Filters: @{ 'Images' = @('png','jpg') }.
    #>
    [CmdletBinding()]
    param([ValidateSet('Open', 'Save', 'Folder')][string]$Kind = 'Open', [string]$Title, [string]$Directory,
          [string]$FileName, [hashtable]$Filters, [switch]$Multiple)
    $ctx = Assert-UiBuilder
    if (-not $ctx.Window) { throw 'File dialogs need a running application.' }
    $params = @{ Window = $ctx.Window; Kind = @{ Open = 'OpenFiles'; Save = 'SaveFile'; Folder = 'ChooseFolder' }[$Kind] }
    if ($Title) { $params.Title = $Title }
    if ($Directory) { $params.Directory = $Directory }
    if ($FileName) { $params.FileName = $FileName }
    if ($Kind -eq 'Open') { $params.Multiple = [bool]$Multiple }
    if ($Filters -and $Kind -ne 'Folder') {
        $params.Filters = @($Filters.Keys | ForEach-Object { @{ name = [string]$_; extensions = @($Filters[$_]) } })
    }
    $result = Show-UI4MEFileDialog @params
    $paths = @()
    if ($null -ne $result -and $result.PSObject.Properties['paths'] -and $null -ne $result.paths) { $paths = @($result.paths) }
    if ($paths.Count -eq 0) { return $null }
    if ($Multiple) { return , $paths }
    return [string]$paths[0]
}

function Start-UI4MEUiScript {
    <#
    .SYNOPSIS
    Legacy compatibility launcher. Normal usage is `pwsh -File app.ps1`; Invoke-UI4MEApp starts Core itself.
    .PARAMETER WindowsPowerShell
    On Windows, run the backend with Windows PowerShell 5.1 (powershell.exe) instead of this PowerShell.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Path,
          [string]$Title, [string]$AppId = 'org.ui4me.UserApp', [switch]$WindowsPowerShell, [switch]$NoWait,
          [switch]$Headless)
    Import-Module UI4ME.Core -ErrorAction Stop
    $source = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    if ($AppId -notmatch '^[A-Za-z][A-Za-z0-9_.-]*$') { throw 'AppId may contain only ASCII letters, digits, dots, hyphens and underscores' }
    $appTitle = if ($Title) { $Title } else { [System.IO.Path]::GetFileNameWithoutExtension($source) }
    if ($WindowsPowerShell -or $PSVersionTable.PSEdition -eq 'Desktop') {
        if (-not (Test-Path -LiteralPath (Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'))) {
            throw 'Windows PowerShell 5.1 is not available'
        }
        # Retain a bare process name for compatibility; Core 1.0.1 also
        # correctly supports absolute Windows PowerShell 5.1 program paths.
        $program = 'powershell.exe'
    } else {
        $program = (Get-Process -Id $PID).Path
    }
    if (-not $program) { throw 'Could not resolve the PowerShell executable' }
    $temp = Join-Path ([System.IO.Path]::GetTempPath()) ('ui4me-ps-' + [guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $temp -Force
    $manifest = Join-Path $temp 'app.toml'
    $q = { param($s) '"' + ([string]$s).Replace('\', '\\').Replace('"', '\"') + '"' }
    $toml = @(
        '[app]', ('id = ' + (& $q $AppId)), ('name = ' + (& $q $appTitle)), 'version = "2.1.0"', '',
        '[backend]', ('program = ' + (& $q $program)),
        ('args = ["-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ' + (& $q $source) + ']'),
        ('cwd = ' + (& $q (Split-Path -Parent $source))), '',
        '[host]', 'startup_timeout_ms = 30000', 'shutdown_timeout_ms = 5000', 'max_windows = 16', 'instance = "multiple"'
    ) -join "`n"
    if ($toml -match '[\x00-\x08\x0b-\x1f]') { throw 'Control characters are not allowed in the manifest values' }
    [System.IO.File]::WriteAllText($manifest, $toml + "`n", (New-Object System.Text.UTF8Encoding($false)))
    if ($Headless) {
        # Test mode: the real host without a desktop window (no native input, focus or dialogs).
        try {
            & (Get-UI4MEHostPath) run --headless --app $manifest
            if ($LASTEXITCODE -ne 0) { throw "UI4ME host exited with code $LASTEXITCODE" }
        } finally { Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue }
        return
    }
    if ($NoWait) { return (Start-UI4MEHost -Manifest $manifest -NoWait) }
    try { Start-UI4MEHost -Manifest $manifest }
    finally { Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue }
}
