# UI4ME 2 PowerShell component gallery.
# Run directly: pwsh -File ./examples/powershell/gallery.ps1
$ErrorActionPreference = 'Stop'
Import-Module UI4ME

Invoke-UI4MEApp -Title 'UI4ME 2 Component Gallery' -Width 1000 -Height 760 -Content {
    $name = New-UI4MEState -Value 'Ada'
    $greeting = New-UI4MEComputed -DependsOn $name -Expression { "Hello, $($name.Value)!" }
    $todos = New-UI4MEState -Value @(
        [pscustomobject]@{ id = 1; title = 'Write the report' },
        [pscustomobject]@{ id = 2; title = 'Review the build' })
    $nextId = New-UI4MEState -Value 3
    $showDetails = New-UI4MEState -Value $false
    $progress = New-UI4MEState -Value 10
    $theme = New-UI4MEState -Value (Get-UI4MEUiSetting -Name theme -Default 'system')

    New-UI4MEHeading -Text 'UI4ME 2 — PowerShell components' -Level 1
    New-UI4MEAlert -Title 'Native' -Text 'Rendered by the UI4ME.Core host: no browser, Python or web server.' -Tone info

    New-UI4METabs -Tabs ([ordered]@{
        'Inputs' = {
            New-UI4MEGrid -Columns 2 -Content {
                New-UI4MECard -Title 'Text and choices' -Content {
                    New-UI4MEInput -Label 'Name' -Bind $name -Placeholder 'Your name'
                    New-UI4METext -Bind $greeting
                    New-UI4MESelect -Label 'Theme' -Options @('system', 'light', 'dark') -Bind $theme -OnChange {
                        param($value)
                        Set-UI4MEUiTheme -ColorScheme $value
                        Set-UI4MEUiSetting -Name theme -Value $value   # remembered next time
                    }
                    New-UI4MERadio -Label 'Size' -Options @('Small', 'Medium', 'Large') -Horizontal
                    New-UI4MECheckbox -Label 'Show details' -Bind $showDetails -Switch
                }
                New-UI4MECard -Title 'Dates, times and colours' -Content {
                    New-UI4MEDate -Label 'Deadline' -Value ([datetime]::Today)
                    New-UI4METime -Label 'Reminder' -Value '09:30'
                    New-UI4MEColor -Label 'Accent'
                    New-UI4MESlider -Label 'Volume' -Value 50
                }
            }
            New-UI4MEWhen -Condition $showDetails -Content {
                New-UI4MEAlert -Text 'Details appear only while the switch is on.' -Tone success
            }
        }
        'Lists' = {
            New-UI4MERow -Content {
                $newTodo = New-UI4MEInput -Label 'New task' -OnSubmit {
                    param($text)
                    if (-not $text) { return }
                    $todos.Set(@($todos.Value) + [pscustomobject]@{ id = $nextId.Value; title = $text })
                    $nextId.Set($nextId.Value + 1)
                    Set-UI4MEDocumentValue -Document (Get-UI4MEUiContext).Document -Element $newTodo -Value ''
                }
            }
            New-UI4MEEach -Items $todos -Key id -Empty { New-UI4METext -Text 'Nothing to do.' -Tone muted } -Template {
                param($todo)
                New-UI4MERow -Content {
                    New-UI4MECheckbox -Label $todo.title
                    New-UI4MEButton -Text 'Remove' -Variant ghost -Size sm -OnClick ({
                        $todos.Set(@($todos.Value | Where-Object { $_.id -ne $todo.id }))
                    }.GetNewClosure())
                }
            }
            New-UI4METable -Columns @('Feature', 'State') -Rows @(
                @{ Feature = 'Keyed lists'; State = 'DOM kept on reorder' },
                @{ Feature = 'Background tasks'; State = 'Cancellable' })
        }
        'New in 2.1' = {
            New-UI4MEHeading -Text 'Reusable desktop components' -Level 2
            New-UI4MERow -Content {
                New-UI4MEMetric -Label 'Checks' -Value 42 -Detail 'Ready'
                New-UI4MEMetric -Label 'Active' -Value $progress -Detail 'Reactive'
            }
            New-UI4MEFieldset -Legend 'Choice selection' -Content {
                $selected = New-UI4MEState -Value @('Testing')
                New-UI4MEMultiSelect -Label 'Topics' -Options @('Desktop', 'Security', 'Testing') -Bind $selected
                New-UI4MESegmented -Label 'Scale' -Options @('Small', 'Medium', 'Large')
            }
            New-UI4MEResizableSplit -Side {
                New-UI4METext -Text 'Left panel'
                New-UI4MEIcon -Name folder -Label 'Folder'
            } -Main {
                New-UI4MEHeading -Text 'Adjustable pane' -Level 3
                New-UI4METooltip -Text 'Available on hover and keyboard focus' -Content {
                    New-UI4MEButton -Text 'Hover or focus me'
                }
            }
            $galleryLog = New-UI4MELog -MaxLines 80 -Label 'Gallery events'
            New-UI4MEButton -Text 'Add log entry' -OnClick {
                Add-UI4MELogLine -Element $galleryLog -Text ('Updated at ' + (Get-Date -Format HH:mm:ss))
            }
            New-UI4MECopyButton -Text 'UI4ME PowerShell gallery' -Label 'Copy description'
        }
        'Feedback' = {
            New-UI4MEProgress -Label 'Work' -Value $progress
            New-UI4MERow -Content {
                New-UI4MEButton -Text 'Run background task' -OnClick {
                    $progress.Set(10)
                    $null = Start-UI4MEUiTask -Work { Start-Sleep -Milliseconds 800; 'done' } -OnDone {
                        param($result)
                        $progress.Set(100)
                        Show-UI4MEUiToast -Text "Task $result" -Tone success
                    }
                }
                New-UI4MEButton -Text 'Show toast' -Variant secondary -OnClick { Show-UI4MEUiToast -Text 'Hello from PowerShell' }
                New-UI4MEButton -Text 'Open file…' -Variant outline -OnClick {
                    $path = Show-UI4MEUiFileDialog -Kind Open -Title 'Choose a file'
                    if ($path) { Show-UI4MEUiToast -Text "Chose $path" } else { Show-UI4MEUiToast -Text 'Cancelled' -Tone warning }
                }
            }
            New-UI4MEAccordion -Title 'Escape hatch' -Content {
                New-UI4MECode -Text '$ctx = Get-UI4MEUiContext; Set-UI4MEDocumentText -Document $ctx.Document -Element <id> -Text ...'
            }
        }
    })
} -OnReady {
    if ($theme.Value -ne 'system') { Set-UI4MEUiTheme -ColorScheme $theme.Value }
}
