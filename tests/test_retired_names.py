"""schemas/retired-names.json: the table reads as its schema says and holds no row at the first release, and what reads it
(`kernel.retired_names`) and what edits a file by it (`kernel.yaml_edit`) behave on the boundary cases. The rows used here are made for
the tests (`made_up_row`), so no test reads a row of the table."""

import copy
import unittest
from unittest import mock

import helpers  # noqa: F401  (puts src on sys.path)
from helpers import made_up_row, only_rows

from aidd import config
from aidd.config import old_shape as config_old_shape
from aidd.kernel import json_schema, resources, retired_names, strict_yaml, yaml_edit
from aidd.setup import migrating
from aidd.workitems import old_shape as workitems_old_shape

SCHEMAS = {
    "config": "config.schema.json",
    "spec": "spec.schema.json",
    "intent": "intent.schema.json",
    "proposal": "proposal.schema.json",
    "runbook": "runbook.schema.json",
    "postmortem": "postmortem.schema.json",
    "release": "release.schema.json",
    "exploration": "exploration.schema.json",
    "handoff": "handoff.schema.json",
    "standard": "standard.schema.json",
}
ROWS = retired_names.rows()
RENAME = made_up_row("config-retries", "config", "limits.max_retries_old", "limits.max_task_retries", "rename")
RECORD = made_up_row("record-stamp", "record", "stamp", "recorded_at", "read_both")


def _described(node: dict, base: str, steps: list[tuple[str, bool]]) -> bool:
    """Whether `node` describes the key that `steps` name, through a `$ref` and the parts of an `allOf`."""
    if "$ref" in node:
        node, base = json_schema.resolve_ref(node["$ref"], base)
    if any(_described(part, base, steps) for part in node.get("allOf", [])):
        return True
    if not steps:
        return True
    (key, each), rest = steps[0], steps[1:]
    child = node.get("additionalProperties") if key == "*" else node.get("properties", {}).get(key)
    if not isinstance(child, dict):
        return False
    return _described(child.get("items", {}), base, rest) if each else _described(child, base, rest)


def schema_has(name: str, pattern: str) -> bool:
    """Whether the schema `name` describes the key `pattern` names (`a.b[].c`; `*` is any key of a mapping)."""
    return _described(resources.load_json(name), name, retired_names.pattern_steps(pattern))


class TheTable(unittest.TestCase):
    def test_the_file_holds_what_its_schema_says_and_no_row_at_the_first_release(self):
        table = resources.load_json("retired-names.json")
        self.assertEqual(json_schema.validate(table, "retired-names.schema.json"), [])
        self.assertEqual(table["retired"], [], "the first release carries no upgrade from a shape that existed only before it")

    def test_a_row_is_bad_when_its_rule_and_its_new_name_disagree(self):
        for changes in ({"rule": "cut"}, {"new": None}, {"rule": "value", "new": 3}, {"retired_in": "1.0"}, {"surface": "nowhere"}):
            with self.subTest(changes=changes):
                doc = {"description": "d", "retired": [{**RENAME, **changes}]}
                self.assertTrue(json_schema.validate(doc, "retired-names.schema.json"))

    def test_a_record_row_reads_both_names_and_no_other_row_does(self):
        good = [RECORD, {**RECORD, "read_as": {"a": "b"}}, {**RECORD, "read_as": {}}]
        bad = [
            {**RECORD, "rule": "rename"},  # a record is never renamed in its file
            {**RECORD, "surface": "config"},  # read_both is a record's
            {**RECORD, "new": None},
            {**RECORD, "read_as": {"approval": 3}},
            {**RENAME, "read_as": {"a": "b"}},  # read_as goes only with read_both
        ]
        for rows, wrong in ((good, False), (bad, True)):
            for row in rows:
                with self.subTest(row=row, wrong=wrong):
                    doc = {"description": "d", "retired": [row]}
                    self.assertEqual(bool(json_schema.validate(doc, "retired-names.schema.json")), wrong)

    def test_the_surfaces_are_the_ones_a_row_can_stand_in(self):
        surfaces = resources.load_json("retired-names.schema.json")["$defs"]["row"]["properties"]["surface"]["enum"]
        self.assertEqual(surfaces, [*SCHEMAS, "record", "cli_value", "standard_id"])
        self.assertEqual(set(migrating._READERS), set(SCHEMAS), "the upgrade has a reader for each surface a file holds")

    def test_each_id_is_one_row_and_the_rows_keep_the_order_the_schema_names(self):
        self.assertEqual(len({r["id"] for r in ROWS}), len(ROWS))
        surfaces = resources.load_json("retired-names.schema.json")["$defs"]["row"]["properties"]["surface"]["enum"]
        by_surface = [surfaces.index(r["surface"]) for r in ROWS]
        self.assertEqual(by_surface, sorted(by_surface), "rows are grouped by surface, in the schema's order")
        for surface in surfaces:
            olds = [r["old"] for r in ROWS if r["surface"] == surface]
            self.assertEqual(olds, sorted(olds), surface)

    def test_every_old_name_is_gone_from_the_schemas_and_every_new_one_is_there(self):
        for row in (r for r in ROWS if r["surface"] in SCHEMAS):
            with self.subTest(row=row["id"]):
                schema = SCHEMAS[row["surface"]]
                if row["old"] != row["new"]:  # a value row that changes only values keeps its key
                    self.assertFalse(schema_has(schema, row["old"]), f"{row['old']} is still in {schema}")
                if row["new"]:
                    self.assertTrue(schema_has(schema, row["new"]), f"{row['new']} is not in {schema}")

    def test_the_check_of_a_name_in_a_schema_tells_a_key_that_is_there_from_one_that_is_not(self):
        """The revert proof of the test above: it passes on an empty table, so its reading of a schema is shown here."""
        for pattern, there in {
            "limits.max_task_retries": True,
            "limits.max_retries_old": False,
            "tests[].reruns": True,
            "tests[].retries": False,
            "development_teams.*.approvers": True,
            "development_teams.*.people": False,
        }.items():
            with self.subTest(pattern):
                self.assertEqual(schema_has("config.schema.json", pattern), there)

    def test_a_value_row_has_its_function_and_a_function_has_its_row(self):
        value_ids = {r["id"] for r in ROWS if r["rule"] == "value"}
        self.assertEqual(value_ids, set(migrating.VALUES))
        self.assertEqual(set(config_old_shape._VALUES) | set(workitems_old_shape._VALUES), value_ids, "a reader of a value has a row")

    def test_a_standard_that_was_renamed_names_a_library_standard(self):
        from aidd.knowledge import standards

        for old, new in retired_names.standard_renames().items():
            self.assertIn(new, standards.standards_library(), old)
            self.assertNotIn(old, standards.standards_library(), old)


