#!/bin/bash
# Linux native release gate (Core 1.0, F1107): every journey and probe against the INSTALLED
# candidate packages (dist/linux-x64), each in a private nested KWin session started by the
# harness (never the desktop session). Automated input, not a person.
#
#   tools/gate/linux_gate.sh OUT_DIR
#
# Writes OUT_DIR/results/<step>.txt and OUT_DIR/results/summary.txt (one "<step> exit N" line
# each, then "done"). Needs: the candidate in dist/linux-x64 (dev.py package), kwin_wayland,
# wayland-scanner and gcc (fake input), pwsh, PyGObject for the a11y/services probes, network
# access for the upgrade matrix (PyPI, PowerShell Gallery).
set -u
R=$(cd "$(dirname "$0")/../.." && pwd)
G=${1:?usage: linux_gate.sh OUT_DIR}
V=$(tr -d '\r\n' < "$R/VERSION")
OUT=$G/results; rm -rf "$G"; mkdir -p "$OUT"
WHEEL=$(ls "$R"/dist/linux-x64/ui4me-"$V"-*.whl); STAGE=$(ls "$R"/dist/linux-x64/Ui4me-"$V"-linux-x64-stage.zip)
python3 -m venv "$G/venv" && "$G/venv/bin/pip" install -q "$WHEEL" || exit 2
python3 -m venv --system-site-packages "$G/venv-sys" && "$G/venv-sys/bin/pip" install -q "$WHEEL" || exit 2
mkdir -p "$G/mod" && (cd "$G/mod" && unzip -q "$STAGE") || exit 3
PY=$G/venv/bin/python
MODDIR=$(dirname "$(find "$G/mod" -name Ui4me.psd1 | head -1)"); export PSModulePath=$(dirname "$MODDIR")
unset PYTHONPATH UI4ME_NATIVE_LIB; export UI4ME_INSTALLED=1
sha256sum "$WHEEL" "$STAGE" > "$OUT/artifacts.sha256"
"$PY" -c "import ui4me; print(ui4me.__file__, ui4me.__version__)" > "$OUT/python-identity.txt"
K=$R/tests/native/kwin; E=$R/examples; N=$R/tests/native
run() { name=$1; shift; timeout 1800 "$@" > "$OUT/$name.txt" 2>&1; echo "$name exit $?" >> "$OUT/summary.txt"; }
plain() { name=$1; shift; mkdir -p "$OUT/$name"; run "$name" python3 "$K/chat_journey.py" --plain --out "$OUT/$name" -- "$@"; }
run chat-python python3 "$K/chat_journey.py" --out "$OUT/chat-python" -- "$PY" "$E/python/chat_log.py" --state {state}
run chat-powershell python3 "$K/chat_journey.py" --out "$OUT/chat-powershell" -- pwsh -NoProfile -File "$E/powershell/chat_log.ps1" -StatePath {state}
run files-python python3 "$K/files_journey.py" --out "$OUT/files-python" -- "$PY" "$E/python/file_utility.py" --start {start} --state {state}
run files-powershell python3 "$K/files_journey.py" --out "$OUT/files-powershell" -- pwsh -NoProfile -File "$E/powershell/file_utility.ps1" -Start {start} -StatePath {state}
run dialogs python3 "$K/dialog_journey.py" --out "$OUT/dialogs" -- "$PY" "$N/file_dialog_app.py" --state {state} --root {root}
plain window-probe "$PY" "$N/window_probe.py" --out "$OUT/window-probe/probe.json"
plain a11y "$G/venv-sys/bin/python" "$N/a11y_probe.py" --out "$OUT/a11y/a11y.json"
run input-python python3 "$K/input_journey.py" --out "$OUT/input-python" -- "$PY" "$N/input_probe.py" --state {state} --commands {commands}
run input-powershell python3 "$K/input_journey.py" --out "$OUT/input-powershell" -- pwsh -NoProfile -File "$N/input_probe.ps1" -StatePath {state} -CommandsPath {commands}
plain environment "$PY" "$N/environment_probe.py" --out "$OUT/environment/env.json"
run file-input python3 "$K/file_input_journey.py" --out "$OUT/file-input" -- "$PY" "$N/file_input_app.py" --state {state} --root {root}
plain services "$G/venv-sys/bin/python" "$N/services_probe.py" --out "$OUT/services/services.json"
plain animation "$PY" "$N/animation_probe.py" --out "$OUT/animation/animation.json"
plain print "$PY" "$N/print_probe.py" --out "$OUT/print/print.json"
plain capabilities "$PY" "$N/capabilities_probe.py" --kde-services --out "$OUT/capabilities/caps.json"
if [ -f "$N/data_journey.py" ]; then plain data-app "$PY" "$N/data_journey.py" --out "$OUT/data-app/data.json"; fi
if [ -f "$N/lua_probe.lua" ] && [ -x "$R/build/luajit/src/luajit" ]; then
  LIB=$(find "$G/venv" -name 'libui4me_core*.so' | head -1)
  UI4ME_NATIVE_LIB=$LIB LUA_PATH="$R/bindings/lua/?.lua;;" plain lua "$R/build/luajit/src/luajit" "$N/lua_probe.lua" --out "$OUT/lua/lua.json"
fi
run upgrade python3 "$R/tests/packaging/upgrade_matrix.py" --wheel "$WHEEL" --stage "$STAGE" --out "$OUT/upgrade/upgrade.json"
echo done >> "$OUT/summary.txt"
