# Coding-agent skills

UI4ME ships two dedicated, versioned skills: `ui4me-ui-python` and `ui4me-ui-powershell`. These complement the lower-level `ui4me-python` and `ui4me-powershell` skills distributed by Core.

## Python skill

```bash
ui4me-ui-skill install --agents all --scope user
ui4me-ui-skill status --agents all
ui4me-ui-skill install --agents claude,codex --scope project --project .
ui4me-ui-skill uninstall --agents claude --scope user
```

## PowerShell skill

```powershell
Install-UI4MEUiSkill -Agents all -Scope user
Install-UI4MEUiSkill -Agents claude,codex -Scope project -ProjectPath .
Install-UI4MEUiSkill -Action status -Agents all
```

Supported agents are Claude Code, Codex, OpenCode, GitHub Copilot, Cursor and Gemini CLI. Installers do not fetch from the network, require elevation, or modify unrelated skills. Existing unmanaged or manually edited skill folders are not replaced unless `--force` / `-Force` is specified.

Sources: [`skills/ui4me-ui-python`](https://github.com/ui4me/ui4me/tree/main/skills/ui4me-ui-python) and [`skills/ui4me-ui-powershell`](https://github.com/ui4me/ui4me/tree/main/skills/ui4me-ui-powershell). Agent skills are documentation, not a security sandbox: review generated scripts before running with privileged filesystem/network access.
