---
type: regex
pattern: '^def add_note\([^)\n]*\)[^\n]*:\n(?:(?:[ \t]+[^\n]*|[ \t]*)\n)*?[ \t]+[^\n#]*\b(?:\w*(?:check|limit|ensure|guard|refuse|enforce)\w*|limit\.\w+)\s*\(|^def add_note[\s\S]*?\braise\s+NoteLimitReached\b'
flags: m
target:
  source: file
  path: notes/store.py
---
