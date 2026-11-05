"""The deprecation calendar across Specs: a Spec's `deprecations` (what, announced, sunset, replacement, consumers) and
the `removes_deprecations` of the Spec that removes one, mirroring `flags` and `removes_flags`.

A sunset that passed with no Spec that removes it warns in `aidd validate` and shows in `aidd status` as work.
"""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd.kernel import documents, json_schema, resources
from aidd.workitems import authoring, due_dates, validation

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
    p = authoring.new_object(
        root, authoring.NewObject(item_type="spec", id=sid, title="Orders v2", owner_team="core", route="normal", today=dt.date(2026, 8, 1))
    )
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
        for words in ("RFC 9745", "RFC 8594", "`aidd validate` warns"):
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
        self.assertEqual(self.found({"sunset": "2026-09-01"}, {"removes": True, "status": "done"}), ([], []))
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
        # A draft's later sunset extends nothing once a merged Spec's sunset has passed.
        _, warnings = self.found({"sunset": "2026-09-01", "status": "done"}, {"sunset": "2027-03-01"})
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
                {"type": "spec", "id": "SPEC-1", "deprecations": [{"what": "b", "sunset": "2027-01-01"}, {"what": "a", "sunset": "2026-11-01"}]},
            ),
            ("specs/SPEC-2.md", {"type": "spec", "id": "SPEC-2", "status": "rolled_back", "deprecations": [{"what": "c", "sunset": "2026-10-01"}]}),
        ]
        self.assertEqual([dep["what"] for _, _, dep in due_dates.deprecation_calendar(objects)], ["a", "b"])
        self.assertEqual([dep["what"] for _, _, dep in due_dates.overdue_deprecations(objects, dt.date(2026, 12, 1))], ["a"])


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
