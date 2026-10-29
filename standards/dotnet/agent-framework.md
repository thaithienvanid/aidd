---
id: dotnet/agent-framework
type: opinionated
fills: [ai-agents-and-tools:agent-framework]
default: true
implements: ai-agents-and-tools:Loop and cost guards
roles: [developer, reviewer]
when_changed: ["**/*.cs", "**/*.csproj", Directory.Packages.props]
why: "Microsoft Agent Framework is the .NET agent library from the teams behind Semantic Kernel and AutoGen, built on the Microsoft.Extensions.AI abstractions, with tool approval and GenAI tracing built in."
reviewed: "2026-10-22"
maturity: emerging
tool:
  name: microsoft-agents-ai
  registry: nuget
  package: Microsoft.Agents.AI
version_policy: current_major
checked_version: "1.25.0"
checked: "2026-10-22"
checked_by: agent:claude-code/claude-opus-5-5
pin: "1.25.0"
source: https://learn.microsoft.com/en-us/agent-framework/overview/
evidence: The Agent Framework is the direct successor, created by the same teams.
alternatives: [the provider's SDK, Microsoft.Extensions.AI alone]
status: active
---

# Microsoft Agent Framework runs the .NET agent loop

It answers the agent-framework choice of `aidd-team:ai-agents-and-tools` for .NET. The `Microsoft.Agents.AI` package is under the MIT license. Microsoft Learn calls it the direct successor of Semantic Kernel and AutoGen, so a new .NET agent starts here and not on either of them.

## What the team does

- Reference `Microsoft.Agents.AI` and the provider's package at `pin`, through central package management.
- Cap the tool loop with `MaximumIterationsPerRequest` on the function-invoking chat client, set lower than its default of 40, and meet `Loop and cost guards` of `aidd-team:ai-agents-and-tools`.
- Wrap each tool that writes, spends, or sends in `ApprovalRequiredAIFunction`. Check every response for `ToolApprovalRequestContent`, and send the person's answer back in the same session.
- Add `UseOpenTelemetry()` to the chat client or to the agent, not both, so each span appears once. Leave `EnableSensitiveData` off outside development.
- Test the agent against a fake `IChatClient` that returns scripted tool calls, and assert the calls as well as the answer.
- Review this choice every quarter, because the framework is young.

## What the gate runs

Nothing of its own. The tests run in the test runner's entry, and central package management holds the version.
