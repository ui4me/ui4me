#!/usr/bin/env bash
# Carried AT-SPI state patch (ported from the 0.x engine, UP-08).
#
# Checks that patches/accesskit_atspi_common/accesskit_atspi_common/ is exactly the crates.io package accesskit_atspi_common 0.21.1
# (without .cargo_vcs_info.json) with P-013-1.patch applied (`patch -p1`), so the patch file, the vendored tree that
# `[patch.crates-io]` in Cargo.toml builds, and the upstream base cannot drift.
# Usage: patches/accesskit_atspi_common/verify.sh   exit 0 = identical, 1 = drift, 2 = pristine source not found (cargo fetch)
set -u
VER=0.21.1
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
src=""
for d in "${CARGO_HOME:-$HOME/.cargo}"/registry/src/*/accesskit_atspi_common-"$VER"; do
  [ -f "$d/Cargo.toml" ] && src="$d" && break
done
[ -z "$src" ] && { echo "verify.sh: no registry source of accesskit_atspi_common $VER (run: cargo fetch)" >&2; exit 2; }
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
cp -r "$src" "$work/accesskit_atspi_common"; rm -f "$work/accesskit_atspi_common/.cargo_vcs_info.json" "$work/accesskit_atspi_common/.cargo-ok"
(cd "$work/accesskit_atspi_common" && patch -s -p1 -i "$here/P-013-1.patch") || { echo "verify.sh: P-013-1.patch does not apply" >&2; exit 1; }
if diff -r "$work/accesskit_atspi_common" "$here/accesskit_atspi_common" >"$work/diff.txt"; then
  echo "verify.sh: OK - patches/accesskit_atspi_common/accesskit_atspi_common == accesskit_atspi_common $VER + P-013-1"
else
  head -40 "$work/diff.txt" >&2; echo "verify.sh: DRIFT between the vendored tree and base+patch" >&2; exit 1
fi
