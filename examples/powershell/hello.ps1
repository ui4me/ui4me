# Install the Ui4me module before running this script.
Import-Module Ui4me -ErrorAction Stop

Invoke-Ui4meApp {
    param($app)
    $html = @'
<body style="background-color: #F3F6FA">
<h1 style="color: blue">ui4me foundation</h1>
<label>Your name:</label>
<input id="name" type="text" value="World">
<button id="greet">Greet</button>
<button id="second">Open second window</button>
<button id="resize">Resize this window</button>
<button id="work">Run background work</button>
<button id="quit">Quit now</button>
<p id="status">Try a button. The first close request is intercepted.</p>
</body>
'@
    $window = New-Ui4meWindow $html -Title 'ui4me - PowerShell' -Width 760 -Height 700
    $state = @{ confirmClose = $false; closed = $false }

    $null = Register-Ui4meEvent $window click {
        $window.SetText('status', ('Hello, ' + $window.GetValue('name') + '!'))
    } -Element greet
    $null = Register-Ui4meEvent $window click {
        $null = New-Ui4meWindow '<h1>Second window</h1><p>Close this window independently.</p>' -Title 'ui4me - second window' -Width 500 -Height 300
    } -Element second
    $null = Register-Ui4meEvent $window click { $window.Resize(860, 760) } -Element resize
    $null = Register-Ui4meEvent $window click {
        $window.SetText('status', 'Working in a background runspace...')
        $null = $app.Work({
            $result = 0L
            foreach ($number in 0..99999) { $result += $number }
            $result
        }, @(), {
            param($values, $error)
            if ($null -ne $error) { throw $error }
            if (-not $state.closed) { $window.SetText('status', ('Background result: ' + $values[0])) }
        })
    } -Element work
    $null = Register-Ui4meEvent $window click { $app.Stop() } -Element quit
    $null = Register-Ui4meEvent $window close_requested {
        if (-not $state.confirmClose) {
            $state.confirmClose = $true
            $window.SetText('status', 'Close again to exit, or use Quit now.')
            return $false
        }
    }
    $null = Register-Ui4meEvent $window closed { $state.closed = $true }
}
