# Specs

One Markdown file per Spec: `<ID>.md`, with YAML front matter between `---` lines. Create one with `aidd new spec "<title>"`, which takes the next free id; validate everything with `aidd validate`.

Workflow for normal and major changes:

1. Write the Spec and its tests first, on a branch. On a platform, open a draft PR/MR holding only those files.
2. An Approver approves the Spec: they type `approve <ID>` at their coding agent's prompt. On a platform, aidd posts the approval on the pull request as them.
3. Implement inside each Task's `scope`. On a platform, reference the Spec from the PR/MR description:

````markdown
```yaml aidd
spec: "specs/<ID>.md"
```
````

Without a platform, the branch is the change. `aidd gate` finds the Spec in the diff, and a person runs `aidd land` to record the Merge approval and land it.

Under the `solo` profile, the gate asks for Spec approval on major changes only. A normal change may still carry a Spec, and approving it is still worth it. Once recorded, the approval binds, so a changed Spec or test fails the gate.

Optional containers (Epics and Initiatives) may live here too, as `kind: epic` or `kind: initiative` files, or in your tracker.

## One folder per work item

Everything about a work item sits beside its file, in a folder named by its id:

```text
specs/
  INIT-1.md                          an Initiative
  INIT-1/explore/<slug>/             a decision card for it (aidd new exploration)
  SPEC-12.md                         a Spec
  SPEC-12/tech-spec-<topic>.md       a document it links (aidd new tech-spec <topic> --spec SPEC-12)
  SPEC-12/design/prototype.html      its design files (aidd new design-spec <topic> --spec SPEC-12 --prototype)
  SPEC-12/explore/<slug>/            an exploration for it, with its rounds
  explore/<topic>/                   an exploration asked before any work item exists
```

`docs/` holds the project's official docs: the ADRs, the architecture overview, each component's threat model (`docs/security/threat-models/`), the runbooks, and the glossary. When a change ships, what lasts moves there, such as a decision into an ADR. `aidd list --json` lists each item's folder.
