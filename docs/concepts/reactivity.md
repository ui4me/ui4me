# Reactive state and component ownership

## Python

`ui.state(initial)` returns a signal; read `.value`, write `.set(new)` or `.update(function)`. A `ui.computed(function)` reads signals and caches derived values. `ui.effect(function)` re-executes when dependencies change; return a cleanup callback when holding external resources. `with ui.batch():` groups state changes and commits one UI update.

```python
with ui.app('Counter') as app:
    count = ui.state(0)

    def count_label():
        return f'Count: {count.value}'

    label = ui.text(ui.computed(count_label))

    def add_one(event):
        count.set(count.value + 1)

    ui.button('Add', on_click=add_one)
app.run()
```

Signal values can trigger DOM patches; the app's owner thread executes component updates. Never modify UI state from external threads; use `app.post(callback)`. `app.tasks` executes background work and delivers results to the owner thread, with cancellation when an owning component is disposed.

## PowerShell

`New-UI4MEState -Value ...` returns a state object with `.Value`, `.Set(new)` and `.Subscribe(scriptblock)`. `New-UI4MEComputed -DependsOn @($state) -Expression { ... }` tracks listed dependencies explicitly. Controls accept `-Bind $state` where supported. All UI callbacks run in the application runspace; background runspace jobs cannot call UI4ME.Core directly.

```powershell
$count = New-UI4MEState -Value 0
New-UI4METext -Bind $count
New-UI4MEButton -Text 'Increment' -OnClick {
    $count.Set([int]$count.Value + 1)
}
```

**Parity policy:** equivalent observable behavior rather than identical APIs. Dispose subscriptions, timers, owned content and task completions with their component/window. Test rapid updates, stale results, nested effects and cleanup.
