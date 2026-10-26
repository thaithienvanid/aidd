# Quickstart

In about 15 minutes, you'll take one change through the whole loop on your own machine. You work alone, with no GitHub, no GitLab, and no CI. You set up a practice repository, write a Spec and its test, and approve the Spec. Then you build it, prove it red-then-green, and land it on `main`. When you're ready for a colleague who approves, read [With a team](#with-a-team). Going live on a platform is in [Platforms](PLATFORMS.md#setup).

aidd is [pre-release](ENTERPRISE.md#1-release-status-and-maturity), so [install it from a commit](INSTALL.md#before-the-first-release).

You need Python 3.11+, git, and the [`aidd` CLI](INSTALL.md#the-cli). The commands below use the `sh` syntax of macOS and Linux.

You will meet two terms:

- **Spec approval** is your approval of a Spec before anything is built.
- **Merge approval** is your approval of the finished change before it lands on `main`.

## 1. Make a practice repository

Start with a tiny Python app and one test, so the tutorial needs nothing but Python. On this machine, aidd knows you by your git email.

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

The `solo` profile is for one person directing agents, so you approve your own changes, on record. The Approver is the email your commits use, because aidd records a local approval as that email. `aidd doctor` warns when the two differ. `aidd init` writes these files:

- `.aidd/config.yaml`, which says who approves, which tests run, and which paths are sensitive. [CONFIG.md](CONFIG.md) has every key.
- `specs/README.md`, the review policy in `REVIEW.md`, and the skill the agents read, in `.agents/skills/aidd/`. A section in `AGENTS.md` points every coding agent at the skill.
- The wiring for each coding agent whose files are in the repository, or that you name with `--harness`. `--harness claude-code` wires Claude Code's guard hook and session hooks, so name your own agent instead. An agent with no hook wired gets only the skill and `AGENTS.md`. Nothing stops it at edit time, so the gate is what catches its mistakes. [INSTALL.md](INSTALL.md#your-coding-agent) lists every agent.

At your own terminal, `aidd init` asks two more things. It asks whether to wire Claude Code too, when this machine has it, and whether to commit the setup now. It commits only the files it wrote, never one you had changed. That commit lands straight on `main` as the Day-0 setup. It's the one change that lands without `aidd land`, and you make it, not an agent. From here on, the agent hook keeps a wired agent off `main`. Every change goes through a branch, and `aidd land` is the only way a change lands.

## 3. Route, then specify

A change's **route** is how much control it gets, from `standard` and `minor` through `normal` and `major` to `emergency`.

- A `standard` change is a pre-approved class that the config names in `standard_changes`, such as a bot's dependency bump.
- A `minor` change needs no Spec.
- A `normal` change needs a Spec and its tests.
- A `major` change needs an approved Spec and an `observe` block. From the team profile up, it also needs a specialist Approver.
- An `emergency` change is a production repair.

The **lane** follows from the route. A minor change takes the fast lane, and a normal or major one takes the spec lane. aidd computes the minimum route from what a change touches. You may declare more, never less, and the gate recomputes the minimum from the real diff.

Work on a branch, as an agent would, and plan the change.

```sh
git switch -c discount
aidd new spec SPEC-1 --title "Apply a percentage discount" --paths app/discount.py
```

It prints `minor`, the minimum route for that path, and writes nothing, because a one-file change needs no Spec. A Spec is still worth it for a new feature, because you write its test before the code. So write one anyway.

```sh
aidd new spec SPEC-1 --title "Apply a percentage discount" --paths app/discount.py --force
```

It writes the short Spec to `specs/SPEC-1.md`, with route `normal` and your path as the first Task's scope. Open it, and replace each `TODO` in place.

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

`aidd validate` must report `0 error(s), 0 warning(s)`. A warning names a `TODO` you missed. A major change gets the full Spec with a diagram, from `aidd new spec --full`. It also links a tech spec for the alternatives and the pre-mortem, which `aidd new tech-spec <topic> --spec SPEC-1` starts. `aidd validate` warns when a major change lacks the diagram, the alternatives, or the pre-mortem.

## 4. Spec approval

Read the Spec and its test. Then type this at your coding agent's prompt:

```text
approve SPEC-1
```

aidd records it from your own words, before the agent reads the prompt. Without an agent, run `aidd approve spec specs/SPEC-1.md` in a terminal you opened yourself. It shows the Spec's title, how many Acceptance items it has, and the commit you approve, then asks you to answer `y`. The approval covers the Spec and its test file as they read at that commit. Under solo, a normal change doesn't need Spec approval. But once you record one, it binds in two ways:

- If the Spec or its test changes afterwards, the gate fails.
- The test must fail before the code and pass after it. That's red-then-green.

## 5. Implement ⟲ Verify

```sh
printf 'def discount(total, percent):\n    return total - total * percent // 100\n' > app/discount.py
git add -A && git commit -m "feat: add discount()" -m "Assisted-by: claude-code/claude-opus-5-5"
aidd test --base main
aidd gate --base main
```

`aidd test` runs every command on your head commit, where they pass. It also runs the Spec's new-behavior command on `main`, where it fails because `app/discount.py` doesn't exist yet. It writes the evidence to `.aidd/evidence/`. `aidd gate` then reports **pending** on one thing only, your Merge approval.

With agents, this is where the team verifies and reviews. Once the tests pass on a head, the verifier and the reviewer check that commit side by side. A failure in either goes back to Implement. When the gate reports a finding, `aidd gate --explain <code>` says what it means and how to fix it.

## 6. Land

```sh
aidd land
```

It does these steps:

1. It checks the change's declaration.
2. It runs the tests again on exactly what will land.
3. It shows the gate's report and the diffstat.
4. It asks you to confirm with `[y/N]`. Your `y` records your Merge approval and merges the branch into `main`.

At your agent's prompt, `land it` does the same. `aidd land --squash` makes one commit that keeps every agent's `Assisted-by` trailer. The change is now on your local trunk, and nothing has left your machine. When it should, type `publish` at the prompt, or run `aidd publish` once the repository has a remote.

A minor change skips the Spec, and needs no Change Request block, because the gate takes its route from the diff:

1. The agent implements.
2. The agent runs `aidd test`.
3. You run `aidd land`.

To see how a founder works like this every day, read [A solo day](ADOPTION.md#a-solo-day).

## With a team

With a colleague who approves, the profile is `team`, where an Approver must be someone other than the author. Make a second practice repository as in step 1. Set it up with this command:

```sh
aidd init --profile team --approvers alice --test "python3 -m unittest" --ci none
```

Commit it. Then take the same change through steps 3 and 5, and skip step 4. On a platform, the approvals come from the PR/MR. To see the gate decide without a platform, give it a dry-run file that stands in for the platform. In that file, `alice` posts the Spec approval line and approves your head commit. Write the file outside the repository, because it's a dry run and never part of the change.

```sh
cat > ../approvals.json <<EOF
{"comments": [{"user": "alice", "body": "/aidd approve-spec SPEC-1 $(git rev-parse HEAD~1)"}],
 "reviews": [{"user": "alice", "state": "approved", "commit_sha": "$(git rev-parse HEAD)"}]}
EOF
aidd gate --base main --approvals ../approvals.json
```

`--ref HEAD~1` hashes the commit before the implementation, which is the Spec-and-test commit. So the line names the commit Alice saw, and that proves Spec approval came before any code. The gate reports **pass**, marked untrusted, because a local run proves the branch is ready, not that it may merge. The file only simulates the platform, and nobody approved anything. The gate also warns `authors`. Your commits carry only an email, and no platform account links that email here. An unlinked author might be an Approver in disguise. On a platform, link the email to your account, or list agent emails in `identities.bots`, and the warning goes away. [Troubleshooting](TROUBLESHOOTING.md#the-gate-warns-that-a-commit-author-is-unlinked) has the details.

On a real repository, the same change runs as a PR/MR:

1. The agent opens a draft holding the Spec and its test.
2. An Approver posts the `/aidd approve-spec` line.
3. The agent pushes the implementation, and `aidd-tests` proves red-then-green in CI.
4. An Approver approves the head, and `aidd/gate` turns green.
5. The PR/MR merges.

Setting that up takes about an hour and admin rights on the repository, on [GitHub](PLATFORMS.md#setup) or [GitLab](PLATFORMS.md#setup-on-gitlab). The pieces are enforce mode, a required check, the gate's App, and a plan that allows the rule. Until every piece is in place, the gate reports without blocking, and [Platforms](PLATFORMS.md#what-holds-without-the-full-setup) says what holds meanwhile.

## Next

- If something didn't work as written, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
- For profiles, local-first, and rollout plans, read [ADOPTION.md](ADOPTION.md).
- [CLI.md](CLI.md) has every command and flag, and [CONFIG.md](CONFIG.md) every config key.
- `aidd gate --explain <rule>` explains any rule the gate applies, and [METHOD.md §7](METHOD.md#7-evidence-and-the-gate) has them all. [ERRORS.md](ERRORS.md) lists every finding code with its fix.
- The [examples](../examples/README.md) are worked cases.
