"""schemas/findings.json: the codes aidd gives when a check finds something, in one place. The registry reads as its schema
says, and it holds exactly the codes its owner's package can give: a code with no row, and a row with no use, both fail.
The shared definitions that go with it (`finding`, `error`, `blocked_by`) take what they should and refuse what they
should not."""

from __future__ import annotations

import ast
import unittest

from helpers import ROOT

from aidd.delegation import policy
from aidd.kernel import json_schema, resources

SRC = ROOT / "src" / "aidd"
# How each group's owner gives a code: the names of the calls whose first argument is the code, and what that code starts with.
# The delegate's calls give the bare code; every other group's give the full code through `findings.finding`. A new group names
# its own.
FINDING = ("findings.finding",)
GIVEN_BY = {
    "cli": (FINDING, "cli."),
    "config": (FINDING, "config."),
    "delegate": (("defer", "reason"), ""),
    "doctor": (FINDING, "doctor."),
    "status": (FINDING, "status."),
    "validate": (FINDING, "validate."),
}
URN = "urn:aidd:1:common#/$defs/"


def codes_given(source: str, calls: tuple[str, ...]) -> tuple[set[str], list[int]]:
    """The codes `source` gives through `calls`, and the lines where a call's first argument is no string literal, which a
    scan cannot read. A call is named by its method (`defer`) or by its module and name (`findings.finding`). A call inside a
    function of the same name forwards its caller's code, so it is no use of its own."""
    given: set[str] = set()
    unreadable: list[int] = []

    class Walk(ast.NodeVisitor):
        def __init__(self) -> None:
            self.inside: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.inside.append(node.name)
            self.generic_visit(node)
            self.inside.pop()

        def visit_Call(self, node: ast.Call) -> None:
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            owner = node.func.value.id if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) else ""
            if (name in calls or f"{owner}.{name}" in calls) and node.args and not (self.inside and self.inside[-1] in calls):
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    given.add(first.value)
                else:
                    unreadable.append(node.lineno)
            self.generic_visit(node)

    Walk().visit(ast.parse(source))
    return given, unreadable


def package_codes(owner: str, calls: tuple[str, ...]) -> tuple[set[str], list[str]]:
    given: set[str] = set()
    unreadable: list[str] = []
    for path in sorted((SRC / owner).rglob("*.py")):
        found, lines = codes_given(path.read_text(encoding="utf-8"), calls)
        given |= found
        unreadable += [f"{path.relative_to(ROOT)}:{n}" for n in lines]
    return given, unreadable


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = resources.load_json("findings.json")

    def test_the_registry_reads_as_its_schema_says(self):
        self.assertEqual(json_schema.validate(self.registry, "findings.schema.json"), [])

    def test_a_row_that_breaks_the_schema_is_refused(self):
        row = {"severity": "error", "title": "t", "why": "w.", "next": {"what": "n."}}
        cases = [
            ("whole", row, True),
            ("a severity that is no severity", {**row, "severity": "fatal"}, False),
            ("no title", {k: v for k, v in row.items() if k != "title"}, False),
            ("an empty title", {**row, "title": ""}, False),
            ("a next with a step code that is none", {**row, "next": {"what": "n.", "code": "spec.nope"}}, False),
            ("a key the format does not know", {**row, "data": {}}, False),
        ]
        for what, entry, valid in cases:
            with self.subTest(what):
                doc = {"description": "d", "groups": {"g": {"owner": "delegation", "description": "d", "codes": {"a_code": entry}}}}
                self.assertEqual(not json_schema.validate(doc, "findings.schema.json"), valid)
        for bad_group, bad_code in (("Bad", "a_code"), ("g", "A-Code"), ("g", "a.code")):
            with self.subTest(group=bad_group, code=bad_code):
                doc = {"description": "d", "groups": {bad_group: {"owner": "delegation", "description": "d", "codes": {bad_code: row}}}}
                self.assertTrue(json_schema.validate(doc, "findings.schema.json"))

    def test_each_group_names_a_package_and_how_it_gives_its_codes(self):
        self.assertEqual(sorted(self.registry["groups"]), sorted(GIVEN_BY), "a new group names how its owner gives a code")
        for name, group in self.registry["groups"].items():
            with self.subTest(group=name):
                self.assertTrue((SRC / group["owner"] / "__init__.py").is_file(), f"{group['owner']} is no package of aidd")
                self.assertTrue(group["codes"], "a group with no code is no group")

    def test_a_package_gives_the_codes_of_its_rows_and_no_others(self):
        """The one comparison, both ways, for each group: no code without a row, and no row without a use."""
        for name, group in self.registry["groups"].items():
            with self.subTest(group=name):
                calls, prefix = GIVEN_BY[name]
                given, unreadable = package_codes(group["owner"], calls)
                self.assertEqual(unreadable, [], "a code is a string literal, so the scan can read it")
                mine = {c.removeprefix(prefix) for c in given if c.startswith(prefix)}
                rows = set(group["codes"])
                self.assertEqual(sorted(mine - rows), [], "a code with no row")
                self.assertEqual(sorted(rows - mine), [], "a row with no use")
                self.assertGreater(len(mine), 40 if name == "delegate" else 0, "the scan reaches the calls")

    def test_a_full_code_is_given_only_by_the_package_that_owns_its_group(self):
        """`findings.finding` takes any full code, so a package could give another owner's code, or a code no group holds."""
        owners = {name: group["owner"] for name, group in self.registry["groups"].items()}
        for package in sorted(p.name for p in SRC.iterdir() if (p / "__init__.py").is_file()):
            with self.subTest(package=package):
                given, unreadable = package_codes(package, FINDING)
                self.assertEqual(unreadable, [], "a code is a string literal, so the scan can read it")
                for code in sorted(given):
                    self.assertEqual(owners.get(code.partition(".")[0]), package, f"{code} is not a code of a group that {package} owns")

    def test_the_scan_sees_a_missing_row_an_unused_row_and_a_code_it_cannot_read(self):
        source = (
            "def go(check, code):\n"
            "    check.defer('first', 'd')\n"
            "    policy.reason('second', 'd')\n"
            "    check.defer(code, 'd')\n"
            "    check.other('third')\n"
            "class C:\n"
            "    def defer(self, code, detail):\n"
            "        self.reasons.append(policy.reason(code, detail))\n"
        )
        given, unreadable = codes_given(source, ("defer", "reason"))
        self.assertEqual((sorted(given), unreadable), (["first", "second"], [4]))
        qualified = "findings.finding('a.b', 'm')\nplaceholders.finding('x', 'm')\nfindings.finding(code, 'm')\n"
        self.assertEqual(codes_given(qualified, FINDING), ({"a.b"}, [3]), "only the module's own call counts, by its qualified name")

    def test_the_delegate_group_says_whether_the_person_decides_and_stops_the_check(self):
        for code, row in policy.reasons().items():
            with self.subTest(code):
                self.assertIsInstance(row["reserved"], bool)
                self.assertEqual(row["severity"], "error", "every reason defers the ask")

    def test_every_full_code_fits_the_finding_shape_and_a_table_cell(self):
        for name, group in self.registry["groups"].items():
            for code, row in group["codes"].items():
                with self.subTest(code=f"{name}.{code}"):
                    finding = {"code": f"{name}.{code}", "severity": row["severity"], "message": row["why"]}
                    self.assertEqual(json_schema.validate(finding, URN + "finding"), [])
                    for text in (row["title"], row["why"], row["next"]["what"]):
                        self.assertNotRegex(text, r"[|\n]", "a generated table cell holds no pipe and no line break")
                    self.assertFalse(row["title"].endswith("."), "a title has no period")


