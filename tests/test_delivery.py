"""Release separate from deploy, and a preview a person can see: a Spec's `flags` with an owner and a cleanup
date (`aidd validate` warns and `aidd status` shows the work once the date passes), the release-rollout skill's flags section,
the `preview` config the verifier starts from a clean checkout of the head, and the preview artifacts evidence may
list for people."""

import copy
import datetime as dt
import re
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git, make_repo

from aidd import config
from aidd.workitems import validation
from aidd.workitems import authoring
from aidd.kernel import documents, json_schema, resources
from aidd.knowledge import team_registry

TEAM = ROOT / "plugins" / "aidd-team"
CFG = 'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@a"]\n'
TODAY = dt.date(2026, 9, 30)
FLAG = '\nflags:\n  - name: checkout-v2\n    default: "off"\n    owner: "@alice"\n    cleanup_due: "{due}"\n    purpose: release the new checkout apart from its deploy\n'


def work_due(root: Path, today: dt.date) -> list[dict]:
    """`aidd status`: what is past due, as the work list gives it."""
    from aidd import workitems

    cfg = config.load_file(config.CONFIG_PATH, str(root))
    return workitems.open_work(root, cfg, today=today)["due"]


def spec_text(root: Path, sid: str, *, flag_due: str | None = None, removes: list[str] | None = None, status: str | None = None) -> Path:
    p = authoring.new_object(root, authoring.NewObject(item_type="spec", id=sid, title="Checkout v2", route="normal", today=dt.date(2026, 8, 1)))
    text = p.read_text(encoding="utf-8")
    head, sep, body = text.partition("\n---\n")
    top = ""
    if removes is not None:
        top += f"removes_flags: {removes!r}\n".replace("'", '"')
    if status:
        top += f"status: {status}\n"
    head = head.replace("\nrollback: ", "\n" + top + "rollback: ", 1)
    if flag_due:
        head += FLAG.format(due=flag_due).rstrip("\n")
    p.write_text(head + sep + body, encoding="utf-8")
    return p


def fresh() -> tempfile.TemporaryDirectory:
    d = tempfile.TemporaryDirectory()
    (Path(d.name) / ".aidd").mkdir()
    (Path(d.name) / ".aidd" / "config.yaml").write_text(CFG, encoding="utf-8")
    return d


def front(text: str) -> dict:
    return documents.split_front_matter(text)[0]


class FlagSchemaTests(unittest.TestCase):
    def test_a_flag_names_its_default_owner_and_cleanup_date(self):
        with fresh() as d:
            p = spec_text(Path(d), "SPEC-1", flag_due="2026-12-01")
            data = front(p.read_text(encoding="utf-8"))
            self.assertEqual(json_schema.validate(data, "spec.schema.json"), [])
            self.assertEqual(data["flags"][0]["default"], "off")
            for key, bad in (("default", "maybe"), ("cleanup_due", "next quarter"), ("name", "Checkout V2")):
                broken = copy.deepcopy(data)
                broken["flags"][0][key] = bad
                self.assertTrue(json_schema.validate(broken, "spec.schema.json"), key)
            for key in ("name", "default", "owner", "cleanup_due"):
                broken = copy.deepcopy(data)
                del broken["flags"][0][key]
                self.assertTrue(json_schema.validate(broken, "spec.schema.json"), key)
            broken = copy.deepcopy(data)
            broken["flags"][0]["rollout"] = "10%"
            self.assertTrue(json_schema.validate(broken, "spec.schema.json"), "unknown key")
            self.assertEqual(json_schema.validate(dict(data, removes_flags=["checkout-v2"]), "spec.schema.json"), [])

    def test_a_flag_is_optional(self):
        spec = resources.load_json("spec.schema.json")
        self.assertNotIn("flags", spec["required"])

    def test_a_flag_owner_is_a_person(self):
        with fresh() as d:
            p = spec_text(Path(d), "SPEC-1", flag_due="2026-12-01")
            p.write_text(p.read_text(encoding="utf-8").replace('owner: "@alice"', "owner: agent:developer"), encoding="utf-8")
            errors = [e for e in validation.validate_file(p) if not e.startswith("warning: ")]
            self.assertTrue(any("flag checkout-v2" in e and "person" in e for e in errors), errors)


