---
type: tool_order
before:
  tool: Bash
  input_match: 'aidd\s+risk\b'
after:
  tool: Bash
  input_match: '\bgit\s+(?:-[cC]\s+\S+\s+)*commit\b'
---
