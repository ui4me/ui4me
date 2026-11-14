# Headless functional tests for the 2.1 components in private/55-advanced.ps1, user-text escaping,
# and regressions found in the 2.1 static/headless review. UI4ME.Core calls are mocked; no host.
BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..\Ui4me\Ui4me.psd1') -Force -ErrorAction Stop
    $script:Hostile = '<b>&"''x'
    $script:HostileEncoded = '&lt;b&gt;&amp;&quot;&#39;x'
    InModuleScope UI4ME {
        function script:New-FakeAdvEvent([string]$Type, [string]$Element, [hashtable]$Fields = @{}) {
            $e = [ordered]@{ type = $Type; element = $Element; path = @($Element) }
            foreach ($k in $Fields.Keys) { $e[$k] = $Fields[$k] }
            return [pscustomobject]$e
        }
    }
}

Describe '55-advanced components (build phase markup)' {
    BeforeEach {
        InModuleScope UI4ME {
            $script:UiBuilder = New-UiContext -Title 'T' -Theme 'system' -Css $null -Assets $null -OnError $null
        }
    }
    AfterEach { InModuleScope UI4ME { $script:UiBuilder = $null } }

    It 'shell, sidebar, content, header, footer and status bar render semantic containers in order' {
        InModuleScope UI4ME -Parameters @{ H = $Hostile; E = $HostileEncoded } {
            param($H, $E)
            $null = New-UI4MEShell -Content {
                $null = New-UI4MEHeader -Content { $null = New-UI4METext -Text 'head' }
                $null = New-UI4MESidebar -Title $H -Content { $null = New-UI4METext -Text 'nav' }
                $null = New-UI4MEContent -Content { $null = New-UI4METext -Text 'main' }
                $null = New-UI4MEFooter -Content { $null = New-UI4METext -Text 'foot' }
                $null = New-UI4MEStatusBar -Content { $null = New-UI4METext -Text 'ready' }
            }
            $m = $script:UiBuilder.Root.Markup.ToString()
            $m | Should -Match '^<div id="u4ps-box-\d+" class="u4-shell"'
            $m | Should -Match '<header id="u4ps-box-\d+" class="u4-header '
            $m | Should -Match '<aside id="u4ps-box-\d+" class="u4-sidebar [^"]*"[^>]*><h3 class="u4-sidebar-title">'
            $m | Should -Match '<section id="u4ps-box-\d+" class="u4-content '
            $m | Should -Match '<footer id="u4ps-box-\d+" class="u4-footer '
            $m | Should -Match 'class="u4-statusbar [^"]*"[^>]*role="status"'
            $m | Should -BeLike "*<h3 class=`"u4-sidebar-title`">$E</h3>*"
            $m | Should -Not -BeLike '*<b>*'
            $m.IndexOf('head') | Should -BeLessThan $m.IndexOf('nav')
            $m | Should -Match '</div>$'
        }
    }

    It 'fieldset needs a legend and escapes it' {
        InModuleScope UI4ME -Parameters @{ H = $Hostile; E = $HostileEncoded } {
            param($H, $E)
            { New-UI4MEFieldset -Legend '  ' -Content { } } | Should -Throw '*legend*'
            $id = New-UI4MEFieldset -Legend $H -Content { $null = New-UI4MEInput -Label 'Name' }
            $m = $script:UiBuilder.Root.Markup.ToString()
            $m | Should -BeLike "*<fieldset id=`"$id`" class=`"u4-fieldset u4-column u4-gap-sm`"*><legend class=`"u4-fieldset-legend`">$E</legend>*"
            $m | Should -Match '</fieldset>$'
        }
    }

    It 'metric escapes label, value and detail and binds a state value' {
        InModuleScope UI4ME -Parameters @{ H = $Hostile; E = $HostileEncoded } {
            param($H, $E)
            $value = New-UI4MEState -Value $H
            $id = New-UI4MEMetric -Label $H -Value $value -Detail $H
            $m = $script:UiBuilder.Root.Markup.ToString()
            $m | Should -BeLike "*aria-label=`"$E`"*<span class=`"u4-metric-label`">$E</span><strong id=`"$id`" class=`"u4-metric-value`">$E</strong><small class=`"u4-metric-detail`">$E</small>*"
            @($script:UiBuilder.Bindings | Where-Object { $_.Element -eq $id -and $_.Apply -eq 'Set-UiTextBinding' }).Count | Should -Be 1
            $null = New-UI4MEMetric -Label 'Plain' -Value 42
            $script:UiBuilder.Root.Markup.ToString() | Should -BeLike '*class="u4-metric-value">42</strong>*'
        }
    }

    It 'empty state and loading escape text; empty state action is a real button' {
        InModuleScope UI4ME -Parameters @{ H = $Hostile; E = $HostileEncoded } {
            param($H, $E)
            $null = New-UI4MEEmpty -Title $H -Description $H -ActionLabel $H -OnAction { }
            $null = New-UI4MELoading -Text $H
            $m = $script:UiBuilder.Root.Markup.ToString()
            $m | Should -BeLike "*<section id=`"u4ps-empty-*`" class=`"u4-state u4-empty`"><h3>$E</h3><p>$E</p><button type=`"button`"*>$E</button></section>*"
            $m | Should -BeLike "*class=`"u4-state u4-loading`" role=`"status`"><span class=`"u4-spinner`" aria-hidden=`"true`"></span><span>$E</span></div>*"
            $script:UiBuilder.Handlers['click'].Count | Should -Be 1
        }
    }

    It 'icons are inline SVG, validated, and labelled or hidden' {
        InModuleScope UI4ME -Parameters @{ H = $Hostile; E = $HostileEncoded } {
            param($H, $E)
            $null = New-UI4MEIcon -Name folder -Label $H -Size 24
            $null = New-UI4MEIcon -Name check
            $m = $script:UiBuilder.Root.Markup.ToString()
            $m | Should -BeLike "*<svg class=`"u4-icon`" viewBox=`"0 0 24 24`" width=`"24`" height=`"24`"*role=`"img`" aria-label=`"$E`"><path d=`"M3 6h6l2 3h10v11H3V6`"></path></svg>*"
            $m | Should -BeLike '*role="presentation" aria-hidden="true"*'
            $m | Should -Not -BeLike '*http*'
            { New-UI4MEIcon -Name 'no-such-icon' } | Should -Throw '*Unknown UI4ME icon*'
            { New-UI4MEIcon -Name check -Size 4 } | Should -Throw
        }
    }

    It 'icon button needs a label, escapes it and supports a disabled state' {
        InModuleScope UI4ME -Parameters @{ H = $Hostile; E = $HostileEncoded } {
            param($H, $E)
            { New-UI4MEIconButton -Icon plus -Label ' ' } | Should -Throw '*accessible*'
            $disabled = New-UI4MEState -Value $true
            $id = New-UI4MEIconButton -Icon plus -Label $H -Disabled $disabled -OnClick { }
            $m = $script:UiBuilder.Root.Markup.ToString()
            $m | Should -BeLike "*<button type=`"button`" class=`"u4-btn u4-btn-ghost u4-icon-button`" id=`"$id`" aria-label=`"$E`" disabled><svg*aria-hidden=`"true`"*</button>*"
            $script:UiBuilder.Handlers['click'].ContainsKey($id) | Should -BeTrue
            @($script:UiBuilder.Bindings | Where-Object { $_.Element -eq $id -and $_.Apply -eq 'Set-UiDisabledBinding' }).Count | Should -Be 1
        }
    }

    It 'tooltip wraps its trigger and escapes the tip text' {
        InModuleScope UI4ME -Parameters @{ H = $Hostile; E = $HostileEncoded } {
            param($H, $E)
            { New-UI4METooltip -Text ' ' -Content { } } | Should -Throw '*empty*'
            $id = New-UI4METooltip -Text $H -Content { $null = New-UI4MEButton -Text 'Hover me' }
            $m = $script:UiBuilder.Root.Markup.ToString()
            $m | Should -BeLike "<span class=`"u4-tooltip-root`" id=`"$id`"><span class=`"u4-tooltip-trigger`" aria-describedby=`"$id-text`"><button*>Hover me</button></span><span role=`"tooltip`" id=`"$id-text`" class=`"u4-tooltip-text`">$E</span></span>"
        }
    }

    It 'breadcrumbs escape items and mark the last one current' {
        InModuleScope UI4ME -Parameters @{ H = $Hostile; E = $HostileEncoded } {
            param($H, $E)
            $null = New-UI4MEBreadcrumbs -Items @('Home', $H)
            $m = $script:UiBuilder.Root.Markup.ToString()
            $m | Should -BeLike "*<nav id=`"u4ps-crumbs-*`" aria-label=`"Breadcrumb`"><ol class=`"u4-breadcrumbs`"><li>Home</li><li aria-current=`"page`">$E</li></ol></nav>*"
        }
    }

    It 'segmented control renders (regression: New-UI4MERadio had no -Class parameter)' {
        # Before the fix New-UI4MESegmented always threw "A parameter cannot be found that matches
        # parameter name 'Class'" and New-UI4MERadio threw "The variable '$Class' cannot be retrieved".
        InModuleScope UI4ME -Parameters @{ H = $Hostile; E = $HostileEncoded } {
            param($H, $E)
            $choice = New-UI4MEState -Value 'b'
            $id = New-UI4MESegmented -Label $H -Options @('a', @{ Value = 'b'; Label = $H }) -Bind $choice
            $m = $script:UiBuilder.Root.Markup.ToString()
            $m | Should -BeLike "*<fieldset class=`"u4-field`" id=`"$id`"><legend class=`"u4-label`">$E</legend><div class=`"u4-radio-group u4-horizontal u4-segmented`" role=`"radiogroup`">*"
            $m | Should -BeLike "*id=`"$id-2`" name=`"$id`" value=`"b`" checked><span>$E</span>*"
            $null = New-UI4MERadio -Label 'Plain' -Options @('x', 'y')
            $null = New-UI4MERadio -Label 'Classy' -Options @('x') -Class 'a" onclick="x'
            $script:UiBuilder.Root.Markup.ToString() | Should -BeLike '*class="u4-radio-group a&quot; onclick=&quot;x"*'
        }
    }

    It 'multi-select renders labelled checkboxes from the bound state' {
        InModuleScope UI4ME -Parameters @{ H = $Hostile; E = $HostileEncoded } {
            param($H, $E)
            $picked = New-UI4MEState -Value @('b')
            $id = New-UI4MEMultiSelect -Label $H -Options @('a', @{ Value = 'b'; Label = $H }, 'c') -Bind $picked
            $m = $script:UiBuilder.Root.Markup.ToString()
            $m | Should -BeLike "<fieldset class=`"u4-fieldset u4-multiselect`" id=`"$id`"><legend class=`"u4-fieldset-legend`">$E</legend>*"
            $m | Should -BeLike "*<input type=`"checkbox`" id=`"$id-1`"><span>a</span>*<input type=`"checkbox`" id=`"$id-2`" checked><span>$E</span>*<input type=`"checkbox`" id=`"$id-3`"><span>c</span>*"
            { New-UI4MEMultiSelect -Label 'x' -Options @('a') -Bind 'notastate' } | Should -Throw '*New-UI4MEState*'
            { New-UI4MEMultiSelect -Label 'x' -Options @('a', 'a') } | Should -Throw '*unique*'
        }
    }

    It 'resizable split clamps the initial percent and escapes its label' {
        InModuleScope UI4ME -Parameters @{ H = $Hostile; E = $HostileEncoded } {
            param($H, $E)
            { New-UI4MEResizableSplit -Side { } -Main { } -Percent 5 } | Should -Throw
            $id = New-UI4MEResizableSplit -Percent 40 -Label $H -Side { $null = New-UI4METext -Text 'S' } -Main { $null = New-UI4METext -Text 'M' }
            $m = $script:UiBuilder.Root.Markup.ToString()
            $m | Should -BeLike "<section class=`"u4-adjustable`"><div class=`"u4-adjustable-controls`"><label for=`"$id-slider`">$E</label><input id=`"$id-slider`" type=`"range`" min=`"15`" max=`"85`" value=`"40`" aria-label=`"$E`"></div><div class=`"u4-resizable-panes`" id=`"$id`" style=`"--u4-split:40%`"><div class=`"u4-resizable-side`">*S</span></div><div class=`"u4-resizable-main`">*M</span></div></div></section>"
            $script:UiBuilder.Handlers['input'].ContainsKey("$id-slider") | Should -BeTrue
        }
    }

    It 'log and copy button escape their labels' {
        InModuleScope UI4ME -Parameters @{ H = $Hostile; E = $HostileEncoded } {
            param($H, $E)
            $log = New-UI4MELog -Label $H -MaxLines 2
            $copy = New-UI4MECopyButton -Text $H -Label $H
            $m = $script:UiBuilder.Root.Markup.ToString()
            $m | Should -BeLike "*<div id=`"$log`" class=`"u4-log`" role=`"log`" aria-label=`"$E`" aria-live=`"polite`"*"
            $m | Should -BeLike "*<button id=`"$copy`" type=`"button`" class=`"u4-btn u4-btn-secondary`">$E</button>*"
            { New-UI4MELog -MaxLines 0 } | Should -Throw
        }
    }
}

