# Windows native gate

The target is the test VM `omegaui` (Windows Server 2022, Proxmox VM 101 on `pvey`), with the
test user `ui4me_test` logged on interactively. It is driven from Linux over SSH as
`administrator`. Automated input, not a person.

## 1. Interactive session

GUI tests need `ui4me_test`'s session on the console. If the VM restarted:

1. Start it: `ssh root@pvey 'qm start 101'`.
2. Log in once with RDP (for example `xfreerdp3` on a private `Xvfb`, password from stdin).
3. Attach the session to the console with `tscon <id> /dest:console`, run from a SYSTEM task.
4. Check with `ssh administrator@omegaui 'query user'`: the session must be `console` and
   `Active`.

## 2. Candidate

In the VM checkout (`C:\Users\Administrator\ui4me-dev`, fed from a `git bundle` of `main`), from
a VS x64 developer prompt with `build\devenv\Scripts` on `PATH`:

```bat
python dev.py build --binding all --profile release
python dev.py package --binding all --profile release
python dev.py test --binding all --suite installed --manifest dist\win-x64\manifest.json
```

The installed `run.json` shows one `failed` step per binding, the "missing native" negative
step. It has `expected_failure: true` and is not a defect.

## 3. Gate

Copy `tools\gate\windows\*` to `C:\Users\Public\ui4me-gui\tools`, then:

```powershell
pwsh -File C:\Users\Public\ui4me-gui\tools\prep_gate.ps1            # as administrator
$t = 'C:\Users\Public\ui4me-gui\tools\task.ps1'
pwsh -File $t -Script C:\Users\Public\ui4me-gui\tools\setlang.ps1 -Marker C:\Users\Public\ui4me-gui\gate\lang-done.txt -Exe C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe
pwsh -File $t -Script C:\Users\Public\ui4me-gui\tools\run_gate.ps1 -Marker C:\Users\Public\ui4me-gui\gate\results\all-done.txt -Seconds 3300
pwsh -File $t -Script C:\Users\Public\ui4me-gui\tools\unlang.ps1 -Marker C:\Users\Public\ui4me-gui\gate\unlang-done.txt -Exe C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe
python C:\Users\Public\ui4me-gui\tools\summarize.py
```

`setlang.ps1` adds the Japanese and Korean IMEs for the input journey, and `unlang.ps1`
restores en-US. **Always restore them.** To rerun only some steps, write a comma list such as
`fileinput,print` to `gate\only.txt`, and delete the file afterwards.

The upgrade matrix (`tests\packaging\upgrade_matrix.py`) runs as the administrator, outside
the GUI session:

```bat
python packaging\upgrade_matrix.py --wheel <whl> --stage <stage.zip> --out results\upgrade.json
```
