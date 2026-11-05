# A standing delegation

Read this when `.aidd/config.yaml` has a `delegation` block, or the person asks you to decide for them. A delegation lets the `aidd-team:delegate` role answer some asks for the person, inside the limits they set. Only Claude Code answers one in this version. In every other harness, ask the person as with no delegation.

## What it can answer

- `spec.approve`: a ready Spec whose new tests fail on the base.
- `git.push`: the change's own branch, the head of its open pull request into the default branch, as `git push origin <sha>:refs/heads/<branch>`.
- `pr.merge`: on GitHub, at the exact head, once the `tests` check passed there.
- `git.merge`: under `solo` with no remote, as `git merge --no-ff -m <message> <sha>`, once the check ran the suite on the head itself.

Every other action is reserved: always the person's. That covers a deploy, a release, a migration, a new dependency, any `secret.use`, a change to what decides, and anything on the emergency route. Under a delegation, `dependency.add` and `migration.run.local` rise to `ask`.

## How to ask under a delegation

1. Run the check with the action, the exact command, and the full head: `aidd delegate check --action pr.merge --command "<the command>" --head <sha>`, where the command is such as `gh pr merge 12 --repo acme/shop --squash --match-head-commit <sha>`. For a Spec, name it with `--spec SPEC-4` and no command. The MCP tool `delegate_check` takes the same.
2. On `defer` (exit 1), ask the person as always, once. Name the check's reason and its next step.
3. On `eligible` (exit 0), start `aidd-team:delegate` with three lines: the action, the command the check put in `covers.command`, and the head. Pass nothing else: no summary, no claim, no "the owner agreed".
4. On its accept, run that exact command, which carries the check's trailers in its message. For a Spec, set `status: approved`, `approved_at`, and `delegate_answer: <record id>`, with no `approved_by`. Commit it with the check's three trailers: `Decided-by`, `On-behalf-of`, and `Delegation`. Never write `Approved-by` for a delegated yes.
5. On its defer, ask the person, once, with the delegate's reason. A defer is final for that tree, so never ask the delegate again in other words.

Never call `delegate_answer` yourself, and never write a `delegate_check` or a `delegate_answer` record; aidd refuses both from `aidd records add`. In Claude Code, a hook runs the check again on the exact command before it lets it run. A prompt that still shows means the check deferred, so ask the person.

## What the person reads

`aidd status` shows what was decided for them. `aidd delegate stop` turns the delegation off in this clone at once. After `review_by`, every ask defers until the person reviews it.