Describe '55-advanced components (runtime behaviour)' {
    BeforeEach {
        InModuleScope UI4ME {
            $script:UiBuilder = New-UiContext -Title 'T' -Theme 'system' -Css $null -Assets $null -OnError $null
            $script:UiBuilder.Document = [pscustomobject]@{ Id = 'doc' }
            $script:UiBuilder.App = [pscustomobject]@{ Id = 'app'; Dispatching = $false; ShutdownRequested = $false; Closed = $false }
            $script:Calls = New-Object System.Collections.ArrayList
            $script:Checked = @{}
            Mock Register-UI4MEDocumentEvent { [pscustomobject]@{ Type = $Type } }
            Mock Set-UI4MEDocumentHtml { [void]$script:Calls.Add(@{ Op = 'html'; Element = $Element; Html = $Html }) }
            Mock Set-UI4MEDocumentText { [void]$script:Calls.Add(@{ Op = 'text'; Element = $Element; Text = $Text }) }
            Mock Set-UI4MEDocumentAttribute { [void]$script:Calls.Add(@{ Op = 'attr'; Element = $Element; Name = $Name; Value = $Value }) }
            Mock Set-UI4MEChecked { [void]$script:Calls.Add(@{ Op = 'checked'; Element = $Element; Checked = $Checked }) }
            Mock Get-UI4MEChecked { [bool]$script:Checked[$Element] }
            Mock Set-UI4MEClipboard { [void]$script:Calls.Add(@{ Op = 'clipboard'; Text = $Text; App = $Application.Id }) }
            Mock Show-UI4MEUiToast { }
        }
    }
    AfterEach { InModuleScope UI4ME { $script:UiBuilder = $null } }

    It 'metric text follows its state' {
        InModuleScope UI4ME {
            $v = New-UI4MEState -Value 1
            $id = New-UI4MEMetric -Label 'Count' -Value $v
            $v.Set('<i>2</i>')
            $call = @($script:Calls | Where-Object { $_.Op -eq 'text' -and $_.Element -eq $id })
            $call.Count | Should -Be 1
            $call[0].Text | Should -Be '<i>2</i>'   # Core sets textContent: never parsed as markup
        }
    }

    It 'multi-select updates the state array on toggle and follows external state changes' {
        InModuleScope UI4ME {
            $picked = New-UI4MEState -Value @('a')
            $seen = New-Object System.Collections.ArrayList
            $id = New-UI4MEMultiSelect -Label 'Pick' -Options @('a', 'b', 'c') -Bind $picked -OnChange { param($v) [void]$seen.Add(($v -join ',')) }
            $script:Checked["$id-2"] = $true
            Invoke-UiDispatch (New-FakeAdvEvent 'input' "$id-2")
            Invoke-UiDispatch (New-FakeAdvEvent 'change' "$id-2")   # second event of the same toggle is ignored
            @($picked.Value) | Should -Be @('a', 'b')
            @($seen) | Should -Be @('a,b')
            $script:Checked["$id-1"] = $false
            Invoke-UiDispatch (New-FakeAdvEvent 'change' "$id-1")
            @($picked.Value) | Should -Be @('b')
            $script:Calls.Clear()
            $picked.Set(@('c'))
            $set = @($script:Calls | Where-Object { $_.Op -eq 'checked' } | ForEach-Object { "$($_.Element)=$($_.Checked)" } | Sort-Object)
            $set | Should -Be @("$id-2=False", "$id-3=True")
        }
    }

    It 'resizable split clamps slider input into the CSS variable' {
        InModuleScope UI4ME {
            $id = New-UI4MEResizableSplit -Side { } -Main { }
            Invoke-UiDispatch (New-FakeAdvEvent 'input' "$id-slider" @{ value = '99' })
            Invoke-UiDispatch (New-FakeAdvEvent 'input' "$id-slider" @{ value = '50' })
            Invoke-UiDispatch (New-FakeAdvEvent 'input' "$id-slider" @{ value = 'x;color:red' })
            $styles = @($script:Calls | Where-Object { $_.Op -eq 'attr' -and $_.Element -eq $id } | ForEach-Object { $_.Value })
            $styles | Should -Be @('--u4-split:85%', '--u4-split:50%')
        }
    }

    It 'log escapes lines, keeps at most MaxLines and accepts an empty line' {
        InModuleScope UI4ME {
            $log = New-UI4MELog -MaxLines 2
            Add-UI4MELogLine -Element $log -Text 'one'
            Add-UI4MELogLine -Element $log -Text '<b>&"''' -Level danger
            Add-UI4MELogLine -Element $log -Text ''   # regression: Mandatory [string] refused ''
            $last = @($script:Calls | Where-Object { $_.Op -eq 'html' -and $_.Element -eq $log })[-1].Html
            $last | Should -Be '<div class="u4-log-line u4-log-danger">&lt;b&gt;&amp;&quot;&#39;</div><div class="u4-log-line u4-log-info"></div>'
            { Add-UI4MELogLine -Element 'nope' -Text 'x' } | Should -Throw '*Unknown UI4ME log*'
            { Add-UI4MELogLine -Element $log -Text 'x' -Level bogus } | Should -Throw
        }
    }

    It 'a log inside removed runtime content is forgotten (regression: UiLogs leaked)' {
        InModuleScope UI4ME {
            $handle = Add-UI4MEUiContent -Into 'u4ps-main' -Content { $script:RuntimeLog = New-UI4MELog }
            $script:UiBuilder.UiLogs.ContainsKey($script:RuntimeLog) | Should -BeTrue
            Mock Remove-UI4MEElement { }
            Remove-UI4MEUiContent -Handle $handle
            $script:UiBuilder.UiLogs.ContainsKey($script:RuntimeLog) | Should -BeFalse
        }
    }

    It 'copy button copies its text through the Core clipboard' {
        InModuleScope UI4ME {
            $id = New-UI4MECopyButton -Text '<b>&"''' -Label 'Copy'
            Invoke-UiDispatch (New-FakeAdvEvent 'click' $id)
            $c = @($script:Calls | Where-Object { $_.Op -eq 'clipboard' })
            $c.Count | Should -Be 1
            $c[0].Text | Should -Be '<b>&"'''
            $c[0].App | Should -Be 'app'
        }
    }

    It 'icon button click runs the callback' {
        InModuleScope UI4ME {
            $script:Clicked = 0
            $id = New-UI4MEIconButton -Icon refresh -Label 'Refresh' -OnClick { $script:Clicked++ }
            Invoke-UiDispatch (New-FakeAdvEvent 'click' $id)
            $script:Clicked | Should -Be 1
        }
    }

    It 'segmented control updates its bound state' {
        InModuleScope UI4ME {
            $choice = New-UI4MEState -Value 'a'
            $id = New-UI4MESegmented -Options @('a', 'b') -Bind $choice
            Invoke-UiDispatch (New-FakeAdvEvent 'change' "$id-2")
            $choice.Value | Should -Be 'b'
        }
    }

    It 'disposed owners leave their parent (regression: rebuilt When branches accumulated)' {
        InModuleScope UI4ME {
            $items = New-UI4MEState -Value @(@{ id = 1 })
            $flag = New-UI4MEState -Value $false
            $null = New-UI4MEEach -Items $items -Key id -Template { param($item) $null = New-UI4MEWhen -Condition $flag -Content { $null = New-UI4METext -Text 'on' } }
            Mock Invoke-UI4MEBatch { }
            $itemOwner = $null
            foreach ($b in $script:UiBuilder.Bindings) { if ($b.Apply -eq 'Set-UiWhenBinding') { $itemOwner = $b.Owner } }
            $itemOwner | Should -Not -BeNullOrEmpty
            1..10 | ForEach-Object { $flag.Set($true); $flag.Set($false) }
            $itemOwner.Children.Count | Should -BeLessOrEqual 1
        }
    }
}

