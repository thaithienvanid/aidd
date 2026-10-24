"""The deprecation calendar across Specs: a Spec's `deprecations` (what, announced, sunset, replacement, consumers) and
the `removes_deprecations` of the Spec that removes one, mirroring `flags` and `removes_flags`.

A sunset that passed with no Spec that removes it warns in `aidd validate`, shows as an `aidd list` step and an upkeep
item, and appears among the overdue in `aidd digest`. `aidd digest --client` lists the whole calendar, and the release
notes say what each landed Spec deprecates. It is never a gate rule.
"""

import datetime as dt
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, git, make_repo, open_work

from aidd.kernel import documents, json_schema, resources
from aidd.tracking import status_rollup, upkeep
from aidd.workitems import authoring, due_dates, steps, validation

CFG = 'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@a"]\n'
TODAY = dt.date(2026, 9, 30)
DEPRECATION = (
    "\ndeprecations:\n"
    '  - what: "GET /v1/orders"\n'
    '    announced: "{announced}"\n'
    '    sunset: "{sunset}"\n'
    '    replacement: "GET /v2/orders"\n'
    '    consumers: ["mobile app", "partner feed"]\n'
)
REMOVAL = 'removes_deprecations: ["GET /v1/orders"]\n'


def spec(root: Path, sid: str, *, sunset: str | None = None, announced: str = "2026-06-01", removes: bool = False, status: str | None = None) -> Path:
    p = authoring.new_object(root, authoring.NewObject(kind="spec", id=sid, title="Orders v2", owner_team="core", route="normal", today=dt.date(2026, 8, 1)))
    head, sep, body = p.read_text(encoding="utf-8").partition("\n---\n")
    top = (REMOVAL if removes else "") + (f"status: {status}\n" if status else "")
    head = head.replace("\ntrace_id: ", "\n" + top + "trace_id: ", 1)
    if sunset:
        head += DEPRECATION.format(announced=announced, sunset=sunset).rstrip("\n")
    p.write_text(head + sep + body, encoding="utf-8")
    return p


def fresh() -> tempfile.TemporaryDirectory:
    d = tempfile.TemporaryDirectory()
    (Path(d.name) / ".aidd").mkdir()
    (Path(d.name) / ".aidd" / "config.yaml").write_text(CFG, encoding="utf-8")
    return d


def front(path: Path) -> dict:
    return documents.split_front_matter(path.read_text(encoding="utf-8"))[0]


class SchemaTests(unittest.TestCase):
    def test_a_deprecation_names_what_when_and_what_replaces_it(self):
        with fresh() as d:
            data = front(spec(Path(d), "SPEC-1", sunset="2026-12-01"))
            self.assertEqual(json_schema.validate(data, "spec.schema.json"), [])
            self.assertEqual(json_schema.validate(dict(data, removes_deprecations=["GET /v1/orders"]), "spec.schema.json"), [])
            for key in ("what", "announced", "sunset", "replacement"):
                with self.subTest(missing=key):
                    entry = {k: v for k, v in data["deprecations"][0].items() if k != key}
                    self.assertTrue(json_schema.validate(dict(data, deprecations=[entry]), "spec.schema.json"))
            entry = {k: v for k, v in data["deprecations"][0].items() if k != "consumers"}
            self.assertEqual(json_schema.validate(dict(data, deprecations=[entry]), "spec.schema.json"), [])  # consumers is optional
            for key, bad in (("sunset", "next quarter"), ("announced", "2026-02-30"), ("owner", "@a")):
                with self.subTest(bad=key):
                    self.assertTrue(json_schema.validate(dict(data, deprecations=[dict(data["deprecations"][0], **{key: bad})]), "spec.schema.json"))

    def test_the_fields_mirror_flags(self):
        props = resources.load_json("spec.schema.json")["properties"]
        self.assertEqual(props["removes_deprecations"]["items"], {"$ref": "#/$defs/deprecation_name"})
        self.assertTrue(props["removes_deprecations"]["uniqueItems"])
        for words in ("RFC 9745", "RFC 8594", "Never a gate rule"):
            self.assertIn(words, props["deprecations"]["description"])


