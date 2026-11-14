# Component catalog

UI4ME uses a declarative component API. Python functions in `from ui4me import ui` return component refs with ownership and styles; PowerShell uses `New-UI4ME*` commands from `Import-Module UI4ME`. **Not every component is available in both languages**; language-specific differences are listed below.

| Group | Documentation | Examples |
| --- | --- | --- |
| Layout | [Layout and dashboards](layout.md) | row/column/card/grid/shell/split/fieldset/metric |
| Controls | [Inputs and forms](inputs.md) | text, number, date/time, selection, validated forms |
| Data | [Tables and streaming](data.md) | tables, logs, chat, data queries |
| Navigation | [Navigation and menus](navigation.md) | tabs, accordion, menu, command palette |
| Feedback | [Dialogs and status](feedback.md) | toast, dialog, alert, tooltip |

See the [gallery](../gallery.md) for complete runnable applications and [Python API](../reference/python-api.md) / [PowerShell command reference](../reference/powershell-api.md) for names and signatures.

Common rules: use `id`/refs for elements, deliver user text through escaped text or Core `set_text`, use trusted HTML only for explicitly trusted markup, dispose timers/tasks with owning components, and never assume an OS capability that Core does not provide.
