# Release preparation

The current candidate is not qualified. Do not publish until both platforms and
both bindings have complete acceptance evidence for the exact final artifacts.
Build and test each platform independently, assemble the final manifest and
packages, test those exact files, and run `python dev.py qualify` against that
manifest. Retain hashes, logs and visual evidence. Assembly and attestation
tools are implemented; their existence or a passing CI run does not establish
that the required native observations and release review have been completed.

Publishing requires a separate, explicit owner action; ordinary CI neither has
registry credentials nor publishes. Before enabling a publishing workflow:

- Verify the PyPI and TestPyPI project names and each registry's trusted-publisher
  configuration, including the exact GitHub organization, repository, workflow
  filename and protected environment. Do not assume organization approval.
- Protect publishing environments with appropriate reviewers and restrict
  `id-token: write` to the job that needs PyPI OIDC. Never grant it to pull
  request code. Consult [PyPI trusted publishers](https://docs.pypi.org/trusted-publishers/adding-a-publisher/).
- Verify the PowerShell Gallery project ownership and place a scoped, expiring
  API key only in the protected publishing environment. Never print it or expose
  it to pull-request jobs. Confirm the gallery's current upload mechanism.
- Set GitHub Actions repository and environment permissions to the minimum
  needed for the explicit release action. Verify the publisher transfers the
  previously qualified files without rebuilding them.
- After explicit authorization, upload first to TestPyPI, verify a clean
  download and installation, then publish the exact qualified production files.
  Verify hashes and installation from each public registry and record any
  partial publication; do not silently rebuild an already-qualified candidate.

These are preparation requirements, not claims that accounts, environments,
workflow permissions, package names, registry access or download verification
have been configured. No release, public tag, or package has been published by
this workflow.
