# Ownership and re-entrancy regressions (mocked Core; no host).
BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..\Ui4me\Ui4me.psd1') -Force -ErrorAction Stop
}

Describe 'Runtime content ownership and nested pumps' {
    BeforeEach {
        InModuleScope UI4ME {
            $script:UiBuilder = New-UiContext -Title 'T' -Theme 'system' -Css $null -Assets $null -OnError $null
            $script:UiBuilder.Document = [pscustomobject]@{ Id = 'doc' }
            $script:UiBuilder.App = [pscustomobject]@{ Dispatching = $false; ShutdownRequested = $false; Closed = $false }
            Mock Register-UI4MEDocumentEvent { [pscustomobject]@{ Type = $Type } }
            Mock Set-UI4MEDocumentHtml { }
            Mock Set-UI4MEDocumentText { }
            Mock Invoke-UI4MEBatch { }
            Mock Show-UI4MEUiToast { }
        }
    }
    AfterEach { InModuleScope UI4ME { $script:UiBuilder = $null } }

    It 'content rebuilt by a When inside an Each item is disposed with the item' {
        # Review finding: rebuilt branches were created with no owner, so their timers and
        # bindings outlived the removed item.
        InModuleScope UI4ME {
            $items = New-UI4MEState -Value @(@{ id = 1 })
            $flag = New-UI4MEState -Value $false
            $null = New-UI4MEEach -Items $items -Key id -Template {
                param($item)
                $null = New-UI4MEWhen -Condition $flag -Content { $null = Start-UI4MEUiTimer -Milliseconds 10 -Repeat -Action { } }
            }
            $flag.Set($true)                       # rebuild inside the item
            @($script:UiBuilder.Timers | Where-Object { -not $_.Owner.Disposed }).Count | Should -Be 1
            $items.Set(@())                        # remove the item
            Invoke-UiTimers $script:UiBuilder
            @($script:UiBuilder.Timers).Count | Should -Be 0
        }
    }

    It 'a one-shot timer fires once even if its callback pumps again' {
        InModuleScope UI4ME {
            $script:fired = 0
            $null = Start-UI4MEUiTimer -Milliseconds 1 -Action { $script:fired++ }
            $null = Start-UI4MEUiTimer -Milliseconds 1 -Action { Invoke-UiTimers $script:UiBuilder }
            Start-Sleep -Milliseconds 20
            Invoke-UiTimers $script:UiBuilder
            $script:fired | Should -Be 1
        }
    }

    It 'timer callbacks run with Core dispatching on, so events are deferred until they return' {
        InModuleScope UI4ME {
            $script:seen = $null
            $null = Start-UI4MEUiTimer -Milliseconds 1 -Action { $script:seen = $script:UiBuilder.App.Dispatching }
            Start-Sleep -Milliseconds 20
            Invoke-UiTimers $script:UiBuilder
            $script:seen | Should -BeTrue
            $script:UiBuilder.App.Dispatching | Should -BeFalse
        }
    }

    It 'date bounds ignore the time of day' {
        InModuleScope UI4ME {
            Mock Set-UI4MEDocumentAttribute { }
            $when = New-UI4MEState -Value $null
            $id = New-UI4MEDate -Bind $when -Min ([datetime]'2026-03-01 15:30')
            Invoke-UiDispatch ([pscustomobject]@{ type = 'input'; element = $id; path = @($id); value = '2026-03-01' })
            $when.Value | Should -Be ([datetime]'2026-03-01')
        }
    }
}
