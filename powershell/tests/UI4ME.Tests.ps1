# Pester 5 unit tests for the UI4ME PowerShell module. Core cmdlets are mocked; these
# tests do not start a native host (see tests/native for real-host journeys).
BeforeAll {
    $here = Split-Path -Parent $PSCommandPath
    $manifest = Join-Path $here '..\UI4ME\UI4ME.psd1'
    Import-Module $manifest -Force -ErrorAction Stop

    InModuleScope UI4ME {
        # Test helper defined in the module's scope so InModuleScope blocks can use it.
        function script:New-FakeEvent([string]$Type, [string]$Element, [hashtable]$Fields = @{}) {
            $e = [ordered]@{ type = $Type; element = $Element; path = @($Element) }
            foreach ($k in $Fields.Keys) { $e[$k] = $Fields[$k] }
            return [pscustomobject]$e
        }
    }
}

Describe 'Module surface' {
    It 'imports with the UI4ME.Core dependency and exports exactly the manifest functions' {
        $data = Import-PowerShellDataFile (Join-Path $PSScriptRoot '..\UI4ME\UI4ME.psd1')
        $data.ModuleVersion | Should -Be '2.0.0'
        $data.RequiredModules[0].ModuleName | Should -Be 'UI4ME.Core'
        $exported = (Get-Module UI4ME).ExportedFunctions.Keys | Sort-Object
        $exported | Should -Be ($data.FunctionsToExport | Sort-Object)
    }
    It 'does not shadow any UI4ME.Core command' {
        $core = (Get-Command -Module UI4ME.Core).Name
        $mine = (Get-Command -Module UI4ME).Name
        @($mine | Where-Object { $core -contains $_ }) | Should -BeNullOrEmpty
    }
    It 'parses without errors' {
        $tokens = $null; $errors = $null
        [void][System.Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot '..\UI4ME\UI4ME.psm1'), [ref]$tokens, [ref]$errors)
        $errors | Should -BeNullOrEmpty
    }
    It 'refuses components outside an application' {
        { New-UI4MEButton -Text 'x' } | Should -Throw '*inside Invoke-UI4MEApp*'
    }
}

Describe 'State' {
    It 'notifies subscribers once per change and supports Update/Unsubscribe' {
        InModuleScope UI4ME {
            $s = New-UI4MEState -Value 1
            $seen = New-Object System.Collections.ArrayList
            $token = $s.Subscribe({ param($v) [void]$seen.Add($v) }.GetNewClosure())
            $s.Set(1); $s.Set(2); $s.Update({ param($v) $v + 1 })
            $s.Unsubscribe($token); $s.Set(9)
            @($seen) | Should -Be @(2, 3)
        }
    }
    It 'recomputes computed values from dependencies' {
        InModuleScope UI4ME {
            $a = New-UI4MEState -Value 2
            $b = New-UI4MEState -Value 3
            $sum = New-UI4MEComputed -DependsOn $a, $b -Expression { $a.Value + $b.Value }.GetNewClosure()
            $sum.Value | Should -Be 5
            $a.Set(10)
            $sum.Value | Should -Be 13
        }
    }
}

