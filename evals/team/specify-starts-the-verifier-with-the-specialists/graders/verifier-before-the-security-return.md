---
type: tool_order
before:
  tool: Agent
  input_match: '"subagent_type"\s*:\s*"aidd-team:verifier"'
after:
  tool: Write
  input_match: '"file_path"\s*:\s*"[^"]*\.aidd/returns/SPEC-1/security-engineer\.md"'
---
