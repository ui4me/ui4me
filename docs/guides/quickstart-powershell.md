# PowerShell: your first UI4ME app

Install `UI4ME` from the PowerShell Gallery (`Install-Module UI4ME -Scope CurrentUser`); it requires `UI4ME.Core` 1.0.1+. Save as `app.ps1`:

```powershell
$ErrorActionPreference = 'Stop'
Import-Module UI4ME

Invoke-UI4MEApp -Title 'Greeter' -Width 560 -Height 360 -Content {
    $name = New-UI4MEState -Value 'world'
    New-UI4MEHeading -Text 'Welcome'
    New-UI4MEInput -Label 'Your name' -Bind $name
    New-UI4METext -Bind $name
    New-UI4MEButton -Text 'Quit' -OnClick {
        Stop-UI4MEUiApp
    }
}
```

Run directly:

```powershell
pwsh -File ./app.ps1
# On Windows PowerShell 5.1:
powershell.exe -NoProfile -File .\app.ps1
```

The high-level `Invoke-UI4MEApp` calls Core's `Start-UI4MEScript` when necessary, which starts the native window host and reruns the same script under a managed backend. Side effects before bootstrap can execute twice. Event handlers and UI operations run on the PowerShell UI runspace. Use background tasks through `Start-UI4MEUiTask`, not UI calls from external runspaces.

**Legacy commands** `Start-UI4MEUiScript -Path ...` and Core `Start-UI4MEHost -Manifest ...` remain for advanced integrations and headless tests. You do not need them for ordinary apps.

See [PowerShell recipes](../recipes/powershell.md), [components](../components/index.md), and [PowerShell reference](../reference/powershell-api.md).
