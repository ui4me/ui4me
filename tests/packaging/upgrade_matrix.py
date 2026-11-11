"""Install / upgrade / rollback matrix (Core 1.0 F1106). Runs on Linux and Windows against a
local release candidate:

    python tests/packaging/upgrade_matrix.py --wheel dist/<platform>/ui4me-1.0.0-*.whl \
        --stage dist/<platform>/Ui4me-1.0.0-<platform>-stage.zip --out build/upgrade.json

Python: a fresh venv installs the published 0.4.0 from PyPI and runs the v0.4.0 installed
contract test (git tag v0.4.0), upgrades to the candidate wheel and runs the v0.4.0 test again
(an old client on the new Core) and the current installed contract test, rolls back to the
published 0.9.0, then upgrades to the candidate once more. PowerShell: the published 0.4.0 and
0.9.0 modules are saved from the PowerShell Gallery beside the candidate module; importing by
version selects each, the v0.4.0 contract test runs against the candidate. Every installed
artifact is checked against its SHA-256 in the candidate manifest. Network access to PyPI and the
PowerShell Gallery is required. Automated; not a person.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = sys.platform == "win32"


def run(cmd, **kw):
    p = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    return p.returncode, (p.stdout + p.stderr)[-4000:]


def tag_file(path: str, dest: Path) -> Path:
    data = subprocess.run(["git", "-C", str(ROOT), "show", f"v0.4.0:{path}"], capture_output=True, check=True).stdout
    dest.write_bytes(data)
    return dest


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wheel", type=Path, required=True)
    ap.add_argument("--stage", type=Path, required=True)
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pwsh", default="pwsh")
    args = ap.parse_args()
    cases: list[dict] = []

    def case(name, ok, detail):
        cases.append({"id": name, "status": "passed" if ok else "failed", "details": detail})
        print("passed" if ok else "failed", name, str(detail)[:300], flush=True)

    work = Path(tempfile.mkdtemp(prefix="ui4me upgrade "))
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "UI4ME_NATIVE_LIB")}
    env["UI4ME_INSTALLED"] = "1"
    try:
        manifest = args.manifest or args.wheel.parent / "manifest.json"
        if manifest.exists():
            m = json.loads(manifest.read_text())
            want = {a["path"]: a["sha256"] for a in m.get("artifacts", [])}
            got = {p.name: sha256(p) for p in (args.wheel, args.stage)}
            ok = all(want.get(k) == v for k, v in got.items() if k in want) and any(k in want for k in got)
            case("U00_artifact_checksums", ok, {"checked": sorted(k for k in got if k in want)})
        venv = work / "venv"
        run([sys.executable, "-m", "venv", venv])
        py = venv / ("Scripts/python.exe" if WINDOWS else "bin/python")
        v04 = tag_file("bindings/python/tests/installed.py", work / "installed_v04.py")
        cur = work / "installed.py"
        shutil.copy2(ROOT / "bindings/python/tests/installed.py", cur)

        def version():
            return run([py, "-I", "-c", "import ui4me; print(ui4me.__version__)"], env=env)[1].strip()

        def contract(script: Path, tag: str):
            res = work / f"{tag}.json"
            code, out = run([py, "-I", script, "--result", res], env=env, cwd=work)
            data = json.loads(res.read_text()) if res.exists() else {}
            failed = [c["id"] for c in data.get("cases", []) if c.get("status") != "passed"]
            return code == 0 and not failed and bool(data.get("cases")), {"failed": failed, "cases": len(data.get("cases", [])), "tail": out[-300:] if code else ""}

        code, out = run([py, "-m", "pip", "install", "-q", "ui4me==0.4.0"], env=env)
        case("U01_install_published_0.4.0", code == 0 and version() == "0.4.0", {"version": version(), "pip": out[-200:] if code else ""})
        ok, d = contract(v04, "v04-on-0.4.0")
        case("U02_v0.4_client_on_0.4.0", ok, d)
        code, out = run([py, "-m", "pip", "install", "-q", "--upgrade", args.wheel], env=env)
        new = version()
        case("U03_upgrade_to_candidate", code == 0 and new not in ("0.4.0", ""), {"version": new, "pip": out[-200:] if code else ""})
        ok, d = contract(v04, "v04-on-candidate")
        case("U04_v0.4_client_on_candidate", ok, d)
        ok, d = contract(cur, "current-on-candidate")
        case("U05_current_contract_on_candidate", ok, d)
        code, out = run([py, "-m", "pip", "install", "-q", "ui4me==0.9.0"], env=env)
        case("U06_rollback_to_0.9.0", code == 0 and version() == "0.9.0", {"version": version()})
        code, out = run([py, "-m", "pip", "install", "-q", args.wheel], env=env)
        case("U07_reupgrade_to_candidate", code == 0 and version() == new, {"version": version()})

        # PowerShell: published modules side by side with the candidate.
        mods = work / "modules"
        mods.mkdir()
        save = "; ".join(f"Save-PSResource -Name Ui4me -Version {v} -Repository PSGallery -TrustRepository -Path '{mods}'" for v in ("0.4.0", "0.9.0"))
        code, out = run([args.pwsh, "-NoProfile", "-Command", f"$ErrorActionPreference='Stop'; {save}"], env=env)
        stage = work / "stage"
        with zipfile.ZipFile(args.stage) as z:
            z.extractall(stage)
        psd1 = next(stage.rglob("Ui4me.psd1"))
        cand_version = run([args.pwsh, "-NoProfile", "-Command", f"(Import-PowerShellDataFile '{psd1}').ModuleVersion"])[1].strip()
        shutil.copytree(psd1.parent, mods / "Ui4me" / cand_version, dirs_exist_ok=True)
        listed = run([args.pwsh, "-NoProfile", "-Command", f"$env:PSModulePath='{mods}'; (Get-Module -ListAvailable Ui4me | Sort-Object Version | ForEach-Object {{ $_.Version.ToString() }}) -join ','"], env=env)[1].strip()
        case("U10_powershell_side_by_side", code == 0 and listed == f"0.4.0,0.9.0,{cand_version}", {"available": listed, "save": out[-200:] if code else ""})
        newest = run([args.pwsh, "-NoProfile", "-Command", f"$env:PSModulePath='{mods}'; Import-Module Ui4me; (Get-Module Ui4me).Version.ToString()"], env=env)[1].strip()
        old = run([args.pwsh, "-NoProfile", "-Command", f"$env:PSModulePath='{mods}'; Import-Module Ui4me -RequiredVersion 0.9.0; (Get-Module Ui4me).Version.ToString()"], env=env)[1].strip()
        case("U11_powershell_upgrade_and_rollback_by_version", newest == cand_version and old == "0.9.0", {"default": newest, "pinned": old})
        ps04 = tag_file("bindings/powershell/tests/installed.ps1", work / "installed_v04.ps1")
        res = work / "ps-v04-on-candidate.json"
        code, out = run([args.pwsh, "-NoProfile", "-File", ps04, "-ModulePath", mods / "Ui4me" / cand_version / "Ui4me.psd1", "-ResultPath", res], env=env, cwd=work)
        data = json.loads(res.read_text(encoding="utf-8-sig")) if res.exists() else {}
        failed = [c["id"] for c in data.get("cases", []) if c.get("status") != "passed"]
        case("U12_powershell_v0.4_client_on_candidate", code == 0 and not failed and bool(data.get("cases")), {"failed": failed, "cases": len(data.get("cases", [])), "tail": out[-300:] if code else ""})
    finally:
        shutil.rmtree(work, ignore_errors=True)
    result = {"status": "passed" if cases and all(c["status"] == "passed" for c in cases) else "failed", "cases": cases}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
