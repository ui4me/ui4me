# CSS themes, density and customization

UI4ME separates **functional CSS** (geometry, display, focus mechanics and component behavior) from **visual CSS** (tokens, colors, borders, spacing and typography). Python and PowerShell distribute the same default `functional.css` and `theme.css` assets; compare their hashes in release tests.

## Python

```python
with ui.app('Styled', theme='dark') as app:
    app.theme.tokens(primary='#6d28d9')
    ui.density('compact')
    ui.heading('Dashboard')
    ui.button('Run', variant='primary')
app.run()
```

You may load a complete custom visual stylesheet with `app.theme.load(css, mode='replace')` or add user CSS with `ui.css(css)`. Do not remove the mandatory functional CSS. Use named `u4-*` selectors and `--u4-*` semantic CSS tokens, not opaque generated DOM IDs, for durable themes.

## PowerShell

```powershell
Invoke-UI4MEApp -Title 'Styled' -Theme dark -Content {
    New-UI4MEHeading -Text 'Dashboard'
    New-UI4MEButton -Text 'Run' -Variant primary
}
```

At runtime use `Set-UI4MEUiTheme -Css $css`, `-ColorScheme` or `-Reset`. Both languages expose local styles without an HTTP server. Test light/dark, high contrast, font scaling and narrow/wide window sizes. The Core desktop CSS profile is not equivalent to a complete web browser's CSS implementation.
