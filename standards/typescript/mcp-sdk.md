+++
id = "typescript/mcp-sdk"
type = "opinionated"
fills = ["ai-agents-and-tools:mcp-server-framework"]
default = true
implements = "ai-agents-and-tools:MCP server security check"
roles = ["developer", "security-engineer", "reviewer"]
when_changed = ["**/*.ts", "package.json"]
why = "The official MCP TypeScript SDK follows each new version of the protocol first, takes Zod schemas for tool input, and serves over stdio, Node.js HTTP, or a web-standard fetch handler."
reviewed = "2026-10-09"
owner = "@thaithienvanid"
maturity = "emerging"
tool = { name = "mcp-typescript-sdk", registry = "npm", package = "@modelcontextprotocol/server" }
version_policy = "current_major"
checked_version = "2.3.1"
checked = "2026-10-09"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://registry.npmjs.org/-/package/@modelcontextprotocol/server/dist-tags"
evidence = '"latest":"2.3.1"'
alternatives = ["the v1 SDK (@modelcontextprotocol/sdk), in fix-only support", "FastMCP for TypeScript"]
status = "active"
enforced_by = [
  { name = "major", command = ["node", "-e", "process.exit(require('./node_modules/@modelcontextprotocol/server/package.json').version.startsWith('2.') ? 0 : 1)"] },
]
+++

# The MCP TypeScript SDK builds the TypeScript MCP servers

It answers the mcp-server-framework choice of `aidd-team:ai-agents-and-tools` for TypeScript. Licence: Apache-2.0 for new code, with older code under MIT, as the repository states.

## What the team does

- Install `@modelcontextprotocol/server`, the v2 line. The v1 package, `@modelcontextprotocol/sdk`, gets fixes only; move a v1 server with the SDK's migration guide.
- Register each tool with `registerTool` and a Zod input schema, and an output schema where the tool returns data.
- Mark a tool that writes or deletes with `destructiveHint`; the annotation only informs the client, so the server still checks each call's rights.
- Over HTTP, put the SDK's `requireBearerAuth` in front of the MCP route, so a request without a valid token gets `401`.
- Test each tool through an in-process `Client` against `createMcpHandler`, with no port and no mock transport.
- Review this choice every quarter: the protocol and the SDK change fast.

## What the gate runs

One `[[tests]]` entry fails when the installed SDK is not the major this file was checked at. The tool tests run in the test runner's own entry.
