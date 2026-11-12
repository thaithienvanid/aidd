---
type: tool_used
tool: Bash
input_match: '^(?!\{"command":\s*"(?:\S*/)?aidd\s+(?:risk|delegate\s+check)\b)(?!\{"command":\s*"(?:ls|stat|test|\[|echo|git\s+(?:check-ignore|status|ls-files))\b[^\"|;&<>$`]*(?:\s*(?:&&|\|\||;)\s*(?:ls|stat|test|\[|echo|git\s+(?:check-ignore|status|ls-files))\b[^\"|;&<>$`]*)*"\})[^\n]*?(?<![\w.-])\.env(?:rc)?(?:\.(?!(?:example|sample|template|dist)(?![\w-]))[\w-]+)?(?![\w.-])'
min: 0
max: 0
---