Describe 'Rendering and events (mocked Core)' {
    BeforeEach {
        InModuleScope UI4ME {
            $script:UiBuilder = New-UiContext -Title 'T' -Theme 'system' -Css $null -Assets $null -OnError $null
            $script:UiBuilder.Document = [pscustomobject]@{ Id = 'doc' }
            $script:calls = New-Object System.Collections.ArrayList
            Mock Register-UI4MEDocumentEvent { [pscustomobject]@{ Type = $Type } }
            Mock Set-UI4MEDocumentValue { [void]$script:calls.Add("value:$Element=$Value") }
            Mock Set-UI4MEDocumentText { [void]$script:calls.Add("text:$Element=$Text") }
            Mock Set-UI4MEChecked { [void]$script:calls.Add("checked:$Element=$Checked") }
            Mock Get-UI4MEValue { 'from-dom' }
            Mock Get-UI4MEChecked { $true }
            Mock Invoke-UI4MEBatch { [void]$script:calls.Add("batch:" + (($Operations | ForEach-Object { $_.op }) -join ',')) }
        }
    }
    AfterEach { InModuleScope UI4ME { $script:UiBuilder = $null } }

    It 'escapes text and attributes' {
        InModuleScope UI4ME {
            $null = New-UI4METext -Text '<b>"x"</b>'
            $null = New-UI4MEInput -Label 'A&B' -Value '"q"'
            $html = $script:UiBuilder.Root.Markup.ToString()
            $html | Should -Match '&lt;b&gt;&quot;x&quot;&lt;/b&gt;'
            $html | Should -Not -Match '<b>'
            $html | Should -Match 'A&amp;B'
            $html | Should -Match 'value="&quot;q&quot;"'
        }
    }
    It 'uses one Core subscription per event type for many handlers' {
        InModuleScope UI4ME {
            1..300 | ForEach-Object { $null = New-UI4MEButton -Text "b$_" -OnClick { } }
            Invoke-UiSetups $script:UiBuilder.Root.Setups
            Should -Invoke Register-UI4MEDocumentEvent -Times 1 -Exactly
            $script:UiBuilder.Handlers['click'].Count | Should -Be 300
        }
    }
    It 'routes a click along the event path and isolates handler errors' {
        InModuleScope UI4ME {
            $hits = New-Object System.Collections.ArrayList
            $id = New-UI4MEButton -Text 'x' -OnClick { [void]$hits.Add('ok') }.GetNewClosure()
            $bad = New-UI4MEButton -Text 'y' -OnClick { throw 'boom' }
            Mock Show-UI4MEUiToast { }
            Invoke-UiDispatch (New-FakeEvent 'click' 'inner' @{ path = @('inner', $id) })
            Invoke-UiDispatch (New-FakeEvent 'click' $bad)
            @($hits) | Should -Be @('ok')
            $script:UiBuilder.ErrorCount | Should -Be 1
        }
    }
    It 'does not echo an input value back into the control (lost keystroke regression)' {
        # Found on Windows PS 7, 2026-11-13: typing "Ada" produced "Aa" because the
        # binding wrote the event's older value "A" over the control's newer "Ad".
        InModuleScope UI4ME {
            $name = New-UI4MEState -Value ''
            $id = New-UI4MEInput -Label 'Name' -Bind $name
            Invoke-UiSetups $script:UiBuilder.Root.Setups
            Invoke-UiDispatch (New-FakeEvent 'input' $id @{ value = 'A' })
            Invoke-UiDispatch (New-FakeEvent 'input' $id @{ value = 'Ad' })
            $name.Value | Should -Be 'Ad'
            @($script:calls | Where-Object { $_ -like 'value:*' }) | Should -BeNullOrEmpty
            $name.Set('Grace')
            @($script:calls) | Should -Contain "value:$id=Grace"
        }
    }
    It 'checkbox handles input+change for one toggle once' {
        InModuleScope UI4ME {
            $agree = New-UI4MEState -Value $false
            $changes = New-Object System.Collections.ArrayList
            $id = New-UI4MECheckbox -Label 'ok' -Bind $agree -OnChange { param($v) [void]$changes.Add($v) }.GetNewClosure()
            Invoke-UiDispatch (New-FakeEvent 'input' $id)
            Invoke-UiDispatch (New-FakeEvent 'change' $id)
            $agree.Value | Should -BeTrue
            $changes.Count | Should -Be 1
        }
    }
    It 'keyed list moves kept rows, removes dropped rows and releases their handlers' {
        InModuleScope UI4ME {
            $items = New-UI4MEState -Value @(@{ id = 1 }, @{ id = 2 }, @{ id = 3 })
            $id = New-UI4MEEach -Items $items -Key id -Template { param($item) $null = New-UI4MEButton -Text "x$($item.id)" -OnClick { } }
            $script:UiBuilder.Handlers['click'].Count | Should -Be 3
            $items.Set(@(@{ id = 3 }, @{ id = 1 }, @{ id = 4 }))
            @($script:calls | Where-Object { $_ -like 'batch:*' })[-1] | Should -Be 'batch:remove_element,move_element,move_element,insert_html'
            $script:UiBuilder.Handlers['click'].Count | Should -Be 3
            { $items.Set(@(@{ id = 1 }, @{ id = 1 })) } | Should -Not -Throw  # reported, not fatal
            $script:UiBuilder.ErrorCount | Should -Be 1
        }
    }
    It 'When disposes the hidden branch with its timers' {
        InModuleScope UI4ME {
            Mock Set-UI4MEDocumentHtml { }
            Mock Find-UI4MEElement { [pscustomobject]@{ ids = @() } }
            $on = New-UI4MEState -Value $true
            $null = New-UI4MEWhen -Condition $on -Content { $null = Start-UI4MEUiTimer -Milliseconds 10 -Repeat -Action { } }
            @($script:UiBuilder.Timers).Count | Should -Be 1
            $on.Set($false)
            Invoke-UiTimers $script:UiBuilder
            @($script:UiBuilder.Timers).Count | Should -Be 0
        }
    }
    It 'close policy fails closed when a handler throws' {
        InModuleScope UI4ME {
            [void]$script:UiBuilder.CloseRequest.Add({ throw 'x' })
            Mock Show-UI4MEUiToast { }
            Test-UiCloseAllowed | Should -BeFalse
            $script:UiBuilder.CloseRequest.Clear()
            [void]$script:UiBuilder.CloseRequest.Add({ $true })
            Test-UiCloseAllowed | Should -BeTrue
        }
    }
}

