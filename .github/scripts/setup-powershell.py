"""CI-only pinned PowerShell bootstrap. This script is not run by importing ui4me."""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import tarfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

VERSION = "7.6.9"
# Verified against the upstream v7.6.9 hashes.sha256 publication during authoring.
ASSETS = {
    "Linux": ("powershell-7.6.9-linux-x64.tar.gz", "1da6d6d6035d651f20e70ddee7c4c15ac6ab8b9fb40ee92240d91263f28a884b"),
    "Windows": ("PowerShell-7.6.9-win-x64.zip", "ce7484804c0f0ad4dda10c958e71acdaf7eebfb22505c1b480f89e0e9f1da94d"),
}


def main() -> None:
    system = platform.system()
    if system not in ASSETS or platform.machine().lower() not in {"x86_64", "amd64"}:
        raise SystemExit("This bootstrap supports Linux/Windows x64 only")
    name, expected = ASSETS[system]
    root = Path(__file__).resolve().parents[2]
    destination = root / "build/tools" / ("powershell-" + VERSION)
    archive = root / "build/tools" / name
    archive.parent.mkdir(parents=True, exist_ok=True)
    url = "https://github.com/PowerShell/PowerShell/releases/download/v" + VERSION + "/" + name
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        temporary = archive.with_suffix(archive.suffix + ".download")
        with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as stream:
            shutil.copyfileobj(response, stream)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected:
            temporary.unlink(missing_ok=True)
            raise SystemExit("PowerShell upstream archive checksum mismatch")
        temporary.replace(archive)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir()
    if system == "Windows":
        with zipfile.ZipFile(archive) as bundle:
            for entry in bundle.infolist():
                part = PurePosixPath(entry.filename.replace("\\", "/"))
                if part.is_absolute() or ".." in part.parts or ":" in entry.filename or ((entry.external_attr >> 16) & 0o170000) == 0o120000:
                    raise SystemExit("Unsafe PowerShell archive entry")
            bundle.extractall(destination)
    else:
        with tarfile.open(archive) as bundle:
            bundle.extractall(destination, filter="data")
        (destination / "pwsh").chmod(0o755)
    if "GITHUB_PATH" not in os.environ:
        print("Add to PATH:", destination)
    else:
        with open(os.environ["GITHUB_PATH"], "a", encoding="utf-8") as stream:
            stream.write(str(destination) + "\n")
    print("Pinned PowerShell prepared:", destination)


if __name__ == "__main__":
    main()
