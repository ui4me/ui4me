param([string] $Root = 'C:\Users\Public\ui4me-gui\gate')
$root = $Root
try { Set-WinUserLanguageList (New-WinUserLanguageList 'en-US') -Force; (Get-WinUserLanguageList | ForEach-Object { $_.LanguageTag + ' ' + ($_.InputMethodTips -join ',') }) -join "`n" | Set-Content "$root\lang-restored.txt" -Encoding UTF8 } catch { $_ | Out-String | Set-Content "$root\lang-restored.txt" }
'done' | Set-Content "$root\unlang-done.txt"
