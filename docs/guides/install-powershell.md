# Install UI4ME for PowerShell

**Platform:** PowerShell 7.2+ on Linux x64 and Windows x64, or Windows PowerShell 5.1 on Windows x64. `UI4ME` depends on `UI4ME.Core` 1.0.1 or later in the 1.x series. There is no Python or Rust runtime dependency.

```powershell
Install-Module UI4ME -Scope CurrentUser
Import-Module UI4ME
Get-Command -Module UI4ME | Select-Object -First 10
```

For source development, first install `UI4ME.Core`, then add the checkout's `powershell` folder to `PSModulePath` and import the `Ui4me/Ui4me.psd1` manifest. Case-sensitive Linux installations **must** retain the `Ui4me` folder and `Ui4me.psd1`/`Ui4me.psm1` file casing.

```powershell
$env:PSModulePath = (Join-Path $PWD 'powershell') + [IO.Path]::PathSeparator + $env:PSModulePath
Import-Module ./powershell/Ui4me/Ui4me.psd1 -Force
```

Next: [quickstart](quickstart-powershell.md), [recipes](../recipes/powershell.md), [PowerShell commands](../reference/powershell-api.md).
