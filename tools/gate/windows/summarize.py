"""Summarize a Windows gate results folder (pass/total per journey and probe)."""
import json, os, glob
import sys
r = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Public\ui4me-gui\gate\results"
print(open(os.path.join(r, "context.txt")).read().strip()); print(open(os.path.join(r, "python-identity.txt"), encoding="utf-8", errors="replace").read().strip())
for name in ["chat-python", "chat-powershell", "files-python", "files-powershell", "input-python", "input-powershell", "file-input"]:
    p = os.path.join(r, name, "journey.json")
    try:
        d = json.load(open(p, encoding="utf-8-sig")); c = d["cases"]
        print(name, d["status"], sum(1 for x in c if x["status"] == "passed"), "/", len(c), [(x["id"], str(x.get("details"))[:200]) for x in c if x["status"] != "passed"])
    except Exception as e:
        print(name, "MISSING", e)
for name, rel in [("window", r"window-probe\probe.json"), ("uia", r"uia\uia.json"), ("uia-native", r"uia\uia_native.json"), ("env", r"environment\env.json"), ("services", r"services\services.json"), ("animation", r"animation\animation.json"), ("print", r"print\print.json"), ("capabilities", r"capabilities\caps.json"), ("data-app", r"data-app\data.json"), ("lua", r"lua\lua.json")]:
    try:
        d = json.load(open(os.path.join(r, rel), encoding="utf-8-sig")); c = d["cases"]
        if isinstance(c, dict):
            print(name, d["status"], sum(1 for v in c.values() if v), "/", len(c), [k for k, v in c.items() if not v], d.get("error"))
        else:
            print(name, d["status"], sum(1 for x in c if x["status"] == "passed"), "/", len(c), [(x["id"], str(x.get("details"))[:300]) for x in c if x["status"] != "passed"])
    except Exception as e:
        print(name, "MISSING", e)
