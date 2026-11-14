# Python recipes

Each recipe assumes `from ui4me import ui` and a running `with ui.app('Example') as app:` block; finish with `app.run()`. Use named callbacks for actions.

## Counter / reactive values

```python
count = ui.state(0)
ui.text(ui.computed(lambda: f'Count: {count.value}'))

def increment(event):
    count.update(lambda old: old + 1)
ui.button('Add', on_click=increment)
```

## Forms from a dataclass

```python
from dataclasses import dataclass, field

@dataclass
class Contact:
    name: str = field(default='', metadata={'required': True, 'min_length': 2})
    email: str = field(default='', metadata={'pattern': 'email'})

def saved(contact):
    ui.notify('Saved ' + contact.name)

form = ui.form(Contact, on_submit=saved, validation_mode='change')
```

## Table, filter and selected item

```python
records = ui.state([{'id': 1, 'name': 'First'}, {'id': 2, 'name': 'Second'}])
ui.table(records, columns=['name'], key='id', search=True, sort=True)
```

## Layout and responsive split

```python
with ui.resizable_split(percent=30) as split:
    with split.side:
        ui.text('Project list')
    with split.main:
        ui.text('Editor')
```

## Background work

Use `app.tasks` or `app.post` rather than writing signals or DOM from a worker thread. Cancel tasks when components close; do not retain stale window references in callbacks. See [threading and lifecycle](../concepts/lifecycle.md).

## Core escape hatch

For native dialogs and desktop preferences, call `app.desktop` or `window.core.native`; unsupported APIs raise `NotImplementedError`. For trusted custom HTML only, use `ui.html(trusted_markup)`. User-supplied text must be escaped or delivered using `ui.text`.
