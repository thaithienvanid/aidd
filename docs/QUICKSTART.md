# Quickstart

Take one change through the whole loop on your own machine, with no GitHub App and no CI: set up a practice repository, write a Spec and its test, get the approval hash, build, prove red-then-green, and watch the gate go from pending to pass. It takes about 15 minutes. Going live on GitHub comes after, in [Platforms](PLATFORMS.md#setup).

aidd is pre-release, so install it from a commit ([README](../README.md), [Install: before the first release](INSTALL.md#before-the-first-release)).

**You need:** Python 3.11+, git, and the `aidd` CLI ([Install](INSTALL.md#the-cli)). The commands below use the `sh` syntax of macOS and Linux.

Two terms you will meet: **Spec approval** is the human approval of a Spec before anything is built; **Merge approval** is the human approval of the finished change before it merges.

## 1. Make a practice repository

A tiny Python app with one test, so the tutorial needs nothing but Python:

```sh
mkdir aidd-practice && cd aidd-practice
git init -b main
mkdir app tests && touch app/__init__.py tests/__init__.py
printf '__pycache__/\n' > .gitignore
printf 'def total(items):\n    return sum(items)\n' > app/cart.py
printf 'import unittest\nfrom app.cart import total\n\n\nclass Cart(unittest.TestCase):\n    def test_total(self):\n        self.assertEqual(total([1, 2]), 3)\n' > tests/test_cart.py
git add -A && git commit -m "scaffold"
```

## 2. Set up aidd

```sh
aidd init --profile team --approvers alice --test "python3 -m unittest"
aidd doctor
git add -A && git commit -m "chore: adopt aidd"
```

`alice` stands for the colleague who approves your changes; in this tutorial you play her part with a file. Every profile but `solo` needs `--approvers`: with no approver, no change can merge. `aidd init` writes:

- `.aidd/config.toml`: who approves, which tests run, which paths are sensitive ([CONFIG.md](CONFIG.md))
- `specs/README.md`: where Specs live
- `REVIEW.md`: the review policy every reviewer, human or agent, follows
- the skill your agents read, vendored in `.agents/skills/aidd/`, and a section in `AGENTS.md` that points every coding agent at it
- the CI workflows and a PR template, which stay idle until you go live
- the agent-specific wiring for every coding agent whose files are in the repository, or that you name with `--harness`, such as `--harness claude-code` ([INSTALL.md](INSTALL.md#your-coding-agent))

`aidd doctor` may warn, for example that a major change will need a `security` reviewer pool; nothing it warns about blocks this tutorial, and it must report no failure. Committing the setup straight to `main` is how a new repository starts ([Day 0](ADOPTION.md#new-or-existing-repository)).

## 3. Route, then specify

A change's **route** is how much control it gets: `minor` (no Spec), `normal` (a Spec and its tests, approved before any code), `major` (a normal route plus a specialist reviewer), or `emergency`. The route picks the **lane**, the path through the loop: minor takes the fast lane, normal and major the spec lane.

- aidd computes the minimum route from the paths the change touches, its type, and its risk. Computing it is the loop's entry rule, not a step.
- `aidd next` shows it for the branch you are on, and before any code exists `aidd new spec --paths` computes it from the paths you plan to touch.
- The gate recomputes it from the real diff and can only raise it.

Work on a branch, as your agent would, and plan the change:

```sh
git switch -c discount
aidd new spec SPEC-1 --title "Apply a percentage discount" --owner-team shop --paths app/discount.py
```

It prints the minimum route for that path, `minor` on the fast lane, and why, and writes nothing: a one-file change needs no Spec. A Spec is still worth it here, because it is what Spec approval approves, and the gate never lets a change go below its minimum, only above it. So write one anyway:

```sh
aidd new spec SPEC-1 --title "Apply a percentage discount" --owner-team shop --paths app/discount.py --force
```

It writes `specs/SPEC-1.md`: the short Spec, with route `normal` and your path as the first Task's scope. This change is small enough for the fast lane; the tutorial writes a Spec anyway so you see both approvals. The gate will print `route normal (required minor)`: normal is what your Spec declares, minor the minimum it computed. Declaring more than the minimum is allowed; less never is. Open it and replace each `TODO`, in place:

| Where | Replace | With |
| --- | --- | --- |
| front matter | `assisted_by = []` | `assisted_by = ["claude-code/claude-opus-5-5"]`, the agent that writes the code or tests (keep `[]` when none does) |
| `[risk]` | `summary = "TODO: who or what behaves differently after this change"` | `summary = "Cart totals can apply a discount."` |
| `[[tasks]]` | `title = "TODO: the first slice"` | `title = "Add discount()"` |
| `[tests]` | `files = ["tests/TODO"]` | `files = ["tests/test_discount.py"]` |
| `[[tests.commands]]` | `command = ["TODO"]` | `command = ["python3", "-m", "unittest", "tests.test_discount"]` |
| `## Intent` | `TODO: quote the request.` | `Checkout needs a percentage discount.` |
| `## Acceptance` | `- A1: TODO: given ..., when ..., then ...` | `- A1: given a total of 200, when a 10% discount applies, then the total is 180` |
| `## Design` | `TODO: the approach.` | `One pure function, discount(total, percent), in app/discount.py.` |
| `## Rollback` | `TODO: how to undo it.` | `Revert the change; nothing is stored.` |

Then write the test, before any code exists, and check the Spec:

```sh
printf 'import unittest\n\nfrom app.discount import discount\n\n\nclass Discount(unittest.TestCase):\n    def test_ten_percent(self):\n        self.assertEqual(discount(200, 10), 180)\n' > tests/test_discount.py
aidd validate specs/SPEC-1.md
git add -A && git commit -m "spec: SPEC-1 and its test" -m "Assisted-by: claude-code/claude-opus-5-5"
```

`aidd validate` must report `0 error(s), 0 warning(s)`. A warning names a `TODO` you missed; a major change gets the full Spec (`aidd new spec --full`), with Alternatives, a Pre-mortem, and a diagram, and the warnings that ask for them.

## 4. Spec approval: the approval hash

```sh
aidd hash specs/SPEC-1.md --comment
```

It prints the line an Approver posts on the PR/MR: `/aidd approve-spec SPEC-1 <hash> <commit>`. The hash covers the Spec and its test file, so changing either afterwards voids the approval; the commit at the end proves the approval came before any implementation. Keep the line for step 6.

## 5. Implement ⟲ Verify: prove red-then-green

```sh
printf 'def discount(total, percent):\n    return total - total * percent // 100\n' > app/discount.py
git add -A && git commit -m "feat: add discount()" -m "Assisted-by: claude-code/claude-opus-5-5"
aidd test --base main
```

`aidd test` runs every command on your head commit (green) and the Spec's new-behavior command on `main` (red, because `app/discount.py` does not exist there), and writes the evidence to `aidd-evidence/`. That is Verify on this head: the evidence names the head SHA it ran on, so a new commit needs a new run.

## 6. Run the gate

```sh
aidd gate --base main
```

It reports **pending**: the tests passed, but nobody has approved the Spec or the head commit. On a PR/MR those approvals come from the platform. Here, give the gate a dry-run file that stands in for the platform, in which `alice` posts the line from step 4 and approves your head commit. Write it outside the repository: it is a dry run, never part of the change.

```sh
cat > ../approvals.json <<EOF
{"comments": [{"user": "alice", "body": "$(aidd hash specs/SPEC-1.md --comment --ref HEAD~1)"}],
 "reviews": [{"user": "alice", "state": "approved", "commit_sha": "$(git rev-parse HEAD)"}]}
EOF
aidd gate --base main --approvals ../approvals.json
```

`--ref HEAD~1` hashes the commit before the implementation, the Spec-and-test commit from step 3, so the line is the one step 4 printed: a Spec approval names the commit it saw, which proves it came before any code. The review approves `HEAD`, the implementation.

The gate reports **pass**, with warnings a local run always shows (your commit email is not linked to a platform account). A local run is always marked untrusted: it proves your branch is ready, not that it may merge. Only the CI gate, reading real approvals from the platform, decides that. Every rule it applied, and how to satisfy each: `aidd gate --explain <rule>` and [METHOD.md §7](METHOD.md#7-evidence-and-the-verifier).

The approvals file only simulates a platform's comments and reviews; nobody approved anything. If you work alone with no platform, you approve for real on this machine: set up for [local-first](ADOPTION.md#local-first-no-github-or-gitlab), then run `aidd approve spec specs/SPEC-1.md` before the implementation and `aidd approve merge` on the finished head, at your own terminal, and merge with `aidd ship`.

## Going live

On a real repository the same change runs as a PR/MR:

1. The agent commits the Spec and its test and opens a **draft** PR/MR whose `toml aidd` block names the Spec. Both checks stay **pending** for now: the new test cannot pass before the code exists, and the gate waits for the Spec approval.
2. An Approver (someone in `owners.approvers` who did not author the change) posts the `/aidd approve-spec` line as a comment.
3. The agent pushes the implementation to the same PR/MR, `aidd-tests` proves red-then-green in CI, and the PR/MR is marked ready.
4. An Approver approves the PR/MR on its head commit, `aidd/gate` turns green, and you merge.

A minor change is shorter: a short `toml aidd` block (`aidd change` prints it) and one approval. Under `solo`, you approve your own change with `/aidd approve <full head SHA>`; Spec approval is needed on major changes only, and they wait out a 30-minute cool-off first ([METHOD.md §8](METHOD.md#solo)).

To get there, set up the gate on your platform, which takes about an hour and admin rights on the repository: [GitHub](PLATFORMS.md#setup) or [GitLab](PLATFORMS.md#setup-on-gitlab).

## Next

- Profiles and rollout plans: [ADOPTION.md](ADOPTION.md)
- Every command and flag: [CLI.md](CLI.md)
- Every config key: [CONFIG.md](CONFIG.md)
- Worked cases: [examples](../examples/README.md)
