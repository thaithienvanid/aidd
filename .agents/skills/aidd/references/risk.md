# Risk rules

Read this when you check a level, ask a person, or a person wants to change the rules. `schemas/risks.json` holds the built-in rules. `aidd risk --list` shows every action, area, and effective rule, with its source.

## Actions

An action is what you do, named `resource.verb`, such as `pr.open` or `git.push.force`. Each built-in action has shell patterns (`aidd risk --command "<cmd>"` matches them) and examples that no pattern catches. When the command runs in another folder than your session's, such as a sibling worktree, give that folder too (`--folder <path>`, or the MCP tool's `folder`), so the branch is read there. You judge those: dropping a table is `data.delete` whatever command does it. When you cannot tell which action a step is, take the one with the higher level. A listing, a preview, or a request for help reads `allow` when it is a form in `read_forms` or `help_forms` (`git tag -l`, `kubectl apply --dry-run=client`), as a note says. A wrapper or any other word keeps the level, and a harness may still ask.

| Action | Level |
| --- | --- |
| `code.edit` | allow, except in the areas below |
| `git.commit`; `git.push` and `git.merge` on your own branch | allow |
| `pr.open`; `migration.run.local`, a forward migration on a database only this checkout uses; `deploy.run` to your own environment (`shared: false`) | report |
| `git.push` to the default branch or a shared branch; `git.merge` on any branch but your own; `git.push.force`, `git.history.rewrite`, `git.branch.delete`, `git.tag.create` | ask |
| `spec.approve` (`report` on a normal change under `solo`), `spec.revise`, `pr.merge` | ask |
| `deploy.run` anywhere else, `release.publish`, `migration.run`, `migration.rollback`, `infra.apply`, `data.delete`, `data.production.access`, `secret.use`, `message.send`, `money.spend` | ask |

A migrate that names a target migration, such as `migrate shop 0003` or `database update InitialCreate`, is `migration.rollback`, unless you checked that the target is ahead.

A branch is `own` (your work branch), `default` (the repository's default branch), or `shared` (any other branch someone else pushed to).

## Areas

An area is a named set of paths. An edit inside it takes its level, and a change that touches it takes at least its route.

<!-- aidd:gen risks:areas:levels -->
| Area | Edit level | Route |
| --- | --- | --- |
| `auth`, `payments`, `personal_data`, `secrets`, `migrations` | ask | major |
| `module_boundaries` | report | major |
| `ci`, `infra`, `dependencies`, `agent_config`, `project_config` | report | normal |
| `risk_rules` | ask | normal |
<!-- aidd:end -->

`aidd risk --paths <paths>` names the areas a path hits. With the CLI, never match a glob by hand; without it, judge the path against the areas in `references/routes.md` by what each holds, and say the route is unchecked.

## Rules and which one wins

A rule is <!-- aidd:gen list:risk-rule-fields -->`{action, area?, branch?, role?, environment?, environment_shared?, route?, level, locked?, reason?}`<!-- aidd:end -->, and `?` marks an optional one. `action` may end in `.*` (`git.*`) or be `*`. `role` is an aidd-team role id. `environment` names one of the config's `environments`: a push to its branch or tag is `deploy.run` to it, so ask "Deploy to production?". `environment_shared: false` matches your own environment. The levels, lowest first, are `allow`, `report`, and `ask`.

Of the rules that match, the most specific wins:

1. An exact action beats a `.*` one, and a longer prefix beats a shorter one.
2. Then the rule that sets more narrowing fields, such as `area` or `route`, wins.
3. Between equals, the higher level wins.

With no rule matching, it is `allow`. The profile's rules replace built-in rules with the same selector (the action and what narrows it), and the config's rules replace both. A rule that an `extends` parent marks `locked: true` is a floor: the level is never lower than it, and it never lowers a built-in or another rule, so a lock below the built-in level changes nothing. `aidd risk` reports a project's rule with the lock's own selector as ignored, and a narrower one may ask more.

## One yes for one piece of work

- A yes to a Spec's approval covers `code.edit` inside its Tasks' `scope`. Outside the scope, the rules apply as usual.
- A yes holds only for what your question showed. A different branch, more commits, or another target is a new question, and so is a head a rebase moved or a command an edit rewrote.

## How to ask

- Ask one plain question. Say what the action does, why you need it, and what it changes: "Force-push to `main`? It replaces 2 commits there with the rebased ones." Say when it cannot be undone.
- Under a delegation, an action it covers goes to the delegate first (`references/delegation.md`).
- A yes is the person's own words (rule 1 of the skill), such as "yes", "go ahead", or "do it". A question back, a "maybe", or silence is no yes.
- On their yes, do it for them, then say what you did. On a no, leave it, and name the next step that works without it.
- The harness may show its own prompt for the same command: its ask rules, which `aidd init` writes. Then ask in the chat first and say that the prompt follows. The person decides once.
- In a headless run, the handoff note names the action and its question (rule 1 of the skill, `references/handoff.md`).

## Record what happened

After you act on a person's answer to an ask, and after a `report` action, record it once. The MCP `record` tool takes `type`, `by` (your `<harness>/<model>`, as in a commit's `Assisted-by`), an optional `subject`, and `data`. Prefer the tool, because aidd's server writes the file outside the harness's sandbox. A sandbox that keeps `.git` read-only, as Codex's `workspace-write` does, refuses the command. `aidd init` lets aidd's own tools run with no prompt in Codex and Claude Code, so a headless run records there too. In another harness a headless run can't approve the call, so there it records nothing. Without the tool, at a terminal, it is:

```bash
aidd records add --type decision --by claude-code/claude-opus-5-5 --subject SPEC-4 --data '{"action": "git.push.force",
  "question": {"type": "yes_no", "text": "Force-push feat/refunds? It replaces 2 commits there."},
  "covers": {"command": "git push --force-with-lease origin feat/refunds", "head": "ab1d6f9"},
  "answer": {"outcome": "accept", "words": "yes, push it"}}'
```

- A `decision` holds the question as you showed it, word for word, and the person's reply as they wrote it. `question.type` is `yes_no`, `choice` (with `options` and the `picked` ids), or `text`. `outcome` is `accept`, `decline`, or `cancel`. Through the MCP tool, name who answered in `answer.by`; `aidd records add` fills it in from the git name.
- A `report` holds the `action`, what it `covers`, and what you `said`. Record a no too: the history shows what the person turned down.
- A record is your account, kept as history. It is never a yes and never evidence. Only a delegate's own answers change a delegation check. Never put a secret's value in one. aidd refuses the known shapes of keys, tokens, and passwords, but it cannot catch every secret, so name the secret instead, such as `the STRIPE_KEY variable`.
- A headless run that stops at an ask has no answer, so it records nothing. Its handoff note names the ask. `aidd records` lists the history, newest first, and `--type` or `--subject` narrows it. The files stay in `.git/aidd/records/`, outside the working tree, so no commit or PR carries them.
- `aidd records pull` adds the records the remote has and this clone lacks. `aidd records push` sends this clone's records to the remote's `refs/aidd/records`, where everyone who can read the repository reads them, for good: union merge never removes a record. So it is `records.push`, an `ask`. Never push them on your own, and never as part of publishing a branch.

## Change the rules

A person changes the rules in `.aidd/config.yaml` under `risks`. A config area or action with a built-in's id replaces it.

```yaml
risks:
  areas:
    billing: {paths: ["src/billing/**"], route: major}
  actions:
    cloud.resource.create: {description: Commands that create paid cloud resources, commands: ["terraform apply*"]}
  rules:
    - {action: code.edit, area: billing, level: ask}
    - {action: pr.open, level: allow}
```

`aidd risk --suggest` names the `ask` rules the person always said yes to, at least 10 times, for actions a person can undo, never their own decision points, such as Spec approval or a merge. Show it when they ask why you ask so often, never to get past an ask.

Then run `aidd risk --list` to see the effect, and `aidd upgrade --yes` to write the new `ask` commands into the harness's ask rules. `aidd doctor` checks both.
