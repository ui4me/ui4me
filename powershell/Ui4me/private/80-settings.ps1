# -------------------------------------------------------------------- settings --

function Get-UiSettingsFile {
    $ctx = Assert-UiBuilder
    $windows = ($PSVersionTable.PSEdition -eq 'Desktop') -or ((Get-Variable -Name IsWindows -ErrorAction SilentlyContinue) -and $IsWindows)
    if ($windows) {
        $base = if ($env:APPDATA) { $env:APPDATA } else { Join-Path $HOME 'AppData\Roaming' }
        $dir = Join-Path (Join-Path $base 'UI4ME') $ctx.AppId
    } else {
        $base = if ($env:XDG_CONFIG_HOME) { $env:XDG_CONFIG_HOME } else { Join-Path $HOME '.config' }
        $dir = Join-Path (Join-Path $base 'ui4me') $ctx.AppId
    }
    return (Join-Path $dir 'settings.json')
}

function Get-UiSettings {
    $ctx = Assert-UiBuilder
    if ($null -ne $ctx.Settings) { return $ctx.Settings }
    $table = [ordered]@{}
    $file = Get-UiSettingsFile
    if (Test-Path -LiteralPath $file) {
        try {
            if ((Get-Item -LiteralPath $file).Length -gt 1MB) { throw 'settings file is larger than 1 MiB' }
            $parsed = [System.IO.File]::ReadAllText($file) | ConvertFrom-Json -ErrorAction Stop
            if ($parsed -isnot [System.Management.Automation.PSCustomObject]) { throw 'settings file must contain a JSON object' }
            foreach ($p in $parsed.PSObject.Properties) { $table[$p.Name] = $p.Value }
        } catch {
            Move-Item -LiteralPath $file -Destination ($file + '.corrupt') -Force -ErrorAction SilentlyContinue
            Write-UiError $_ "settings $file"
        }
    }
    $ctx.Settings = $table
    return $table
}

function Get-UI4MEUiSetting {
    <#
    .SYNOPSIS
    Reads a persistent per-user setting of this app (same settings.json as Python's app.settings).
    .DESCRIPTION
    Stored in %APPDATA%\UI4ME\<AppId>\settings.json (Windows) or ~/.config/ui4me/<AppId>/settings.json (Linux).
    Invoke-UI4MEApp -AppId sets the folder (default: derived from -Title).
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][string]$Name, [AllowNull()][object]$Default)
    $table = Get-UiSettings
    if ($table.Contains($Name)) { return $table[$Name] }
    return $Default
}

function Set-UI4MEUiSetting {
    <# .SYNOPSIS Stores a persistent setting (JSON-compatible value) atomically. -Remove deletes it. #>
    [CmdletBinding(DefaultParameterSetName = 'Set')]
    param([Parameter(Mandatory)][string]$Name, [Parameter(ParameterSetName = 'Set', Mandatory)][AllowNull()][object]$Value,
          [Parameter(ParameterSetName = 'Remove', Mandatory)][switch]$Remove)
    if (-not $Name -or $Name.Length -gt 200) { throw 'Setting names must be 1-200 characters' }
    $table = Get-UiSettings
    if ($Remove) { if (-not $table.Contains($Name)) { return }; $table.Remove($Name) } else { $table[$Name] = $Value }
    $json = ConvertTo-Json -InputObject ([pscustomobject]$table) -Depth 10
    if ([System.Text.Encoding]::UTF8.GetByteCount($json) -gt 1MB) { throw 'Settings are limited to 1 MiB' }
    $file = Get-UiSettingsFile
    $dir = Split-Path -Parent $file
    if (-not (Test-Path -LiteralPath $dir)) { $null = New-Item -ItemType Directory -Path $dir -Force }
    $tmp = Join-Path $dir ('.settings-' + [guid]::NewGuid().ToString('N') + '.tmp')
    [System.IO.File]::WriteAllText($tmp, $json, (New-Object System.Text.UTF8Encoding($false)))
    if (Test-Path -LiteralPath $file) { [System.IO.File]::Replace($tmp, $file, [NullString]::Value) }  # [NullString]: $null would become ""
    else { [System.IO.File]::Move($tmp, $file) }
}