Describe 'Application id (parity with Python _derived_app_id)' {
    It 'derives ids like Python, including digit-first and non-ASCII titles' {
        InModuleScope UI4ME {
            Get-UiDerivedAppId 'My App' | Should -Be 'org.ui4me.app.my-app'
            Get-UiDerivedAppId '2048' | Should -Be 'org.ui4me.app.2048'
            # python3 -c "import hashlib;print(hashlib.sha256('日本語ツール'.encode()).hexdigest()[:12])"
            Get-UiDerivedAppId ([string]::new([char[]](0x65E5, 0x672C, 0x8A9E, 0x30C4, 0x30FC, 0x30EB))) | Should -Be 'org.ui4me.app.app-684678785419'
            Get-UiDerivedAppId '' | Should -Be ('org.ui4me.app.app-' + 'e3b0c44298fc')
            Get-UiDerivedAppId ('x' * 70) | Should -Be ('org.ui4me.app.' + ('x' * 60))
            # Non-ASCII letters never leak into the id (-creplace, not case-insensitive -replace).
            Get-UiDerivedAppId ([string]::new([char[]](0x130, 0x73))) | Should -Match '^[A-Za-z][A-Za-z0-9_.-]{0,127}$'
        }
    }
    It 'a digit-first title starts the app (regression: derived id was checked as a dotted identity)' {
        Mock Start-UI4MEScript -ModuleName UI4ME { throw "reached Start-UI4MEScript AppId=[$AppId]" }
        { Invoke-UI4MEApp -Title '2048' -Content { } } | Should -Throw 'reached Start-UI4MEScript AppId=`[`]'
    }
    It 'still validates a caller-supplied -AppId as a dotted identity and passes it to Core' {
        Mock Start-UI4MEScript -ModuleName UI4ME { throw "reached Start-UI4MEScript AppId=[$AppId]" }
        { Invoke-UI4MEApp -Title 'x' -AppId '2048' -Content { } } | Should -Throw '*AppId may contain only*'
        { Invoke-UI4MEApp -Title 'x' -AppId 'org.example.Tool' -Content { } } | Should -Throw 'reached Start-UI4MEScript AppId=`[org.example.Tool`]'
    }
    It 'passes the calling script path to Start-UI4MEScript -ScriptPath' {
        Mock Start-UI4MEScript -ModuleName UI4ME { throw "SCRIPTPATH=[$ScriptPath]" }
        $dir = Join-Path $TestDrive 'dir with space'
        $null = New-Item -ItemType Directory -Path $dir -Force
        $app = Join-Path $dir 'app.ps1'
        Set-Content -LiteralPath $app -Value "Invoke-UI4MEApp -Title 'Demo' -Content { }"
        { & $app } | Should -Throw ('SCRIPTPATH=`[' + [WildcardPattern]::Escape($app) + '`]')
    }
}

