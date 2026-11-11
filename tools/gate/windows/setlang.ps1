# Windows PowerShell 5.1, in the ui4me_test session: add Japanese and Korean input methods.
param([string] $Root = 'C:\Users\Public\ui4me-gui\gate')
$root = $Root
try {
  $before = Get-WinUserLanguageList
  ($before | ForEach-Object { $_.LanguageTag + ' ' + ($_.InputMethodTips -join ',') }) -join "`n" | Set-Content "$root\lang-before.txt" -Encoding UTF8
  $l = Get-WinUserLanguageList
  foreach ($tag in 'ja-JP', 'ko-KR') { if (-not ($l | Where-Object LanguageTag -eq $tag)) { $l.Add($tag) } }
  Set-WinUserLanguageList $l -Force
  (Get-WinUserLanguageList | ForEach-Object { $_.LanguageTag + ' ' + ($_.InputMethodTips -join ',') }) -join "`n" | Set-Content "$root\lang-after.txt" -Encoding UTF8
} catch { $_ | Out-String | Set-Content "$root\lang-error.txt" }
'done' | Set-Content "$root\lang-done.txt"
