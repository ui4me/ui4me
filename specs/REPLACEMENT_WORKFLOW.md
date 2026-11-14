# Installing the full UI4ME replacement source

The source ZIP contains the complete `ui4me/` repository tree, not a patch. It deliberately excludes `.git`, `.pytest_cache`, `dist`, `build`, native UI4ME Core binaries and secrets. It **replaces** the source of the `ui4me/ui4me` project while retaining the original Git history.

Preferred: preserve the original repository as a backup/snapshot, then unpack this ZIP into a new directory. Keep the existing `.git` metadata by moving/copying only `.git` from the old Git checkout into the new complete source tree; inspect `git status` and `git diff` before committing. Do **not** accidentally bundle the old files from the previous tree by unpacking directly on top of it without removing orphans.

Example on Linux, after verifying the paths and making a backup:

```bash
cd ~/projects
mv ui4me ui4me-backup-2.0.1
unzip /path/to/ui4me-full-2.1.0-source.zip -d ~/projects
cp -a ui4me-backup-2.0.1/.git ui4me/.git
cd ui4me
git status --short
python -m pytest -q tests/unit tests/bridge
```

A local agent must reconcile new upstream changes and run the staged qualification sequence in `specs/LOCAL_AGENT_HANDOFF.md` before push/publish. It should not force-reset or force-push. No Core checkout is included: install/qualify published UI4ME Core 1.0.1 as a dependency.
