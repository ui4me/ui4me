# Install the UI4ME high-level PowerShell coding-agent skill without Python.
# Never overwrite modified/unowned skills without explicit -Force.

function Get-UiSkillHashes {
    param([Parameter(Mandatory)][string]$Path)
    $root = [IO.Path]::GetFullPath($Path).TrimEnd([char]'\', [char]'/')
    $result = @{}
    foreach ($entry in @(Get-ChildItem -LiteralPath $root -Recurse -Force)) {
        if (([int]$entry.Attributes -band [int][IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing symlink/reparse point in UI4ME skill: $($entry.FullName)"
        }
        if ($entry.PSIsContainer -or $entry.Name -eq '.ui4me-ui-managed.json') { continue }
        $key = $entry.FullName.Substring($root.Length + 1).Replace('\', '/')
        $result[$key] = (Get-FileHash -LiteralPath $entry.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    if (-not $result.ContainsKey('SKILL.md')) { throw 'UI4ME skill is missing SKILL.md' }
    return $result
}

function Get-UiSkillState {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return 'missing' }
    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer -or (([int]$item.Attributes -band [int][IO.FileAttributes]::ReparsePoint) -ne 0)) {
        return 'unmanaged'
    }
    $marker = Join-Path $Path '.ui4me-ui-managed.json'
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { return 'unmanaged' }
    try {
        $entry = Get-Item -LiteralPath $marker -Force  # -Force: dot-files are hidden on Linux/macOS
        if (([int]$entry.Attributes -band [int][IO.FileAttributes]::ReparsePoint) -ne 0) { return 'unmanaged' }
        $data = Get-Content -LiteralPath $marker -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
        if ($data.name -ne 'ui4me-ui-powershell') { return 'unmanaged' }
        $files = Get-UiSkillHashes $Path
        $expected = @($data.files.PSObject.Properties)
        if ($expected.Count -ne $files.Count) { return 'modified' }
        foreach ($member in $expected) {
            if (-not $files.ContainsKey($member.Name) -or $files[$member.Name] -ne [string]$member.Value) { return 'modified' }
        }
        return 'installed'
    } catch { return 'unmanaged' }
}

function Install-UI4MEUiSkill {
    <#
    .SYNOPSIS
    Install, inspect, update or remove the UI4ME high-level PowerShell agent skill.
    .EXAMPLE
    Install-UI4MEUiSkill -Agents all -Scope user
    .EXAMPLE
    Install-UI4MEUiSkill -Action status -Agents claude,codex -Scope project -ProjectPath .
    #>
    [CmdletBinding()]
    param([ValidateSet('install', 'status', 'uninstall')][string]$Action = 'install',
          [string[]]$Agents = @('all'), [ValidateSet('user', 'project')][string]$Scope = 'user',
          [string]$ProjectPath, [switch]$Force, [switch]$DryRun)
    if ($Scope -eq 'project' -and -not $ProjectPath) { throw '-ProjectPath is required with -Scope project' }
    if ($Scope -eq 'user' -and $ProjectPath) { throw '-ProjectPath only applies to -Scope project' }
    $names = @('claude','codex','opencode','copilot','cursor','gemini')
    $choices = @($Agents | ForEach-Object { $_.Split(',') } | ForEach-Object { $_.Trim().ToLowerInvariant() } |
        Where-Object { $_ } | Select-Object -Unique)
    $targets = if ($choices -contains 'all') { $names } else { $choices }
    if (-not $targets) { throw 'Select at least one coding agent' }
    foreach ($name in $targets) { if ($name -notin $names) { throw "Unknown agent '$name'" } }
    $mapping = @{ claude = '.claude/skills'; codex = '.agents/skills'; opencode = '.config/opencode/skills'
        copilot = '.copilot/skills'; cursor = '.cursor/skills'; gemini = '.gemini/skills' }
    if ($Scope -eq 'project') {
        $base = (Resolve-Path -LiteralPath $ProjectPath -ErrorAction Stop).Path
        $mapping.opencode = '.opencode/skills'; $mapping.copilot = '.github/skills'
    } else {
        $base = [Environment]::GetFolderPath('UserProfile')
        if (-not $base) { $base = $HOME }
    }
    $source = Join-Path $script:ModuleRoot 'skills/ui4me-ui-powershell'
    if ($Action -eq 'install' -and -not $DryRun -and -not (Test-Path -LiteralPath (Join-Path $source 'SKILL.md') -PathType Leaf)) {
        throw 'UI4ME PowerShell skill missing from the module. Reinstall UI4ME.'
    }
    foreach ($agent in $targets) {
        $target = [IO.Path]::GetFullPath((Join-Path (Join-Path $base $mapping[$agent]) 'ui4me-ui-powershell'))
        $parent = Split-Path -Parent $target
        $ancestor = $target
        while ($ancestor) {
            if (Test-Path -LiteralPath $ancestor) {
                $node = Get-Item -LiteralPath $ancestor -Force
                if (([int]$node.Attributes -band [int][IO.FileAttributes]::ReparsePoint) -ne 0) {
                    throw "Refusing linked UI4ME skill destination: $ancestor"
                }
            }
            $next = Split-Path -Parent $ancestor
            if (-not $next -or $next -eq $ancestor) { break }
            $ancestor = $next
        }
        $state = Get-UiSkillState $target
        if ($Action -eq 'status' -or $DryRun) {
            [pscustomobject]@{ Agent = $agent; Scope = $Scope; State = $state; Path = $target
                Action = $(if ($DryRun) { "would-$Action" } else { 'status' }) }
            continue
        }
        if ($Action -eq 'uninstall') {
            if ($state -eq 'missing') { continue }
            if ($state -ne 'installed' -and -not $Force) { throw "Refusing to remove $state skill at $target; use -Force" }
            Remove-Item -LiteralPath $target -Recurse -Force
            [pscustomobject]@{ Agent = $agent; Scope = $Scope; Path = $target; Action = 'removed' }
            continue
        }
        if ($state -in @('modified', 'unmanaged') -and -not $Force) {
            throw "Refusing to replace $state skill at $target; use -Force"
        }
        [void](New-Item -ItemType Directory -Path $parent -Force)
        $stage = Join-Path $parent ('.ui4me-ui-new-' + [guid]::NewGuid().ToString('N'))
        $backup = Join-Path $parent ('.ui4me-ui-old-' + [guid]::NewGuid().ToString('N'))
        try {
            Copy-Item -LiteralPath $source -Destination $stage -Recurse -ErrorAction Stop
            $files = Get-UiSkillHashes $stage
            $record = @{ name = 'ui4me-ui-powershell'; files = $files; version = '2.1.0' } | ConvertTo-Json -Depth 8
            [IO.File]::WriteAllText((Join-Path $stage '.ui4me-ui-managed.json'), $record,
                (New-Object Text.UTF8Encoding($false)))
            if ($state -ne 'missing') { Move-Item -LiteralPath $target -Destination $backup -ErrorAction Stop }
            try { Move-Item -LiteralPath $stage -Destination $target -ErrorAction Stop }
            catch { if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination $target }; throw }
            if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Recurse -Force }
            [pscustomobject]@{ Agent = $agent; Scope = $Scope; Path = $target; Action = 'installed' }
        } finally {
            if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
        }
    }
}
