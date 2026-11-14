# Python API reference — UI4ME 2.1.0

Import `from ui4me import ui`, create a top-level `with ui.app(title, width=..., height=..., theme=..., app_id=...) as app:`, then call `app.run()` **after** the `with` block. Launch the script directly with `python app.py` / `uv run app.py`. Advanced Core types remain available directly from `ui4me` / `ui4me_core`.

## State and app

- `ui.state(initial)` -> Signal: `.value`, `.peek()`, `.set(v)`, `.update(fn)`, `.mutate(fn)`, `.subscribe(fn)`.
- `ui.computed(fn)` -> computed reactive value; `ui.effect(fn)` -> side effect with disposable reaction; `with ui.batch():` batches multiple mutations.
- `app.window(title,width,height,on_close=...)` creates another native window; `app.stop()`, `app.close()`, `app.post(callback)`, `app.after(seconds,fn)`, `app.every(seconds,fn)` control lifetime and scheduling.
- `app.tasks` runs bounded background work; `app.settings.get/set/remove/state` persists JSON settings by app ID; `app.desktop` exposes capability-dependent native services; `app.commands` registers app commands/shortcuts.
- `app.theme.tokens(...)`, `app.theme.load(css,mode='replace')`, `ui.theme_preset(name)`, `ui.density(name)`, `ui.css(css)`, `ui.stylesheet(...)` customize appearance.

## Text, layout, controls

| Family | Public calls |
| --- | --- |
| Text | `ui.text`, `ui.heading`, `ui.caption`, `ui.badge`, `ui.markdown`, `ui.code`, `ui.link`, `ui.icon`, `ui.image` |
| Layout | `ui.row`, `ui.column`, `ui.stack`, `ui.card`, `ui.surface`, `ui.paper`, `ui.grid`, `ui.scroll`, `ui.spacer`, `ui.divider`, `ui.shell`, `ui.sidebar`, `ui.content`, `ui.header`, `ui.footer`, `ui.statusbar`, `ui.toolbar`, `ui.split`, `ui.resizable_split`, `ui.fieldset`, `ui.metric` |
| Inputs | `ui.button`, `ui.icon_button`, `ui.input`, `ui.password`, `ui.textarea`, `ui.number`, `ui.checkbox`, `ui.switch`, `ui.radio`, `ui.select`, `ui.multiselect`, `ui.segmented`, `ui.slider`, `ui.date`, `ui.time`, `ui.datetime`, `ui.month`, `ui.week`, `ui.color`, `ui.email`, `ui.url`, `ui.search`, `ui.telephone`, `ui.combobox`, `ui.path`, `ui.file_input` |
| Dynamic | `ui.when`, `ui.each`, `ui.component`, `ui.html` (trusted markup), `ui.slot` |
| Data | `ui.table`, `ui.query_table`, `ui.tree`, `ui.log`, `ui.chat`, `ui.sparkline`, `ui.progress_ring` |
| Navigation | `ui.tabs`, `ui.navigation`, `ui.breadcrumbs`, `ui.accordion`, `ui.disclosure`, `ui.menu`, `ui.command_palette`, `ui.drawer` |
| Feedback | `ui.notify`, `ui.dialog`, `ui.confirm`, `ui.alert`, `ui.tooltip`, `ui.copy_button`, `ui.empty`, `ui.loading`, `ui.error_state`, `ui.spinner`, `ui.progress` |
| Forms | `ui.form(Dataclass, on_submit=..., validation_mode='submit'|'change'|'blur')` |

Component refs provide `.id`, `.on(event, callback)`, `.classes`, `.style`, `.attr(name,value)`, `.focus()`, `.visible`, `.dispose()` and Core escape hatches where meaningful. Not every ref exposes every method (e.g. text `.set`, input `.set_value`, dialog `.open/.close`, list `.scope`). Public component call signatures are in [`src/ui4me/_ui/ui.py`](https://github.com/ui4me/ui4me/blob/main/src/ui4me/_ui/ui.py); the corresponding class code defines argument validation.

## Forms

`form.values` gets raw field values, `form.fields[name]` accesses the specific control, `form.validate()` returns issues and focuses the first error, `form.submit()` runs validated submit handlers, `form.reset()` resets values, `form.mark_clean()` resets pristine baseline. `form.dirty`, `form.touched`, `form.valid`, `form.submitting` are signals.

## Core protocol and native APIs

For window/clipboard/file dialogs/host capabilities, use `app.core` / `app.desktop` or directly call Core APIs documented by [Core](https://github.com/ui4me/ui4me-core/blob/main/docs/reference/python-api.md). Never invent native OS services not exposed by Core. Never use a separate Python HTTP server for UI4ME rendering.
