# Release and platform compatibility

| Package | Candidate | Dependency | Supported language |
| --- | --- | --- | --- |
| Python `ui4me` | 2.1.0 | `ui4me-core>=1.0.1,<2` | Python 3.11–3.14 |
| PowerShell `UI4ME` | 2.1.0 | `UI4ME.Core>=1.0.1,<2` | pwsh 7.2+ Linux/Windows; Windows PowerShell 5.1 on Windows |

Core hosts are qualified on Debian 13/KDE Plasma 6 Wayland and Windows Server 2022 x64. This UI4ME source candidate has **not yet independently passed its 2.1.0 native qualification gates**. Other Linux desktops, macOS, X11 sessions and ARM are not qualified. The local release agent must test the exact final packages on each platform and record evidence before publishing.

`ui4me` and `ui4me-core` publish independently. PowerShell Gallery package id is `Ui4me`; module folder/manifest casing must be preserved on Linux. The historical `ui4me` 1.x was an earlier different library; UI4ME 2.x is intentionally a new high-level component framework with no backward compatibility guarantee for 1.x APIs. The latest previous release was UI4ME 2.0.1 on GitHub (2.0.0 on registries), and Core 1.0.1 on both registries. Choose a registry-unused version if 2.1.0 is already occupied.
