# Specs

One Markdown file per Spec: `<ID>.md`, with TOML front matter between `+++` lines. Create one with `aidd new spec <ID> --title "..."`; validate everything with `aidd validate`.

Workflow for normal and major changes:

1. Write the Spec and its tests first, on a branch. On a platform, open a draft PR/MR holding only those files.
2. An Approver approves the Spec. On a platform, they comment the line `aidd hash specs/<ID>.md --line` prints. Without one, they run `aidd approve spec specs/<ID>.md` in a terminal they opened themselves.
3. Implement inside each Task's `scope`. On a platform, reference the Spec from the PR/MR description:

````markdown
```toml aidd
spec = "specs/<ID>.md"
```
````

Without a platform, the branch is the change. `aidd gate` finds the Spec in the diff, and a person runs `aidd ship` to record the Merge approval and land it.

Under the `solo` profile, the gate asks for Spec approval on major changes only. A normal change may still carry a Spec, and approving it is still worth it. Once recorded, the approval binds, so a changed Spec or test fails the gate.

Optional containers (Epics and Initiatives) may live here too, as `kind = "epic"` or `kind = "initiative"` files, or in your tracker.