class OverdueFlagTests(unittest.TestCase):
    def warnings(self, **kw) -> list[str]:
        with fresh() as d:
            spec_text(Path(d), "SPEC-1", **kw)
            return [w for w in validation.check_repo(Path(d), today=TODAY)[1] if "flag" in w]

    def test_a_flag_past_its_cleanup_date_is_warned(self):
        self.assertEqual(
            self.warnings(flag_due="2026-09-01"),
            [
                "specs/SPEC-1.md: flag checkout-v2 was due for removal on 2026-09-01 (owner @alice); "
                'write the cleanup Spec that deletes it and lists it in removes_flags: ["checkout-v2"]'
            ],
        )

    def test_a_flag_in_date_a_cancelled_spec_and_a_removed_flag_are_quiet(self):
        self.assertEqual(self.warnings(flag_due="2026-12-01"), [])
        self.assertEqual(self.warnings(flag_due="2026-09-30"), [])  # due today: not yet overdue
        self.assertEqual(self.warnings(flag_due="2026-09-01", status="cancelled"), [])
        with fresh() as d:
            spec_text(Path(d), "SPEC-1", flag_due="2026-09-01")
            spec_text(Path(d), "SPEC-2", removes=["checkout-v2"], status="done")
            self.assertEqual([w for w in validation.check_repo(Path(d), today=TODAY)[1] if "flag" in w], [])

    def test_a_removal_counts_once_its_spec_has_landed(self):
        with fresh() as d:
            spec_text(Path(d), "SPEC-1", flag_due="2026-09-01")
            spec_text(Path(d), "SPEC-2", removes=["checkout-v2"])  # a draft: the flag is still in the code
            self.assertEqual(
                [w for w in validation.check_repo(Path(d), today=TODAY)[1] if "flag" in w],
                [
                    "specs/SPEC-1.md: flag checkout-v2 was due for removal on 2026-09-01 (owner @alice); take SPEC-2, which lists it in "
                    "removes_flags, through Spec approval and land it: the removal counts once it lands"
                ],
            )
        with fresh() as d:  # a later date in a draft extends nothing while a landed Spec's date has passed
            spec_text(Path(d), "SPEC-1", flag_due="2026-09-01", status="done")
            spec_text(Path(d), "SPEC-3", flag_due="2027-03-01")
            self.assertEqual(len([w for w in validation.check_repo(Path(d), today=TODAY)[1] if "flag checkout-v2" in w]), 1)
        with fresh() as d:  # a later Spec declares the flag again, with a later date: it extends it
            spec_text(Path(d), "SPEC-1", flag_due="2026-09-01")
            spec_text(Path(d), "SPEC-3", flag_due="2027-03-01")
            self.assertEqual([w for w in validation.check_repo(Path(d), today=TODAY)[1] if "flag" in w], [])

    def test_aidd_status_shows_an_overdue_flag_as_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp).resolve() / "repo", branch=None)
            spec_text(root, "SPEC-1", flag_due="2026-09-01")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "SPEC-1")
            due = work_due(root, TODAY)
            self.assertEqual(len(due), 1, due)
            self.assertEqual(due[0]["path"], "specs/SPEC-1.md")
            self.assertIn("checkout-v2", due[0]["what"])
            self.assertEqual(due[0]["next"]["code"], "flag.overdue")
            self.assertEqual(work_due(root, dt.date(2026, 8, 30)), [])


