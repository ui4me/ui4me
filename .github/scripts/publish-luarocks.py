"""Publish the LuaJIT rock to luarocks.org (the steps of `luarocks upload --src-rock`).

    LUAROCKS_API_KEY=... python .github/scripts/publish-luarocks.py dist/release

Uploads ui4me-<version>-1.rockspec and ui4me-<version>-1.src.rock from the release folder. An
existing revision is never replaced: the script fails instead. Exit status 0 only when both
files were accepted and the rockspec is then served by luarocks.org.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

SERVER = "https://luarocks.org"


def call(path: str, params: dict | None = None, files: dict[str, Path] | None = None) -> dict:
    url = f"{SERVER}/api/1/{os.environ['LUAROCKS_API_KEY']}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data, headers = None, {"User-Agent": "ui4me-release"}
    if files:
        boundary = uuid.uuid4().hex
        parts = []
        for field, file in files.items():
            parts += [f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{file.name}\"\r\n"
                      "Content-Type: application/octet-stream\r\n\r\n".encode(), file.read_bytes(), b"\r\n"]
        parts.append(f"--{boundary}--\r\n".encode())
        data = b"".join(parts)
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if files else "GET")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:  # never print the URL: it contains the key
        try:
            detail = ", ".join(map(str, json.loads(error.read()).get("errors", [])))
        except (ValueError, AttributeError):
            detail = ""
        raise SystemExit(f"LuaRocks API {path.split('/')[0]} failed: HTTP {error.code} {detail}".rstrip())
    if result.get("two_factor_required"):
        raise SystemExit("LuaRocks requires two-factor verification for this account; publish with "
                         "`luarocks upload` interactively or use a key that does not require it")
    if isinstance(result.get("errors"), list):
        raise SystemExit("LuaRocks API " + path.split("/")[0] + " failed: " + ", ".join(map(str, result["errors"])))
    return result


def main() -> int:
    if not os.environ.get("LUAROCKS_API_KEY"):
        raise SystemExit("Set LUAROCKS_API_KEY in the luarocks environment")
    folder = Path(sys.argv[1])
    version = (Path(__file__).resolve().parents[2] / "VERSION").read_text().strip()
    rockspec = folder / f"ui4me-{version}-1.rockspec"
    rock = folder / f"ui4me-{version}-1.src.rock"
    for file in (rockspec, rock):
        if not file.is_file():
            raise SystemExit(f"Missing {file}")
    existing = call("check_rockspec", {"package": "ui4me", "version": f"{version}-1"})
    if existing.get("version"):
        raise SystemExit(f"ui4me {version}-1 already exists on LuaRocks; not replacing it")
    uploaded = call("upload", files={"rockspec_file": rockspec})
    identifier = (uploaded.get("version") or {}).get("id")
    if not identifier:
        raise SystemExit("LuaRocks accepted the rockspec but returned no version id")
    if uploaded.get("is_new") and not uploaded.get("manifests"):
        print("::warning::LuaRocks did not add ui4me to the root manifest (name taken)")
    call(f"upload_rock/{int(identifier)}", files={"rock_file": rock})
    print("Uploaded:", uploaded.get("module_url"))
    # The public file can take a moment to appear.
    for _ in range(12):
        try:
            with urllib.request.urlopen(f"{SERVER}/{rockspec.name}", timeout=60) as response:
                if response.read() == rockspec.read_bytes():
                    print(f"Verified: {SERVER}/{rockspec.name}")
                    return 0
        except urllib.error.URLError:
            pass
        time.sleep(10)
    raise SystemExit(f"{SERVER}/{rockspec.name} is not served with the uploaded content")


if __name__ == "__main__":
    sys.exit(main())
