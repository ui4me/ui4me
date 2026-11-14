# PowerShell dashboard using the native UI4ME component module.
# Run directly: pwsh -File ./examples/powershell/dashboard.ps1
$ErrorActionPreference = 'Stop'
Import-Module UI4ME

Invoke-UI4MEApp -Title 'UI4ME Operations' -Width 1040 -Height 760 -Content {
    $rows = New-UI4MEState -Value @(
        [pscustomobject]@{ Name = 'Gateway'; Team = 'Platform'; State = 'Healthy'; Latency = 19 },
        [pscustomobject]@{ Name = 'Backup'; Team = 'Storage'; State = 'Warning'; Latency = 108 },
        [pscustomobject]@{ Name = 'Alerts'; Team = 'Security'; State = 'Healthy'; Latency = 31 }
    )
    $checkedAt = New-UI4MEState -Value 'Not checked yet'
    New-UI4MEHeading -Text 'Operations dashboard' -Level 1
    New-UI4MEAlert -Text 'A pure PowerShell desktop app; no Python runtime.' -Tone info
    New-UI4MERow -Content {
        New-UI4MEMetric -Label 'Services' -Value 3 -Detail 'Local demo'
        New-UI4MEMetric -Label 'Warnings' -Value 1 -Detail 'Review backup'
        New-UI4MEMetric -Label 'Last refresh' -Value $checkedAt
    }
    New-UI4MEResizableSplit -Percent 30 -Side {
        New-UI4MEHeading -Text 'Workspace' -Level 3
        New-UI4METext -Text 'Adjust panel width using the slider.'
        New-UI4MEIcon -Name folder -Label 'Folder'
    } -Main {
        New-UI4MEHeading -Text 'Service inventory' -Level 3
        New-UI4METable -Columns @('Name','Team','State','Latency') -Rows $rows
    }
    New-UI4MERow -Content {
        New-UI4MEButton -Text 'Refresh' -OnClick {
            $checkedAt.Set((Get-Date -Format HH:mm:ss))
            Show-UI4MEUiToast -Text 'Inventory checked' -Tone success
        }
        New-UI4MEButton -Text 'Quit' -Variant secondary -OnClick { Stop-UI4MEUiApp }
    }
}
