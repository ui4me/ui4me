# Install Ui4me first. The same HTML/CSS/assets also ship in the installed packages.
Import-Module Ui4me -ErrorAction Stop
$source = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../foundation'))
Invoke-Ui4meApp -ArgumentList @($source) {
    param($app, $source)
    $window = $app.OpenFile((Join-Path $source 'index.html'), 'UI4ME · PowerShell', 1000, 820)
    $state = @{rows=4; highlight=$false}
    $null = $window.On('click', {
        $enabled = if ($window.GetChecked('enabled')) { 'on' } else { 'off' }
        $window.SetText('status', ('Hello, ' + $window.GetValue('name') + '! Notifications: ' + $enabled + '.'))
    }, 'greet')
    $null = $window.On('click', {
        $state.rows++
        $html = (1..$state.rows | ForEach-Object { '<p class="row">' + $_ + ' · Result row updated by PowerShell</p>' }) -join ''
        $window.ReplaceChildrenHtml('rows', $html)
        $window.SetText('status', ($state.rows.ToString() + ' rows. Your other inputs are unchanged.'))
    }, 'add')
    $null = $window.On('click', {
        $state.highlight = -not $state.highlight
        if ($state.highlight) { $window.AddClass('form', 'highlight') }
        else { $window.RemoveClass('form', 'highlight') }
    }, 'accent')
    $null = $window.On('click', {
        $window.SetText('status', 'Calculating in a background runspace…')
        $null = $app.Work({
            $total = 0L
            foreach ($number in 0..99999) { $total += $number }
            $total
        }, @(), {
            param($values, $error)
            if ($error) { throw $error }
            if (-not $window.IsClosed) { $window.SetText('status', ('Background result: ' + $values[0] + '. Callback is on the UI owner.')) }
        })
    }, 'work')
    $null = $window.On('click', {
        $null = $app.OpenFile((Join-Path $source 'settings.html'), 'UI4ME · Settings', 520, 380)
    }, 'settings')
    $null = $window.On('click', { $app.Stop() }, 'quit')
}
