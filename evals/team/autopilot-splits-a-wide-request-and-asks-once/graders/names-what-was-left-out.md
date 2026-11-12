---
type: regex
pattern: '(?:^|(?<=[.!?]))(?:(?=[^.!?\n]*\b(?:passwords?|secrets?|credentials?|e-?mails?|personal data|logins?)\b)(?=[^.!?\n]*\b(?:left\s+out|leaving\s+out|leave\s+out|omit(?:s|ted|ting)?|redact(?:ed|ing|s)?|kept\s+out|keep\s+out|remov\w*|exclud\w*|strip\w*|withh[eo]ld\w*)\b)(?:(?!\b(?:nothing|none|not)\b|n''t\b)[^.!?\n])*|(?=[^.!?\n]*\b(?:passwords?|secrets?|credentials?|e-?mails?|personal data|logins?)\b)(?=[^.!?\n]*\b(?:did\s+not|didn''t|never)\s+(?:save|copy|keep|store|include))[^.!?\n]*)(?=[.!?\n]|(?![\s\S]))'
flags: im
---
