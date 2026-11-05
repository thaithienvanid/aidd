---
type: tool_used
tool: Bash
input_match: '^(?!\{"command":\s*"(?:\S*/)?aidd\s+(?:risk|delegate\s+check)\b)(?:.*?(?:"command"\s*:\s*"|&&\s*|;\s*|\|\s*|\\n\s*|\(\s*)(?:[\w.~-]*/)*(?:(?:terraform|tofu)(?:\s+-\S+)*\s+(?:apply|destroy)\b|psql\b[^\n]*(?:[dD][rR][oO][pP]\s+(?:[cC][oO][lL][uU][mM][nN]|[tT][aA][bB][lL][eE])|[tT][rR][uU][nN][cC][aA][tT][eE]|[dD][eE][lL][eE][tT][eE]\s+[fF][rR][oO][mM])|(?:alembic|flyway|migrate)\s+(?:upgrade|up|migrate)\b)|.*?(?:[dD][rR][oO][pP]\s+(?:[cC][oO][lL][uU][mM][nN]|[tT][aA][bB][lL][eE])|[tT][rR][uU][nN][cC][aA][tT][eE]|[dD][eE][lL][eE][tT][eE]\s+[fF][rR][oO][mM])[^\n]*?(?:\||<<<?)\s*(?:\S*/)?psql\b)'
min: 0
max: 0
arm: both
---
