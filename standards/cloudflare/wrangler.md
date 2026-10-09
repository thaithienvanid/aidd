+++
id = "cloudflare/wrangler"
type = "opinionated"
fills = ["cloud-and-infrastructure:iac-tool"]
default = true
implements = "cloud-and-infrastructure:Plan or dry-run check"
roles = ["developer", "platform-engineer", "reviewer"]
when_changed = ["wrangler.jsonc", "wrangler.json", "wrangler.toml", "package.json"]
why = "For a project that runs only on Cloudflare, the Wrangler file declares every Worker, binding, limit, and environment, and Wrangler deploys it, so a second tool would only repeat that file."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
alternatives = ["OpenTofu with the Cloudflare provider", "Terraform with the Cloudflare provider"]
status = "active"
source = "https://developers.cloudflare.com/workers/wrangler/commands/workers/"
evidence = "Compile a project without actually deploying to live servers."
enforced_by = [
  { name = "dry-run", command = ["npx", "wrangler", "deploy", "--dry-run", "--outdir", "dist-dry-run"] },
]
+++

# Wrangler defines and deploys the Cloudflare project

It answers the iac-tool choice of `aidd-team:cloud-and-infrastructure` for a project that runs only on Cloudflare. A project on two providers uses `iac/opentofu`.

## What the team does

- Keep one Wrangler file, `wrangler.jsonc`, for each Worker, with an `env` block for preview and production. It is the record of every binding, limit, route, and cron.
- Pin Wrangler in `devDependencies` and commit the lockfile. The pack's dry-run check names the version it was read at.
- Generate the environment types with `wrangler types` and commit them, so a missing binding fails the type check.
- Deploy only from CI, with an API token scoped to the account and the Workers it deploys.
- Create the account resources (DNS, WAF, Zero Trust) in the dashboard only through a written runbook, or move the project to `iac/opentofu`.

## What the gate runs

One `[[tests]]` entry runs `npx wrangler deploy --dry-run --outdir dist-dry-run` with the project's pinned Wrangler. A Wrangler file or a bundle that does not build fails the change.
