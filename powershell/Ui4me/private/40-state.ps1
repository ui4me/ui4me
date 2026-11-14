# ----------------------------------------------------------------------------- state --

function New-UI4MEState {
    <#
    .SYNOPSIS
    Observable value. Read .Value, change with .Set(new) or .Update({ param($old) ... }); bound components follow.
    #>
    [CmdletBinding()]
    param([AllowNull()][object]$Value)
    $state = [pscustomobject]@{ Value = $Value; Subscribers = (New-Object System.Collections.ArrayList); Next = 0 }
    $state.PSObject.TypeNames.Insert(0, 'UI4ME.UiState')
    $state | Add-Member -MemberType ScriptMethod -Name Set -Value {
        param([AllowNull()][object]$NewValue)
        if ($null -eq $NewValue -and $null -eq $this.Value) { return }
        if ($null -ne $NewValue -and $null -ne $this.Value -and -not ($NewValue -is [System.Collections.IEnumerable] -and
                -not ($NewValue -is [string])) -and [object]::Equals($this.Value, $NewValue)) { return }
        $this.Value = $NewValue
        foreach ($subscriber in @($this.Subscribers)) {
            try { $null = Invoke-UiCallable $subscriber.Callback @(, $NewValue) }
            catch { Write-UiError $_ 'state subscriber' }
        }
    }
    $state | Add-Member -MemberType ScriptMethod -Name Update -Value {
        param([scriptblock]$Transform)
        $this.Set((& $Transform $this.Value))
    }
    $state | Add-Member -MemberType ScriptMethod -Name Subscribe -Value {
        param($Callback)
        $this.Next = [int]$this.Next + 1
        [void]$this.Subscribers.Add([pscustomobject]@{ Token = $this.Next; Callback = $Callback })
        return $this.Next
    }
    $state | Add-Member -MemberType ScriptMethod -Name Unsubscribe -Value {
        param([int]$Token)
        foreach ($subscriber in @($this.Subscribers)) { if ($subscriber.Token -eq $Token) { [void]$this.Subscribers.Remove($subscriber) } }
    }
    return $state
}

function New-UI4MEComputed {
    <#
    .SYNOPSIS
    A read-only state whose value is -Expression, recomputed whenever any -DependsOn state changes.
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory)][object[]]$DependsOn, [Parameter(Mandatory)][scriptblock]$Expression)
    $computed = New-UI4MEState -Value (& $Expression)
    $data = [pscustomobject]@{ Target = $computed; Expression = $Expression }
    foreach ($dependency in $DependsOn) {
        if (-not (Test-UiState $dependency)) { throw '-DependsOn takes states from New-UI4MEState/New-UI4MEComputed' }
        $null = $dependency.Subscribe((New-UiCallable 'Update-UiComputed' $data))
    }
    return $computed
}

function Update-UiComputed {
    param($Data, $ignored)
    $Data.Target.Set((& $Data.Expression))
}
