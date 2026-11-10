# Publishing ui4me

This is a setup and operating guide. No names were reserved, accounts configured,
packages uploaded or workflows executed during reconstruction. Package version
0.1.0 is a candidate version, not an already-published release.

## Decisions before the first release

| Setting | Proposed value | What you must establish |
| --- | --- | --- |
| GitHub product repository | `ui4me/ui4me` | Create it under your organization; default branch `main` |
| PyPI distribution | `ui4me` | Check availability and establish registry ownership |
| Python import | `ui4me` | Keep consistent with examples and metadata |
| PowerShell module | `Ui4me` | Check Gallery availability and establish package ownership |
| Documentation URL | `https://ui4me.github.io/` | Create `ui4me/ui4me.github.io` as the generated-output host |
| Product version | `0.1.0` | Keep VERSION and binding/crate metadata synchronized |
| Native ABI | `1` for this new library | Do not substitute an old engine DLL with different exports |
| License | MIT | Confirm the intended license before publishing |

Registry namespaces are independent. A GitHub organization does not reserve a
PyPI or Gallery package name. A pending PyPI publisher also does not reserve its
name until it publishes. If a name is unavailable, change package metadata,
loader/package diagnostics, publication URLs and documentation together.

## PyPI and TestPyPI setup

1. Create your PyPI account at https://pypi.org/account/register/ and complete its account verification and authentication requirements.
2. Create a separate TestPyPI account at https://test.pypi.org/account/register/.
3. For a new project, open the account's **Publishing** section and add a pending GitHub publisher. For an existing project, use its **Manage → Publishing** settings.
4. Enter the fields below exactly. Configure the TestPyPI publisher separately.
5. Establish the project's owner/maintainer access after creation. GitHub team membership does not automatically grant PyPI project permissions.

| Publisher field | Production | Test |
| --- | --- | --- |
| Project name | `ui4me` | `ui4me` |
| Repository owner | `ui4me` | `ui4me` |
| Repository name | `ui4me` | `ui4me` |
| Workflow filename | `publish.yml` | `publish.yml` |
| GitHub environment | `pypi` | `testpypi` |

The included workflow uses the official PyPI publishing action with OIDC. It
publishes only the two already-qualified wheels, copied unchanged into a clean
directory. It does not publish an incomplete sdist. The local CLI's optional
Twine route uses operator-supplied `TWINE_USERNAME=__token__` and
`TWINE_PASSWORD`; the CI path does not need those long-lived secrets.

