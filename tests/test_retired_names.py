"""schemas/retired-names.json: every row is true of today's schemas, the table reads as its schema says, and what reads it
(`kernel.retired_names`) and what edits a file by it (`kernel.yaml_edit`) behave on the boundary cases."""

import copy
import unittest

import helpers  # noqa: F401  (puts src on sys.path)

from aidd import config
from aidd.kernel import json_schema, resources, retired_names, strict_yaml, yaml_edit
from aidd.setup import migrating

SCHEMAS = {
    "config": "config.schema.json",
    "spec": "spec.schema.json",
    "intent": "intent.schema.json",
    "proposal": "proposal.schema.json",
    "runbook": "runbook.schema.json",
    "postmortem": "postmortem.schema.json",
    "exploration": "exploration.schema.json",
    "handoff": "handoff.schema.json",
    "standard": "standard.schema.json",
}
ROWS = retired_names.rows()
# A list that a later row moved: the keys an earlier row renamed in it stand at its new place (an Intent's `slices[]` is `phases[].slices[]`).
MOVED = {"intent": {"slices[]": "phases[].slices[]"}}


def at_its_place_now(surface: str, name: str) -> str:
    return next((new + name[len(old) :] for old, new in MOVED.get(surface, {}).items() if name.startswith(old)), name)


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
    def test_the_file_holds_what_its_schema_says(self):
        self.assertEqual(json_schema.validate(resources.load_json("retired-names.json"), "retired-names.schema.json"), [])

    def test_a_row_is_bad_when_its_rule_and_its_new_name_disagree(self):
        row = dict(next(r for r in ROWS if r["rule"] == "rename"))
        for changes in ({"rule": "cut"}, {"new": None}, {"rule": "value", "new": 3}, {"retired_in": "1.0"}, {"surface": "nowhere"}):
            with self.subTest(changes=changes):
                doc = {"description": "d", "retired": [{**row, **changes}]}
                self.assertTrue(json_schema.validate(doc, "retired-names.schema.json"))

    def test_a_record_row_reads_both_names_and_no_other_row_does(self):
        record = dict(next(r for r in ROWS if r["id"] == "record-question-type-approval"))
        rename = dict(next(r for r in ROWS if r["rule"] == "rename"))
        good = [record, {**record, "read_as": {"a": "b"}}, {**record, "read_as": {}}]
        bad = [
            {**record, "rule": "rename"},  # a record is never renamed in its file
            {**record, "surface": "config"},  # read_both is a record's
            {**record, "new": None},
            {**record, "read_as": {"approval": 3}},
            {**rename, "read_as": {"a": "b"}},  # read_as goes only with read_both
        ]
        for rows, wrong in ((good, False), (bad, True)):
            for row in rows:
                with self.subTest(row=row, wrong=wrong):
                    doc = {"description": "d", "retired": [row]}
                    self.assertEqual(bool(json_schema.validate(doc, "retired-names.schema.json")), wrong)

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
                    self.assertTrue(schema_has(schema, at_its_place_now(row["surface"], row["new"])), f"{row['new']} is not in {schema}")

    def test_a_rename_keeps_the_parent_and_a_value_row_has_its_function(self):
        for row in ROWS:
            if row["rule"] == "rename":
                self.assertEqual(
                    row["old"].rsplit(".", 1)[0] if "." in row["old"] else "", row["new"].rsplit(".", 1)[0] if "." in row["new"] else "", row["id"]
                )
        # An `experiment` is only ever refused (a person moves it), so the upgrade needs no edit for it: the shared reading's refusal is its row.
        self.assertEqual({r["id"] for r in ROWS if r["rule"] == "value"}, set(migrating.VALUES) | {"spec-experiment"})

    def test_a_standard_that_was_renamed_names_a_library_standard(self):
        from aidd.knowledge import standards

        for old, new in retired_names.standard_renames().items():
            self.assertIn(new, standards.standards_library(), old)
            self.assertNotIn(old, standards.standards_library(), old)

    def test_a_retired_flag_is_hidden_in_its_command_and_what_replaced_it_is_listed(self):
        import argparse

        from aidd.cli import parser

        commands = next(a for a in parser.build_parser()._actions if isinstance(a, argparse._SubParsersAction)).choices
        for row in retired_names.rows("cli_flag"):
            holders = [c for c in commands.values() if row["old"] in c._option_string_actions]
            with self.subTest(row=row["id"]):
                self.assertTrue(holders, f"no command takes {row['old']}")
                for command in holders:
                    self.assertEqual(command._option_string_actions[row["old"]].help, argparse.SUPPRESS)
                    self.assertIn(row["new"], command._option_string_actions)
                    self.assertNotEqual(command._option_string_actions[row["new"]].help, argparse.SUPPRESS)


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
        self.assertIsNotNone(retired_names.row_for("config", ("project", "rules", 0, "level")))
        for path in (("risks", "rules", 0, "level"), ("level",), ("project", "level")):
            with self.subTest(path=path):
                self.assertIsNone(retired_names.row_for("config", path))
        self.assertIsNone(retired_names.row_for("spec", ("project", "rules", 0, "level")))

    def test_an_error_for_an_old_name_says_what_replaced_it(self):
        cases = [
            (
                "config",
                "$.mcp: unknown field 'approve_own_tools'. Did you mean `allow_own_tools`?",
                "`mcp.approve_own_tools` was retired in 1.0.0; it is now `allow_own_tools`",
            ),
            ("config", "$.project.rules[1]: unknown field 'level'", "`project.rules[1].level` was retired in 1.0.0; it is now `requirement_level`"),
            ("config", "$.owners: unknown field 'default_owner_team'", "`aidd new` names no team on its own"),
            ("spec", "$: unknown field 'uat'", "it is now `manual_acceptance`. `aidd upgrade --yes` renames it"),
            ("spec", "$: unknown field 'blockers'", "it is now `waiting_on`"),
            ("spec", "$: unknown field 'assisted_by'", "The `Assisted-by` trailer of each commit says which agent wrote it"),
            ("spec", "$: unknown field 'relations'", "A Spec lists the work it waits for in `blocked_by`"),
            ("spec", "$: unknown field 'residual_risk'", "`aidd upgrade --yes` moves it"),
            ("exploration", "$: unknown field 'evidence'", "it is now `basis`. `aidd upgrade --yes` renames it"),
            ("proposal", "$.claims[0]: unknown field 'evidence'", "`claims[0].evidence` was retired in 1.0.0; it is now `basis`"),
            ("proposal", "$: unknown field 'owner_team'", "it is now `delivery_team`. `aidd upgrade --yes` renames it"),
            ("runbook", "$: unknown field 'restore'", "it is now `restores_data`. `aidd upgrade --yes` renames it"),
            ("postmortem", "$: unknown field 'owner_team'", "it is now `delivery_team`"),
        ]
        for surface, error, said in cases:
            with self.subTest(error=error):
                out = retired_names.explain(surface, error)
                self.assertIn(said, out)
                self.assertNotIn("Did you mean", out)
        for surface, error in [
            ("config", "$.mcp: unknown field 'typo'"),
            ("spec", "$.mcp: unknown field 'approve_own_tools'"),
            ("config", "$.profile: must be one of solo, team"),
        ]:
            with self.subTest(error=error):
                self.assertEqual(retired_names.explain(surface, error), error)

    def test_a_retired_value_and_a_key_held_under_its_old_name_say_so_and_any_other_error_stays_alone(self):
        """With the file's data, a value error at a key whose `value` row moves the value names the row, and a missing key that an old
        name beside it holds says that name. A value the row leaves alone, such as a typo, and a missing key with no old name keep
        the error as it is."""
        from aidd.workitems import old_shape

        enum = "$.change_type: must be one of feat, fix; got "
        risk = {"summary": "s", "dimensions": []}
        cases = [
            ("spec", enum + '"security"', {"change_type": "security", "risk": risk}, "`change_type: security` was retired in 1.0.0"),
            ("spec", enum + '"deps"', {"change_type": "deps", "risk": risk}, "`aidd upgrade --yes` moves it"),
            ("spec", enum + '"security"', {"change_type": "security"}, "`aidd upgrade --yes` leaves this one for a person"),
            ("runbook", "$: missing required field 'delivery_team'", {"owner_team": "core"}, "`owner_team` holds it under the name retired in 1.0.0"),
        ]
        for surface, error, data, said in cases:
            with self.subTest(error=error, data=data):
                out = old_shape.explained(surface, error, data)
                self.assertTrue(out.startswith(error), out)
                self.assertIn(said, out)
        for surface, error, data in [
            ("spec", enum + '"feet"', {"change_type": "feet", "risk": risk}),
            ("spec", '$.route: must be one of normal, major; got "minor"', {"route": "minor"}),
            ("runbook", "$: missing required field 'delivery_team'", {"service": "x"}),
            ("runbook", "$: missing required field 'service'", {"owner_team": "core"}),
        ]:
            with self.subTest(error=error, data=data):
                self.assertEqual(old_shape.explained(surface, error, data), error)
        self.assertEqual(retired_names.explain("spec", enum + '"security"'), enum + '"security"', "without the data, a value error stays alone")

    def test_the_config_load_error_names_the_row(self):
        text = 'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\nmcp:\n  approve_own_tools: false\n'
        with self.assertRaises(config.ConfigError) as caught:
            config.load_text(text)
        self.assertIn("`aidd upgrade --yes` renames it", str(caught.exception))


