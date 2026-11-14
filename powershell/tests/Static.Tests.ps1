# Static safety checks for Ui4me.psm1 (no host needed).
Describe 'Static safety' {
    BeforeAll {
        $tokens = $null; $errors = $null
        $root = Join-Path $PSScriptRoot '..\Ui4me'
        $files = @((Join-Path $root 'Ui4me.psm1')) + @(
            Get-ChildItem (Join-Path $root 'private') -Filter '*.ps1' -File | Sort-Object Name | Select-Object -ExpandProperty FullName)
        $script:asts = @()
        foreach ($file in $files) {
            $ast = [System.Management.Automation.Language.Parser]::ParseFile($file, [ref]$tokens, [ref]$errors)
            $script:asts += $ast
        }
        $errors | Should -BeNullOrEmpty
    }

    It 'never reassigns a parameter variable inside the function body' {
        # PowerShell variable names are case-insensitive, so `$tone = ...` overwrites a
        # [ValidateSet()]$Tone parameter and `$disabled = ...` a [switch]$Disabled one.
        # Regression: both made New-UI4MEBadge / New-UI4MEButton throw on every call
        # (found on the real host, 2026-11-13).
        $isFunction = { param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }
        $isAssignment = { param($n) $n -is [System.Management.Automation.Language.AssignmentStatementAst] -and
            $n.Left -is [System.Management.Automation.Language.VariableExpressionAst] }
        $problems = New-Object System.Collections.ArrayList
        foreach ($ast in $script:asts) { foreach ($fn in $ast.FindAll($isFunction, $true)) {
            $params = @()
            if ($fn.Body.ParamBlock) {
                $params = @($fn.Body.ParamBlock.Parameters | ForEach-Object { $_.Name.VariablePath.UserPath.ToLowerInvariant() })
            }
            foreach ($a in $fn.Body.FindAll($isAssignment, $false)) {
                $nested = $false
                $parent = $a.Parent
                while ($null -ne $parent -and $parent -ne $fn.Body) {
                    if ($parent -is [System.Management.Automation.Language.ScriptBlockExpressionAst]) { $nested = $true; break }
                    $parent = $parent.Parent
                }
                $name = $a.Left.VariablePath.UserPath
                if (-not $nested -and $params -contains $name.ToLowerInvariant()) {
                    [void]$problems.Add("$($fn.Name): `$$name (line $($a.Extent.StartLineNumber))")
                }
            }
        }
        }  # all split module files
        @($problems) | Should -BeNullOrEmpty
    }

    It 'contains no .GetNewClosure() in module code (closures lose module-private functions)' {
        $isClosure = { param($n) $n -is [System.Management.Automation.Language.InvokeMemberExpressionAst] -and
            $n.Member.Extent.Text -eq 'GetNewClosure' }
        foreach ($ast in $script:asts) { @($ast.FindAll($isClosure, $true)) | Should -BeNullOrEmpty }
    }
}
