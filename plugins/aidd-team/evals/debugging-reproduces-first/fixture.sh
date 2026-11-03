#!/usr/bin/env bash
set -euo pipefail
# The workspace the prompt describes: the buggy pricing module, so the agent can reproduce the bug before fixing it.
cat > pricing.py <<'PY'
BULK_THRESHOLD = 10
BULK_RATE = 0.10


def order_total(quantity: int, unit_price: float) -> float:
    subtotal = quantity * unit_price
    if quantity > BULK_THRESHOLD:
        subtotal -= subtotal * BULK_RATE
    return round(subtotal, 2)
PY
