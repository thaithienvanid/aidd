---
id: cost/llm-spend-caps
type: opinionated
fills: [ai-features:llm-budget-mechanism]
default: true
implements: ai-features:Implement
roles: [developer, architect, reviewer]
when_changed: ["src/**", "app/**", "lib/**"]
why: "One module that calls the model is the one place the code can enforce each cap the ai-features Implement row requires, before the call, so no other path reaches the provider unbudgeted."
reviewed: "2026-10-16"
maturity: emerging
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [a gateway's budget per key, the provider's spend limit alone]
status: active
source: https://genai.owasp.org/download/56857/
evidence: "Set non-overridable budget ceilings per API key, user, team, and cloud account."
---

# One calling module enforces the model spend caps

It answers the llm-budget-mechanism choice of `aidd-team:ai-features`: where the layered caps of its Implement row (OWASP LLM06:2026, Unbounded Consumption) are enforced. That row lists the caps; this standard places them.

## What the team does

- Call the model through one module, and let no other code call the provider's SDK. A lint rule or a review check finds a second caller.
- Enforce each cap of the Implement row in that module, before the call. Over a cap, return a clear message and make no call.
- Keep the per-user usage in the application's store, written after each call from the provider's usage figures.
- Set the provider's own limit in its console for each workspace or project, and give each environment its own key.
- Once the project runs a gateway, move the per-key budgets there (`cloudflare/ai-gateway`), and keep the module's checks.

## What the gate runs

Nothing of its own. Test that a user over budget gets the message and that no model call is made.
