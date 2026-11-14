# Run directly: pwsh -File ./examples/powershell/counter.ps1 (or powershell.exe -File on Windows).
# Compatibility mode: Start-UI4MEUiScript -Path ./examples/powershell/counter.ps1 -Title 'Counter'
$ErrorActionPreference = 'Stop'
Import-Module UI4ME

Invoke-UI4MEApp -Title 'Counter' -Width 620 -Height 420 -Content {
    $counter = New-UI4MEState -Value 0
    $increment = { $counter.Set([int]$counter.Value + 1) }.GetNewClosure()
    $reset = { $counter.Set(0) }.GetNewClosure()
    New-UI4MEHeading -Text 'UI4ME 2 / PowerShell'
    New-UI4METext -Text 'Native HTML/CSS, no web server'
    New-UI4MECard -Content {
        New-UI4METext -Bind $counter
        New-UI4MERow -Content {
            New-UI4MEButton -Text 'Increment' -OnClick $increment
            New-UI4MEButton -Text 'Reset' -Variant secondary -OnClick $reset
        }
    }
}