class ValidateTests(unittest.TestCase):
    def found(self, *specs) -> tuple[list[str], list[str]]:
        with fresh() as d:
            for i, kw in enumerate(specs, 1):
                spec(Path(d), f"SPEC-{i}", **kw)
            errors, warnings = validation.check_repo(Path(d), today=TODAY)
            return [e for e in errors if "deprecation" in e], [w for w in warnings if "deprecation" in w]

    def test_a_passed_sunset_warns_and_names_the_removal_spec(self):
        self.assertEqual(
            self.found({"sunset": "2026-09-01"}),
            (
                [],
                [
                    "specs/SPEC-1.md: deprecation 'GET /v1/orders' passed its sunset on 2026-09-01; "
                    'write the Spec that removes it and lists it in removes_deprecations: ["GET /v1/orders"]'
                ],
            ),
        )

    def test_in_date_cancelled_removed_and_extended_are_quiet(self):
        self.assertEqual(self.found({"sunset": "2026-12-01"}), ([], []))
        self.assertEqual(self.found({"sunset": "2026-09-30"}), ([], []))  # sunset today: not yet passed
        self.assertEqual(self.found({"sunset": "2026-09-01", "status": "cancelled"}), ([], []))
        self.assertEqual(self.found({"sunset": "2026-09-01"}, {"removes": True, "status": "landed"}), ([], []))
        self.assertEqual(self.found({"sunset": "2026-09-01"}, {"sunset": "2027-03-01"}), ([], []))  # a later Spec extends it

    def test_a_draft_that_removes_it_names_itself_and_silences_nothing(self):
        _, warnings = self.found({"sunset": "2026-09-01"}, {"removes": True})
        self.assertEqual(
            warnings,
            [
                "specs/SPEC-1.md: deprecation 'GET /v1/orders' passed its sunset on 2026-09-01; take SPEC-2, which lists it in "
                "removes_deprecations, through Spec approval and land it: the removal counts once it lands"
            ],
        )
        # A draft's later sunset extends nothing once a landed Spec's sunset has passed.
        _, warnings = self.found({"sunset": "2026-09-01", "status": "landed"}, {"sunset": "2027-03-01"})
        self.assertEqual(len(warnings), 1, warnings)

    def test_the_suggested_removal_is_valid_yaml_whatever_the_name_holds(self):
        for what in ('GET /v1/orders?q="x"', "it's \\ odd", "naïve"):
            with self.subTest(what=what):
                line = due_dates.deprecation_removal({"what": what}).split(": ", 1)[1]
                self.assertEqual(documents.parse_yaml(f"removes_deprecations: {line}\n", "test")["removes_deprecations"], [what])

    def test_a_sunset_before_its_announcement_is_an_error(self):
        errors, _ = self.found({"sunset": "2026-05-01", "announced": "2026-06-01"})
        self.assertEqual(
            errors,
            [
                "specs/SPEC-1.md: deprecation 'GET /v1/orders' has sunset 2026-05-01 before announced 2026-06-01; "
                "the Sunset date is never earlier than the Deprecation date (RFC 9745), so set the sunset later"
            ],
        )

    def test_the_calendar_is_by_sunset(self):
        objects = [
            (
                "specs/SPEC-1.md",
                {"kind": "spec", "id": "SPEC-1", "deprecations": [{"what": "b", "sunset": "2027-01-01"}, {"what": "a", "sunset": "2026-11-01"}]},
            ),
            ("specs/SPEC-2.md", {"kind": "spec", "id": "SPEC-2", "status": "rolled_back", "deprecations": [{"what": "c", "sunset": "2026-10-01"}]}),
        ]
        self.assertEqual([dep["what"] for _, _, dep in due_dates.deprecation_calendar(objects)], ["a", "b"])
        self.assertEqual([dep["what"] for _, _, dep in due_dates.overdue_deprecations(objects, dt.date(2026, 12, 1))], ["a"])


