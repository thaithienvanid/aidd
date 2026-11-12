#!/usr/bin/env bash
set -euo pipefail
# A small cart module whose total is wrong for an empty cart, in a repository that the real `aidd init` set up: its AGENTS.md
# holds the block a project gets, and nothing else tells the agent about aidd. The prompt names no aidd, so a run that checks
# the route before its first edit does it because that file told it to. Claude Code reads AGENTS.md here, since the folder
# has no CLAUDE.md. The case uses the checkout it lives in, so it tests that checkout's block, else the `aidd` on the PATH.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$here/../../../src/aidd/__main__.py" ]; then
  aidd_init() { PYTHONPATH="$here/../../../src" python3 -m aidd init "$@"; }
elif command -v aidd >/dev/null 2>&1; then
  aidd_init() { aidd init "$@"; }
else
  echo "this case sets its workspace up with the real 'aidd init': put aidd on the PATH (the aidd-cli plugin, or 'uv tool install'), then run the suite again" >&2
  exit 1
fi
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
mkdir -p src tests
cat > src/cart.py <<'PY'
def total(items):
    """The sum of price times quantity for each item, or 0 for an empty cart."""
    return sum(item["price"] * item["qty"] for item in items) or None
PY
cat > tests/test_cart.py <<'PY'
import unittest

from src.cart import total


class CartTests(unittest.TestCase):
    def test_a_cart_adds_price_times_quantity(self):
        self.assertEqual(total([{"price": 3, "qty": 2}, {"price": 1, "qty": 1}]), 7)


if __name__ == "__main__":
    unittest.main()
PY
git add -A && git commit -q -m "feat: cart total"
# init writes a launcher under the home folder in some installs, so it gets a throwaway one.
home="$(mktemp -d)"
HOME="$home" AIDD_OFFLINE=1 aidd_init --profile solo --ci none --harness none --test "python3 -m unittest discover -s tests"
git add -A && git commit -q -m "chore: set up aidd"
