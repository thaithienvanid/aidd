#!/usr/bin/env bash
set -euo pipefail
# The same cart module in a repository that has the person's own CLAUDE.md, which Claude Code reads in place of AGENTS.md. The
# real `aidd init` adds one line to it that imports AGENTS.md, so the block still reaches a session that never names aidd.
# The case uses the checkout it lives in, so it tests that checkout's block, else the `aidd` on the PATH.
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
def total(items, discount=0):
    """The sum of price times quantity for each item, less the discount."""
    return sum(item["price"] * item["qty"] for item in items) - discount
PY
cat > tests/test_cart.py <<'PY'
import unittest

from src.cart import total


class CartTests(unittest.TestCase):
    def test_a_discount_comes_off_the_total(self):
        self.assertEqual(total([{"price": 3, "qty": 2}], discount=1), 5)


if __name__ == "__main__":
    unittest.main()
PY
cat > CLAUDE.md <<'MD'
# Cart

A small library. Keep it free of dependencies, and keep each function short.
MD
git add -A && git commit -q -m "feat: cart total"
# init writes a launcher under the home folder in some installs, so it gets a throwaway one.
home="$(mktemp -d)"
HOME="$home" AIDD_OFFLINE=1 aidd_init --profile solo --ci none --harness claude-code --test "python3 -m unittest discover -s tests"
git add -A && git commit -q -m "chore: set up aidd"
