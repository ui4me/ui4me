#!/usr/bin/env bash
# Build a pinned LuaJIT 2.1 (MIT licence, https://luajit.org/) into <repo>/build/luajit/.
# No system-wide install, no sudo. Result: build/luajit/src/luajit
set -euo pipefail
COMMIT=63c8f1a9b479ba5518cf6a170ff7729178bc3cfd   # LuaJIT/LuaJIT branch v2.1
SHA256=8cad76f444b76001b7123dc626c5d0bfc24f1f790333737443345f7e6b41bb5f
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
DEST="$ROOT/build/luajit"
if [ -x "$DEST/src/luajit" ]; then echo "already built: $DEST/src/luajit"; exit 0; fi
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
curl -fsSL -o "$WORK/luajit.tar.gz" "https://github.com/LuaJIT/LuaJIT/archive/$COMMIT.tar.gz"
echo "$SHA256  $WORK/luajit.tar.gz" | sha256sum -c -
mkdir -p "$DEST"
tar -xzf "$WORK/luajit.tar.gz" -C "$DEST" --strip-components=1
nice make -C "$DEST" -j"$(nproc)" amalg
echo "built: $DEST/src/luajit"
"$DEST/src/luajit" -e 'print(jit.version)'
