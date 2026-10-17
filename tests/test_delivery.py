"""Release separate from deploy, and a preview a person can see: a Spec's `flags` with an owner and a cleanup
date (`aidd validate` warns and `aidd list` shows the work once the date passes), the release-rollout skill's flags section,
the `preview` config the verifier starts from a clean checkout of the head, and the preview artifacts evidence may
list for people, which the gate never reads."""

import copy
import datetime as dt
import re
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, example, git, make_repo, open_work, package_source

from aidd import config
from aidd.workitems import validation
from aidd.workitems import authoring
from aidd.kernel import documents, json_schema, resources
from aidd.knowledge import team_registry

TEAM = ROOT / "plugins" / "aidd-team"
CFG = 'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@a"]\n'
TODAY = dt.date(2026, 9, 30)
FLAG = '\nflags:\n  - name: checkout-v2\n    default: "off"\n    owner: "@alice"\n    cleanup_due: "{due}"\n    purpose: release the new checkout apart from its deploy\n'


def spec_text(root: Path, sid: str, *, flag_due: str | None = None, removes: list[str] | None = None, status: str | None = None) -> Path:
    p = authoring.new_object(root, authoring.NewObject(kind="spec", id=sid, title="Checkout v2", owner_team="core", route="normal", today=dt.date(2026, 8, 1)))
    text = p.read_text(encoding="utf-8")
    head, sep, body = text.partition("\n---\n")
    top = ""
    if removes is not None:
        top += f"removes_flags: {removes!r}\n".replace("'", '"')
    if status:
        top += f"status: {status}\n"
    head = head.replace("\ntrace_id: ", "\n" + top + "trace_id: ", 1)
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

    def test_a_flag_is_optional_and_never_part_of_a_change_request(self):
        spec = resources.load_json("spec.schema.json")
        self.assertNotIn("flags", spec["required"])
        self.assertNotIn("flags", resources.load_json("change-request.schema.json").get("properties", {}))

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
            spec_text(Path(d), "SPEC-2", removes=["checkout-v2"])
            self.assertEqual([w for w in validation.check_repo(Path(d), today=TODAY)[1] if "flag" in w], [])
        with fresh() as d:  # a later Spec declares the flag again, with a later date: it extends it
            spec_text(Path(d), "SPEC-1", flag_due="2026-09-01")
            spec_text(Path(d), "SPEC-3", flag_due="2027-03-01")
            self.assertEqual([w for w in validation.check_repo(Path(d), today=TODAY)[1] if "flag" in w], [])

    def test_aidd_list_shows_an_overdue_flag_as_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp).resolve() / "repo", branch=None)
            spec_text(root, "SPEC-1", flag_due="2026-09-01")
            git(root, "add", "-A")
            git(root, "commit", "-qm", "SPEC-1")
            steps = [s for s in open_work(root, today=TODAY) if s["code"] == "flag.overdue"]
            self.assertEqual(len(steps), 1, steps)
            self.assertEqual((steps[0]["where"], steps[0]["id"], steps[0]["who"]), ("specs/SPEC-1.md", "SPEC-1", "@alice"))
            self.assertIn("checkout-v2", steps[0]["what"])
            self.assertEqual([s for s in open_work(root, today=dt.date(2026, 8, 30)) if s["code"] == "flag.overdue"], [])


class FlagPracticeTests(unittest.TestCase):
    def test_the_skill_is_wired_to_the_roles_that_decide_build_test_and_run_a_flag(self):
        roles = team_registry.roles()["roles"]
        self.assertLessEqual({"architect", "developer", "tester", "sre"}, {k for k, r in roles.items() if "release-rollout" in r["practices"]})
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

    def test_the_documented_flag_flip_is_held_for_a_person(self):
        from aidd.guard import held_commands

        doc = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
        block = next(b for b in re.findall(r"```yaml\n(.*?)```", doc, re.S) if "production flag flip" in b)
        cfg = config.load_text(CFG + block)
        self.assertIsNotNone(held_commands.held_command(cfg, "./scripts/flags set checkout-v2 on --env production", environ={}))
        self.assertIsNone(held_commands.held_command(cfg, "./scripts/flags set checkout-v2 on --env staging", environ={}))
        # The default config holds no command (tests/test_guard_hooks.py); the example lives in the config reference.
        self.assertIn("production flag flip", (ROOT / ".agents" / "skills" / "aidd" / "references" / "config.md").read_text(encoding="utf-8"))


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
            self.assertIn("# preview:", text)
            self.assertNotIn("preview", documents.parse_yaml(text, "config"))
            composed = Path(tmp) / "composed"
            composed.mkdir()
            (composed / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
            make_repo(composed, branch=None)
            data = documents.parse_yaml((composed / ".aidd" / "config.yaml").read_text(encoding="utf-8"), "config")
            self.assertEqual(data["preview"]["command"], ["docker", "compose", "up", "--build"])
            self.assertEqual(json_schema.validate(data, "config.schema.json"), [])


class PreviewEvidenceTests(unittest.TestCase):
    ARTIFACTS = [
        {"path": "preview/{sha}/a1-checkout.png", "kind": "screenshot", "sha256": "a" * 64},
        {"path": "preview/{sha}/main-flow.zip", "kind": "trace", "sha256": "b" * 64},
        {"path": "preview/{sha}/api.txt", "kind": "transcript", "sha256": "c" * 64},
    ]

    def test_the_previews_artifacts_json_lists_them(self):
        self.assertEqual(json_schema.validate(self.ARTIFACTS, "artifacts.schema.json"), [])
        for bad in (
            {"path": "x.png", "kind": "photo", "sha256": "a" * 64},
            {"path": "x.png", "kind": "screenshot"},
            {"path": "x.png", "kind": "video", "sha256": "xyz"},
        ):
            self.assertTrue(json_schema.validate([bad], "artifacts.schema.json"), bad)

    def test_evidence_holds_no_artifacts_and_the_gate_never_reads_them(self):
        ctx = example("02-normal-feature")
        self.assertTrue(json_schema.validate(dict(ctx["evidence"], artifacts=self.ARTIFACTS), "evidence.schema.json"))
        self.assertNotIn("artifacts", package_source("aidd.gate.rules"))


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
        self.assertIn("local preview", flow["stops_at"])

    def test_the_environment_ladder_and_the_recipes(self):
        platforms = (ROOT / "docs" / "PLATFORMS.md").read_text(encoding="utf-8")
        self.assertIn("## Environments: local preview first", platforms)
        howto = (ROOT / "docs" / "HOW-TO.md").read_text(encoding="utf-8")
        for q in ("**…ship behind a feature flag?**", "**…preview and verify a change locally?**"):
            self.assertIn(q, howto)
        self.assertIn("A flag is past its cleanup date", (ROOT / "docs" / "TROUBLESHOOTING.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