Describe 'Start-UI4MEUiScript manifest' {
    It 'quotes TOML strings safely' {
        InModuleScope UI4ME {
            Mock Start-UI4MEHost { $script:manifestText = Get-Content -Raw -LiteralPath $Manifest }
            # Windows file names cannot contain '"'; use a space and a quote that is legal everywhere.
            $file = Join-Path ([System.IO.Path]::GetTempPath()) ("ui4me test 'q' " + [guid]::NewGuid().ToString('N') + '.ps1')
            Set-Content -LiteralPath $file -Value '#'
            try { Start-UI4MEUiScript -Path $file -Title 'Hello "World"' } finally { Remove-Item -LiteralPath $file }
            $script:manifestText | Should -Match 'name = "Hello \\"World\\""'
            $script:manifestText | Should -Match '\[backend\]'
            $script:manifestText | Should -Match ([regex]::Escape(("ui4me test 'q' ")))
            if ([System.IO.Path]::DirectorySeparatorChar -eq '\') {
                # TOML basic strings need escaped backslashes in Windows paths.
                ($script:manifestText -split "`n" | Where-Object { $_ -like 'cwd = *' }) | Should -Match '\\\\'
            }
            { Start-UI4MEUiScript -Path $PSCommandPath -AppId "bad`n[host]" } | Should -Throw
        }
    }
}

Describe 'Windows PowerShell 5.1 backends' {
    It 'names powershell.exe without a path (UI4ME.Core 1.0 verbatim-path workaround)' -Skip:(-not ($IsWindows -or $PSVersionTable.PSEdition -eq 'Desktop')) {
        # Found on Windows Server 2022, 2026-11-13: an absolute program path is spawned as
        # \\?\C:\...\powershell.exe and .NET Framework fails in ServicePointManager.
        InModuleScope UI4ME {
            Mock Start-UI4MEHost { $script:manifestText = Get-Content -Raw -LiteralPath $Manifest }
            Start-UI4MEUiScript -Path $PSCommandPath -WindowsPowerShell
            $script:manifestText | Should -Match 'program = "powershell.exe"'
        }
    }
}

