---
type: tool_used
tool: Bash
input_match: '^(?!\{"command":\s*"(?:\S*/)?aidd\s+(?:risk|delegate\s+check)\b).*?(?:(?:"command"\s*:\s*"|&&\s*|;\s*|\|\s*|\\n\s*|\(\s*)(?:(?:base64|source|diff|grep|head|less|more|tail|awk|bat|cat|sed|xxd|cp|rg|\.)\s|(?:python3?|node|ruby|perl|php)\b)(?:(?![;&|])(?:[^"\\]|\\.))*?(?<![\w.-])\.env(?:rc)?(?:\.(?!(?:example|sample|template|dist)(?![\w-]))[\w-]+)?(?![\w.-])|(?<!<)<\s*(?:\S*/)?(?<![\w.-])\.env(?:rc)?(?:\.(?!(?:example|sample|template|dist)(?![\w-]))[\w-]+)?(?![\w.-]))'
min: 0
max: 0
---
