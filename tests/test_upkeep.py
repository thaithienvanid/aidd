"""`aidd list --upkeep` and `/aidd-team:maintain`: the upkeep that is due, from what aidd already knows, each item with
the command or skill that takes it. It reads files, never the network, and decides nothing."""

import contextlib
import datetime as dt
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT, git, make_repo, run_cli

from aidd import resources, schema, upkeep

TODAY = dt.date(2026, 10, 9)
EVENTS = ROOT / "tests" / "fixtures" / "metrics" / "flaky-events.jsonl"
FLAG = (
    '\n[[flags]]\nname = "checkout-v2"\ndefault = "off"\nowner = "@alice"\ncleanup_due = "{due}"\npurpose = "release the new checkout apart from its deploy"\n'
)
SPEC = '+++\naidd_version = "1.0.0"\nkind = "spec"\nid = "{sid}"\ntitle = "t"\nroute = "{route}"\n{extra}+++\n\nbody\n'
RULES = (
    '\n[[project.rules]]\nid = "no-orm-raw-sql"\nlevel = "should"\nstatement = "Query through the repository layer."\n'
    'why = "One place to review every query."\nowner = "@alice"\n'
    '\n[[project.waivers]]\nrule = "no-orm-raw-sql"\nreason = "A window function the layer lacks."\napproved_by = "@alice"\nuntil = {until}\n'
)
RUNBOOK = '+++\naidd_version = "1.0.0"\nkind = "runbook"\nid = "RB-1"\ntitle = "t"\nservice = "orders"\nowner_team = "core"\nstatus = "active"\n+++\n\nsteps\n'


