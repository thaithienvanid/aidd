---
type: tool_order
before:
  tool: Agent
  input_match: '"subagent_type"\s*:\s*"aidd-team:security-engineer"'
after:
  tool: Write
  input_match: '"file_path"\s*:\s*"[^"]*/tests/'
---
