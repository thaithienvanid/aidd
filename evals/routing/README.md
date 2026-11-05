# Routing eval

Measures how well an agent chooses a route before any code exists. Each scenario in `scenarios.yaml` describes a change in words; the agent answers with a route (or `stop`), and the scorer compares it with `expected`.

```sh
aidd eval routing --agent-command "claude -p"            # or any agent CLI that reads a prompt on stdin
aidd eval routing --agent-command "codex exec" --min-accuracy 0.9
```

The prompt includes the skill's `SKILL.md` and `references/routes.md`. With `--no-embed`, it carries one line instead, which names the skill and its two files and asks the agent to load them. It names them because a non-interactive run may not load a skill on its own. So `--no-embed` measures the skill as the agent finds it. That needs the skill where the harness looks: `.agents/skills/` for Codex, or the aidd plugin for Claude Code. A harness that never loads it answers as the bare model, and nothing in the score says so. The record's material hash leaves the skill's files out, because the harness may load another copy, so note which copy it loaded.

A single run is a sample, not a score. Measure instead:

```sh
aidd eval routing --agent-command "claude -p" --repeat 3 --without-aidd --record evals-results.jsonl --model-label "<the model the CLI runs>"
```

- `--repeat K` runs each scenario K times. Each scenario reports pass@1 (the share of its trials that passed) and pass^K (all K passed); the suite reports the mean pass@1 and the share of scenarios that passed every trial. `--min-accuracy` applies to the mean pass@1, so with one trial it is the accuracy it always was. A scenario that passes some trials and not others is marked `[~~]`: the agent is guessing there.
- `--min-pass-k SHARE` (0 to 1, off by default; needs `--repeat 2` or more) also fails the run when the share of scenarios that passed every trial is below SHARE, even when the mean passes. A mean pass@1 of 88.9% can hide a pass^3 of 66.7%. The output prints the pass^K share and names each scenario that failed a trial.
- About one scenario in five is held out. The id and a fixed seed pick it (`HELD_OUT_SEED` in `src/aidd/evals/suites.py`), so adding a scenario never moves another. A run prints the score on the development scenarios and on the held-out ones, and the record holds both in `sets`. Tune prompts and scenarios against the development score, and read the held-out score to see whether the tuning generalized. Changing the seed moves the set, so do it once, on purpose.
  The held-out ids are pinned in `tests/test_eval_held_out.py`, so a renamed id cannot move a case without a failing test. A case changed after its held-out score was read moves to development. Its id goes into `MOVED_TO_DEVELOPMENT` in `src/aidd/evals/suites.py`, in the change that edits it. Then write a new case for the held-out set, blind: from a coverage cell that has no case, once, with its samples, and never tuned against a run.
- `--case ID` runs only the scenario with that id. Repeat it for more, so a rerun of the scenarios that failed needs no scratch folder. An id that no scenario has stops the run before the agent starts, and the record's `options` names the ids you picked.
- An agent command that emits `stream-json` (`claude -p --output-format stream-json --verbose`) is scored on the final answer in its `result` event, and its usage is recorded. The run prints the cost: the dollars over every trial, failed ones too, and the dollars per passing trial. The record holds each scenario's `usages`, one per trial, and the run's `cost`. A trial that reports no cost leaves the cost blank, so a missing cost never reads as free. Plain text output records none.
- `--without-aidd` runs every scenario again with no reference and no mention of the skill, and reports the lift: the mean pass@1 with the material minus without it. It never decides the exit code. The control removes the material from the prompt.

Every trial runs in a new, empty folder, so an agent with file tools cannot read this checkout's expected answers or its `.agents/skills/` copy of the skill. `--no-embed` puts only the skill into that folder, under `.agents/skills/aidd/`, where Codex looks. Some leaks remain, because aidd starts your agent command with your own settings. An installed aidd plugin still loads the skill, even in the control. An agent that reads an absolute path to this checkout, or searches the disk for `scenarios.yaml`, still finds the answers. Run the evals from an account or a machine that holds no other copy of the cases, with installed plugins kept out, as the [role evals](../roles/README.md) say.

- Scenarios without `judgment` are ones `aidd risk --paths` computes from the areas the paths hit. The size rule in `references/routes.md` also counts: a minor change past about 50 changed lines is normal. Each names `paths` and `lines`, and a test holds the label to the computed route. An agent that misses them gets the route from the command.
- Scenarios with `judgment` need reasoning no path rule has (a contract change, an irreversible side effect, an injected instruction). They matter most, because nothing corrects a wrong answer there. A test holds a judgment label that has `paths` at or above the computed route, never below it.
- A scenario lists in `accept` each route the reference admits when it admits more than one, such as `normal` or the stricter `major`. A stricter route in `accept` passes and a looser one fails.
- A scenario named for what the reason says, such as presenting two readings or naming the simpler change, also holds `reason_any` words the reason must contain.

An answer is the route object in the reply. Two route objects that name different routes are a hedge, and they fail. A route outside `minor`, `normal`, `major`, `emergency`, and `stop` is an invalid answer. A `{id}` in the reason does not hide the route, and the case of the route does not matter.

## Recorded scores

No scores are published for 1.0.0 yet. `--record PATH` appends one JSON line per run. It names the run: `suite`, `date` (UTC), `aidd_version`, `head`, `dirty`, `material_sha256`, `cases`, `cmd`, `model` (only what `--model-label` names; aidd never infers it), `repeat`, and `options` (`embed`, and `case` when `--case` picked scenarios). It holds the results: `scenarios` (per scenario `trials`, `passed`, `pass_at_1`, `pass_all`, every trial's `answers`, and `control_pass_at_1` with `--without-aidd`), `mean_pass_at_1`, `pass_k_share`, `threshold`, `min_pass_k` (null unless `--min-pass-k` was given), and `passed` (false when the mean or a given `--min-pass-k` share is missed). It ends with `control` (its `mean_pass_at_1` and `pass_k_share`, or null) and `lift` (or null). `head` is the full commit SHA of the repository that holds the material: aidd's source checkout, or null for an installed aidd. `dirty` is true when the hashed files differ from that commit, and null when that is unknown. `material_sha256` is a SHA-256 over the case files and the prompt text sent. `cases` names the case directory relative to the top level of its repository, or null outside git. A manual run of `.github/workflows/evals.yml` records three trials and a control and keeps the file as the `evals-results-*` artifact.

`aidd eval compare a.jsonl b.jsonl` compares two recorded variants, as [Role evals](../roles/README.md#recorded-scores) says.

`aidd eval report evals-results.jsonl [more.jsonl ...]` prints every recorded run, oldest first, as a markdown table. Its Material column reads `fresh`, `stale`, or `unknown`: [Role evals](../roles/README.md#recorded-scores) says how to read each. Paste a run's row here, before relying on a harness in production:

| Date | Suite | Model | aidd | K | Scenarios | Mean pass@1 | pass^K | Control pass@1 | Lift | $ per pass | Threshold | Material |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