class SharedDefinitionTests(unittest.TestCase):
    def test_a_finding_takes_its_members_and_refuses_the_rest(self):
        whole = {
            "code": "spec.frozen_test_changed",
            "severity": "warning",
            "message": "m",
            "path": "specs/S.md",
            "line": 3,
            "next": {"what": "w"},
            "data": {"id": "S"},
        }
        cases = [
            ("whole", whole, True),
            ("only the required members", {"code": "a.b", "severity": "note", "message": "m"}, True),
            ("no message", {"code": "a.b", "severity": "note"}, False),
            ("a code with no group", {**whole, "code": "bare"}, False),
            ("a code with two dots", {**whole, "code": "a.b.c"}, False),
            ("a severity that is a risk level", {**whole, "severity": "major"}, False),
            ("a line of zero", {**whole, "line": 0}, False),
            ("a member the shape does not know", {**whole, "level": "error"}, False),
        ]
        for what, finding, valid in cases:
            with self.subTest(what):
                self.assertEqual(not json_schema.validate(finding, URN + "finding"), valid)

    def test_an_error_wraps_one_finding_under_the_version(self):
        finding = {"code": "cli.no_repository", "severity": "error", "message": "m"}
        cases = [
            ("whole", {"schema_version": "1", "error": finding}, True),
            ("no version", {"error": finding}, False),
            ("another version", {"schema_version": "2", "error": finding}, False),
            ("no finding", {"schema_version": "1"}, False),
            ("a bad finding", {"schema_version": "1", "error": {"code": "x"}}, False),
        ]
        for what, error, valid in cases:
            with self.subTest(what):
                self.assertEqual(not json_schema.validate(error, URN + "error"), valid)

    def test_blocked_by_is_a_list_of_unique_ids_and_a_slice_uses_it(self):
        cases = [
            ([], True),
            (["SPEC-1"], True),
            (["SPEC-1", "SPEC-2"], True),
            (["SPEC-1", "SPEC-1"], False),
            (["spec 1"], False),
            ("SPEC-1", False),
        ]
        for value, valid in cases:
            with self.subTest(value=value):
                self.assertEqual(not json_schema.validate(value, URN + "blocked_by"), valid)
        slice_ = resources.load_json("common.schema.json")["$defs"]["slice"]["properties"]["blocked_by"]
        self.assertEqual(slice_["$ref"], "#/$defs/blocked_by")

    def test_a_next_step_carries_only_a_step_code(self):
        cases = [("spec.approve", True), ("nothing_open", True), ("spec.nope", False), ("", False)]
        for code, valid in cases:
            with self.subTest(code=code):
                self.assertEqual(not json_schema.validate({"what": "w", "code": code}, URN + "next"), valid)


if __name__ == "__main__":
    unittest.main()