Primary guidance: [create a project through OIDC](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/),
[configure a publisher](https://docs.pypi.org/trusted-publishers/adding-a-publisher/),
[security model](https://docs.pypi.org/trusted-publishers/security-model/).

## PowerShell Gallery setup

1. Sign in/register at https://www.powershellgallery.com/ and verify the account details.
2. Check that the module name is available or that your account owns it.
3. Create an API key with the narrowest applicable package scope and an appropriate expiration. Put it in the GitHub **psgallery environment secret** named `PSGALLERY_API_KEY`.
4. Add the intended co-owners through the package's owner-management UI. Co-owners have substantial package control; they are not synchronized with the GitHub organization.
5. Confirm Author, CompanyName, description, license and project URLs in `Ui4me.psd1`.

Use PowerShell 7.6 for the documented contributor/publisher path and
PSResourceGet 1.1 or newer. The module's reference API floor is 7.4; this is not a
claim that every host release has been exercised.

Both platform builds contribute to **one** final `Ui4me` nupkg. Do not publish a
Windows-only package and later try to replace the same Gallery version with a
Linux payload. The final nupkg is created with `Compress-PSResource` and uploaded
with `Publish-PSResource -NupkgPath`, preserving the candidate package.

Installed tests resolve that nupkg through PSResourceGet in a temporary local
feed, save it to an isolated directory and import it there. They do not install
into the contributor's normal module scope. A fresh PowerShell process is
required for testing an upgrade of an already-loaded native module.

The installed acceptance also removes the native payload temporarily and expects
a fresh consumer to fail clearly, restores it, then removes and reinstalls the
candidate before another fresh consumer run. Python performs uninstall/reinstall
with pip; PowerShell removes and re-saves the isolated module through its local
feed. The first 0.1 release has no previous public version to upgrade from. Add
an explicit previous-to-current version switch when a predecessor exists.

Primary guidance: [package owners](https://learn.microsoft.com/en-us/powershell/gallery/how-to/publishing-packages/managing-package-owners),
[Compress-PSResource](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.psresourceget/compress-psresource),
[Publish-PSResource](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.psresourceget/publish-psresource).

## GitHub environments and runners

Create environments `native-validation`, `release-review`, `testpypi`, `pypi`,
`psgallery` and `github-release`. Restrict release environments to the default
branch and configure trusted reviewers. Store the Gallery key only in
`psgallery`. The GitHub release job uses the repository's scoped Actions token.
No registry secrets are needed for pull-request CI.

The supplied workflows use verified full commit references for external Actions.
Review dependency-update pull requests. The pinned PowerShell CI bootstrap checks
the upstream archive hash before extraction; it does not install a machine-wide
PowerShell instance.

`ci.yml` builds Windows/Linux, assembles final files, tests installed Python,
PowerShell and C SDK consumers on each platform, and uploads `ci-bundle`.
It requires the reviewed Cargo and NuGet lock files committed in the repository.

Native tests run on your desktop against that exact candidate. For the optional
evidence collection workflow, register trusted self-hosted runners with the
normal OS/X64 labels and `ui4me-native`. Set the runner's
`UI4ME_EVIDENCE_DIRECTORY` to a separate directory containing complete native
run folders from both bindings. Do not place this directory inside the runner's
checkout because checkout cleanup can remove it. Windows runners need Git Bash
for the workflow's short shell steps.

The following setup is an owner action because registering a runner uses a
short-lived GitHub registration token. Do not put that token in source,
shell history, screenshots, or test evidence:

1. On each dedicated machine, open the repository's **Settings → Actions →
   Runners → New self-hosted runner** page and follow the OS-specific download
   and configuration commands there. Register one Linux x64 runner and one
   Windows x64 runner; add the custom label `ui4me-native` to each. Download
   and register only on hosts the owner trusts to run this repository's code.
2. Put the complete, reviewed native run folders for that platform in a local
   directory outside the runner's work directory and checkout. Use the evidence
   generated for the exact `ci-bundle` manifest: locally rebuilt artifacts
   with different manifest hashes will be rejected, even at the same commit.
3. Start the runner process with the directory set in its environment. For an
   interactive Linux runner, in its installation directory use
   `UI4ME_EVIDENCE_DIRECTORY=/absolute/path/to/native-evidence ./run.sh`.
   For an interactive Windows PowerShell runner, set
   `$env:UI4ME_EVIDENCE_DIRECTORY = 'C:\path\to\native-evidence'` and run
   `.\run.cmd`. A runner installed as a service must receive the same variable
   in the service environment and be restarted. These collection runners do
   not need an interactive desktop; the desktop tests must already have run.
4. Dispatch **Collect reviewed native evidence** twice on the candidate's
   default-branch commit, once for each platform, with the same successful
   Foundation CI run ID. Keep both successful collection run IDs for the
   guarded publication workflow. The collector does not publish anything.

The owner's release review remains necessary: the evidence importer validates
source and artifact identity, but cannot authenticate the truth of an operator's
observations. Do not label an automated observation as a human attestation.

`native-evidence.yml` does not pretend to automate human observations. It checks
the CI producer, collects matching source/manifest receipts from that directory,
and uploads `native-linux-x64` or `native-win-x64`. Collect each platform after
its operator has completed and recorded the procedures. Publication recomputes
qualification; a successful collection upload alone is not a passing native test.

## Final artifact sequence

```sh
# On each target, from the same committed source and reviewed locks:
python dev.py build --binding all --profile release
python dev.py test --binding all --suite unit --profile release
python dev.py package --binding all --profile release

# After bringing both full platform directories to the assembly machine:
python dev.py assemble --manifest dist/linux-x64/manifest.json --manifest dist/win-x64/manifest.json --out dist/release
```

Run installed Python, PowerShell and native SDK acceptance against
`dist/release/manifest.json` on both platforms. Run and attest the native desktop
scenarios. Merge complete run folders under `build/reports` without changing
their names or contents. Then review:

```sh
python dev.py report --manifest dist/release/manifest.json
python dev.py qualify --manifest dist/release/manifest.json --reviewer "YOUR_NAME" --review-url https://github.com/ui4me/ui4me/actions/runs/REAL_RUN_ID
```

Use the real review/run URL. Qualification requires the complete current matrix,
both platforms' unit suites, both native SDK consumers, exact artifact/proof
hashes, a clean matching source revision and tracked dependency locks. It cannot
authenticate an operator's truthfulness; review the originating workflow and
manual evidence.

## First publication

Run `publish.yml` from the default branch at the candidate commit. Supply the
successful CI run ID and the two native-evidence collection run IDs. The workflow
checks repository, workflow, event, branch, commit, completion and artifact
identity before retrieving them. Start with `execute=false` to review
qualification and the publication command. Actual execution is explicit.

All referenced producer runs must match the workflow's current default-branch
commit. Complete qualification before advancing that release commit, or rerun
the candidate cycle for the new commit. This first workflow deliberately does
not accept arbitrary historic or pull-request artifacts for publication.

Publish one destination at a time. TestPyPI and production PyPI are separate
services. Gallery does not provide the same parallel TestPyPI workflow; use the
local feed and an appropriate prerelease/version strategy when needed. Do not
publish disposable test versions under the final public package name casually.

For a deliberate local publication, the equivalent commands are:

```sh
python dev.py publish --manifest dist/release/manifest.json --registry pypi
python dev.py publish --manifest dist/release/manifest.json --registry powershell
python dev.py publish --manifest dist/release/manifest.json --registry github
# Add --execute only when the displayed operation is intended.
```

Create the GitHub `v0.1.0` tag at the reviewed source commit before the GitHub
release operation. Never retag a published version to different source. A source
archive can be generated with `python dev.py source-zip`; GitHub also supplies
the repository source for the tagged release.

After publication:

```sh
python dev.py verify --manifest dist/release/manifest.json --registry pypi
python dev.py verify --manifest dist/release/manifest.json --registry powershell
python dev.py verify --manifest dist/release/manifest.json --registry github
```

Verification downloads public artifacts and compares exact hashes before an
installed consumer runs on the current host. Repeat on Windows as well as Linux.
If indexing delays a new version, retry verification after it becomes visible;
do not rebuild or substitute another file. Public verification receipts are a
separate phase and do not replace candidate-acceptance results. The Python
publisher resumes only after downloading and matching already-published wheels;
the Gallery CLI similarly checks any existing package before skipping it.
The GitHub creator refuses to overwrite an existing release. If creation already
succeeded, rerun verification directly instead of rerunning release creation.

Publication across registries is not transactional. Preserve each successful
upload, mark remaining destinations pending, and inspect remote file identity
before retrying. A changed package requires a new version and new acceptance.

## Documentation and evidence at GitHub Pages

Create `ui4me/ui4me.github.io`. In that repository's Pages settings select the
generated publication branch and its root directory. Keep editable documentation
in this product repository. Copy the generated report tree and its referenced
run folders together; moving only index.html breaks screenshot and log links.

The included `scripts/export-pages.py` produces a static documentation and
evidence site under `build/site` when run locally. Publish that generated
directory to the hosting repository. It contains no credentials and performs no
git push. This keeps website publishing reviewable without requiring a second
product repository or an extra registry credential in ordinary CI.

```sh
python -m pip install Markdown==3.7
python dev.py report
python scripts/export-pages.py
```

[GitHub Pages organization-site rules](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages)
explain why the root URL uses the `ui4me.github.io` repository name.

## Before claiming public support

Review license notices and the dependency inventory from the actual locked graph,
verify native runtime dependencies on clean consumer machines, and record the
tested OS/runtime/backend versions. Linux auditwheel output reports compatibility
for the produced ELF payload; it does not qualify every compositor or dynamically
loaded desktop library. Broad accessibility, IME, signing, additional platforms
and a standalone installer remain separate work. WinGet is relevant when there
is an actual application installer to distribute; it is unnecessary for these
language library packages.
