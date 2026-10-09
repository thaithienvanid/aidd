+++
id = "typescript/node-lts"
type = "opinionated"
fills = ["ci-pipeline:language-version"]
default = true
implements = "ci-pipeline:Dependencies declared and locked"
roles = ["developer", "platform-engineer", "reviewer"]
when_changed = [".nvmrc", "package.json", ".github/workflows/**", "Dockerfile"]
why = "A long-term support line of Node.js gets security fixes for thirty months, so the runtime in development, CI, and production stays one supported version."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "established"
tool = { name = "node", registry = "nodejs.org", package = "node" }
version_policy = "latest_lts"
checked_version = "24.21.0"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://nodejs.org/dist/index.json"
evidence = '{"version":"v24.21.0","date":"2026-09-07","files":["aix-ppc64","headers","linux-arm64","linux-ppc64le","linux-s390x","linux-x64","linux-x64-musl","osx-arm64-tar","osx-x64-pkg","osx-x64-tar","src","win-arm64-7z","win-arm64-zip","win-x64-7z","win-x64-exe","win-x64-msi","win-x64-zip"],"npm":"11.19.0","v8":"13.6.233.17","uv":"1.52.1","zlib":"1.3.2.1-motley","openssl":"3.5.8","modules":"137","lts":"Krypton","security":false}'
alternatives = ["the current Node.js release", "Bun", "Deno"]
status = "active"
enforced_by = [
  { name = "runtime", command = ["node", "-e", "const want = require('fs').readFileSync('.nvmrc', 'utf8').trim().replace(/^v/, ''); process.exit(process.versions.node.startsWith(want) ? 0 : 1)"] },
]
+++

# The project runs on the newest Node.js LTS line

It answers the language-version choice of `aidd-team:ci-pipeline`.

## What the team does

- Write the LTS major in `.nvmrc`, the one file CI, the container image, and each developer read.
- Point the CI setup step at `.nvmrc` (`node-version-file`), and build the image from the same major.
- Set `engines.node` in `package.json` to that major, so an install on another one warns.
- Move to each new line once it becomes LTS. From Node.js 27, every release line becomes LTS, one a year.
- Test the move in its own change, before the old line leaves active support.

## What the gate runs

One `[[tests]]` entry compares the running Node.js with `.nvmrc`. A runner on another version fails the change.