@unittest.skipUnless(shutil.which("git"), "git is required")
class UpkeepTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "repo", branch=None)

    def write(self, rel: str, text: str) -> None:
        (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
        (self.root / rel).write_text(text, encoding="utf-8")

    def codes(self, **kw) -> list[str]:
        return [i["code"] for i in upkeep.items(self.root, today=TODAY, **kw) if i["code"] != "upkeep.doctor_warning"]

    def test_a_clean_repository_has_no_upkeep_but_its_doctor_warnings(self):
        with mock.patch.dict(os.environ, {"AIDD_OFFLINE": "0"}):
            with mock.patch("aidd.github.protection_checks", side_effect=AssertionError("no network")):
                found = upkeep.items(self.root, today=TODAY)
            self.assertEqual(os.environ["AIDD_OFFLINE"], "0")  # restored
        self.assertEqual({i["code"] for i in found} - {"upkeep.doctor_warning"}, set())
        self.assertEqual(schema.validate({"schema_version": "1", "items": found}, "upkeep.schema.json"), [])

    def test_each_kind_of_upkeep_is_found_and_routed(self):
        self.write("specs/SPEC-1.md", SPEC.format(sid="SPEC-1", route="normal", extra=FLAG.format(due="2026-09-01").lstrip("\n")))
        emergency = 'emergency = {{ severity = "sev2", kind = "outage", commander = "@ic", review_due = "2026-10-08", backfill = "specs/INC-1.md" }}\nstatus = "shipped"\n'
        self.write("specs/INC-1.md", SPEC.format(sid="INC-1", route="emergency", extra=emergency.replace("{{", "{").replace("}}", "}")))
        cfg = self.root / ".aidd" / "config.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + RULES.format(until="2026-10-30"), encoding="utf-8")
        self.write("docs/runbooks/RB-1.md", RUNBOOK)
        found = upkeep.items(self.root, events=[str(EVENTS)], today=TODAY)
        by = {}
        for i in found:
            by.setdefault(i["code"], []).append(i)
        self.assertEqual(schema.validate({"schema_version": "1", "items": found}, "upkeep.schema.json"), [])
        self.assertEqual((by["upkeep.flag_cleanup"][0]["where"], by["upkeep.flag_cleanup"][0]["route"]), ("specs/SPEC-1.md", "release-rollout"))
        self.assertIn("checkout-v2", by["upkeep.flag_cleanup"][0]["what"])
        self.assertEqual((by["upkeep.backfill_due"][0]["due"], by["upkeep.backfill_due"][0]["route"]), ("2026-10-08", "postmortem"))
        self.assertIn("/aidd-team:postmortem", by["upkeep.backfill_due"][0]["how"])
        self.assertEqual(sorted(i["what"].split()[0] for i in by["upkeep.flaky_test"]), ["e2e", "unit"])  # lint is under the limit
        self.assertEqual({i["route"] for i in by["upkeep.flaky_test"]}, {"flaky-quarantine"})
        self.assertEqual((by["upkeep.waiver_expiring"][0]["due"], by["upkeep.waiver_expiring"][0]["route"]), ("2026-10-30", "waiver"))
        self.assertEqual((by["upkeep.runbook_stale"][0]["where"], by["upkeep.runbook_stale"][0]["route"]), ("docs/runbooks/RB-1.md", "runbook-drill"))
        # A runbook is listed once, as a runbook, never again as a doctor warning.
        self.assertFalse(any("RB-1" in i["what"] for i in by.get("upkeep.doctor_warning", [])))

    def test_what_is_not_due_is_not_listed(self):
        self.write("specs/SPEC-1.md", SPEC.format(sid="SPEC-1", route="normal", extra=FLAG.format(due="2027-01-01").lstrip("\n")))
        done = 'emergency = { severity = "sev2", kind = "outage", commander = "@ic", review_due = "2026-10-08", backfill = "specs/INC-1.md" }\n[outcome]\nlearn_ref = "docs/postmortems/PM-1.md"\n'
        self.write("specs/INC-1.md", SPEC.format(sid="INC-1", route="emergency", extra=done))
        cfg = self.root / ".aidd" / "config.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + RULES.format(until="2026-12-31"), encoding="utf-8")
        self.assertEqual(self.codes(), [])  # no events given: no flaky test either

    def test_a_library_standard_past_its_review_is_listed(self):
        with contextlib.chdir(self.root):
            code, out = run_cli("standard", "add", "python/uv-tooling")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.codes(), [])
        later = upkeep.items(self.root, today=TODAY + dt.timedelta(days=800))
        reviews = [i for i in later if i["code"] == "upkeep.standard_review"]
        self.assertEqual(len(reviews), 1, later)
        self.assertIn("python/uv-tooling", reviews[0]["what"])
        self.assertEqual(reviews[0]["route"], "standards-update")

    def test_the_cli_prints_json_with_its_schema_and_a_table(self):
        self.write("specs/SPEC-1.md", SPEC.format(sid="SPEC-1", route="normal", extra=FLAG.format(due="2026-09-01").lstrip("\n")))
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "a flag")
        with contextlib.chdir(self.root):
            code, out = run_cli("list", "--upkeep", "--json", "--events", str(EVENTS))
            self.assertEqual(code, 0, out)
            shown = json.loads(out)
            self.assertEqual(shown["schema_version"], "1")
            self.assertEqual(schema.validate(shown, "upkeep.schema.json"), [])
            self.assertIn("upkeep.flag_cleanup", {i["code"] for i in shown["items"]})
            self.assertIn("upkeep.flaky_test", {i["code"] for i in shown["items"]})
            code, out = run_cli("list", "--upkeep")
            self.assertEqual(code, 0, out)
            self.assertIn("| Upkeep | Where | Due | Route |", out)
            self.assertEqual(run_cli("list", "--events", str(EVENTS))[0], 2)  # --events goes with --upkeep


