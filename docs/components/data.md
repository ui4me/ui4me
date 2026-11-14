# Tables, data views, logs and live content

**Python:** `ui.table(rows, columns=..., key=..., search=True, sort=True, ...)`, `ui.query_table(loader=..., key=..., columns=...)`, `ui.each` keyed lists, `ui.tree`, `ui.log`, `ui.chat`, `ui.sparkline`, `ui.progress_ring`. Data loaders run asynchronously with cancellation/stale-result suppression; UI callbacks belong to the owner thread. Bind state to controls rather than rebuilding whole documents.

```python
records = ui.state([{'id': 'a', 'name': 'Ada'}, {'id': 'b', 'name': 'Grace'}])
ui.table(records, key='id', columns=['name'], search=True, sort=True)
```

**PowerShell:** `New-UI4METable` supports reactive rows and row click; `New-UI4MEList`, `New-UI4MEEach`, `New-UI4MEWhen`, `New-UI4MELog` and `Add-UI4MELogLine` support tables, dynamic items and bounded logs.

```powershell
$rows = New-UI4MEState -Value @(
    [pscustomobject]@{ Name = 'Ada' },
    [pscustomobject]@{ Name = 'Grace' }
)
New-UI4METable -Columns @('Name') -Rows $rows
```

PowerShell does not yet have a native equivalent of Python's full `query_table` data-source engine. Never claim parity for table sorting, paging, selection, chat or tree until dedicated PowerShell tests exercise them. For very large datasets, measure load/typing latency before implementing virtualization.
