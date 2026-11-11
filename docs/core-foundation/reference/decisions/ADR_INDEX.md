# Proposed architectural decisions (draft; not yet merged into UI4ME repo)

The following ADRs are recommendations drawn from the source and framework research. Each should be accepted, modified or rejected explicitly before it becomes an implementation rule in a subsequent version.

| ID | Decision | Status | Key reason |
| --- | --- | --- | --- |
| ADR-001 | Core is native HTML/CSS/DOM/events/window/OS runtime only | **Recommend adopt** | Keep independent raw-HTML consumers |
| ADR-002 | `ui4me-ui` is optional, separately versioned and depends only on public Core API | **Recommend adopt** | Prevent component and server coupling |
| ADR-003 | App logic, ACP/SSE, databases, authentication and policy are external | **Recommend adopt** | No framework business logic in renderer |
| ADR-004 | No JS/Node/browser/web-server required by Core | **Recommend adopt** | Product differentiation and reliability |
| ADR-005 | Add bounded incremental DOM and batch mutation in Core 0.3 | **Recommend adopt** | Generic feature underpins UI frameworks |
| ADR-006 | Add programmatic scroll, geometry, read-only selection and clipboard in Core | **Recommend adopt** | Needed by raw apps, not merely chat |
| ADR-007 | Platform services have explicit capability/permission results | **Recommend adopt** | OS differences, security, Wayland policies |
| ADR-008 | Standard HTML control semantics belong in Core | **Recommend adopt** | `<select>` cannot require optional widgets |
| ADR-009 | Optional UI uses push-reactive properties; polling opt-in | **Recommend adopt** | Avoid hidden process-global refresh loops |
| ADR-010 | Reuse old algorithms selectively; never treat donor code as qualified | **Recommend adopt** | Old 0.5.0-rc.1 release was blocked |
| ADR-011 | Release qualification needs installed native evidence per host | **Recommend adopt** | Headless success is not desktop behavior |
| ADR-012 | Specialized editor/terminal/chart engines are optional extensions | **Recommend adopt** | Avoid huge Core surface |
| ADR-013 | UI library has independently published Python/PowerShell ergonomics | **Needs feasibility check** | Semantics shared, syntax may differ |
| ADR-014 | Delay general plugin host, GPU rendering and remote UI server | **Recommend defer** | No supported consumer need demonstrated |
| ADR-015 | Explicit source identity and immutable evidence for every release | **Recommend adopt** | Preserve reliable distribution across bindings |

## ADR template for a new feature

```
ID: ADR-NNN
Issue: <user-visible problem>
Core-only raw HTML scenario: <does it belong in Core?>
Owner: Core/Renderer | Core/Host | UI4ME UI | Extension | Application | Delivery
Alternatives considered: <2-3 ways, including no change>
Decision: <chosen approach>
Invariants and compatibility implications: <DOM, lifetime, ABI, OS>
Donor evidence: <original zip SHA and exact file:line + status>
Release target and dependencies: <feature IDs>
Acceptance: <one automated + one installed target scenario where relevant>
Risks, explicitly excluded behavior and revisit condition: ...
Reviewers/date: ...
```

A **proposed** ADR is not permission to expand Core. The agent implementing a release should treat unaccepted entries as review prompts, not absolute instructions.