class ReadingThePaths(unittest.TestCase):
    DATA = {
        "project": {"rules": [{"level": "must"}, {"requirement_level": "may"}, {"level": "may", "id": "r"}]},
        "risks": {"rules": [{"level": "ask"}]},
        "teams": {"a": {"people": [1]}, "b": {}},
    }

    def test_a_pattern_names_the_places_that_hold_the_key(self):
        cases = {
            "project.rules[].level": [("project", "rules", 0, "level"), ("project", "rules", 2, "level")],
            "teams.*.people": [("teams", "a", "people")],
            "risks.rules[].level": [("risks", "rules", 0, "level")],
            "project.rules[].nothing": [],
            "nothing.here": [],
            "level": [],
        }
        for pattern, want in cases.items():
            with self.subTest(pattern=pattern):
                self.assertEqual(retired_names.paths_in(self.DATA, pattern), want)

    def test_a_key_with_the_name_of_a_retired_one_elsewhere_is_no_row(self):
        row = made_up_row("config-rule-level", "config", "project.rules[].level", "project.rules[].requirement_level", "rename")
        with only_rows(row):
            self.assertIsNotNone(retired_names.row_for("config", ("project", "rules", 0, "level")))
            for path in (("risks", "rules", 0, "level"), ("level",), ("project", "level")):
                with self.subTest(path=path):
                    self.assertIsNone(retired_names.row_for("config", path))
            self.assertIsNone(retired_names.row_for("spec", ("project", "rules", 0, "level")))


