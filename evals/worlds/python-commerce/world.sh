#!/usr/bin/env bash
set -euo pipefail
# A small shop's cart code in Python, in a repository that uses aidd under the solo profile. The cart adds up its lines, and
# its one test passes. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd src/shop tests
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo
YAML
: > src/shop/__init__.py
cat > src/shop/cart.py <<'PY'
def total_cents(lines):
    """The cart's total in cents: each line is (unit price in cents, quantity)."""
    return sum(price * quantity for price, quantity in lines)
PY
cat > tests/test_cart.py <<'PY'
from src.shop.cart import total_cents


def test_total_adds_each_line():
    assert total_cents([(250, 2), (100, 1)]) == 600
PY
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A && git commit -q -m "feat: cart total"