class FlagPracticeTests(unittest.TestCase):
    def test_the_skill_is_wired_to_the_roles_that_decide_build_test_and_run_a_flag(self):
        roles = team_registry.roles()["roles"]
        self.assertLessEqual({"architect", "developer", "verifier", "sre"}, {k for k, r in roles.items() if "release-rollout" in r["practices"]})
        self.assertFalse((TEAM / "skills" / "feature-flags").exists(), "the flags are a section of release-rollout")
        text = (TEAM / "skills" / "release-rollout" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("## Feature flags", text)
        head = text.split("---")[1]
        desc = re.search(r'^description: "(.*)"$', head, re.M)
        assert desc
        self.assertLessEqual(len(desc.group(1)), 200)
        self.assertIn("in an aidd repository ", desc.group(1))
        for must in ("OpenFeature", "flagd", "default off", "kill switch", "cleanup", "not authorization", "both states", "removes_flags"):
            self.assertIn(must.lower(), text.lower(), must)


class PreviewConfigTests(unittest.TestCase):
    def test_the_preview_section(self):
        base = documents.parse_yaml(CFG, "config")
        good = dict(base, preview={"command": ["docker", "compose", "up", "--build"], "url": "http://localhost:3000"})
        self.assertEqual(json_schema.validate(good, "config.schema.json"), [])
        self.assertTrue(json_schema.validate(dict(base, preview={"url": "http://localhost:3000"}), "config.schema.json"), "command is required")
        self.assertTrue(json_schema.validate(dict(base, preview={"command": "docker compose up"}), "config.schema.json"), "a vector")
        self.assertTrue(json_schema.validate(dict(base, preview={"command": ["x"], "port": 3000}), "config.schema.json"), "unknown key")

    def test_init_fills_it_only_when_obvious(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = make_repo(Path(tmp) / "plain", branch=None)
            text = (plain / ".aidd" / "config.yaml").read_text(encoding="utf-8")
            self.assertNotIn("preview", text, "init writes only the keys it sets")
            self.assertNotIn("preview", documents.parse_yaml(text, "config"))
            composed = Path(tmp) / "composed"
            composed.mkdir()
            (composed / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
            make_repo(composed, branch=None)
            data = documents.parse_yaml((composed / ".aidd" / "config.yaml").read_text(encoding="utf-8"), "config")
            self.assertEqual(data["preview"]["command"], ["docker", "compose", "up", "--build"])
            self.assertEqual(json_schema.validate(data, "config.schema.json"), [])


class PreviewPlaybookTests(unittest.TestCase):
    def test_the_verifier_records_preview_evidence_on_the_exact_head(self):
        verifier = team_registry.roles()["roles"]["verifier"]
        text = (TEAM / "agents" / "verifier.md").read_text(encoding="utf-8")
        for words in (".aidd/evidence/preview/", "worktree", "`preview`"):
            self.assertIn(words, text, words)
            self.assertIn(words, verifier["does"] + verifier["done_when"] + verifier["hands_off"] + text, words)
        self.assertIn(".aidd/evidence/preview/", verifier["hands_off"])

    def test_day_zero_sets_up_the_local_preview(self):
        mvp = (TEAM / "commands" / "mvp.md").read_text(encoding="utf-8")
        self.assertIn("`preview`", mvp)
        self.assertIn("seed data", mvp)
        self.assertIn("already has hosting", mvp)
        flow = next(f for f in team_registry.roles()["loop"]["flows"] if f["command"] == "mvp")
        self.assertIn("local preview", flow["stops_when"])

    def test_autopilot_takes_the_first_matching_path_so_a_request_in_an_empty_repository_is_the_mvp(self):
        """The rule "When two paths fit, ask" stopped every headless run on a request at "fast lane or MVP?". The paths are
        tried in order, the MVP before the fix, and a question comes only when the files don't decide."""
        sort = (TEAM / "commands" / "autopilot.md").read_text(encoding="utf-8").split("0. **Sort the request by size.**", 1)[1].split("\n1. ", 1)[0]
        paths = [line for line in sort.splitlines() if re.match(r"   \d\. ", line)]
        order = [
            next(i for i, line in enumerate(paths) if flow in line) for flow in ("/aidd-team:mvp", "/aidd-team:fix", "/aidd-team:specify", "/aidd-team:plan")
        ]
        self.assertEqual(order, sorted(order), "a question, a new product, a minor fix, one change, then a plan")
        self.assertIn("/aidd-team:plan", paths[-1], "the last paths are plans: one goal bigger than one Spec, then several goals")
        self.assertIn("several goals", paths[-1].lower())
        # The MVP's first stage starts only the product manager, and its first stop is the person's agreement to the plan.
        mvp = (TEAM / "commands" / "mvp.md").read_text(encoding="utf-8").split("1. **The plan.**", 1)[1].split("\n2. ", 1)[0]
        self.assertEqual(set(re.findall(r"aidd-team:[a-z-]+", mvp)), {"aidd-team:product-manager"})
        flow = next(f for f in team_registry.roles()["loop"]["flows"] if f["command"] == "mvp")
        self.assertRegex(flow["stops_when"].split(": ", 1)[1], r"^a person agrees to the plan")


if __name__ == "__main__":
    unittest.main()
