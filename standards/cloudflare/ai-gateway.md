+++
id = "cloudflare/ai-gateway"
type = "opinionated"
fills = ["ai-features:llm-gateway"]
default = true
implements = "ai-evals:Cost and latency budget"
roles = ["architect", "developer", "ml-engineer", "reviewer"]
when_changed = ["wrangler.jsonc", "wrangler.json", "wrangler.toml", "src/**"]
why = "AI Gateway sits between the code and the model providers with rate limits, caching, logs, and spend limits (in Beta), so one place can stop the cost of a runaway user or a loop."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "emerging"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
alternatives = ["no gateway (the provider's SDK)", "LiteLLM", "Vercel AI Gateway", "OpenRouter"]
status = "active"
source = "https://developers.cloudflare.com/ai-gateway/features/spend-limits/"
evidence = "When cumulative spend reaches the limit within a time window, AI Gateway blocks further requests with a 429 response until the window resets."
+++

# Cloudflare AI Gateway fronts the model providers

It answers the llm-gateway choice of `aidd-team:ai-features` on Cloudflare.

## What the team does

- Send every model call through one gateway for each environment. Turn on authentication, so only the project's Workers can call it.
- Set spend limits on the gateway, a Beta feature on the `checked` day: one for the whole gateway, and one for each user through the request's metadata. Handle the `429` as a clear message to the user, never as a retry.
- Add a rate limit for each user, and a fallback model through a dynamic route where the product can accept one.
- Turn on caching only for prompts that repeat with the same answer, such as a fixed classification.
- Keep the logs only as long as the privacy rules allow, and redact the prompts that carry personal data.
- Keep the caps in the code that `cost/llm-spend-caps` places. The gateway is a second line, not the only one.

## What the gate runs

Nothing of its own. The cost and latency evals of `aidd-team:ai-evals` run on each change to a model call.
