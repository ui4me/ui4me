# Tests, installed module and release

Local: `Import-Module ./powershell/Ui4me/Ui4me.psd1 -Force` after installing `UI4ME.Core>=1.0.1`; Pester: `Invoke-Pester ./powershell/tests` in pwsh and Windows PowerShell 5.1.

Native UI: `pwsh -File ./examples/powershell/gallery.ps1`; headless only for tests: `Start-UI4MEUiScript -Headless -Path ./examples/powershell/gallery.ps1`.

Build from repository root: `python tools/build_dist.py dist`. Output is one wheel, one sdist, one PowerShell module ZIP, plus source/checksum records. The PowerShell module is pure PS and includes its own CSS, README and agent skill; it must not bundle Rust/Core binaries.

Install coding-agent skill: `Install-UI4MEUiSkill -Agents all -Scope user`; status/uninstall with `-Action status|uninstall`; project scope `-Scope project -ProjectPath .`. Existing unowned/modified skills are not replaced without `-Force`.

Publishing is manual after local Linux Python, Windows Python, Linux pwsh, Windows pwsh and Windows PowerShell 5.1 acceptance gates. Do not publish an artifact from an unqualified source commit. Check registry for unused version; UI4ME 2.1.0 is a candidate until native tests pass.