Describe 'Skill installer state' {
    It 'reports a fresh install as installed, then modified (regression: hidden marker on Linux/macOS)' {
        $home2 = Join-Path $TestDrive 'proj'
        $null = New-Item -ItemType Directory -Path $home2 -Force
        $r = Install-UI4MEUiSkill -Scope project -ProjectPath $home2 -Agents claude
        $r.Action | Should -Be 'installed'
        (Install-UI4MEUiSkill -Action status -Scope project -ProjectPath $home2 -Agents claude).State | Should -Be 'installed'
        (Install-UI4MEUiSkill -Scope project -ProjectPath $home2 -Agents claude).Action | Should -Be 'installed'   # clean update, no -Force
        Add-Content -LiteralPath (Join-Path $r.Path 'SKILL.md') -Value 'local edit'
        (Install-UI4MEUiSkill -Action status -Scope project -ProjectPath $home2 -Agents claude).State | Should -Be 'modified'
        { Install-UI4MEUiSkill -Scope project -ProjectPath $home2 -Agents claude } | Should -Throw '*Refusing to replace modified*'
        { Install-UI4MEUiSkill -Action uninstall -Scope project -ProjectPath $home2 -Agents claude } | Should -Throw '*Refusing to remove modified*'
        (Install-UI4MEUiSkill -Action uninstall -Scope project -ProjectPath $home2 -Agents claude -Force).Action | Should -Be 'removed'
        Test-Path -LiteralPath $r.Path | Should -BeFalse
    }
}

