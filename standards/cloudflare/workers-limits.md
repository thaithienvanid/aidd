---
id: cloudflare/workers-limits
type: opinionated
fills: [cloud-and-infrastructure:spend-caps]
default: true
implements: cloud-and-infrastructure:Implement
roles: [architect, sre, reviewer]
when_changed: [wrangler.jsonc, wrangler.json, wrangler.toml]
why: "Cloudflare's budget alerts only send an email and never stop usage, so the caps that stop a runaway cost are the ones each Worker, queue, and gateway sets on itself."
reviewed: "2026-10-16"
maturity: emerging
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [an automated action on a budget alert, alerts only]
status: active
source: https://developers.cloudflare.com/billing/manage/budget-alerts/
evidence: Budget alerts are informational only. They do not pause or cap usage.
enforced_by:
  - name: limits
    command:
      - python3
      - -c
      - "import json,re,sys,tomllib,pathlib as P;f=next((p for p in map(P.Path,['wrangler.toml','wrangler.jsonc','wrangler.json']) if p.is_file()),None) or sys.exit('no Wrangler file');t=f.read_text();c=tomllib.loads(t) if f.suffix=='.toml' else json.loads(re.sub(r'(\"(?:\\\\.|[^\"\\\\])*\")|//[^\\n]*|/\\*[\\s\\S]*?\\*/|,(?=\\s*[]}])',lambda x:x.group(1) or '',t));B=[c,*(c.get('env') or {}).values()];m=sorted({k for b in B for k in ('cpu_ms','subrequests') if k not in ((b['limits'] if 'limits' in b else c.get('limits')) or {})});sys.exit(f'{f}: set limits.cpu_ms and limits.subrequests in every environment; missing {m}' if m else 0)"
---

# Each Worker caps its own use on Cloudflare

It answers the spend-caps choice of `aidd-team:cloud-and-infrastructure` on Cloudflare.

## What Cloudflare supports

As read on the `checked` day: no account-wide hard spending cap. The caps are per Worker (CPU time and subrequests for each invocation), per queue consumer (retries and concurrency), and per AI Gateway (spend limits, in Beta, that return `429`).

## What the team does

- Set `limits.cpu_ms` in the Wrangler file, at the most a request needs, not at the plan's maximum.
- Set `limits.subrequests` at the most calls a request makes.
- Put a rate limit in front of each public route that does costly work, with the Workers rate limiting binding or a WAF rule.
- Cap queue consumers as `cloudflare/queues-workflows` says, and the model spend as `cloudflare/ai-gateway` says.
- Keep `cloudflare/budget-alerts` as the warning, and `cost/kill-switch` as the stop.

## What the gate runs

One `tests` entry reads the Wrangler file (`wrangler.toml`, `wrangler.jsonc`, or `wrangler.json`). A Worker or an environment with no `limits.cpu_ms` or no `limits.subrequests` fails the change.