class TheLoadersNameTheReplacement(unittest.TestCase):
    """A config that still holds a retired name fails with the old name, the new one, and `aidd upgrade --yes`: never a default."""

    HEAD = 'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\n'

    def test_a_refusal_that_quotes_the_files_value_shows_no_credential_and_stays_on_one_line(self):
        """The invariant: a loader's message is printed to a terminal, a CI log, and an agent's context, and the value a refusal quotes
        is the repository's text. So no credential in it and no character that moves the cursor or the reading order gets through,
        whichever row's function wrote the refusal."""
        token = (
            "ghp_" + "a1B2c3D4e5" * 3 + "f6G7h8"
        )  # the shape of a token (36 characters after the prefix), joined here so no such literal sits in the repository
        password = "hunter2" + "pass"
        value = f"curl https://ci:{password}@example.com/x && GITHUB_TOKEN={token} ./run \u202e\u0007"
        row = made_up_row("config-check", "config", "limits.check_old", "limits.check", "value")

        def refuse_with_the_value(data: dict, path: retired_names.Path) -> None:
            raise retired_names.Refused(f"{strict_yaml.flow(data['limits']['check_old'])} is no name in `tests`")

        with only_rows(row), mock.patch.dict(config_old_shape._VALUES, {row["id"]: refuse_with_the_value}):
            with self.assertRaises(config.ConfigError) as caught:
                config.load_text(self.HEAD + f"limits:\n  check_old: {strict_yaml.flow(value)}\n")
        said = str(caught.exception)
        self.assertIn("leaves this one for a person", said, "the refusal is still named")
        for label, secret in {"the token": token, "the URL's password": password, "a bidi override": "\u202e", "a bell": "\u0007"}.items():
            with self.subTest(label):
                self.assertNotIn(secret, said)

        def refuse(data, path):
            raise retired_names.Refused(f"password={password} {token}\nsecond line")

        with only_rows(row):
            text = retired_names.explain("config", "$.limits: unknown field 'check_old'", {"limits": {"check_old": "x"}}, {row["id"]: refuse})
        self.assertNotIn(token, text)
        self.assertNotIn(password, text)
        self.assertNotIn("\n", text)


class ReadingAConfigAsToday(unittest.TestCase):
    """`config.todays_shape` reads every retired name of the config as its replacement, for a base commit never written."""

    def test_a_retired_name_is_read_as_its_replacement_and_a_name_the_upgrade_leaves_is_refused(self):
        with only_rows(RENAME):
            old = {"limits": {"max_retries_old": 2, "other": 1}}
            self.assertEqual(config.todays_shape(old), {"limits": {"max_task_retries": 2, "other": 1}})
            today = config.todays_shape({"limits": {"max_task_retries": 2}})
            self.assertEqual(config.todays_shape(today), today, "today's shape is read as it is")
            with self.assertRaises(retired_names.Refused):
                config.todays_shape({"limits": {"max_retries_old": 2, "max_task_retries": 3}})

    def test_the_text_of_today_is_returned_as_it_is_and_so_is_a_text_that_cannot_be_read(self):
        today = 'aidd_version: "1.0.0"\n# a comment\nprofile: team\n'
        both = "limits:\n  max_retries_old: 2\n  max_task_retries: 3\n"
        with only_rows(RENAME):
            self.assertEqual(config.in_todays_shape(both), both, "a refused name is not guessed at: the load that follows fails at it")
            self.assertEqual(config.in_todays_shape("limits:\n  max_retries_old: 2\n"), "limits:\n  max_task_retries: 2\n", "plain YAML, for a read")
            self.assertEqual(config.in_todays_shape(today), today)
            self.assertEqual(config.in_todays_shape("a: [unclosed"), "a: [unclosed")
        with only_rows():
            self.assertEqual(config.todays_shape({"limits": {"max_retries_old": 2}}), {"limits": {"max_retries_old": 2}}, "with no row it is read as written")


class ReadingARecordAsToday(unittest.TestCase):
    """`retired_names.todays_shape` on the `record` surface: a retired key or value is read as today's, in the place it stands."""

    ROWS = (RECORD, made_up_row("record-question-type", "record", "data.question.type", "data.question.type", "read_both", read_as={"approval": "yes_no"}))

    def read(self, record: dict) -> dict:
        with only_rows(*self.ROWS):
            return retired_names.todays_shape(record, "record", {})

    def test_a_retired_key_and_a_retired_value_are_read_as_todays_and_everything_else_stays(self):
        yes_no = {"data": {"question": {"type": "yes_no"}}}
        cases = {
            "the old key": ({"id": "i", "stamp": "t", "by": "b", "data": {}}, {"id": "i", "recorded_at": "t", "by": "b", "data": {}}),
            "the old value": ({"data": {"question": {"type": "approval", "text": "?"}}}, {"data": {"question": {"type": "yes_no", "text": "?"}}}),
            "both at once": ({"stamp": "t", "data": {"question": {"type": "approval"}}}, {"recorded_at": "t", **yes_no}),
            "today's names": ({"recorded_at": "t", **yes_no}, {"recorded_at": "t", **yes_no}),
            "a value this aidd does not know": ({"data": {"question": {"type": "ranking"}}}, {"data": {"question": {"type": "ranking"}}}),
            "a value that is no string": ({"data": {"question": {"type": ["approval"]}}}, {"data": {"question": {"type": ["approval"]}}}),
            "a question that is no mapping": ({"data": {"question": "approval"}}, {"data": {"question": "approval"}}),
            "a data that is no mapping": ({"data": [1]}, {"data": [1]}),
            "a `stamp` inside data": ({"data": {"stamp": "x"}}, {"data": {"stamp": "x"}}),
            "nothing": ({}, {}),
        }
        for name, (old, want) in cases.items():
            with self.subTest(case=name):
                before = copy.deepcopy(old)
                self.assertEqual(self.read(old), want)
                self.assertEqual(old, before, "the record that was read is not changed")
        with self.assertRaises(retired_names.Refused, msg="the new key beside the old: no one reading, so none is guessed"):
            self.read({"stamp": "old", "recorded_at": "new"})

    def test_a_record_reads_with_its_keys_where_it_was_written(self):
        record = {"id": "i", "type": "report", "stamp": "t", "by": "b", "data": {}}
        self.assertEqual(list(self.read(record)), ["id", "type", "recorded_at", "by", "data"])


