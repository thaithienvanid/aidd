"""What the Policy command sees: every path the change touches, and the route the gate will enforce."""

import json
import sys
import unittest

from helpers import ROOT  # noqa: F401  (puts src on sys.path)

from aidd import config, policy, rules

# The Policy answers with what it was given, so a test can read its inputs back.
ECHO = (
    "import json, os; d = json.load(open(os.environ['AIDD_INPUT_FILE']));"
    "print(json.dumps({'verdict': 'allow', 'detail': json.dumps([d['route'], d['required_route'], os.environ['AIDD_ROUTE'], d['paths']])}))"
)
CFG = config.load_text('aidd_version = "1.0.0"\nprofile = "team"\n[owners]\napprovers = ["@lead"]\n')
SPEC_BODY = """Rotate the session signing key.

```toml aidd
route = "normal"
type = "fix"
confidence = "high"
scope = ["src/auth/"]
rollback = "Revert the PR."
assisted_by = []

[risk]
summary = "Changes how sessions are signed."
dimensions = []
reversible = true
```
"""


def seen(paths, body=SPEC_BODY, cfg=CFG):
    out = policy.evaluate([sys.executable, "-c", ECHO], cwd=".", change_id="1", base_sha="b", head_sha="h", paths=paths, body=body, head_files={}, cfg=cfg)
    return json.loads(out["detail"])


class PolicyInputTests(unittest.TestCase):
    def test_a_rename_source_reaches_the_policy(self):
        files = [{"path": "docs/main.tf", "previous_path": "infra/prod/main.tf", "additions": 0, "deletions": 0}]
        _, _, _, paths = seen(rules.changed_paths(files))
        self.assertIn("infra/prod/main.tf", paths)  # a rule denying infra/prod/** must see the move out of it

    def test_the_policy_sees_the_route_the_gate_will_enforce(self):
        # A declared normal change touching auth code is major to the gate, so the Policy sees major.
        route, required, env_route, _ = seen(["src/auth/session.py"])
        self.assertEqual((route, required, env_route), ("major", "major", "major"))

    def test_a_route_already_high_enough_is_unchanged(self):
        route, required, _, _ = seen(["docs/guide.md"])
        self.assertEqual((route, required), ("normal", "minor"))

    def test_without_a_config_the_declared_route_is_passed_through(self):
        route, required, _, _ = seen(["src/auth/session.py"], cfg=None)
        self.assertEqual((route, required), ("normal", ""))


if __name__ == "__main__":
    unittest.main()
