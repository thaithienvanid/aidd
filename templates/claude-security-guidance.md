# Security guidance for this repository

aidd wrote these rules. Add your threat model's rules below them. The security-guidance plugin reads this file as extra context for its reviews.

- Validate every input at a trust boundary against an allow-list or a schema. Reject bad input; never repair it.
- Build queries with parameters. Never build a shell command from input.
- Check authorization on every path and object, on the server, and deny by default. A failing security check denies.
- Fetch a URL from input only from an allow-list of hosts, never a private or metadata address.
- Read secrets from the environment or a secret manager. Never put one in code, repository config, logs, or prompts.
- Log facts, never sensitive values.
- A new dependency must exist on the official registry, be maintained, have no advisories, be pinned in the lockfile, and be allowed by the change's Spec.
- A test or design file a Spec froze stays as it is. If a finding seems to need an edit to one, report it and stop: the change goes back through the Spec (`spec.revise`) and a person's approval.
