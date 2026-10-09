+++
id = "python/fastmcp-server"
type = "opinionated"
fills = ["ai-agents-and-tools:mcp-server-framework"]
default = true
implements = "ai-agents-and-tools:MCP server security check"
roles = ["developer", "security-engineer", "reviewer"]
when_changed = ["**/*.py", "pyproject.toml"]
why = "FastMCP turns typed Python functions into MCP tools, resources, and prompts, and adds authentication, server composition, and an in-memory test client on top of the protocol."
reviewed = "2026-10-07"
owner = "@thaithienvanid"
maturity = "emerging"
tool = { name = "fastmcp", registry = "pypi", package = "fastmcp" }
version_policy = "current_major"
checked_version = "4.0.11"
checked = "2026-10-07"
checked_by = "agent:claude-code/claude-opus-5-5"
source = "https://pypi.org/pypi/fastmcp/json"
evidence = '"version":"4.0.11"'
alternatives = ["the official MCP Python SDK"]
status = "active"
enforced_by = [
  { name = "major", command = ["uv", "run", "python", "-c", "import importlib.metadata as m, sys; sys.exit(not m.version('fastmcp').startswith('4.'))"] },
]
+++

# FastMCP builds the Python MCP servers

It answers the mcp-server-framework choice of `aidd-team:ai-agents-and-tools`.

## What the team does

- Declare each tool as a typed function with a docstring; the types become the tool's input schema, so validate nothing by hand twice.
- Give each tool the least access it needs. Mark a tool that writes or deletes with `destructiveHint`; the client decides whether to ask a person.
- Serve over stdio for a local client. Over HTTP, put FastMCP's authentication in front and check each request's token audience.
- Test each tool through FastMCP's in-memory client, without a network.
- Review this choice every quarter: the protocol and the library change fast.

## What the gate runs

One `[[tests]]` entry fails when the installed FastMCP is not the major this file was checked at. The tool tests run in the test runner's own entry.
