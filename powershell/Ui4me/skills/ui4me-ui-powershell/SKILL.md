---
name: ui4me-ui-powershell
description: Build native desktop GUI applications in PowerShell 7 or Windows PowerShell 5.1 using UI4ME components on UI4ME.Core 1.0.1+. Supports state, layouts, forms, events, tables, timers, tasks and native dialogs without browser or Python.
---

# UI4ME high-level PowerShell skill

This is the `UI4ME` (Gallery package `Ui4me`) **component** module. It requires `UI4ME.Core>=1.0.1,<2` for native host, DOM, input, accessibility and OS integration. All UI/application logic stays in PowerShell, including on Linux. Do not ship Python, Node, WPF, WebKit, browsers, HTTP listeners or JavaScript.

## Run a normal PowerShell script

```powershell
Install-Module UI4ME -Scope CurrentUser
pwsh -File ./app.ps1
# Windows PowerShell 5.1: powershell.exe -NoProfile -File .\app.ps1
```

`app.ps1`:

```powershell
$ErrorActionPreference = 'Stop'
Import-Module UI4ME

Invoke-UI4MEApp -Title 'Tasks' -Width 800 -Height 560 -Content {
    $count = New-UI4MEState -Value 0
    New-UI4MEHeading -Text 'Tasks' -Level 1
    New-UI4MERow -Content {
        New-UI4MEButton -Text 'Finish task' -OnClick {
            $count.Set([int]$count.Value + 1)
        }
        New-UI4METext -Bind $count
    }
}
```

`Invoke-UI4MEApp` now delegates direct startup to Core's `Start-UI4MEScript`: no manifest or `Start-UI4MEUiScript` is required. With direct startup, statements before `Invoke-UI4MEApp` may execute twice (launcher and supervised backend). Keep side effects in `-Content` or `-OnReady`. `Start-UI4MEUiScript` is retained for advanced/headless compatibility.

## Rules for correct PowerShell apps

1. Build with `Invoke-UI4MEApp -Content { ... }`. `New-UI4ME*` functions create components and return IDs or state objects. Callbacks execute on the same UI runspace; do not access Core UI from jobs, runspaces or .NET worker threads.
2. Use `New-UI4MEState -Value initial` and `New-UI4MEComputed -DependsOn @($a,$b) -Expression {...}`; `.Value` reads, `.Set()` mutates. UI4ME Core handles the native channel and document updates.
3. Prefer native `New-UI4MEInput/Checkbox/Select/Radio/Slider`, `New-UI4MEDate/Time/Color`, and `New-UI4MEMultiSelect`, using `-Bind` to connect states. State/checkbox input handlers must not echo an older value over newly typed characters.
4. Compose `New-UI4MERow/Column/Card/Grid/Shell/Sidebar/Content/Fieldset`; use forms with `New-UI4MEForm` and `-OnSubmit`; table and dynamic lists with `New-UI4METable`, `New-UI4MEEach -Key`, `New-UI4MEWhen`.
5. Use owner-aware timers/tasks `Start-UI4MEUiTimer`/`Start-UI4MEUiTask`. Completion callbacks run on the owner runspace. Terminated windows/regions must not receive stale callbacks.
6. Use native `Show-UI4MEUiFileDialog`, settings, `Get-UI4MEUiContext` for public Core escape hatch, and `Set-UI4MEUiTheme` to replace only visual CSS. Native system tray, OS menus, print/PDF and global hotkeys are not in Core 1.x.
7. Never build raw HTML with untrusted values. `New-UI4METext` escapes HTML, `New-UI4MEHtml` explicitly trusts markup; Core never executes JavaScript.
8. In callbacks, PowerShell variables defined in the `-Content` block remain visible through dot-sourcing. Scriptblocks created *inside a function* may need explicit capture. Internal UI4ME framework callbacks use `{Fn,Data}` to preserve access to private module functions.
9. Tests: Pester 5 mocks, then real Core host `-Headless`, then actual Linux KDE Wayland and Windows PowerShell 7/5.1 GUI input. Do not equate mock test pass with native qualification.

## References

- [PowerShell components, state and data](references/components.md)
- [Lifecycle, tasks, Native Core and platform facts](references/lifecycle.md)
- [Testing, agent setup, publishing](references/testing-and-release.md)

High-level module source: https://github.com/ui4me/ui4me · Core: https://github.com/ui4me/ui4me-core
