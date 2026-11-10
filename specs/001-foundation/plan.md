# Foundation implementation plan

## Boundaries

Use one Rust crate with ordinary modules for lifecycle, native integration and
the small document renderer. Keep the C ABI at that crate boundary. Both binding
packages call the same ABI; their host-language behavior stays in their facade.
Build/release tooling does not enter the runtime dependency graph.

## Incremental sequence

1. Freeze C ABI ownership, callback, error and session contracts.
2. Implement headless contracts and actual native startup in the same engine.
3. Implement Python and PowerShell beginner facades and explicit advanced operations.
4. Make one small consumer example per binding exercise input, windows and return-to-host.
5. Build platform outputs and test the installed packages outside the repository.
6. Assemble one final release, including the combined PowerShell package.
7. Record native evidence against those final artifacts on each supported desktop.
8. Qualify the final files, publish deliberately, then verify public downloads and installation.
9. Port renderer changes as separate pull requests, retaining all foundation acceptance.

## Dependency decision

Use released winit/softbuffer versions rather than importing old engine patches.
The initial reconstruction does not execute dependency resolution. The first
local contributor must generate and review Cargo.lock, commit it, and retain it
for subsequent `--locked` builds. This delivery does not claim reproducible
dependency resolution or bit-identical builds before that step.

## Change selection

Changes to the native ABI, runtime, C header or common harness select both
bindings. Binding-only changes can use targeted local tests, but release
qualification still checks the final supported matrix. Native integration
changes select native acceptance, even when headless tests remain green.

## Reconstruction review

This source was authored under an explicit no-execution constraint. Static review
can catch mismatched interfaces and packaging paths but cannot replace compiling
the native and managed components or running actual desktop scenarios. Fix any
first-build defects before broadening rendering scope. Preserve the distinction
between implementation tasks and acceptance tasks in the task list.
