---
id: typescript/promptfoo-evals
type: opinionated
fills: [ai-evals:eval-runner]
default: true
implements: "ai-evals:Eval suite (emerging)"
roles: [developer, verifier, reviewer]
when_changed: ["promptfooconfig.yaml", "evals/**", "**/prompts/**", "**/*.ts", package.json]
why: "promptfoo runs the eval cases from one YAML file against any model provider, scores them with assertions, and returns a failing exit code when a case misses, so CI needs no code of its own."
reviewed: "2026-10-22"
maturity: emerging
tool:
  name: promptfoo
  registry: npm
  package: promptfoo
version_policy: current_stable
checked_version: "0.124.1"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "0.124.1"
source: https://registry.npmjs.org/promptfoo/0.124.1
evidence: "\"version\":\"0.124.1\""
alternatives: [Inspect AI, DeepEval for TypeScript, the repository's own runner on Vitest]
status: active
enforced_by:
  - name: evals
    command: [env, PROMPTFOO_DISABLE_TELEMETRY=1, npx, --yes, promptfoo@0.124.1, eval, --no-cache, --output, eval-results.json]
---

# promptfoo runs the TypeScript eval suite

It answers the eval-runner choice of `aidd-team:ai-evals`. promptfoo is under the MIT license. It is now part of OpenAI, and it says that it remains open source. A vendor of models now owns the runner that scores them. So keep the cases in plain YAML that another runner can read, and review this choice if the project's terms change.

## What the team does

- Keep `promptfooconfig.yaml`, the golden set, and the regression set in git.
- Pin each provider's model id and every parameter in the config. Set `temperature: 0`, and a `seed` where the provider takes one.
- Score with deterministic assertions first, such as `is-json`, `contains`, or a JavaScript check. Use `llm-rubric` only with a pinned grader model.
- For pass^k, run `--repeat` k times and count a case as passed only when every repeat passes.
- Turn off promptfoo's telemetry, which is on by default, with `PROMPTFOO_DISABLE_TELEMETRY=1`. Run with `--no-cache` on the head run, so no stored answer hides a change.
- Put the pass rate from `eval-results.json` in the PR/MR description.
- Give the run its own provider key with a spend limit, and pass it to `aidd test` with `--pass-env`.

## What the gate runs

One `tests` entry runs `promptfoo eval`. promptfoo exits 100 when a case fails, or when the pass rate falls below `PROMPTFOO_PASS_RATE_THRESHOLD`, which defaults to 100%. Either fails the change.
