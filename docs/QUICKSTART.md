# Quickstart

Take one change through the whole loop on your own machine. You work alone, with no GitHub, no GitLab, and no CI. You set up a practice repository, write a Spec and its test, and approve the Spec. Then you build, prove red-then-green, and ship to `main`. It takes about 15 minutes. Working with a colleague who approves comes after, in [With a team](#with-a-team). Going live on a platform is in [Platforms](PLATFORMS.md#setup).

aidd is pre-release, so install it from a commit ([README](../README.md), [Install: before the first release](INSTALL.md#before-the-first-release)).

**You need:** Python 3.11+, git, and the `aidd` CLI ([Install](INSTALL.md#the-cli)). The commands below use the `sh` syntax of macOS and Linux.

You will meet two terms:

- **Spec approval** is your approval of a Spec before anything is built.
- **Merge approval** is your approval of the finished change before it lands on `main`.

## 1. Make a practice repository

A tiny Python app with one test, so the tutorial needs nothing but Python. Your git email is who you are to aidd on this machine:

```sh
mkdir aidd-practice && cd aidd-practice
git init -b main
git config user.email you@example.com
mkdir app tests && touch app/__init__.py tests/__init__.py
printf '__pycache__/\n' > .gitignore
printf 'def total(items):\n    return sum(items)\n' > app/cart.py
printf 'import unittest\nfrom app.cart import total\n\n\nclass Cart(unittest.TestCase):\n    def test_total(self):\n        self.assertEqual(total([1, 2]), 3)\n' > tests/test_cart.py
git add -A && git commit -m "scaffold"
```

## 2. Set up aidd

```sh
aidd init --profile solo --approvers email:you@example.com --ci none --test "python3 -m unittest" --harness claude-code
aidd doctor
git add -A && git commit -m "chore: adopt aidd"
```

`solo` is one person directing agents: you approve your own changes, on record. The Approver is the email your commits use, because aidd records a local approval as that email. `aidd doctor` warns when the two differ. `aidd init` writes:

- `.aidd/config.yaml`: who approves, which tests run, which paths are sensitive ([CONFIG.md](CONFIG.md))
- `specs/README.md`, `REVIEW.md` (the review policy), and the skill the agents read, in `.agents/skills/aidd/`. A section in `AGENTS.md` points every coding agent at the skill.
- the agent-specific wiring for every coding agent whose files are in the repository, or that you name with `--harness` ([INSTALL.md](INSTALL.md#your-coding-agent)). `--harness claude-code` wires Claude Code's guard hook and session hooks. Name your own agent instead. An agent with no hook wired gets the skill and `AGENTS.md` only. Nothing stops that agent at edit time; the gate is what catches its mistakes.

At your own terminal, `aidd init` asks the rest: whether to wire Claude Code too when this machine has it, and whether to commit the setup now. It commits only the files it wrote, never one you had changed. That commit, straight on `main`, is the Day-0 setup. It is the one change that lands without `aidd ship`, and you make it, not an agent. From here on, the agent hook keeps a wired agent (Claude Code here) off `main`. Every change goes through a branch, and `aidd ship` is the only way a change lands.

## 3. Route, then specify

A change's **route** is how much control it gets: `standard`, `minor`, `normal`, `major`, or `emergency`.

- `standard`: a pre-approved class of change that the config names in `standard_changes`, such as a bot's dependency bump.
- `minor`: no Spec.
- `normal`: a Spec and its tests.
- `major`: a Spec, approved, plus an `observe` block. From the team profile up, it also needs a specialist Approver.
- `emergency`: a production repair.

The **lane** follows from the route: minor takes the fast lane, and normal and major take the spec lane. aidd computes the minimum route from what a change touches. You may declare more, never less. The gate recomputes the minimum from the real diff.

Work on a branch, as an agent would, and plan the change:

```sh
git switch -c discount
aidd new spec SPEC-1 --title "Apply a percentage discount" --paths app/discount.py
```

It prints the minimum route for that path, `minor`, and writes nothing: a one-file change needs no Spec. A Spec is still worth it for a new feature, because you write its test before the code. So write one anyway:

```sh
aidd new spec SPEC-1 --title "Apply a percentage discount" --paths app/discount.py --force
```

It writes `specs/SPEC-1.md`: the short Spec, route `normal`, with your path as the first Task's scope. Open it. Replace each `TODO` in place:

| Where | Replace | With |
| --- | --- | --- |
| front matter | `assisted_by: []` | `assisted_by: ["claude-code/claude-opus-5-5"]`, the agent that writes the code or tests (keep `[]` when none does) |
| `risk` | `summary: "TODO: who or what behaves differently after this change"` | `summary: Cart totals can apply a discount.` |
| `tasks` | `title: "TODO: the first slice"` | `title: Add discount()` |
| `tests` | `files: ["tests/TODO"]` | `files: ["tests/test_discount.py"]` |
| `tests.commands` | `command: ["TODO"]` | `command: ["python3", "-m", "unittest", "tests.test_discount"]` |
| `## Intent` | `TODO: quote the request.` | `Checkout needs a percentage discount.` |
| `## Context` | `TODO: the context.` | `Totals are computed in app/; no discount exists yet.` |
| `## Acceptance` | `- A1: TODO: given ..., when ..., then ...` | `- A1: given a total of 200, when a 10% discount applies, then the total is 180` |
| `## Design` | `TODO: the approach.` | `One pure function, discount(total, percent), in app/discount.py.` |
| `## Rollback` | `TODO: how to undo it.` | `Revert the change; nothing is stored.` |

Then write the test, before any code exists. Then check the Spec:

```sh
printf 'import unittest\n\nfrom app.discount import discount\n\n\nclass Discount(unittest.TestCase):\n    def test_ten_percent(self):\n        self.assertEqual(discount(200, 10), 180)\n' > tests/test_discount.py
aidd validate specs/SPEC-1.md
git add -A && git commit -m "spec: SPEC-1 and its test" -m "Assisted-by: claude-code/claude-opus-5-5"
```

`aidd validate` must report `0 error(s), 0 warning(s)`. A warning names a `TODO` you missed. A major change gets the full Spec (`aidd new spec --full`) with a diagram. It also links a tech spec for the alternatives and the pre-mortem (`aidd new tech-spec <topic> --spec SPEC-1`). `aidd validate` warns when a major change lacks the diagram, the alternatives, or the pre-mortem.

## 4. Spec approval

Read the Spec and its test. Then run this in a terminal you opened yourself, never one an agent started:

```sh
aidd approve spec specs/SPEC-1.md
```

It shows the Spec's title, how many Acceptance items it has, and its hash. Answer `y` to record the approval. The hash covers the Spec and its test file. Under solo, a normal change does not need Spec approval. But once you record one, it binds:

- If the Spec or its test changes afterwards, the gate fails.
- The test must fail before the code and pass after it (red-then-green).

## 5. Implement ⟲ Verify

```sh
printf 'def discount(total, percent):\n    return total - total * percent // 100\n' > app/discount.py
git add -A && git commit -m "feat: add discount()" -m "Assisted-by: claude-code/claude-opus-5-5"
aidd test --base main
aidd gate --base main
```

`aidd test` runs every command on your head commit (green). It also runs the Spec's new-behavior command on `main` (red, because `app/discount.py` does not exist there). It writes the evidence to `.aidd/evidence/`. `aidd gate` then reports **pending** on one thing only: your Merge approval.

## 6. Ship

```sh
aidd ship
```

It does these steps:

1. It checks the change's declaration.
2. It runs the tests again on exactly what will land.
3. It shows the gate's report and the diffstat.
4. It asks you to confirm (`[y/N]`). Your `y` records your Merge approval and merges the branch into `main`.

`aidd ship --squash` makes one commit that keeps every agent's `Assisted-by` trailer.

A minor change skips the Spec:

1. The agent implements.
2. The agent runs `aidd describe --commit`. It records the change's block in a new commit, so the head moves.
3. The agent runs `aidd test` on that head.
4. You run `aidd ship`.

How a founder works like this every day: [A solo day](ADOPTION.md#a-solo-day).

## With a team

With a colleague who approves, the profile is `team`, where an Approver must be someone other than the author. Make a second practice repository as in step 1. Set it up with this command:

```sh
aidd init --profile team --approvers alice --test "python3 -m unittest" --ci none
```

Commit it. Then take the same change through steps 3 and 5, and skip step 4. On a platform, the approvals come from the PR/MR. To see the gate decide without a platform, give it a dry-run file that stands in for the platform. In that file, `alice` posts the Spec approval line and approves your head commit. Write the file outside the repository: it is a dry run, never part of the change.

```sh
cat > ../approvals.json <<EOF
{"comments": [{"user": "alice", "body": "$(aidd hash specs/SPEC-1.md --line --ref HEAD~1)"}],
 "reviews": [{"user": "alice", "state": "approved", "commit_sha": "$(git rev-parse HEAD)"}]}
EOF
aidd gate --base main --approvals ../approvals.json
```

`--ref HEAD~1` hashes the commit before the implementation: the Spec-and-test commit. So the line names the commit Alice saw, which proves Spec approval came before any code. The gate reports **pass**, marked untrusted: a local run proves the branch is ready, not that it may merge. The file only simulates the platform. Nobody approved anything. The gate also warns `authors`. Your commits carry only an email, and no platform account links that email here. An unlinked author might be an Approver in disguise. On a platform, link the email to your account, or list agent emails in `identities.bots`. Then the warning goes away ([Troubleshooting](TROUBLESHOOTING.md#the-gate-warns-that-a-commit-author-is-unlinked)).

On a real repository, the same change runs as a PR/MR:

1. The agent opens a draft holding the Spec and its test.
2. An Approver posts the `/aidd approve-spec` line.
3. The agent pushes the implementation, and `aidd-tests` proves red-then-green in CI.
4. An Approver approves the head, and `aidd/gate` turns green.
5. The PR/MR merges.

Setting that up takes about an hour and admin rights on the repository: [GitHub](PLATFORMS.md#setup) or [GitLab](PLATFORMS.md#setup-on-gitlab). Until every piece is in place, the gate reports without blocking ([what holds without them](PLATFORMS.md#what-holds-without-the-full-setup)). The pieces are enforce mode, a required check, the gate's App, and a plan that allows the rule.

## Next

- Something did not work as written: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Profiles, local-first, and rollout plans: [ADOPTION.md](ADOPTION.md)
- Every command and flag: [CLI.md](CLI.md)
- Every config key: [CONFIG.md](CONFIG.md)
- Every rule the gate applies: `aidd gate --explain <rule>` and [METHOD.md §7](METHOD.md#7-evidence-and-the-gate)
- Worked cases: [examples](../examples/README.md)