@unittest.skipUnless(shutil.which("git"), "git is required")
class ListDigestAndNotesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.root = make_repo(Path(cls._tmp.name).resolve() / "repo", branch=None)
        spec(cls.root, "SPEC-1", sunset="2026-09-01")
        spec(cls.root, "SPEC-2", sunset="2026-12-01", announced="2026-09-15", status="landed")
        p = spec(cls.root, "SPEC-3", sunset="2027-06-01", announced="2026-12-01")
        p.write_text(p.read_text(encoding="utf-8").replace("GET /v1/orders", "order.total_cents"), encoding="utf-8")
        q = spec(cls.root, "SPEC-4", sunset="2026-11-01", status="landed")
        q.write_text(q.read_text(encoding="utf-8").replace("GET /v1/orders", "GET /v1/carts"), encoding="utf-8")
        git(cls.root, "add", "-A")
        git(cls.root, "commit", "-qm", "the deprecations", env=None)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_aidd_list_shows_a_passed_sunset_as_the_authors_step(self):
        # SPEC-1 and SPEC-2 deprecate the same thing: SPEC-2's later sunset extends it, so nothing is due yet.
        self.assertEqual([s for s in open_work(self.root, today=TODAY) if s["code"] == "deprecation.overdue"], [])
        found = [s for s in open_work(self.root, today=dt.date(2026, 11, 15)) if s["code"] == "deprecation.overdue"]
        self.assertEqual([(s["id"], s["where"]) for s in found], [("SPEC-4", "specs/SPEC-4.md")])
        self.assertEqual(found[0]["what"], "SPEC-4 deprecates GET /v1/carts, whose sunset passed on 2026-11-01")
        self.assertIn('lists it in removes_deprecations: ["GET /v1/carts"]', found[0]["how"])
        self.assertEqual(steps.STEP_CODES["deprecation.overdue"], steps.AUTHOR)

    def test_upkeep_routes_it_to_the_api_design_skill(self):
        objects = [(f"specs/SPEC-{i}.md", front(self.root / "specs" / f"SPEC-{i}.md")) for i in range(1, 5)]
        (item,) = upkeep.deprecation_sunsets(objects, dt.date(2026, 11, 15))
        self.assertEqual(
            (item["code"], item["route"], item["due"], item["where"]), ("upkeep.deprecation_removal", "api-design", "2026-11-01", "specs/SPEC-4.md")
        )
        shown = {"schema_version": "1", "items": upkeep.upkeep_items(self.root, today=dt.date(2026, 11, 15))}
        self.assertIn("upkeep.deprecation_removal", {i["code"] for i in shown["items"]})
        self.assertEqual(json_schema.validate(shown, "upkeep.schema.json"), [])

    def test_the_team_digest_lists_it_as_overdue(self):
        d = status_rollup.status_digest(self.root, "2026-09-01", today=dt.date(2026, 11, 15))
        self.assertEqual(d["overdue"]["deprecations"], ["SPEC-4 deprecates GET /v1/carts, whose sunset passed on 2026-11-01"])
        self.assertEqual(json_schema.validate(d, "digest.schema.json"), [])
        self.assertIn("- SPEC-4 deprecates GET /v1/carts, whose sunset passed on 2026-11-01", status_rollup.digest_markdown(d))

    def test_the_client_digest_shows_the_calendar(self):
        d = status_rollup.status_digest(self.root, "2026-09-01", client=True, today=dt.date(2026, 11, 15))
        self.assertEqual(json_schema.validate(d, "digest.schema.json"), [])
        # SPEC-3's is not announced until December, so the client does not see it yet.
        self.assertEqual(
            d["deprecations"],
            [
                {
                    "id": "SPEC-4",
                    "what": "GET /v1/carts",
                    "announced": "2026-06-01",
                    "sunset": "2026-11-01",
                    "replacement": "GET /v2/orders",
                    "passed": True,
                },
                {
                    "id": "SPEC-2",
                    "what": "GET /v1/orders",
                    "announced": "2026-09-15",
                    "sunset": "2026-12-01",
                    "replacement": "GET /v2/orders",
                    "passed": False,
                },
            ],
        )
        md = status_rollup.digest_markdown(d)
        self.assertIn("## Deprecations", md)
        self.assertIn("- GET /v1/carts stopped working on 2026-11-01 (announced 2026-06-01); use GET /v2/orders", md)
        self.assertIn("- GET /v1/orders stops working on 2026-12-01 (announced 2026-09-15); use GET /v2/orders", md)
        self.assertIn("GET /v1/orders stops working on 2026-12-01", status_rollup.digest_page(d))

    def test_a_draft_never_reaches_the_client_and_its_removal_counts_once_it_lands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_repo(Path(tmp).resolve() / "repo", branch=None)
            spec(root, "SPEC-1", sunset="2026-11-01", status="landed")
            p = spec(root, "SPEC-2", sunset="2027-06-01")  # a draft's plan: not announced to anyone yet
            p.write_text(p.read_text(encoding="utf-8").replace("GET /v1/orders", "GET /v1/carts"), encoding="utf-8")
            spec(root, "SPEC-3", removes=True)  # a draft that removes SPEC-1's: the endpoint still serves
            git(root, "add", "-A")
            git(root, "commit", "-qm", "the deprecations", env=None)
            later = dt.date(2026, 11, 15)
            d = status_rollup.status_digest(root, "2026-09-01", client=True, today=later)
            self.assertEqual([(x["id"], x["what"]) for x in d["deprecations"]], [("SPEC-1", "GET /v1/orders")])
            (step,) = [s for s in open_work(root, today=later) if s["code"] == "deprecation.overdue"]
            self.assertEqual(step["id"], "SPEC-1")
            self.assertIn("take SPEC-3, which lists it in removes_deprecations, through Spec approval and land it", step["how"])
            objects = [(f"specs/SPEC-{i}.md", front(root / "specs" / f"SPEC-{i}.md")) for i in range(1, 4)]
            self.assertEqual([i["where"] for i in upkeep.upkeep_items(root, today=later) if i["code"] == "upkeep.deprecation_removal"], ["specs/SPEC-1.md"])
            self.assertEqual(len(upkeep.deprecation_sunsets(objects, later)), 1)

    def test_a_client_with_no_deprecation_sees_no_section(self):
        d = status_rollup.status_digest(self.root, "2026-09-01", client=True, today=dt.date(2026, 5, 1))
        self.assertEqual(d["deprecations"], [])
        self.assertNotIn("## Deprecations", status_rollup.digest_markdown(d))

    def test_release_notes_say_what_a_spec_deprecates_and_removes(self):
        e = {
            "id": "SPEC-9",
            "title": "Orders v2",
            "intent": "",
            "flags": [],
            "removes_flags": [],
            "deprecations": [{"what": "GET /v1/orders", "sunset": "2026-12-01", "replacement": "GET /v2/orders"}],
            "removes_deprecations": ["GET /v1/carts"],
        }
        out = status_rollup.release_notes_markdown(
            {"audience": "developers", "window": {"since": "v1.0", "head": "abc"}, "groups": [{"name": "Changed", "entries": [e]}]}
        )
        self.assertIn("`GET /v1/orders` is deprecated: it stops working on 2026-12-01; use GET /v2/orders", out)
        self.assertIn("`GET /v1/carts` is removed, as its deprecation announced", out)

    def test_the_output_schemas_name_the_keys(self):
        digest = resources.load_json("digest.schema.json")
        self.assertIn("deprecations", digest["$defs"]["landed"]["required"])
        self.assertIn("removes_deprecations", digest["$defs"]["landed"]["required"])
        notes = resources.load_json("release-notes.schema.json")
        entry = notes["properties"]["groups"]["items"]["properties"]["entries"]["items"]
        self.assertLessEqual({"deprecations", "removes_deprecations"}, set(entry["required"]))


class GuidanceTests(unittest.TestCase):
    def test_the_api_asset_and_the_api_design_skill_point_to_the_field(self):
        api = (ROOT / ".agents" / "skills" / "aidd" / "assets" / "api.md").read_text(encoding="utf-8")
        section = api.split("## Versioning and deprecation", 1)[1].split("\n## ", 1)[0]
        for words in ("`deprecations`", "`removes_deprecations`", "RFC 9745", "RFC 8594"):
            self.assertIn(words, section)
        skill = ROOT / "plugins" / "aidd-team" / "skills" / "api-design"
        for text in ((skill / "SKILL.md").read_text(encoding="utf-8"), (skill / "references" / "graphql-grpc-webhooks.md").read_text(encoding="utf-8")):
            self.assertIn("`deprecations`", text)


if __name__ == "__main__":
    unittest.main()