@unittest.skipUnless(shutil.which("git"), "git is required")
class OfflineTests(unittest.TestCase):
    """`aidd list --upkeep` reads files only: a URL parent in `extends` is never fetched, and one it cannot read is an
    upkeep item, never a crash."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = make_repo(Path(tmp.name).resolve() / "repo", branch=None)
        cfg = self.root / ".aidd" / "config.toml"
        parent = 'extends = [{ url = "https://example.invalid/aidd-org-preset.toml", sha256 = "' + "a" * 64 + '" }]\n'
        cfg.write_text(parent + cfg.read_text(encoding="utf-8"), encoding="utf-8")

    def test_a_url_parent_is_never_fetched_and_becomes_an_item(self):
        with (
            mock.patch.dict(os.environ, {"AIDD_OFFLINE": "0", "AIDD_HOOK_OFFLINE": "0"}),
            mock.patch("aidd.inputs.fetch_text", side_effect=AssertionError("upkeep reached the network")),
        ):
            found = upkeep.items(self.root, today=TODAY)
            self.assertEqual((os.environ["AIDD_OFFLINE"], os.environ["AIDD_HOOK_OFFLINE"]), ("0", "0"))  # restored
        unread = [i for i in found if i["code"] == "upkeep.config_unread"]
        self.assertEqual(len(unread), 1, found)
        self.assertIn("https://example.invalid/aidd-org-preset.toml", unread[0]["what"])
        self.assertEqual(schema.validate({"schema_version": "1", "items": found}, "upkeep.schema.json"), [])

    def test_aidd_offline_stops_every_config_fetch(self):
        from aidd import config as cfgmod

        with (
            mock.patch.dict(os.environ, {"AIDD_OFFLINE": "1"}),
            mock.patch("aidd.inputs.fetch_text", side_effect=AssertionError("a fetch under AIDD_OFFLINE=1")),
            self.assertRaises(Exception) as err,
        ):
            cfgmod.load_file(cfgmod.CONFIG_PATH, str(self.root))
        self.assertNotIsInstance(err.exception, AssertionError)


class MaintainCommandTests(unittest.TestCase):
    """`/aidd-team:maintain` runs the upkeep list on a rhythm and routes each item; it never decides for a person."""

    def setUp(self):
        self.text = (ROOT / "plugins" / "aidd-team" / "commands" / "maintain.md").read_text(encoding="utf-8")

    def test_it_is_a_flow_on_demand_that_preloads_nothing(self):
        flow = next(f for f in resources.roles()["loop"]["flows"] if f["command"] == "maintain")
        self.assertEqual((flow["runs"], flow["starts_on"]), ([["sre"]], []))
        self.assertIn("\ndisable-model-invocation: true\n", self.text.split("---")[1] + "\n")
        self.assertNotIn("!`", self.text)  # no shell output preloaded into the prompt
        self.assertIn("| `/aidd-team:maintain` |", (ROOT / "docs" / "TEAM.md").read_text(encoding="utf-8"))

    def test_it_routes_every_kind_and_decides_nothing(self):
        self.assertIn("aidd list --upkeep --json", self.text)
        for route in ("standards-update", "release-rollout", "postmortem", "flaky-quarantine", "waiver", "runbook-drill", "doctor"):
            self.assertIn(f"`{route}`", self.text, route)
        for target in ("aidd-team:dependency-upgrade", "aidd-team:release-rollout", "/aidd-team:postmortem", "/aidd-team:fix", "/aidd-team:specify"):
            self.assertIn(target, self.text, target)
        self.assertIn("Never decide for that person", self.text)
        self.assertEqual(set(upkeep.ROUTES), set(resources.load_json("upkeep.schema.json")["$defs"]["item"]["properties"]["code"]["enum"]))

    def test_the_method_names_maintain_without_touching_the_loop_contract(self):
        method = (ROOT / "docs" / "METHOD.md").read_text(encoding="utf-8")
        self.assertIn("**Maintain: the loop on a rhythm.**", method)
        self.assertNotIn("maintain", json.dumps(resources.roles()["loop"]["contract"]).lower())


if __name__ == "__main__":
    unittest.main()
