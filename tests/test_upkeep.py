"""`aidd list --upkeep` and `/aidd-team:maintain`: the upkeep that is due, from what aidd already knows, each item with
the command or skill that takes it. It reads files, never the network, and decides nothing."""

import datetime as dt
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import make_repo, ROOT

from aidd.knowledge import team_registry

TODAY = dt.date(2026, 10, 9)
EVENTS = ROOT / "tests" / "fixtures" / "metrics" / "flaky-events.jsonl"
FLAG = '\nflags:\n  - name: checkout-v2\n    default: "off"\n    owner: "@alice"\n    cleanup_due: "{due}"\n    purpose: release the new checkout apart from its deploy\n'
SPEC = '---\naidd_version: "1.0.0"\ntype: spec\nid: "{sid}"\ntitle: t\nroute: "{route}"\n{extra}---\n\nbody\n'
RULES = (
    "\nproject:\n  rules:\n    - id: no-orm-raw-sql\n      level: should\n      statement: Query through the repository layer.\n"
    '      why: One place to review every query.\n      owner: "@alice"\n'
    '  waivers:\n    - rule: no-orm-raw-sql\n      reason: A window function the layer lacks.\n      approved_by: "@alice"\n      until: "{until}"\n'
)
RUNBOOK = '---\naidd_version: "1.0.0"\ntype: runbook\nid: RB-1\ntitle: t\nservice: orders\nowner_team: core\nstatus: active\n---\n\nsteps\n'


@unittest.skipUnless(shutil.which("git"), "git is required")
class OfflineTests(unittest.TestCase):
    """`aidd list --upkeep` reads files only: a URL parent in `extends` is never fetched, and one it cannot read is an
    upkeep item, never a crash."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "repo", branch=None)
        cfg = self.root / ".aidd" / "config.yaml"
        parent = 'extends: [{ url: "https://example.invalid/aidd-org-preset.yaml", sha256: "' + "a" * 64 + '" }]\n'
        cfg.write_text(parent + cfg.read_text(encoding="utf-8"), encoding="utf-8")

    def test_aidd_offline_stops_every_config_fetch(self):
        from aidd import config

        with (
            mock.patch.dict(os.environ, {"AIDD_OFFLINE": "1"}),
            mock.patch("aidd.kernel.egress.fetch_text", side_effect=AssertionError("a fetch under AIDD_OFFLINE=1")),
            self.assertRaises(Exception) as err,
        ):
            config.load_file(config.CONFIG_PATH, str(self.root))
        self.assertNotIsInstance(err.exception, AssertionError)


class MaintainCommandTests(unittest.TestCase):
    """`/aidd-team:maintain` runs the upkeep list on a rhythm and routes each item; it never decides for a person."""

    def setUp(self):
        self.text = (ROOT / "plugins" / "aidd-team" / "commands" / "maintain.md").read_text(encoding="utf-8")

    def test_it_is_a_flow_on_demand_that_preloads_nothing(self):
        flow = next(f for f in team_registry.roles()["loop"]["flows"] if f["command"] == "maintain")
        self.assertEqual((flow["runs"], flow["starts_on"]), ([["sre"]], []))
        self.assertIn("\ndisable-model-invocation: true\n", self.text.split("---")[1] + "\n")
        self.assertNotIn("!`", self.text)  # no shell output preloaded into the prompt
        self.assertIn("| `/aidd-team:maintain` |", (ROOT / "docs" / "TEAM.md").read_text(encoding="utf-8"))

    def test_the_method_names_maintain_without_touching_the_loop_contract(self):
        method = (ROOT / "docs" / "METHOD.md").read_text(encoding="utf-8")
        self.assertRegex(method, r"\*\*Maintain\b[^*\n]*\*\*")  # the method's run-in label for the Maintain module
        self.assertNotIn("maintain", json.dumps(team_registry.roles()["loop"]["contract"]).lower())


if __name__ == "__main__":
    unittest.main()
