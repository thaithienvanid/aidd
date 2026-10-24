---
id: python/deepeval-evals
type: opinionated
fills: [ai-evals:eval-runner]
default: true
implements: "ai-evals:Eval suite (emerging)"
roles: [developer, verifier, reviewer]
when_changed: ["evals/**", "**/prompts/**", "**/*.py", pyproject.toml]
why: "DeepEval writes each eval case as a pytest test with a threshold on each metric, so the Python team's own runner, fixtures, and CI report carry the evals."
reviewed: "2026-10-22"
maturity: emerging
tool:
  name: deepeval
  registry: pypi
  package: deepeval
version_policy: current_major
checked_version: "4.3.1"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "4.3.1"
source: https://pypi.org/pypi/deepeval/4.3.1/json
evidence: "\"version\":\"4.3.1\""
alternatives: [Inspect AI, the repository's own runner on pytest]
status: active
enforced_by:
  - name: evals
    command: [env, DEEPEVAL_TELEMETRY_OPT_OUT=1, uv, run, deepeval, test, run, evals/]
---

# DeepEval runs the Python eval suite

It answers the eval-runner choice of `aidd-team:ai-evals`. DeepEval is under Apache-2.0. Inspect AI, under MIT from the UK AI Security Institute, is the alternative where the agent's path is scored, not only its answer. It needs a short script that fails on a score below the threshold.

## What the team does

- Lock `deepeval` at `pin` in the project, and keep the eval cases in `evals/`, apart from the unit tests.
- Keep the golden set and the regression set in git, beside the cases that read them.
- Pin the model, the prompt, and every parameter in the case's config. Set temperature 0, and a seed where the provider takes one.
- Put deterministic checks first, such as the JSON schema, an exact field, or a refusal phrase. An LLM judge scores only what they cannot, with its model pinned.
- Repeat each case k times with `-r` for pass^k. Leave the cache off (no `-c`) on the head run.
- Turn off DeepEval's telemetry, which is on by default, with `DEEPEVAL_TELEMETRY_OPT_OUT=1`. Never log the CI run in to Confident AI, its hosted platform, unless the Spec names it.
- Give the run its own provider key with a spend limit. `aidd test` drops a variable named like a key, so pass it with `--pass-env`.

## What the gate runs

One `tests` entry runs `deepeval test run evals/`. A case below its threshold fails the change.
