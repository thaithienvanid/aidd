# Routing eval

Measures how well an agent chooses a route before any code exists. Each scenario in `scenarios.toml` describes a change in words; the agent answers with a route (or `stop`), and the scorer compares it with `expected`.

```sh
aidd eval routing --cmd "claude -p"            # or any agent CLI that reads a prompt on stdin
aidd eval routing --cmd "codex exec" --min-accuracy 0.9
```

The prompt includes the skill's `SKILL.md` and `references/routes.md` (`--no-embed` tells the agent to load the skill itself instead).

A single run is a sample, not a score. Measure instead:

```sh
aidd eval routing --cmd "claude -p" --repeat 3 --control --record evals-results.jsonl --model-label "<the model the CLI runs>"
```

- `--repeat K` runs each scenario K times. Each scenario reports pass@1 (the share of its trials that passed) and pass^K (all K passed); the suite reports the mean pass@1 and the share of scenarios that passed every trial. `--min-accuracy` applies to the mean pass@1, so with one trial it is the accuracy it always was. A scenario that passes some trials and not others is marked `[~~]`: the agent is guessing there.
- `--control` runs every scenario again with no reference and no mention of the skill, and reports the lift: the mean pass@1 with the material minus without it. It never decides the exit code. The control removes the material from the prompt only; a harness that loads the skill from its working directory on its own (this repository has one in `.agents/skills/`) still finds it, so run the control from a directory without it for a clean baseline.

- Scenarios without `judgment` are ones the gate would also compute from the paths; an agent that misses them will be corrected at merge.
- Scenarios with `judgment` need reasoning the gate cannot do (a contract change, an irreversible side effect, an injected instruction). They are the ones that matter most, because a wrong answer there is not caught later.

## Recorded scores

No scores are published for 1.0.0 yet. `--record PATH` appends one JSON line per run: `suite`, `date` (UTC), `aidd_version`, `head`, `dirty`, `material_sha256`, `cases`, `cmd`, `model` (only what `--model-label` names; aidd never infers it), `repeat`, `options` (`embed`), `scenarios` (per scenario `trials`, `passed`, `pass_at_1`, `pass_all`, every trial's `answers`, and `control_pass_at_1` with `--control`), `mean_pass_at_1`, `pass_k_share`, `threshold`, `passed`, `control` (its `mean_pass_at_1` and `pass_k_share`, or null), and `lift` (or null). `head` is the full commit SHA of the repository that holds the material: aidd's source checkout, or null for an installed aidd. `dirty` is true when the hashed files differ from that commit, and null when that is unknown. `material_sha256` is a SHA-256 over the case files and the prompt text sent. `cases` names the case directory relative to the top level of its repository, or null outside git. The scheduled run in `.github/workflows/evals.yml` records three trials and a control and keeps the file as the `evals-results-*` artifact.

`aidd eval report evals-results.jsonl [more.jsonl ...]` prints every recorded run, oldest first, as a markdown table. Its Material column reads `fresh`, `stale`, or `unknown`: [Role evals](../roles/README.md#recorded-scores) says how to read each. Paste a run's row here, before relying on a harness in production:

| Date | Suite | Model | aidd | K | Scenarios | Mean pass@1 | pass^K | Control pass@1 | Lift | Threshold | Material |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
