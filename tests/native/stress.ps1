[CmdletBinding()]
param([Parameter(Mandatory)][string]$ModulePath)
$ErrorActionPreference='Stop'
Import-Module "$ModulePath/Ui4me.psd1"
$record=[hashtable]::Synchronized(@{})
Invoke-Ui4meApp -ArgumentList @($record) {
  param($app,$record)
  $null=New-Ui4meWindow '<p>Queue bound</p>'
  $items=[System.Collections.Generic.List[object]]::new()
  foreach($i in 1..512) { $items.Add($app.Post({1})) }
  $overflow=$app.Post({2})
  if(-not $overflow.IsCompleted) {throw 'Overflow was not rejected immediately'}
  $rejected=$false
  try { $null=$overflow.GetResult() } catch { $rejected=$true }
  if(-not $rejected) {throw 'Overflow unexpectedly succeeded'}
  $record.posts=$items
  $app.Stop()
}
if (@($record.posts | Where-Object { $_.IsCancelled }).Count -ne 512) { throw 'Not all queued work was cancelled' }
$record.Remove('posts')
$record.queue_full_stop=@{accepted=512;cancelled=512;overflow='rejected'}

$state=[hashtable]::Synchronized(@{})
$entered=[System.Threading.ManualResetEventSlim]::new($false)
$release=[System.Threading.ManualResetEventSlim]::new($false)
Invoke-Ui4meApp -ArgumentList @($state,$entered,$release) {
 param($app,$state,$entered,$release)
 $null=New-Ui4meWindow '<p>Running cancellation</p>'
 $null=$app.Timer(10000,{throw 'Running cancellation probe timed out'},$false)
 $running=$app.Post({
   $entered.Set()
   if(-not $release.Wait(5000)) { throw 'worker failed to release running callback' }
   return 7
 })
 $queued=$app.Post({ throw 'cancelled work ran' })
 $state.running=$running; $state.queued=$queued
 $state.worker=$app.Work({
   param($app,$running,$queued,$entered,$release,$state)
   try {
     if(-not $entered.Wait(5000)) { throw 'callback did not start' }
     $state.running_cancel=$running.Cancel()
     $state.queued_cancel=$queued.Cancel()
     $app.Stop()
   } finally { $release.Set() }
 }, @($app,$running,$queued,$entered,$release,$state), {})
}
if($state.running_cancel -ne $false -or $state.queued_cancel -ne $true -or -not $state.queued.IsCancelled -or $state.running.GetResult() -ne 7) {throw 'Cancellation outcome mismatch'}
$record.running_queued=@{running_cancel=$state.running_cancel;queued_cancel=$state.queued_cancel;running_result=$state.running.GetResult();queued_cancelled=$state.queued.IsCancelled}

# A managed worker is deliberately held until a replacement session starts.
# It then submits against the disposed old app, and the result must be terminal.
Add-Type -TypeDefinition @'
using System;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;
public static class Ui4meLateSubmitProbe {
  public static Task<object> Start(object app, ManualResetEventSlim go) {
    return Task.Run<object>(() => {
      if (!go.Wait(5000)) throw new Exception("Late submit signal timed out");
      var method = app.GetType().GetMethod("PostManaged");
      return method.Invoke(app, new object[] { new Func<object>(() => {throw new Exception("stale callback ran");}) });
    });
  }
}
'@
$late=[hashtable]::Synchronized(@{})
$go=[System.Threading.ManualResetEventSlim]::new($false)
Invoke-Ui4meApp -ArgumentList @($late,$go) {
 param($app,$late,$go)
 $late.oldWindow=New-Ui4meWindow '<p id="state">old</p>'
 $late.task=[Ui4meLateSubmitProbe]::Start($app,$go)
 $null=$app.On('started',{$app.Stop()})
}
Invoke-Ui4meApp -ArgumentList @($late,$go) {
 param($app,$late,$go)
 $window=New-Ui4meWindow '<input id="state" value="new">'
 $null=$app.Timer(10000,{throw 'Late-session probe timed out'},$false)
 $null=$app.On('started',{
   $go.Set()
   if(-not $late.task.Wait(5000)) {throw 'late worker did not complete'}
   $work=$late.task.GetAwaiter().GetResult()
   if(-not $work.IsCompleted) {throw 'late work did not settle'}
   $rejected=$false
   try {$null=$work.GetResult()} catch {$rejected=$true}
   if(-not $rejected -or $window.GetValue('state') -ne 'new') {throw 'late work was not rejected'}
   $stale=$false
   try {$late.oldWindow.SetText('state','bad')} catch {$stale=$true}
   if(-not $stale) {throw 'stale window remained usable'}
   $late.checked=$true
   $app.Stop()
 })
}
if(-not $late.checked) {throw 'late-session check did not run'}
$record.late_session=@{late_rejected=$true;new_window_value='new';stale_window_rejected=$true}

$record.sessions=[System.Collections.Generic.List[object]]::new()
foreach($i in 1..10) {
 $one=[hashtable]::Synchronized(@{})
 Invoke-Ui4meApp -ArgumentList @($one) {
  param($app,$one)
  $null=New-Ui4meWindow '<p>Idle</p>'
  $null=$app.Timer(10000,{throw 'Repeated-session probe timed out'},$false)
  $one.start=[System.Diagnostics.Stopwatch]::StartNew()
  $null=$app.Timer(200,{$app.Stop()},$false)
  $null=$app.On('stopped',{$one.stats=$app.StatsJson()|ConvertFrom-Json; $one.elapsed=$one.start.Elapsed.TotalSeconds})
 }
 if($one.stats.windows -ne 0 -or $one.stats.timers -ne 0 -or $one.stats.pending_posts -ne 0 -or $one.stats.loop_turns -ge 500 -or $one.elapsed -lt .15) {throw 'Idle or resource mismatch'}
 $record.sessions.Add(@{elapsed=$one.elapsed;turns=$one.stats.loop_turns;waits=$one.stats.wait_requests})
}
@{build_info=Get-Ui4meInfo; observations=$record} | ConvertTo-Json -Depth 12
