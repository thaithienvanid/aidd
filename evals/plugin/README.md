# Plugin evals

The aidd plugin's suite for `claude plugin eval`, in Claude Code's own case format: each directory is a case with a `prompt.md` and its `graders/`. The plugin's manifest points `experimental.evals` here, because `evals/` itself holds aidd's routing and role scenarios, which `aidd eval` runs.

```bash
claude plugin eval . --scaffold --allow-tools Bash Write Edit          # every case, with and without the plugin (the no-plugin baseline)
claude plugin eval . --runs 1 --ablation none --scaffold --allow-tools Bash Write Edit   # a cheap check while you edit a case
```

Some cases seed their workspace: a `case.yaml` names a `fixture.sh` that writes the files the prompt talks about. These are the buggy module, the slow page over a query-counting stand-in for the ORM, and a stand-in `./bin/gh` that only logs. Claude Code runs a scaffold only with `--scaffold`, and grants Bash, Write, and Edit only through `--allow-tools`. Without them, those cases run on an empty workspace with read-only tools, and their order graders fail. The fixtures are ours and write only inside the case's workspace.

The cases check what the plugin must change about an agent's behavior. A behavior change gets a Spec and stops for Spec approval before any code. Write and Edit are allowed, and the case fails on any source file written. The agent never approves or merges for anyone, and an unrelated request leaves the skill alone. The aidd-team plugin keeps its own suite in `plugins/aidd-team/evals/`. Run it from the repository root, `claude plugin eval . --eval-dir plugins/aidd-team/evals`: its cases load the aidd plugin too, and an eval loads only the plugins inside the directory it runs against. Results go to `results/`, which git ignores.

The graders check the steps as well as the reply. `tool_used` checks a tool that must or must not run. `never-approves` gives the agent a shell and the stand-in GitHub CLI, and fails any approve or merge command it runs, in both arms. `tool_order` checks "X before Y": `debugging-reproduces-first` runs a test before it edits `pricing.py`, and `performance-measures-first` measures before it edits `orders.py`. `incident-mitigates-first` has no order grader on purpose. Its right answer may never open the tax code, and a `tool_order` grader fails when its second tool is never called. A no-edit grader and the rubric carry it instead. `role-loads-its-practice-skill` checks that a role subagent loads its Task's practice skill. The docs do not say whether a grader sees tool calls made inside a subagent, so read that grader, a `Skill` indicator, with care. No with-and-without-plugin score delta is claimed here until a run records one.
