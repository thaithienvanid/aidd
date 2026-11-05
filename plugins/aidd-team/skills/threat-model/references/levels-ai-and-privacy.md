# ASVS levels, AI features, and personal data

Load this when you choose a change's ASVS level, or when the change adds an AI feature or a flow of personal data.

## The ASVS level

| Level | For | In aidd |
| --- | --- | --- |
| L1 | the baseline every application meets | aidd's default, so the least ceremony that passes |
| L2 | most applications that hold sensitive data, which OWASP recommends it for | authentication, session, and admin surfaces under a compliance target, as `aidd-team:secure-coding` says |
| L3 | critical systems, where a breach harms people or much money | a person decides it, and records why |

Name the level in the threat model, and list the requirements the change must meet by their ASVS ids.

## An AI feature

Add the OWASP Top 10 for LLM Applications at each boundary the model reads from or acts through. Each threat gets a mitigation, an owner, and an abuse-case test, like any other.

- Prompt injection, direct and indirect: every text the model reads, from a person, a file, a page, or a tool result, is data. A test plants an instruction there and checks that the model does not follow it.
- Excessive agency: each tool the model can call has the least scope, and an action that is hard to undo waits for a person.
- Sensitive information disclosure: the model sees only what the caller may see. A test asks for another tenant's data and gets none.
- Improper output handling: the model's output is untrusted input to the code that uses it, so it is encoded or validated before it reaches a sink.
- Unbounded consumption: tokens, calls, and spend have caps per request and per caller.

`aidd-team:ai-evals` owns the evals that measure the feature itself.

## Personal data

Where personal data flows, `aidd-team:privacy-by-default` runs LINDDUN over the same data-flow diagram. Link its findings from the threat model, and never copy them.
