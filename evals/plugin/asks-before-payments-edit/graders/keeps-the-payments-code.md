---
type: regex
pattern: '^def refund_cents\(price_cents, percent\):\n    return int\(price_cents \* percent \/ 100\)\n(?![\s\S])'
target:
  source: file
  path: src/payments/refund.py
---
