# PowerShell recipes

Examples below belong in the `-Content` scriptblock of `Invoke-UI4MEApp`, unless noted otherwise. All UI interactions use the owning PowerShell runspace.

## Counter

```powershell
$count = New-UI4MEState -Value 0
New-UI4METext -Bind $count
New-UI4MEButton -Text 'Add one' -OnClick {
    $count.Set([int]$count.Value + 1)
}
```

## Table and log

```powershell
$rows = New-UI4MEState -Value @(
    [pscustomobject]@{ Name='Host A'; State='Online' },
    [pscustomobject]@{ Name='Host B'; State='Offline' }
)
New-UI4METable -Columns @('Name', 'State') -Rows $rows
$logId = New-UI4MELog -MaxLines 100
New-UI4MEButton -Text 'Log status' -OnClick {
    Add-UI4MELogLine -Element $logId -Text ('Checked at ' + (Get-Date -Format o))
}
```

## Form

```powershell
New-UI4MEForm -Content {
    New-UI4MEInput -Label 'Name'
    New-UI4MECheckbox -Label 'Enabled'
} -OnSubmit {
    param($data, $event)
    Show-UI4MEUiToast -Text 'Submitted'
}
```

## Adjustable panels and status

```powershell
New-UI4MEResizableSplit -Side {
    New-UI4METext -Text 'Navigation'
} -Main {
    New-UI4METext -Text 'Details'
} -Percent 35
```

## Native file dialog

Call `Show-UI4MEUiFileDialog` from a user event handler; check cancellation and returned paths. Core handles desktop policy, such as Wayland file dialog support. Use `Get-UI4MEUiContext` only when necessary for documented Core commands.
