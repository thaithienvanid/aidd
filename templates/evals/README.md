# Evals for your agent configuration

Your agent configuration (`AGENTS.md`, `CLAUDE.md`, skills, subagents, hooks, the MCP servers you wire) is code that decides how every agent in this repository behaves. Change it the way you change code: with tests. These are those tests: real tasks, each graded by commands that must pass.

## Start

```sh
mkdir -p evals && cp -R "$(python3 -c 'from aidd.kernel import resources; print(resources.data_dir("templates") / "evals" / "tasks")')" evals/tasks
aidd eval tasks --agent-command "claude -p --permission-mode acceptEdits"   # or any agent CLI that reads a prompt on stdin and may edit files
aidd eval tasks --agent-command "codex exec --full-auto" --min-accuracy 0.9
aidd eval tasks --agent-command "claude -p --permission-mode acceptEdits" --repeat 3 --record evals/runs.jsonl --model-label "sonnet-5"
aidd eval report evals/runs.jsonl   # every recorded run as one table
```

Each task runs in a fresh scratch worktree of the repository (HEAD plus your uncommitted changes to tracked files), so the agent never edits your checkout. The worktree is removed afterwards. The command exits non-zero when the share of passing tasks is below `--min-accuracy` (default 0.9), which makes it a merge check. Agents are not deterministic, so measure with `--repeat K`. Each task reports pass@1 (the share of its trials that passed) and pass^K (all K passed). `--min-accuracy` then applies to the mean pass@1. `--record` appends one JSON line per run, so a model or instruction change can be compared with the runs before it. For tasks, `material_sha256` covers the task files only. The agent configuration measured is your repository itself. `head` names its commit, and `dirty` is true when the run included uncommitted changes. `aidd eval report` marks a run `stale` when a task file changed after it.

## A task

A task is one `scenario` in any `evals/tasks/*.yaml` file; `tasks/examples.yaml` documents every field. Grade with `checks` wherever you can: an exit code is evidence, a phrase in the answer is not. `expected` (words the answer must or must not contain) is for tasks where the right outcome is to stop and say something, such as refusing to approve.

Good checks are the ones a reviewer would run:

- the project's tests for the area
- a linter
- `git diff --quiet` when the agent must not have edited anything
- `grep` for a line the agent must not have weakened

## Every incident becomes an eval

When an agent gets something wrong in this repository, add the task that exposed it, the same day. Such a mistake can be a PR that edited a test to pass, a change outside its scope, or a skipped step. It can also be a review comment that had to say the same thing twice. To add the task:

1. Write the prompt the way the agent was asked, and name the incident, PR, or comment in `source`.
2. Reproduce the starting state in `setup` if HEAD no longer has it (a fixture file, a failing test).
3. Write the checks that fail on what the agent did and pass on the right fix. Run the eval once to see it fail on the current configuration, if it still does.
4. Change the configuration (the instruction, the skill, the hook) until it passes, and commit the task with the change. It stays: the task is a permanent regression test for your agents.

Aim for 20 to 50 real tasks. Fewer lets a configuration change pass by luck. Many more makes the suite too slow to run on every change to what the agents read. Prefer tasks from real work over invented ones, and retire a task only when the thing it tests no longer exists.

## Run it on every change to what the agents read

Run the suite in CI on pull requests that touch the agent configuration (`AGENTS.md`, `CLAUDE.md`, `.claude/**`, `.agents/**`, `evals/**`). Give the job the model's API key as a secret that a fork's pull request cannot read. Make the job a required check. Record the pass rate per model when you change models: a smaller model that still passes is a cheaper one.
