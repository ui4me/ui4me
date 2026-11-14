# UI4ME documentation

UI4ME is the high-level Python and PowerShell component framework for [UI4ME Core](https://github.com/ui4me/ui4me-core): native HTML/CSS desktop windows, without JavaScript, a browser, Electron, Node or an HTTP server.

## Start here

| I want to… | Python | PowerShell |
| --- | --- | --- |
| Install | [Install Python](guides/install-python.md) | [Install PowerShell](guides/install-powershell.md) |
| Build my first app | [Python quickstart](guides/quickstart-python.md) | [PowerShell quickstart](guides/quickstart-powershell.md) |
| Learn practical patterns | [Python recipes](recipes/python.md) | [PowerShell recipes](recipes/powershell.md) |
| Read the complete public API | [Python reference](reference/python-api.md) | [PowerShell reference](reference/powershell-api.md) |
| Install coding-agent skills | [Agent skills](guides/agent-skills.md) | [Agent skills](guides/agent-skills.md) |
| Explore every control | [Component catalog](components/index.md) | [Gallery](gallery.md) |

## Concepts and maintenance

- [Reactive state](concepts/reactivity.md) · [Lifecycle and threading](concepts/lifecycle.md) · [Themes and CSS](concepts/theming.md)
- [Accessibility](concepts/accessibility.md) · [Core integration and limitations](concepts/core-integration.md) · [Compatibility](reference/compatibility.md)
- [Troubleshooting](guides/troubleshooting.md) · [Building](release/building.md) · [Testing](release/testing.md) · [Publishing](release/publishing.md)

Core owns the native rendering/IPC. UI4ME owns components, state, theme and application-level behavior. The two packages release independently.
