# Static safety checks for UI4ME.psm1 (no host needed).
Describe 'Static safety' {
    BeforeAll {
        $tokens = $null; $errors = $null
        $script:ast = [System.Management.Automation.Language.Parser]::ParseFile(
            (Join-Path $PSScriptRoot '..\UI4ME\UI4ME.psm1'), [ref]$tokens, [ref]$errors)
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
        foreach ($fn in $script:ast.FindAll($isFunction, $true)) {
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
        @($problems) | Should -BeNullOrEmpty
    }

    It 'contains no .GetNewClosure() in module code (closures lose module-private functions)' {
        $isClosure = { param($n) $n -is [System.Management.Automation.Language.InvokeMemberExpressionAst] -and
            $n.Member.Extent.Text -eq 'GetNewClosure' }
        @($script:ast.FindAll($isClosure, $true)) | Should -BeNullOrEmpty
    }
}
