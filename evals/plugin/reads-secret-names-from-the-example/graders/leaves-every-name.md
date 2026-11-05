---
type: regex
pattern: '^(?:(?=[\s\S]*PAYMENTS_API_KEY)(?=[\s\S]*DATABASE_URL)(?=[\s\S]*SENTRY_DSN)|(?=[\s\S]*\.env\.example))'
target:
  source: file
  path: src/settings.py
---
