#!/bin/bash
# Linux native release gate (Core 1.0, F1107): every journey and probe against the INSTALLED
# candidate packages (dist/linux-x64), each in a private nested KWin session started by the
# harness (never the desktop session). Automated input, not a person.
#
#   tools/gate/linux_gate.sh OUT_DIR
#
# OUT_DIR must not exist, be empty, or be a directory this script created earlier (it holds the
# .ui4me-gate marker); only then is it replaced. Writes OUT_DIR/results/<step>.txt,
# OUT_DIR/results/summary.txt (one "<step> exit N" line each, then "done") and the verdict of
# tools/gate/verdict.py (OUT_DIR/results/verdict.json). Exit status 0 only when every mandatory
# step ran and passed; a missing or skipped step fails the gate.
# Needs: the candidate in dist/linux-x64 (dev.py package), kwin_wayland, wayland-scanner and gcc
# (fake input), pwsh, PyGObject for the a11y/services probes, LuaJIT in build/luajit
# (bindings/lua/tools/build_luajit.sh), network access for the upgrade matrix (PyPI, PowerShell
# Gallery).
set -u
R=$(cd "$(dirname "$0")/../.." && pwd)
G=$(realpath -m "${1:?usage: linux_gate.sh OUT_DIR}")
V=$(tr -d '\r\n' < "$R/VERSION")
MARK=.ui4me-gate
refuse() { echo "refusing OUT_DIR $G: $1" >&2; exit 2; }
case "$G" in "$R"/build/?*) ;; /|"$HOME"|"$R"|"$R"/*) refuse "use a dedicated directory (outside the checkout or under build/)" ;; esac
case "$R/" in "$G"/*) refuse "it contains the checkout" ;; esac
[ -L "$G" ] && refuse "symbolic link"
if [ -e "$G" ]; then
  if [ -d "$G" ] && [ -f "$G/$MARK" ] && [ ! -L "$G/$MARK" ]; then rm -rf --one-file-system -- "$G"
  elif [ -d "$G" ] && [ -z "$(ls -A "$G")" ]; then rmdir -- "$G"
  else refuse "exists and is not a gate directory (no $MARK marker)"; fi
fi
OUT=$G/results; mkdir -p "$OUT" && echo "ui4me gate output; tools/gate/linux_gate.sh may delete this directory" > "$G/$MARK" || exit 2
WHEEL=$(ls "$R"/dist/linux-x64/ui4me-"$V"-*.whl); STAGE=$(ls "$R"/dist/linux-x64/Ui4me-"$V"-linux-x64-stage.zip)
[ -f "$WHEEL" ] && [ -f "$STAGE" ] || { echo "candidate $V not found in dist/linux-x64 (run dev.py package)" >&2; exit 2; }
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
plain orca "$PY" "$N/orca_journey.py" --out "$OUT/orca/orca.json"
plain capabilities "$PY" "$N/capabilities_probe.py" --kde-services --out "$OUT/capabilities/caps.json"
plain data-app "$PY" "$N/data_journey.py" --out "$OUT/data-app/data.json"
# LuaJIT (bindings/lua/tools/build_luajit.sh) is mandatory: without it the step fails, it is not skipped.
LIB=$(find "$G/venv" -name 'libui4me_core*.so' | head -1)
if [ -x "$R/build/luajit/src/luajit" ] && [ -n "$LIB" ]; then
  UI4ME_NATIVE_LIB=$LIB LUA_PATH="$R/bindings/lua/?.lua;;" plain lua "$R/build/luajit/src/luajit" "$N/lua_probe.lua" --out "$OUT/lua/lua.json"
else
  echo "LuaJIT ($R/build/luajit/src/luajit) or the installed native library is missing" > "$OUT/lua.txt"; echo "lua exit 127" >> "$OUT/summary.txt"
fi
run upgrade python3 "$R/tests/packaging/upgrade_matrix.py" --wheel "$WHEEL" --stage "$STAGE" --out "$OUT/upgrade/upgrade.json"
echo done >> "$OUT/summary.txt"
python3 "$R/tools/gate/verdict.py" "$OUT" --platform linux
