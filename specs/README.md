# Specs

One Markdown file per Spec: `<ID>.md`, with TOML front matter between `+++` lines. Create one with `aidd new spec <ID> --title "..."`; validate everything with `aidd validate`.

Workflow for normal and major changes:

1. Write the Spec and its tests first. Then open a draft PR/MR holding only those files.
2. An Approver comments the line `aidd hash specs/<ID>.md --comment` prints.
3. Implement inside each Task's `scope`, and reference the Spec from the PR/MR description:

````markdown
```toml aidd
spec = "specs/<ID>.md"
```
````

Optional containers (Epics and Initiatives) may live here too, as `kind = "epic"` or `kind = "initiative"` files, or in your tracker.
