---
id: cloudflare/static-assets
type: opinionated
fills: [cloud-and-infrastructure:hosting-target]
default: true
implements: cloud-and-infrastructure:Pick the placement
roles: [architect, developer, sre]
when_changed: [wrangler.jsonc, wrangler.json, wrangler.toml, "public/**", "dist/**", ".assetsignore"]
why: "A Worker serves the built front end from its assets directory without running any code for a matching file, so the site and its API deploy as one unit and the static traffic invokes nothing."
reviewed: "2026-10-16"
maturity: emerging
checked: "2026-10-16"
checked_by: agent:claude-code/claude-opus-5-5
alternatives: [Cloudflare Pages, an object store behind a CDN]
status: active
source: https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/
evidence: Requests to static assets are free and unlimited.
---

# Workers static assets host the front end on Cloudflare

It answers the hosting-target choice of `aidd-team:cloud-and-infrastructure` for the web front end on Cloudflare.

## What the team does

- Point `assets.directory` in the Wrangler file at the build output, and deploy the front end and its Worker together.
- Leave `run_worker_first` off, so a request that matches a file never runs the Worker. Turn it on only for the paths that need code, such as an authenticated area.
- List the server files and the build leftovers in `.assetsignore`, so no private file is uploaded as a public asset.
- Set the caching and security headers in a `_headers` file, and check them in the deploy preview.
- Give each build hashed file names, so a long cache never serves an old script.
- Keep the files that need a login out of the assets directory. Serve them from a Worker route that checks the session.

## What the gate runs

Nothing of its own. `cloudflare/wrangler` builds the Worker and its assets in a dry run.
