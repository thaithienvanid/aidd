#!/usr/bin/env bash
set -euo pipefail
# A small invoicing project with a test and no aidd config: the case needs a repository aidd has not been set up in.
# The files are ours and are written only inside the case's workspace.
mkdir -p invoicing tests
touch invoicing/__init__.py tests/__init__.py
cat > README.md <<'MD'
# Invoicing

Builds an invoice from a list of lines. Run the tests with `python3 -m unittest`.
MD
cat > invoicing/invoice.py <<'PY'
"""An invoice built from lines of (description, price in cents)."""


def total_cents(lines):
    return sum(price for _, price in lines)


def render(lines):
    rows = [f"{name}: {price / 100:.2f}" for name, price in lines]
    return "\n".join(rows + [f"Total: {total_cents(lines) / 100:.2f}"])
PY
cat > tests/test_invoice.py <<'PY'
import unittest

from invoicing import invoice


class InvoiceTests(unittest.TestCase):
    def test_total_adds_the_lines(self):
        self.assertEqual(invoice.total_cents([("a", 100), ("b", 250)]), 350)


if __name__ == "__main__":
    unittest.main()
PY
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A
git commit -q -m "feat: build an invoice from lines"
