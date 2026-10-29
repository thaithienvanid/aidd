---
id: ai/litellm-gateway
type: opinionated
fills: [ai-features:llm-gateway]
default: true
implements: ai-features:Implement
roles: [architect, developer, sre, reviewer]
when_changed: ["litellm*.yaml", "**/litellm/**", "docker-compose*.yml", "src/**"]
why: "The LiteLLM proxy gives every model provider one OpenAI-style API on the team's own host, with a virtual key, a budget, and a rate limit for each user or service, and fallbacks between models."
reviewed: "2026-10-22"
maturity: emerging
tool:
  name: litellm
  registry: pypi
  package: litellm
version_policy: current_stable
checked_version: "1.105.1"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "1.105.1"
cooldown_until: "2026-10-28"
source: https://docs.litellm.ai/blog/security-update-march-2026
evidence: The compromised PyPI packages were litellm==1.82.7 and litellm==1.82.8.
alternatives: [no gateway (the provider's SDK), Cloudflare AI Gateway, Vercel AI Gateway, Portkey, OpenRouter]
status: active
---

# The LiteLLM proxy fronts the model providers

It answers the llm-gateway choice of `aidd-team:ai-features` where the team runs its own gateway. LiteLLM is under the MIT license outside its `enterprise/` folder, which needs a commercial license.

## What happened to its releases

On 2026-03-24, LiteLLM said the PyPI releases 1.82.7 and 1.82.8 were malicious. An attacker had published them with the maintainer's stolen PyPI credentials. LiteLLM said that the official proxy Docker image was not affected, because it pins its dependencies.

## What the team does

- Run the proxy from the official image, `ghcr.io/berriai/litellm`, at the version in `pin`, and pin the image by its digest. Install from PyPI only with `--require-hashes` against a lockfile.
- Keep the master key and the provider keys in the secret store, and give each service and each user a virtual key with a budget, a rate limit, and the models it may call.
- Handle a budget or rate-limit error as a clear message to the user, and never retry it.
- Name a fallback model only where the product accepts its answers, and cover the fallback in the evals.
- Log request metadata by default. Log prompt and output text only under the privacy rules, with a set retention.
- Keep the caps in the code that `cost/llm-spend-caps` places, so the proxy is the second line.
- Review this choice every 90 days, and read LiteLLM's security notes before each upgrade.

## What the gate runs

Nothing of its own. The cost and latency evals of `aidd-team:ai-evals` measure each change to a model call.
