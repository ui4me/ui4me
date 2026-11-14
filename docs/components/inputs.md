# Inputs and forms

**Python controls:** `ui.input`, `ui.password`, `ui.textarea`, `ui.number`, `ui.checkbox`, `ui.switch`, `ui.radio`, `ui.select`, `ui.multiselect`, `ui.segmented`, `ui.slider`, `ui.date`, `ui.time`, `ui.datetime`, `ui.month`, `ui.week`, `ui.color`, `ui.search`, `ui.path`, `ui.file_input`, `ui.combobox`, `ui.fieldset`.

```python
with ui.fieldset('Filters'):
    query = ui.input('Search', placeholder='Item name')
    choices = ui.multiselect('Tags', options=['Security', 'Desktop', 'Testing'], value=('Testing',))
    ui.text(lambda: f'Selected: {", ".join(choices.value)}')
```

**PowerShell:** `New-UI4MEInput`, `New-UI4MENumber`, `New-UI4METextArea`, `New-UI4MECheckbox`, `New-UI4MERadio`, `New-UI4MESelect`, `New-UI4MEMultiSelect`, `New-UI4MESegmented`, `New-UI4MESlider`, `New-UI4MEDate`, `New-UI4METime`, `New-UI4MEColor`, `New-UI4MEForm`, `New-UI4MEFieldset`.

Core 1.0.1 deliberately rejects unsupported native HTML `date/time/color` pickers: UI4ME provides in-window text/calendar/swatch controls instead. Multi-select uses visible accessible checkboxes, not a fake native picker.

**Python typed forms:** `ui.form(MyDataclass, on_submit=..., validation_mode='submit'|'change'|'blur')`. `form.dirty`, `form.touched`, `form.valid` are signals; `form.validate()`, `form.reset()`, `form.mark_clean()` manage state. Field metadata supports required, validators, choices, min/max and descriptions. PowerShell has a native Core-backed `New-UI4MEForm` and field controls; full schema-driven parity is not claimed.

Do not pass secrets into general logs or HTML `replace_html`; use password fields and escaped text. Test keyboard navigation and IME on actual platforms.
