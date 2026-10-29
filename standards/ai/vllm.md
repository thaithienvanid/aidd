---
id: ai/vllm
type: opinionated
fills: [ai-features:model-serving]
default: true
implements: ai-features:Implement
roles: [architect, developer, sre, reviewer]
when_changed: ["**/vllm*.yaml", "**/vllm/**"]
why: "Where the team serves a model itself, vLLM serves the open-weights model on its own GPUs behind an OpenAI-compatible API, so the code calls it as it calls a hosted provider, through the same gateway."
reviewed: "2026-10-28"
maturity: established
tool:
  name: vllm
  registry: pypi
  package: vllm
version_policy: current_stable
checked_version: "0.32.0"
checked: "2026-10-28"
checked_by: agent:claude-code/claude-opus-5-5
pin: "0.32.0"
source: https://docs.vllm.ai/en/latest/
evidence: vLLM is a fast and easy-to-use library for LLM inference and serving
alternatives: [a hosted provider's API, SGLang, Text Generation Inference]
status: active
---

# vLLM serves the open-weights models

It answers the model-serving choice of `aidd-team:ai-features` where the team serves a model itself. vLLM is under the Apache License 2.0; each model's weights carry their own license, which the team reads before it ships one.

## What the team does

- Run the official image at `pin`, pinned by digest. Pin the model by its exact revision (a commit hash), never a moving name, so a model never changes under the evals.
- Put it behind the gateway (`ai/litellm-gateway`) as one more provider, with its own budget. Fall back to a hosted model only where the data may leave the team's hosts; where it may not, fail or queue the request instead.
- Run the eval suite (`aidd-team:ai-evals`) on any change of model, revision, quantization, or vLLM version, and keep the scores beside the change.
- Measure cost per request on the GPUs (`aidd-team:ai-features`' FinOps unit), and size the replicas from the load test, not from a guess.
