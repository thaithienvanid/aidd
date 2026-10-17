---
id: cloudflare/queues-workflows
type: opinionated
fills: [cloud-and-infrastructure:queue]
default: true
implements: resilience:Retry policy in one place
roles: [architect, developer, sre, reviewer]
when_changed: [wrangler.jsonc, wrangler.json, wrangler.toml, "src/**"]
why: "Queues carries background work between Workers with a retry limit and a dead-letter queue on each consumer, and Workflows runs a long job as durable steps that retry on their own, both without a server to run."
reviewed: "2026-10-16"
maturity: emerging
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [Amazon SQS, Google Cloud Pub/Sub]
status: active
source: https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
evidence: "Without a DLQ configured, messages that reach the retry limit are deleted permanently."
enforced_by:
  - name: consumers
    command:
      - python3
      - -c
      - "import json,re,sys,tomllib,pathlib as P;f=next((p for p in map(P.Path,['wrangler.toml','wrangler.jsonc','wrangler.json']) if p.is_file()),None) or sys.exit('no Wrangler file');t=f.read_text();c=tomllib.loads(t) if f.suffix=='.toml' else json.loads(re.sub(r'(\"(?:\\\\.|[^\"\\\\])*\")|//[^\\n]*|/\\*[\\s\\S]*?\\*/|,(?=\\s*[]}])',lambda x:x.group(1) or '',t));B=[c,*(c.get('env') or {}).values()];m=[x.get('queue') for b in B for x in ((b.get('queues') or {}).get('consumers') or []) if 'max_retries' not in x or 'dead_letter_queue' not in x];sys.exit(f'{f}: set max_retries and dead_letter_queue on each queue consumer; missing on {m}' if m else 0)"
---

# Cloudflare Queues and Workflows carry the background work

It answers the queue choice of `aidd-team:cloud-and-infrastructure` on Cloudflare.

## What the team does

- Give every queue consumer `max_retries` and `dead_letter_queue` in the Wrangler file. A consumer without a dead-letter queue loses the message it cannot process.
- Set `max_concurrency` on a consumer that calls a paid or a rate-limited service.
- Make each consumer idempotent: a message can arrive twice.
- Alert on the backlog and on the dead-letter queue's depth, and write in the runbook who replays it and how.
- Use a Workflow when a job has several steps that must each finish once, such as charge, then fulfil, then email. Give each step its own retry limit and timeout.
- Keep each message small. Put a large payload in R2, and send its key.

## What the gate runs

One `tests` entry reads the Wrangler file. A queue consumer, in any environment, with no `max_retries` or no `dead_letter_queue` fails the change.
