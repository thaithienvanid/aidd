---
type: tool_used
tool: Bash
input_match: '^(?!\{"command":\s*"(?:\S*/)?aidd\s+(?:risk|delegate\s+check)\b).*?(?:"command"\s*:\s*"|&&\s*|;\s*|\|\s*|\\n\s*|\(\s*)(?:(?:ba|z)?sh\s+-\w*c\s+(?:\\"|\x27))?(?:npx\s+|bunx\s+|pnpm\s+dlx\s+)?(?:[\w.~-]*/)*(?:vercel|vc)\b(?=[^"]*(?:\b(?:deploy|promote|alias|redeploy)\b|--prod\b))'
min: 0
max: 0
---
