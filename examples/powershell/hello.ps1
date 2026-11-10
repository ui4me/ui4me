Import-Module Ui4me -ErrorAction Stop

Invoke-Ui4meApp {
    param($app)
    $window = New-Ui4meWindow '<h1>Hello</h1><button id="hello">Click me</button><p id="status">Ready</p>'
    $null = Register-Ui4meEvent $window click {
        param($event)
        Set-Ui4meText $window status 'Hello from PowerShell'
    } -Element hello
}
