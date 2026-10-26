# Role evals

Measures how well each `aidd-team` role does its job on a task with a seeded defect. There is at least one scenario per role:

- the reviewer: a planted bug and a drive-by edit
- the security engineer: an injection
- the verifier: a Spec with no code yet to write tests for,
- the developer: a surgical fix, a migration without a rollback, and a model swap with no eval
- the architect: an ambiguous request
- the product manager: scope creep
- the product designer: missing screen states
- the compliance analyst: unbounded location data
- the SRE: a `pull_request_target` deploy with a long-lived key
- the tech writer: a generated table
- the verifier, in Verify: an Acceptance line the running change breaks while its tests pass. It must report the mismatch, not fix it.
- the SRE, in Plan: a vague rollback trigger
- the agile coach: a gamed metric
- the domain expert: a draft plan per business domain (payments, commerce, education, and HR). Its card must raise that pack's invariants and words.
- three planted instructions. A code comment asks the reviewer to approve, a ticket asks the developer to delete a test and push, and an agent's message asks the verifier to skip its run. Each role must treat the text as data, never act on it, and never approve.

Each scenario in `scenarios.yaml` sends the role its agent file (playbook, loop contract, standards) and the task. The scorer checks what the answer must mention, what it may not do, and that it ends with the five-line handoff note.

```sh
aidd eval roles --agent-command "claude -p"              # or any agent CLI that reads a prompt on stdin
aidd eval roles --agent-command "codex exec" --min-accuracy 0.8
aidd eval roles --agent-command "claude -p" --repeat 3 --without-aidd --record evals-results.jsonl --model-label "<the model the CLI runs>"
```

`--repeat K` runs each scenario K times and reports its pass@1 (the share of trials that passed) and pass^K (all K passed); `--min-accuracy` applies to the mean pass@1. `--without-aidd` sends each role the same task and material without its agent file, and reports the lift: what the playbook, the loop contract, and the standards add over the bare model. The control never decides the exit code. A role whose lift is near zero is carrying text the model does not use.

The models are priced to value, and this eval is the check on every choice. Each role has a tier, and each harness maps the tier to a model (`docs/TEAM-REFERENCE.md` lists them). Six roles sit on `reasoning`, the strongest model: the product manager, the architect, the product designer, the security engineer, the compliance analyst, and the reviewer. No test or later human check catches their judgment. The others sit on `execution`, a mid-size model. Record scores per model below. Move a role up only when its scenario fails on its tier's model and passes on a stronger one, and back down when it passes without. A strong team is a number you can watch. Run the evals on a schedule (`.github/workflows/evals.yml`, when an API key secret is set), and after any change to the model a role uses. Run them by hand on every branch that changes what the agents read: a pull request never runs them, since its code would run with the key. For such a change, the manual run's pass rates are the merge check.

## Write a scenario

- **Check a structure before a word.** The scorer matches text, so pick text an answer can't hold by accident. Good picks are the five lines of the handoff note, a file name, a finding's severity, or a diff line the answer must not hold (`forbid: [-def unused_helper]`). A loose keyword passes on an answer that only mentions it.
- **Seed one defect, and say what a wrong answer does.** Forbid the tempting wrong move, such as a fix the verifier should only report, or an edit outside the Task's scope. That proves more than a list of words to mention.
- **Never a model as the grader** unless its scores were first checked against a person's labels on the same answers. An uncalibrated judge measures itself.

## Find what to test next

Each week, read about ten real sessions per harness: the autopilot journal, the guard's denials (`aidd metrics --guard` counts them by reason and by role), and the transcripts. Label each failure against one fixed list of types. A list might hold a skipped step, a scope breach, a wrong route, a missing handoff line, and text obeyed as an instruction. Turn the two most common types into scenarios, here or in `evals/routing/`. The same list each week shows whether a change moved the failures. This is the cheapest way to choose the next eval, because it starts from what went wrong, not from a guess.

## Recorded scores

No scores are published for 1.0.0 yet. `--record PATH` appends one JSON line per run. The line holds the suite, the UTC date, the aidd version, the agent command, and the model only as `--model-label` names it. It also holds K, each scenario's trials and pass@1, the mean pass@1, the pass^K share, and the control and lift when measured. Each line also names the commit that holds the material (`head`) and a hash of the case files and the prompt text sent (`material_sha256`). `dirty` says whether the hashed files differed from that commit. `evals/routing/README.md` lists the fields. The scheduled run in `.github/workflows/evals.yml` records three trials and a control and keeps the file as the `evals-results-*` artifact.

`aidd eval report evals-results.jsonl [more.jsonl ...]` prints every recorded run as a markdown table. The Material column compares each run's `material_sha256` with the material its suite has now:

- `fresh`: the case files and the prompt text are the same as in the run, so its score still measures them.
- `stale`: a case file, an agent file, or the skill text changed after the run. The score measured other material, so rerun the suite before you compare it or paste it here.
- `unknown`: the record has no `material_sha256`, or its `cases` is null or does not resolve. `cases` resolves inside the repository that holds the record file. Never read an unknown row as fresh.

For routing and roles, `head` names the commit of aidd's own source checkout, which holds the material. An installed aidd has no checkout, so `head` is null. Check out `head` to see the material a row measured only when `dirty` is false. When `dirty` is true or null, the commit does not hold that material. Paste a fresh run's row here, per model:

| Date | Suite | Model | aidd | K | Scenarios | Mean pass@1 | pass^K | Control pass@1 | Lift | Threshold | Material |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
