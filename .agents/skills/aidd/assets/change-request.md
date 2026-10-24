# Change Request block

A change needs a block only for an emergency, a standard change, or several Specs in one diff. Add one also to raise the route, or to declare a risk or a scope the paths do not show, such as money logic in a generic file. Without one, the gate takes the Spec the diff carries. Otherwise it takes the route the diff computes, the type from the commit subjects, and `assisted_by` from the `Assisted-by:` trailers. Put at most one block in the PR/MR description. The gate reads it, then derives all evidence from the platform. Write the summary for humans above or below the block. Write it in `locale` if one is set (a declarative field that the gate does not read). `aidd describe` prints the block for the current branch. When there is no PR/MR, `aidd describe --commit` records it on the branch.

<!-- Write the summary at the `ste-80` level (the `aidd-team:plain-language` skill). -->

## Several Specs in one diff: name the change's Spec

````markdown
```yaml aidd
spec: specs/SPEC-220.md
```
````

## Minor: inline, to name the type or the scope

Every other field has a default: `type: chore`, high confidence, no risk dimension, revert to undo, `assisted_by` from the trailers, and, without `scope`, the changed paths.

````markdown
```yaml aidd
route: minor
type: docs
scope: [docs/guide.md]
assisted_by: [claude-code/claude-opus-5-5]
```
````

## Standard change: inline

````markdown
```yaml aidd
route: standard
standard_change: dependency-patch
type: deps
scope: [package.json, package-lock.json]
assisted_by: []

risk:
  summary: Patch-level upgrade of one dependency.
  dimensions: [third_party]
  reversible: true
```
````

## Emergency: inline now, Spec by review_due

````markdown
```yaml aidd
route: emergency
type: fix
scope: [src/auth/session.ts]
rollback: Revert the PR; sessions created meanwhile keep their organization.
assisted_by: [claude-code/claude-opus-5-5]
backfill: specs/INC-481.md  # commit the stub in this change: aidd new spec INC-481 --title "Login outage" --route emergency

risk:
  summary: Restores activeOrganizationId on new sessions.
  dimensions: [security]
  reversible: true

emergency:
  severity: sev1
  kind: outage
  commander: "@oncall-lead"
  incident: INC-481
  review_due: "2026-10-02"  # a real date: the day the change opened or its head was last pushed, whichever is later, plus emergency.review_sla_days

tests:
  files: [tests/smoke/session.test.ts]

  commands:
    - name: smoke-session
      command: [npx, vitest, run, tests/smoke/session.test.ts]
```
````
