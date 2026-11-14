# Publishing UI4ME

**Publishing is a consequential action.** The local agent may publish after the owner's explicit instruction **only if every required gate passes**. PyPI and PowerShell Gallery cannot replace already-published versions. Verify 2.1.0 availability immediately before final publication; if occupied, bump to the next unused release and align all metadata, docs, tags and manifests.

The repository includes `.github/workflows/publish.yml` (manual `workflow_dispatch` only). Preserve PyPI Trusted Publishing/OIDC and the Gallery's protected API-key environment. Never commit tokens, secrets, machine passwords, logs or host evidence to public source.

Suggested order: qualify immutable final commit → compare package hashes and verify `python tools/release/source_manifest.py --check` → update README & published descriptions from actual APIs → stage source wheel/sdist/module ZIP → green CI on that exact SHA → run `python tools/preflight_publish.py VERSION` → publish Python release → publish PowerShell Gallery module → fresh install from both registries → create final version tag and release notes (or adjust manually depending on workflow release features) → record final artifact hashes/links and success. Do not allow publication when only Linux or only Python tests passed.

Keep `UI4ME` source separate from `UI4ME.Core`: do not copy native Core executables or change the Core repository. New Core blockers should be filed upstream with reproducible evidence.
