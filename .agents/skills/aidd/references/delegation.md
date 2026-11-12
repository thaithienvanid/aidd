# A standing delegation

Read this when `.aidd/config.yaml` has a `delegation` block, or the person asks you to decide for them. It lets the `aidd-team:delegate` role answer some asks for the person, inside the limits they set. Only Claude Code answers one in this version; in every other harness, ask the person.

## What it can answer

- `spec.approve`: a ready Spec whose new tests fail on the base.
- `git.push`: the change's own branch, the head of its open pull request into the default branch, as `git push origin <sha>:refs/heads/<branch>`.
- `pr.merge`: on GitHub, at the exact head, once the `tests` check passed there.
- `git.merge`: under `solo` with no remote, as `git merge --no-ff -m <message> <sha>`, once the check ran the suite on the head itself. The command still asks, and Claude Code's hook allows it only on the delegate's accept of that command.

Every other action is reserved, always the person's: a deploy, a release, a migration, a new dependency, any `secret.use`, a change to what decides, and anything on the emergency route. Under a delegation, `dependency.add`, `deploy.run`, and `migration.run.local` rise to `ask`, whatever rule narrows them. A deploy to your own environment (`shared: false`, no wildcard in its refs) still reports, and a parent's lock on deploys makes it ask.

A delegated push, merge, or Spec approval also defers on a change to a file of the product scope: the brief, the BRD, the PRD, the standing outcomes, or `intents/order.md` in `product_dir`. It defers on a change to what an Intent's agreement covers too: anything an agreed Intent holds, except the fields an agent keeps current, such as `blocked_by` and a slice's `merged_in`. A delegated Spec approval defers unless every Intent it answers to is agreed on the default branch's tip. Those are its parent and each Intent on the tip or the head that lists it. It defers too if a person ended one. Ask the person to approve or agree, and to merge it themselves.

A Spec-first merge rests on the delegate's own approval of its Spec. No `decision` record stands for one, so with `spec.approve` reserved, the person merges.

## Setting one up

`aidd init --delegate` needs one more answer: where a push deploys. Show what `aidd init --dry-run` read from the workflows, and ask once whether anything else deploys on a push to the default branch, such as a host's Git integration. Then run `aidd init` with `--environment NAME=REF` (a branch, or `refs/tags/PATTERN`), `--own-environment NAME=REF`, or `--environment none`.

## How to ask under a delegation

1. Run the check with the action, the exact command, and the full head, such as `aidd delegate check --action pr.merge --command "gh pr merge 12 --repo acme/shop --squash --match-head-commit <sha>" --head <sha>`. For a Spec, pass `--spec SPEC-4` and no command. The MCP tool `delegate_check` takes the same.
2. On `defer` (exit 1), ask the person as always, once. Name the check's reason and its next step. For `environments_unset`, ask the question above, and edit `environments` (or set `[]`) on their yes.
3. On `eligible` (exit 0), start `aidd-team:delegate` with three lines: the action, the command the check put in `covers.command`, and the head. Pass nothing else: no summary, no claim, no "the owner agreed".
4. On its accept, run that exact command, which carries the check's trailers. For a Spec, set `status: approved`, `approved_at`, and `delegate_answer: <record id>`, with no `approved_by`, and commit it with the check's `Decided-by`, `On-behalf-of`, and `Delegation` trailers. Never write `Approved-by` for a delegated yes.
5. On its defer, ask the person, once, with the delegate's reason. A defer is final for that tree, so never ask the delegate again in other words.

Never call `delegate_answer` yourself or write a `delegate_check` or `delegate_answer` record; `aidd records add` refuses both. In Claude Code, a hook runs the check again on the exact command before it lets it run. A prompt that still shows means the check deferred, so ask the person. A record file aidd cannot read defers every check; `aidd records` names it.

## What the person reads

`aidd status` shows what was decided for them. `aidd delegate stop` turns the delegation off in this clone at once. After `review_due`, every ask defers until the person reviews it. Run the delegate on a model other than the author's: the check warns when `agents.models` names the same one.