class TheLoadersNameTheReplacement(unittest.TestCase):
    """A config or a Spec that still holds a retired name fails with the old name, the new one, and `aidd upgrade --yes`: never a default."""

    HEAD = 'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\n'
    RULE = '  rules:\n    - id: r\n      requirement_level: must\n      statement: s\n      why: w\n      owner: "@x"\n'
    CASES = {
        "a test command's retries": ("tests:\n  - name: t\n    command: [a]\n    retries: 1\n", "`tests[0].retries` was retired in 1.0.0; it is now `reruns`"),
        "the dev services": ("project:\n  dev_services:\n    up: [a]\n", "`project.dev_services` was retired in 1.0.0"),
        "a project rule's applies": (
            "project:\n" + RULE + '      applies: ["src/**"]\n',
            "`project.rules[0].applies` was retired in 1.0.0; it is now `when_changed`",
        ),
        "a project rule's check": ("project:\n" + RULE + "      check: t\n", "`project.rules[0].check` was retired in 1.0.0"),
        "a waiver's approved_by": (
            "project:\n" + RULE + '  waivers:\n    - rule: r\n      reason: x\n      approved_by: "@x"\n      until: "2099-01-01"\n',
            "`project.waivers[0].approved_by` was retired in 1.0.0; it is now `granted_by`",
        ),
    }

    def test_a_config_with_a_retired_key_stops_at_it(self):
        for name, (extra, said) in self.CASES.items():
            with self.subTest(name), self.assertRaises(config.ConfigError) as caught:
                config.load_text(self.HEAD + extra)
            self.assertIn(said, str(caught.exception))
            self.assertIn("`aidd upgrade --yes`", str(caught.exception))

    def test_a_refusal_that_quotes_the_files_value_shows_no_credential_and_stays_on_one_line(self):
        """The invariant: a loader's message is printed to a terminal, a CI log, and an agent's context, and the value a refusal quotes
        is the repository's text. So no credential in it and no character that moves the cursor or the reading order gets through,
        whichever row's function wrote the refusal."""
        token = (
            "ghp_" + "a1B2c3D4e5" * 3 + "f6G7h8"
        )  # the shape of a token (36 characters after the prefix), joined here so no such literal sits in the repository
        password = "hunter2" + "pass"
        value = f"curl https://ci:{password}@example.com/x && GITHUB_TOKEN={token} ./run \u202e\u0007"
        with self.assertRaises(config.ConfigError) as caught:
            config.load_text(self.HEAD + "project:\n" + self.RULE + f"      check: {strict_yaml.flow(value)}\n")
        said = str(caught.exception)
        self.assertIn("leaves this one for a person", said, "the refusal is still named")
        for label, secret in {"the token": token, "the URL's password": password, "a bidi override": "\u202e", "a bell": "\u0007"}.items():
            with self.subTest(label):
                self.assertNotIn(secret, said)
        # the same holds for any row: a row's function that raises with a credential in its text
        row = next(r for r in retired_names.rows("config") if r["id"] == "project-rule-check")

        def refuse(data, path):
            raise retired_names.Refused(f"password={password} {token}\nsecond line")

        text = retired_names.explain("config", "$.project.rules[0]: unknown field 'check'", {"project": {"rules": [{"check": "x"}]}}, {row["id"]: refuse})
        self.assertNotIn(token, text)
        self.assertNotIn(password, text)
        self.assertNotIn("\n", text)

    def test_a_spec_with_a_retired_test_key_is_refused_by_name(self):
        from aidd.workitems import spec_file

        text = (
            '---\naidd_version: "1.0.0"\ntype: spec\nid: SPEC-1\ntitle: T\nchange_type: feat\nroute: normal\nconfidence: high\n'
            "risk:\n  summary: s\n  dimensions: []\n  irreversible: false\nrollback: r\nassisted_by: []\ntasks:\n  - id: T1\n    title: t\n    scope: [a/]\n    risk: low\n    proof: p\n"
            "tests:\n  files: [t.py]\n  commands:\n    - name: c\n      command: [a]\n      retries: 1\n---\n\n## Request\n\nx\n"
        )
        _, _, errors = spec_file.load_object(text, "specs/SPEC-1.md")
        self.assertTrue(any("`tests.commands[0].retries` was retired in 1.0.0; it is now `reruns`" in e for e in errors), errors)


