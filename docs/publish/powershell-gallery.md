# UI4ME — native desktop UI components for PowerShell

Use ordinary PowerShell to build native desktop applications with high-level components, state and CSS themes. The module depends on [UI4ME.Core](https://www.powershellgallery.com/packages/UI4ME.Core) for native Rust host, layout, events, accessibility and desktop dialogs. **No Python runtime, browser, JavaScript, WPF or HTTP server required.**

## Install

```powershell
Install-Module UI4ME -Scope CurrentUser
Import-Module UI4ME
```

Supported: PowerShell 7.2+ on Linux x64 (Wayland) and Windows x64, and Windows PowerShell 5.1 on Windows x64. Requires `UI4ME.Core` 1.0.1 or later within 1.x.

## Your first app — save as `app.ps1`

```powershell
Import-Module UI4ME

Invoke-UI4MEApp -Title 'Hello' -Content {
    $count = New-UI4MEState -Value 0
    New-UI4MEHeading -Text 'Native PowerShell UI'
    New-UI4METext -Bind $count
    New-UI4MEButton -Text 'Click' -OnClick {
        $count.Set([int]$count.Value + 1)
    }
}
```

Run it normally with `pwsh -File ./app.ps1` or, on Windows, `powershell.exe -NoProfile -File .\app.ps1`. **No host manifest is required.** UI4ME delegates direct startup and native host supervision to UI4ME.Core. Code above bootstrap may run twice.

## Features

State and computed values, text and input bindings, forms and selection, buttons, segmented inputs, multiselect, accessible fieldsets, grids and native-window layout, metrics and logs, tabs, tables, keyed lists, timers and cancellable background tasks, dialogs/toasts, CSS theme replacement, file dialogs and agent-skill installer. Advanced Core commands remain directly available.

PowerShell is still missing some of Python's advanced data-source controls, multiwindow composition and rich Markdown/chat widgets. The documentation explicitly identifies unsupported functionality.

[PowerShell quickstart](https://github.com/ui4me/ui4me/blob/main/docs/guides/quickstart-powershell.md) · [PowerShell command reference](https://github.com/ui4me/ui4me/blob/main/docs/reference/powershell-api.md) · [Gallery](https://github.com/ui4me/ui4me/blob/main/docs/gallery.md) · [Source](https://github.com/ui4me/ui4me) · [License](https://github.com/ui4me/ui4me/blob/main/LICENSE)
