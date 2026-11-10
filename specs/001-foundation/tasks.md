# Foundation tasks

The source for the implementation work is included. No runtime acceptance is
checked off in this reconstruction. Use the evidence report to complete the
acceptance column; do not mark a feature accepted because its source exists.

| Task | Source deliverable | Local acceptance |
| --- | --- | --- |
| T01 | Lifecycle specification and C ABI | [ ] Review ownership and error semantics |
| T02 | Rust core, native platform integration and small renderer | [ ] Compile and pass core tests |
| T03 | Python facade, loader and tests | [ ] Build/install wheel and pass selected tests |
| T04 | PowerShell module, managed host and tests | [ ] Build/install module and pass selected tests |
| T05 | Multiwindow/input/example applications | [ ] Perform native scenarios on both platforms |
| T06 | Developer command line and bootstrap scripts | [ ] Complete clean-host development cycle |
| T07 | Package/assembly manifests | [ ] Validate final artifacts and dependencies |
| T08 | Installed consumers outside checkout | [ ] Test actual final packages, Unicode paths and missing native payload |
| T09 | Structured evidence and report generation | [ ] Exercise latest failure, stale evidence and zero-test negative cases |
| T10 | CI and guarded publication workflows | [ ] Run on the new organization repository |
| T11 | Registry and documentation setup instructions | [ ] Establish owners, names, environments and Pages hosting |
| T12 | Clean source archive and delivery report | [ ] Import into git; generate/review/commit dependency lock |
| T13 | Public v0.1 acceptance | [ ] Qualify all required observations; publish and verify public installs |

## First local session

- [ ] Confirm the proposed MIT license and package names before publication.
- [ ] Install the contributor tools and inspect `python dev.py doctor`.
- [ ] Generate Cargo.lock, review direct/transitive dependencies and commit it.
- [ ] Build and test each binding on the current host.
- [ ] Resolve first-build or runtime defects before assuming packaging is correct.
- [ ] Build final platform outputs and exercise isolated installation.
- [ ] Run native acceptance on a real desktop; record logs and actual captures.
- [ ] Repeat the platform cycle on the other operating system.

## After v0.1 acceptance

- [ ] Port one renderer/layout capability per reviewable change.
- [ ] Add its requirement, owning tests and compatibility observations.
- [ ] Preserve startup, ownership, stop, native reuse and installed-package tests.
- [ ] Add accessibility, IME and other deferred targets explicitly rather than silently expanding support claims.