class ReadingAnOldConfigAsToday(unittest.TestCase):
    """`config.todays_shape` reads every retired name of the config as its replacement, for a base commit never written."""

    def test_each_config_row_moves_the_value_it_held(self):
        old = {
            "tests": [{"name": "t", "command": ["a"], "retries": 2}],
            "project": {
                "repo": "x",
                "dev_services": {"up": ["a"]},
                "rules": [{"id": "r", "level": "must", "applies": ["a/**"], "check": "t"}, {"id": "q", "level": "may"}],
                "waivers": [{"rule": "r", "approved_by": "@x"}],
            },
            "environments": [{"name": "production", "branches": ["main"]}],
            "delegation": {"to": "delegate", "review_by": "2027-01-01", "default_branch": "main", "default_branch_deploys": True},
            "delivery_teams": {"core": {"people": ["@x"], "intents": ["INT-1"]}},
            "docs": {"required": {"authz": "off", "runbook": "warn"}},
            "mcp": {"approve_own_tools": False},
        }
        want = {
            "tests": [{"name": "t", "command": ["a"], "reruns": 2}],
            "project": {
                "rules": [{"id": "r", "requirement_level": "must", "when_changed": ["a/**"], "enforced_by": ["t"]}, {"id": "q", "requirement_level": "may"}],
                "waivers": [{"rule": "r", "granted_by": "@x"}],
            },
            "environments": [{"name": "production", "branches": ["main"]}],
            "delegation": {"review_due": "2027-01-01", "default_branch": "main"},
            "delivery_teams": {"core": {"approvers": ["@x"]}},
            "docs": {"disabled": {"authz-matrix": config.DISABLED_REASON}},
            "mcp": {"allow_own_tools": False},
        }
        self.assertEqual(config.todays_shape(old), want)
        self.assertEqual(config.todays_shape(want), want, "today's shape is read as it is")

    def test_a_name_the_upgrade_leaves_is_refused_and_the_text_of_today_is_returned_as_it_is(self):
        for name, held in {
            "a name beside its replacement": {"mcp": {"approve_own_tools": True, "allow_own_tools": False}},
            "a rule's check that names no test": {"project": {"rules": [{"id": "q", "check": "make lint"}]}},
        }.items():
            with self.subTest(name), self.assertRaises(retired_names.Refused):
                config.todays_shape(held)
        text = "mcp:\n  approve_own_tools: true\n  allow_own_tools: false\n"
        self.assertEqual(config.in_todays_shape(text), text, "a refused name is not guessed at: the load that follows fails at it")
        today = 'aidd_version: "1.0.0"\n# a comment\nprofile: team\n'
        self.assertEqual(config.in_todays_shape(today), today)
        self.assertEqual(config.in_todays_shape("a: [unclosed"), "a: [unclosed")


