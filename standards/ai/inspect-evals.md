---
id: ai/inspect-evals
type: opinionated
fills: [ai-evals:eval-runner]
default: true
implements: "ai-evals:Eval suite (emerging)"
roles: [developer, verifier, reviewer]
when_changed: ["evals/**", "**/prompts/**", "**/*.py", pyproject.toml]
why: "Inspect scores the path an agent takes, not only its final answer, so it is the runner where a tool-using agent or a multi-step solver is under test. The UK AI Security Institute maintains it."
reviewed: "2026-10-22"
maturity: emerging
tool:
  name: inspect-ai
  registry: pypi
  package: inspect-ai
version_policy: current_major
checked_version: "0.3.283"
checked: "2026-10-24"
checked_by: agent:claude-code/claude-opus-5-5
pin: "0.3.282"
cooldown_until: "2026-10-28"
source: https://pypi.org/pypi/inspect-ai/0.3.283/json
evidence: "\"version\":\"0.3.283\""
alternatives: [DeepEval, promptfoo, the repository's own runner on pytest]
status: active
enforced_by:
  - name: evals
    command: [uvx, --from, inspect-ai==0.3.282, inspect, eval, evals/, --fail-on-error]
---

# Inspect runs the agent eval suite

It answers the eval-runner choice of `aidd-team:ai-evals` where the agent's path is scored, not only its answer. Inspect is under MIT from the UK AI Security Institute. DeepEval, under Apache-2.0, stays the default for a Python feature whose answer is what matters, and promptfoo for a TypeScript one.

inspect-ai 0.3.283 came out inside the cooldown of `aidd-team:dependency-upgrade`, so `pin` holds 0.3.282 until `cooldown_until`.

## What the team does

- Lock `inspect-ai` at `pin`, and keep the eval tasks in `evals/`, apart from the unit tests.
- Keep the golden set and the regression set in git, beside the tasks that read them.
- Pin the model, the prompt, and every parameter in the task. Set temperature 0, and a seed where the provider takes one.
- Put deterministic scorers first, such as a JSON-schema check, an exact field, or a refusal phrase. An LLM-judge scorer scores only what they cannot, with its model pinned.
- Repeat each sample with `--epochs k` and the `pass_k` reducer for pass^k. Record the token cost and the latency per task.
- Score the path for a tool-using agent, so a wrong tool call or a skipped step fails the task, not only a wrong final answer.

## What the gate runs

One `evals` test runs `inspect eval evals/` at the pinned version, failing on any error and on a score below each task's threshold.
