---
id: ai/ollama
type: opinionated
fills: [ai-features:model-serving]
default: false
implements: ai-features:Implement
roles: [developer]
when_changed: ["Modelfile", "**/Modelfile"]
why: "Ollama runs an open-weights model on a developer's machine with one command, so a developer works offline and without a provider key; self-hosted production serving is vLLM's."
reviewed: "2026-10-28"
maturity: established
tool:
  name: ollama
  registry: github
  package: ollama/ollama
version_policy: current_stable
checked_version: "0.40.11"
checked: "2026-10-28"
checked_by: agent:claude-code/claude-opus-5-5
pin: "0.40.7"
cooldown_until: "2026-10-31"
source: https://raw.githubusercontent.com/ollama/ollama/main/README.md
evidence: Start building with open models.
alternatives: [llama.cpp, vLLM]
status: active
---

# Ollama runs a model on a developer's machine

It answers the model-serving choice of `aidd-team:ai-features` for local development. Ollama is under the MIT license; each model's weights carry their own license. It ships often: 0.40.11 came out on 2026-10-24, inside the cooldown of `aidd-team:dependency-upgrade`, so `pin` holds 0.40.7 until `cooldown_until`.

## What the team does

- Use it for local development and tests only. The code reaches it through the same OpenAI-compatible client and gateway setting as production, so no code branches on where the model runs.
- Pin the model by its tag and digest in a `Modelfile` in the repository.
- Never let a result from a local model stand in for the production model's evals.