class ReadingARecordAsToday(unittest.TestCase):
    """`retired_names.todays_shape` on the `record` surface: a retired key or value is read as today's, in the place it stands."""

    def read(self, record: dict) -> dict:
        return retired_names.todays_shape(record, "record", {})

    def test_a_retired_key_and_a_retired_value_are_read_as_todays_and_everything_else_stays(self):
        yes_no = {"data": {"question": {"type": "yes_no"}}}
        cases = {
            "the old key": ({"id": "i", "at": "t", "by": "b", "data": {}}, {"id": "i", "recorded_at": "t", "by": "b", "data": {}}),
            "the old value": ({"data": {"question": {"type": "approval", "text": "?"}}}, {"data": {"question": {"type": "yes_no", "text": "?"}}}),
            "both at once": ({"at": "t", "data": {"question": {"type": "approval"}}}, {"recorded_at": "t", **yes_no}),
            "today's names": ({"recorded_at": "t", **yes_no}, {"recorded_at": "t", **yes_no}),
            "a value this aidd does not know": ({"data": {"question": {"type": "ranking"}}}, {"data": {"question": {"type": "ranking"}}}),
            "a value that is no string": ({"data": {"question": {"type": ["approval"]}}}, {"data": {"question": {"type": ["approval"]}}}),
            "a question that is no mapping": ({"data": {"question": "approval"}}, {"data": {"question": "approval"}}),
            "a data that is no mapping": ({"data": [1]}, {"data": [1]}),
            "an `at` inside data": ({"data": {"at": "x"}}, {"data": {"at": "x"}}),
            "nothing": ({}, {}),
        }
        for name, (old, want) in cases.items():
            with self.subTest(case=name):
                before = copy.deepcopy(old)
                self.assertEqual(self.read(old), want)
                self.assertEqual(old, before, "the record that was read is not changed")
        with self.assertRaises(retired_names.Refused, msg="the new key beside the old: no one reading, so none is guessed"):
            self.read({"at": "old", "recorded_at": "new"})

    def test_a_record_reads_with_its_keys_where_it_was_written(self):
        record = {"id": "i", "type": "report", "at": "t", "by": "b", "data": {}}
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

    def test_keys_gather_under_a_new_parent_at_the_first_of_them_and_each_value_stays_as_written(self):
        keys = {"source": "url", "evidence": "quote"}
        text = "a: 1\nsource: https://x.example   # feed\nb: 2\nevidence: 'It''s #1.'\nlast: 3\n"
        got = yaml_edit.gather(text, "citation", keys)
        self.assertEqual(got, "a: 1\ncitation:\n  url: https://x.example   # feed\n  quote: 'It''s #1.'\nb: 2\nlast: 3\n")
        strict_yaml.load(got)
        self.assertEqual(yaml_edit.gather("evidence: q q\nsource: s\n", "citation", keys), "citation:\n  url: s\n  quote: q q\n")
        self.assertEqual(yaml_edit.gather("a: 1\nsource: s\n", "citation", keys), "a: 1\ncitation:\n  url: s\n")

    def test_keys_that_cannot_gather_leave_the_text_alone(self):
        keys = {"source": "url", "evidence": "quote"}
        for name, text in {
            "none of them": "a: 1\n",
            "the parent is there": "citation: {}\nsource: s\nevidence: q\n",
            "a block scalar": "source: s\nevidence: |\n  q\n",
            "a flow collection": "source: s\nevidence: [q]\n",
            "a value on the next line": "source:\n  s\nevidence: q\n",
            "no value": "source:\nevidence: q\n",
            "a comment for a value": "source: # s\nevidence: q\n",
            "an anchor": "source: &s s\nevidence: q\n",
            "inside a mapping": "outer:\n  source: s\n  evidence: q\n",
            "inside a flow mapping": "outer: {source: s, evidence: q}\n",
            "in a list item": "- source: s\n  evidence: q\n",
        }.items():
            with self.subTest(name):
                self.assertIsNone(yaml_edit.gather(text, "citation", keys))

    def test_a_key_nests_into_the_one_item_of_a_new_list_with_everything_under_it_moved_together(self):
        head = {"id": "P1", "name": "A name"}
        cases = {
            "a block list": (
                "a: 1\nslices:\n  - id: S1\n    t: x\nb: 2\n",
                "a: 1\nphases:\n  - id: P1\n    name: A name\n    slices:\n      - id: S1\n        t: x\nb: 2\n",
            ),
            "a flow list and its comment": ("slices: [1, 2]   # all\nb: 2\n", "phases:\n  - id: P1\n    name: A name\n    slices: [1, 2]   # all\nb: 2\n"),
            "items at the key's column": ("slices:\n- id: S1\n  t: x\n", "phases:\n  - id: P1\n    name: A name\n    slices:\n    - id: S1\n      t: x\n"),
            "a blank line and a comment inside": (
                "slices:\n  - id: S1\n\n  # next\n  - id: S2\n",
                "phases:\n  - id: P1\n    name: A name\n    slices:\n      - id: S1\n\n      # next\n      - id: S2\n",
            ),
            "an empty list": ("slices: []\n", "phases:\n  - id: P1\n    name: A name\n    slices: []\n"),
        }
        for name, (text, want) in cases.items():
            with self.subTest(name):
                got = yaml_edit.nest(text, "slices", "phases", head)
                self.assertEqual(got, want)
                before, after = strict_yaml.load(text), strict_yaml.load(got)
                self.assertEqual(after["phases"], [{**head, "slices": before["slices"]}], "the values move whole")
                self.assertEqual({k: v for k, v in after.items() if k != "phases"}, {k: v for k, v in before.items() if k != "slices"})
        for name, text in {
            "a key that is not there": "a: 1\n",
            "the new list is there": "phases: []\nslices: [1]\n",
            "a key under another": "a:\n  slices: [1]\n",
            "a key in a list item": "- slices: [1]\n",
            "a key in a flow mapping": "a: {slices: [1]}\n",
        }.items():
            with self.subTest(name):
                self.assertIsNone(yaml_edit.nest(text, "slices", "phases", head))

    def test_a_key_is_added_at_the_end(self):
        self.assertEqual(yaml_edit.append_key("a: 1\n", "delivery_team", "core"), "a: 1\ndelivery_team: core\n")
        self.assertEqual(yaml_edit.append_key("a: 1", "b", "c"), "a: 1\nb: c")
        self.assertEqual(yaml_edit.append_key("", "b", "c"), "b: c\n")


if __name__ == "__main__":
    unittest.main()