class EditingYaml(unittest.TestCase):
    TEXT = (
        "a: 1\n# keep me\nproject:\n  repo: x   # c\n  rules:\n    - id: r1\n      level: must  # why\n    - level: should\n      id: r2\n"
        'delegation:\n  to: delegate\n  review_by: "2026-12-01"\n  note: |\n    kept\n"quoted-key": 2\nflow: {k: 1}\nlist:\n- one\n- two\nlast: 3\n'
    )

    def test_a_rename_changes_the_key_alone(self):
        cases = [
            ((("project", "rules", 0, "level"), "requirement_level"), "      level: must  # why", "      requirement_level: must  # why"),
            ((("project", "rules", 1, "level"), "requirement_level"), "    - level: should", "    - requirement_level: should"),
            ((("delegation", "review_by"), "review_due"), '  review_by: "2026-12-01"', '  review_due: "2026-12-01"'),
            ((("quoted-key",), "plain"), '"quoted-key": 2', "plain: 2"),
        ]
        for (path, new), before, after in cases:
            with self.subTest(path=path):
                got = yaml_edit.rename_key(self.TEXT, path, new)
                self.assertEqual(got, self.TEXT.replace(before, after, 1))
                strict_yaml.load(got)

    def test_a_cut_takes_the_key_and_what_is_under_it(self):
        cases = {
            ("project", "repo"): "  repo: x   # c\n",
            ("delegation", "to"): "  to: delegate\n",
            ("delegation", "note"): "  note: |\n    kept\n",
            ("list",): "list:\n- one\n- two\n",
            ("project", "rules", 0, "level"): "      level: must  # why\n",
        }
        for path, gone in cases.items():
            with self.subTest(path=path):
                got = yaml_edit.cut(self.TEXT, path)
                self.assertEqual(got, self.TEXT.replace(gone, "", 1))
                strict_yaml.load(got)

    def test_a_cut_on_a_dash_line_moves_the_next_key_up_and_an_only_key_stays(self):
        got = yaml_edit.cut(self.TEXT, ("project", "rules", 1, "level"))
        self.assertIn("    - id: r2\n", got)
        strict_yaml.load(got)
        only = "items:\n  - id: a\n  - type: x\n"
        self.assertIsNone(yaml_edit.cut(only, ("items", 1, "type")))

    def test_a_value_is_rewritten_on_its_line_and_its_comment_stays(self):
        text = 'a: 1\nrule:\n  check: smoke   # run by aidd test\n  q: "x"\n  b: [1]\n  c:\n    - d\n'
        got = yaml_edit.set_value(text, ("rule", "check"), ["smoke"])
        self.assertEqual(got, text.replace("check: smoke   #", "check: [smoke]   #"))
        self.assertEqual(yaml_edit.set_value(text, ("rule", "q"), "zed"), text.replace('q: "x"', "q: zed"))
        for path in (("rule", "b"), ("rule", "c"), ("rule", "nothing"), ("rule",)):
            with self.subTest(path=path):
                self.assertIsNone(yaml_edit.set_value(text, path, "z"))

    def test_the_only_key_of_a_mapping_leaves_the_mapping_empty(self):
        text = "project:   # the project\n  repo: x\nother: 1\n"
        self.assertEqual(yaml_edit.cut(text, ("project", "repo"), parent_empty=True), "project: {}  # the project\nother: 1\n")

    def test_a_key_that_has_no_line_of_its_own_is_left_alone(self):
        for path in (("flow", "k"), ("nothing",), ("project", "nothing"), ("list", 0)):
            with self.subTest(path=path):
                self.assertIsNone(yaml_edit.rename_key(self.TEXT, path, "z"))
                self.assertIsNone(yaml_edit.cut(self.TEXT, path))


if __name__ == "__main__":
    unittest.main()
