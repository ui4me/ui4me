# Reference source handling

`reference/` is the supplied architecture/research bundle from 2026-11-11. The old-code file/line anchors refer to the separate original source archive, **not** to `ui4me/ui4me` `main`.

To allow fast donor reuse, make the original `bigbatmanorg-ui4me-old(1).zip` available to the local agent **outside the tracked repository**, such as `../ui4me-old.zip` (or unpack it in `../ui4me-old-reference/`). The archive's internal root is `ui4me-main/`, and source paths within it begin with e.g. `engine/crates/...`. Agent should locate it, verify paths, and copy only relevant routines. Do not add 116 MB of old source and its old tests to the new repo.

Example (optional, performed by the local developer/agent only if the archive is present):

```sh
mkdir -p ../ui4me-old-reference
unzip -q ../ui4me-old.zip -d ../ui4me-old-reference
```

If the reference archive has a different name/path, update the path locally; don't assume the old GitHub repo is public. `DONOR_PRIORITY_MAP.md` is enough to find precise symbols once the old archive is accessible. Research source lines indicate potential implementation, not production correctness. Do not bulk-copy old crates, tools, tests or package metadata.