Describe 'Source encoding for Windows PowerShell 5.1' {
    It 'every PowerShell source with non-ASCII bytes has a UTF-8 BOM' {
        $repo = Join-Path $PSScriptRoot '..\..'
        # Windows PowerShell 5.1 ignores -Include together with -LiteralPath: filter explicitly.
        $files = @(Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot '..\Ui4me') -Recurse -File |
            Where-Object { @('.ps1', '.psm1', '.psd1') -contains $_.Extension })
        $examples = Join-Path $repo 'examples\powershell'
        if (Test-Path -LiteralPath $examples) { $files += @(Get-ChildItem -LiteralPath $examples -File -Filter '*.ps1') }
        $files += @(Get-ChildItem -LiteralPath $PSScriptRoot -File -Filter '*.ps1')
        $bad = foreach ($f in $files) {
            $bytes = [System.IO.File]::ReadAllBytes($f.FullName)
            $bom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
            if (-not $bom -and @($bytes | Where-Object { $_ -gt 127 }).Count -gt 0) { $f.FullName }
        }
        @($bad) | Should -BeNullOrEmpty
    }
}


Describe 'Theme switch suspends CSS transitions (Core forwards every DOM event)' {
    It 'adds u4-theme-switching before the restyle and removes it from an app-owned timer' {
        InModuleScope UI4ME {
            $ctx = New-UiContext -Title 'T' -Theme 'system' -Css $null -Assets $null -OnError $null
            $ctx.Document = [pscustomobject]@{ Id = 'doc' }
            $ctx.CurrentOwner = [pscustomobject]@{ Cleanups = (New-Object Collections.ArrayList) }
            $script:UiBuilder = $ctx
            $script:Order = New-Object Collections.ArrayList
            Mock Invoke-UI4MEBatch { foreach ($op in $Operations) { [void]$script:Order.Add("$($op.op):$($op.name)") } }
            Mock Set-UI4MEEnvironment { [void]$script:Order.Add("env:$ColorScheme") }
            Mock Set-UI4MEStylesheet { [void]$script:Order.Add('css') }
            try {
                Set-UI4MEUiTheme -ColorScheme dark
                @($script:Order) | Should -Be @('add_class:u4-theme-switching', 'env:dark')
                $timer = @($ctx.Timers)[-1]
                $timer.Owner | Should -BeNullOrEmpty
                Invoke-UiCallable $timer.Action
                @($script:Order)[-1] | Should -Be 'remove_class:u4-theme-switching'
                $script:Order.Clear()
                Set-UI4MEUiTheme -Css '.x{}'
                @($script:Order) | Should -Be @('add_class:u4-theme-switching', 'css')
            } finally { $script:UiBuilder = $null }
        }
    }

    It 'ships no colour transitions on controls in the default theme' {
        $css = Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\Ui4me\assets\theme.css') -Raw
        $css | Should -Not -Match '\.u4-btn \{[^}]*transition:'
        (Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\Ui4me\assets\functional.css') -Raw) |
            Should -BeLike '*.u4-theme-switching, .u4-theme-switching * { transition: none !important; }*'
    }
}