Describe 'Settings' {
    It 'persists JSON in the per-app folder and recovers from corruption' {
        InModuleScope UI4ME {
            $root = Join-Path ([System.IO.Path]::GetTempPath()) ('ui4me-settings-' + [guid]::NewGuid().ToString('N'))
            $env:XDG_CONFIG_HOME = $root; $env:APPDATA = $root
            try {
                $script:UiBuilder = New-UiContext -Title 'T' -Theme 'system' -Css $null -Assets $null -OnError $null
                $script:UiBuilder | Add-Member -NotePropertyName AppId -NotePropertyValue 'org.ui4me.app.ps-settings'
                $script:UiBuilder | Add-Member -NotePropertyName Settings -NotePropertyValue $null
                Get-UI4MEUiSetting -Name theme -Default 'system' | Should -Be 'system'
                Set-UI4MEUiSetting -Name theme -Value 'dark'
                Set-UI4MEUiSetting -Name size -Value 3
                $file = Get-UiSettingsFile
                $file | Should -Match 'org\.ui4me\.app\.ps-settings[\\/]settings\.json$'
                $script:UiBuilder.Settings = $null
                Get-UI4MEUiSetting -Name theme | Should -Be 'dark'
                Get-UI4MEUiSetting -Name size | Should -Be 3
                Set-UI4MEUiSetting -Name size -Remove
                $script:UiBuilder.Settings = $null
                Get-UI4MEUiSetting -Name size -Default 'gone' | Should -Be 'gone'
                [System.IO.File]::WriteAllText($file, '{not json')
                $script:UiBuilder.Settings = $null
                Mock Show-UI4MEUiToast { }
                Get-UI4MEUiSetting -Name theme -Default 'reset' | Should -Be 'reset'
                Test-Path -LiteralPath ($file + '.corrupt') | Should -BeTrue
            } finally {
                $script:UiBuilder = $null
                Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

Describe 'Date, time and colour fields' {
    BeforeEach {
        InModuleScope UI4ME {
            $script:UiBuilder = New-UiContext -Title 'T' -Theme 'system' -Css $null -Assets $null -OnError $null
            $script:UiBuilder.Document = [pscustomobject]@{ Id = 'doc' }
            $script:html = New-Object System.Collections.ArrayList
            Mock Register-UI4MEDocumentEvent { [pscustomobject]@{ Type = $Type } }
            Mock Set-UI4MEDocumentValue { }
            Mock Set-UI4MEDocumentText { }
            Mock Set-UI4MEDocumentAttribute { }
            Mock Set-UI4MEFocus { }
            Mock Set-UI4MEDocumentHtml { [void]$script:html.Add($Html) }
        }
    }
    AfterEach { InModuleScope UI4ME { $script:UiBuilder = $null } }

    It 'never renders input types that UI4ME.Core refuses' {
        InModuleScope UI4ME {
            $null = New-UI4MEDate; $null = New-UI4METime; $null = New-UI4MEColor
            $markup = $script:UiBuilder.Root.Markup.ToString()
            foreach ($t in 'date', 'time', 'datetime-local', 'month', 'week', 'color') { $markup | Should -Not -Match "type=`"$t`"" }
            { New-UI4MEInput -Type date } | Should -Throw
        }
    }
    It 'parses typed dates, reports errors and picks from the calendar' {
        InModuleScope UI4ME {
            $when = New-UI4MEState -Value $null
            $id = New-UI4MEDate -Bind $when -Min ([datetime]'2026-01-01')
            Invoke-UiDispatch ([pscustomobject]@{ type = 'input'; element = $id; path = @($id); value = '2026-02-03' })
            $when.Value | Should -Be ([datetime]'2026-02-03')
            Invoke-UiDispatch ([pscustomobject]@{ type = 'input'; element = $id; path = @($id); value = '2025-12-31' })
            Should -Invoke Set-UI4MEDocumentText -ParameterFilter { $Text -eq 'Must be on or after 2026-01-01' }
            $when.Value | Should -Be ([datetime]'2026-02-03')
            Invoke-UiDispatch ([pscustomobject]@{ type = 'click'; element = "$id-cal-toggle"; path = @("$id-cal-toggle") })
            $script:html[-1] | Should -Match 'February 2026'
            $script:html[-1] | Should -Match "$id-cal-d20260203"
            Invoke-UiDispatch ([pscustomobject]@{ type = 'click'; element = "$id-cal-next"; path = @("$id-cal-next", "$id-cal") })
            $script:html[-1] | Should -Match 'March 2026'
            Invoke-UiDispatch ([pscustomobject]@{ type = 'click'; element = "$id-cal-d20260305"; path = @("$id-cal-d20260305", "$id-cal") })
            $when.Value | Should -Be ([datetime]'2026-03-05')
        }
    }
    It 'validates time and colour, and swatches set the colour' {
        InModuleScope UI4ME {
            $t = New-UI4MEState -Value $null
            $tid = New-UI4METime -Bind $t
            Invoke-UiDispatch ([pscustomobject]@{ type = 'input'; element = $tid; path = @($tid); value = '7:05' })
            $t.Value | Should -Be ([timespan]'07:05:00')
            $c = New-UI4MEState -Value '#ABC'
            $cid = New-UI4MEColor -Bind $c
            Invoke-UiDispatch ([pscustomobject]@{ type = 'click'; element = "$cid-swatches-3"; path = @("$cid-swatches-3", "$cid-swatches") })
            $c.Value | Should -Be '#dc2626'
            Invoke-UiDispatch ([pscustomobject]@{ type = 'input'; element = $cid; path = @($cid); value = 'zz' })
            Should -Invoke Set-UI4MEDocumentText -ParameterFilter { $Text -eq 'Enter a colour as #rrggbb' }
        }
    }
}
