#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${1:-}" == "--install-system" ]]; then
  if ! command -v apt-get >/dev/null; then
    echo "Install prerequisites using your distribution's package manager; this convenience flag supports Debian/Ubuntu." >&2
    exit 1
  fi
  sudo apt-get update
  sudo apt-get install -y build-essential pkg-config python3 python3-venv python3-dev libx11-dev libxkbcommon-dev libwayland-dev libxrandr-dev libxi-dev libxcursor-dev libgl1-mesa-dev
fi
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
cat <<'TEXT'
Python development tools are ready in .venv.
Install Rust 1.99.1 via rustup, .NET SDK 10 and PowerShell 7.6 from their official installers.
The supported native build host is Linux x86-64 with Wayland or X11 development libraries.
Next: source .venv/bin/activate
Then: python dev.py doctor
Use the committed dependency locks. Regenerate them with python dev.py lock only when updating dependencies.
TEXT
