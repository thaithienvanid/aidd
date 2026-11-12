# Specs

One Markdown file per Spec: `<ID>.md`, with YAML front matter between `---` lines. Create one with `aidd new spec "<title>"`, which takes the next free id; validate everything with `aidd validate`.

Workflow for normal and major changes:

1. The agent writes the Spec and its tests first, on a branch of its own, and sets `status: ready`.
2. The agent asks for Spec approval in plain words, such as "Approve SPEC-3? It covers ...". On your yes, it sets `status: approved`, `approved_by`, and `approved_at`, and commits with an `Approved-by:` trailer of the same value, in the form the aidd skill's `references/spec.md` gives. Under the `solo` profile, it asks on major changes only.
3. The agent implements inside each Task's `scope` until `aidd test` is green on the head.
4. It asks before the work reaches the default branch. On a platform under the `team` profile, it opens a PR/MR instead, and your review there is the Merge approval.

After approval, a change to a Spec's tests or Acceptance needs your yes again, and the Spec goes back to `draft`.

Work bigger than one Spec is an Intent (`type: intent`): the phases of slices a person agrees to. It lives in `product/intents/` (`aidd new intent`), not here. A tracker's own records link to it.

## One folder per work item

Everything about a work item sits beside its file, in a folder named by its id:

```text
product/intents/
  INTENT-1.md                        an Intent
  INTENT-1/explore/<slug>/           a decision card for it (aidd new exploration)
specs/
  SPEC-12.md                         a Spec
  SPEC-12/tech-spec-<topic>.md       a document it links (aidd new tech-spec <topic> --spec SPEC-12)
  SPEC-12/design/prototype.html      its design files (aidd new design-spec <topic> --spec SPEC-12 --prototype)
  SPEC-12/explore/<slug>/            an exploration for it, with its rounds
  explore/<topic>/                   an exploration asked before any work item exists
```

`docs/` holds the project's official docs: the ADRs, the architecture overview, each component's threat model (`docs/security/threat-models/`), the runbooks, and the glossary. When a change ships, what lasts moves there, such as a decision into an ADR. `aidd status --json` lists each item's folder.
