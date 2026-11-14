# Python components — practical reference

Use `from ui4me import ui`. This is the high-level, component-first facade, not raw `ui4me_core.Document` APIs.

| Family | Typical calls |
| --- | --- |
| Layout | `ui.row`, `ui.column`, `ui.stack`, `ui.grid`, `ui.card`, `ui.scroll`, `ui.shell`, `ui.sidebar`, `ui.content`, `ui.split`, `ui.resizable_split`, `ui.fieldset`, `ui.tooltip` |
| Text/visual | `ui.heading`, `ui.text`, `ui.caption`, `ui.badge`, `ui.markdown`, `ui.code`, `ui.icon`, `ui.image`, `ui.metric`, `ui.sparkline` |
| Input | `ui.button`, `ui.copy_button`, `ui.input`, `ui.password`, `ui.number`, `ui.textarea`, `ui.checkbox`, `ui.switch`, `ui.select`, `ui.multiselect`, `ui.radio`, `ui.slider`, `ui.segmented`, `ui.combobox`, `ui.date`, `ui.time`, `ui.color`, `ui.path`, `ui.file_input` |
| Dynamic | `ui.when`, `ui.each`, `ui.state`, `ui.computed`, `ui.effect`, `ui.batch` |
| Navigation | `ui.tabs`, `ui.navigation`, `ui.breadcrumbs`, `ui.tree`, `ui.menu`, `ui.command_palette`, `ui.drawer` |
| Data | `ui.table`, `ui.query_table`, `ui.log`, `ui.chat` |
| Feedback | `ui.alert`, `ui.empty`, `ui.loading`, `ui.error_state`, `ui.dialog`, `ui.confirm`, `ui.notify`, `ui.progress`, `ui.spinner` |
| Advanced | `ui.component`, `ui.html` (trusted only), `ui.css`, `ui.stylesheet`, `ui.theme`, `ui.density` |

A component returns a reference with common methods like `.classes.add()`, `.style.set()`, `.attr()`, `.on()`, `.dispose()` and `.focus()` where applicable. Use only documented methods; inspect signatures when unsure.

```python
with ui.resizable_split(percent=35) as split:
    pass  # named slot panes are built separately
with split.side:
    ui.text("Navigation")
with split.main:
    ui.table([{"id": 1, "name": "Job"}], key="id", sort=True)
```

For any component that has multiple named slots use the exact API shown in its source/docs; `ui.resizable_split` can be created without a with block:

```python
split = ui.resizable_split(percent=35)
with split.side:
    ui.text("Left")
with split.main:
    ui.text("Right")
```

Use `ui.multiselect("Features", options={"a":"Alpha", "b":"Beta"}, value=("a",))` and read its `value` tuple. It uses native checkboxes rather than a simulated browser popover.

Do not treat CSS support as arbitrary web compatibility. The Core HTML/CSS scope is authoritative.
