"""The upgrade and the readers of an earlier shape agree, row by row, because they share one function for each row.

Invariant: for every old-shape input, the file `aidd upgrade` writes, read back strictly, equals the in-memory reading of the old
file (`config.todays_shape`, `workitems.todays_shape`, and the shared reading of the surfaces only the upgrade reads); where the
upgrade leaves a name for a person (a `manual` line), the reader refuses the same input (`retired_names.Refused`), and the file the
upgrade left reads as refused too; and where no row applies, both leave the data as it is. The table is generated from
schemas/retired-names.json: every row, crossed with the old name alone, the new name alone, both, a colliding neighbour, and the key
nested where the row does not apply. A `value` row adds the value forms its function handles and those it does not (`FORMS`), so a
new rename or cut is covered with no new line here, and a new `value` row fails until its forms are listed.

Out of the table, by design: a layout the parsed data cannot show (a flow mapping, a key that shares its line), which the upgrade
leaves with a `manual` line and the reader reads, so the person's edit by hand reads the same (`AnUnusualLayout`); and the two facts
written into another file (`blocks`, a team's `intents`), which only group the work list (workitems.old_shape's docstring).
"""

from __future__ import annotations

import copy
import json
import unittest

import helpers  # noqa: F401  (puts src on sys.path)
from helpers import git
from spec_repo_fixtures import RepoCase, spec_text

from aidd import config, workitems
from aidd.kernel import documents, retired_names, strict_yaml
from aidd.records import files as record_files
from aidd.setup import migrating, migration_blocks
from aidd.testing import governing
from aidd.workitems import authoring, intent_checks, intents, work_list

REFUSED = "refused"
READERS = {
    "config": config.todays_shape,
    "exploration": lambda d: retired_names.todays_shape(d, "exploration", {}),
    "handoff": lambda d: retired_names.todays_shape(d, "handoff", {}),
    "intent": workitems.todays_shape,
    "postmortem": workitems.todays_shape,
    "proposal": workitems.todays_shape,
    "runbook": workitems.todays_shape,
    "sitemap": lambda d: retired_names.todays_shape(d, "sitemap", migrating.SITEMAP_VALUES),
    "spec": workitems.todays_shape,
    "standard": lambda d: retired_names.todays_shape(d, "standard", migrating.STANDARD_VALUES),
}
BASES = {
    "config": {"aidd_version": "1.0.0"},
    "exploration": {"type": "exploration", "id": "pick"},
    "handoff": {"done": "x"},
    "intent": {"type": "intent", "id": "INT-1", "title": "Cheaper checkout"},
    "postmortem": {"type": "postmortem", "id": "PM-1", "title": "t"},
    "proposal": {"type": "proposal", "id": "PROP-1", "title": "t"},
    "runbook": {"type": "runbook", "id": "RB-1", "title": "t"},
    "sitemap": {"product": "Shop", "flows": [{"id": "start", "title": "Start"}], "navigation": [], "fixtures": {"format": 1}},
    "spec": {"type": "spec", "id": "SPEC-1", "title": "t"},
    "standard": {"id": "python/x", "title": "t"},
}
KNOWN = {"specs": ("SPEC-9",), "intents": ("INT-3",)}  # the items a `blocks` entry may name, as a repository holds them
RISK = {"summary": "s", "dimensions": []}
TESTS = [{"name": "unit", "command": ["t"]}]
# The value forms of each `value` row, as what the base of its surface holds besides: the ones its function places and the ones it
# does not. The first is the row's old name alone.
FORMS: dict[str, dict[str, dict]] = {
    "delegation-default-branch-deploys": {
        "false": {"delegation": {"default_branch_deploys": False}},
        "true, listed by an environment": {
            "environments": [{"name": "p", "branches": ["main"]}],
            "delegation": {"default_branch": "main", "default_branch_deploys": True},
        },
        "true, listed by a wildcard": {
            "environments": [{"name": "p", "branches": ["ma*"]}],
            "delegation": {"default_branch": "main", "default_branch_deploys": True},
        },
        "true, with no environments": {"delegation": {"default_branch": "main", "default_branch_deploys": True}},
        "true, and no environment lists the branch": {
            "environments": [{"name": "s", "branches": ["release/*"]}],
            "delegation": {"default_branch": "main", "default_branch_deploys": True},
        },
        "true, and no default branch named": {"environments": [{"name": "p", "branches": ["main"]}], "delegation": {"default_branch_deploys": True}},
        "no boolean": {"environments": [{"name": "p", "branches": ["main"]}], "delegation": {"default_branch": "main", "default_branch_deploys": "yes"}},
    },
    "delivery-team-intents": {
        "a list of ids": {"delivery_teams": {"core": {"intents": ["INT-1"]}}},
        "no list": {"delivery_teams": {"core": {"intents": "INT-1"}}},
        "a list of no ids": {"delivery_teams": {"core": {"intents": [1]}}},
    },
    "docs-required": {
        "off and warn": {"docs": {"required": {"adr": "off", "runbook": "warn"}}},
        "warn alone": {"docs": {"required": {"adr": "warn"}}},
        "a renamed type": {"docs": {"required": {"authz": "off"}}},
        "the type disabled already": {"docs": {"disabled": {"adr": "kept"}, "required": {"adr": "off"}}},
        "another level": {"docs": {"required": {"adr": "strict"}}},
        "no mapping": {"docs": {"required": "off"}},
        "a disabled that is no mapping": {"docs": {"disabled": ["adr"], "required": {"adr": "off"}}},
    },
    "intent-context": {
        "no text": {"context": ""},
        "text": {"context": "terms"},
        "a list": {"context": ["terms"]},
    },
    "intent-launch": {
        "the last slice": {"launch": "S2", "slices": [{"id": "S1"}, {"id": "S2"}]},
        "another slice": {"launch": "S1", "slices": [{"id": "S1"}, {"id": "S2"}]},
        "the last slice of the last phase": {"launch": "S2", "phases": [{"id": "P1", "name": "p", "slices": [{"id": "S2"}]}]},
    },
    "intent-relations": {
        "blocked_by and blocks": {"relations": [{"type": "blocked_by", "id": "INT-9"}, {"type": "blocks", "id": "INT-3"}]},
        "an implements, with no place in an Intent": {"relations": [{"type": "implements", "id": "INT-4"}]},
        "no list": {"relations": "INT-9"},
    },
    "intent-slices": {
        "slices": {"slices": [{"id": "S1", "title": "One"}]},
        "slices beside phases": {"slices": [{"id": "S1"}], "phases": [{"id": "P1", "name": "p", "slices": [{"id": "S2"}]}]},
    },
    "project-rule-check": {
        "a test's name": {"tests": TESTS, "project": {"rules": [{"id": "r1", "check": "unit"}]}},
        "a command no test holds": {"tests": TESTS, "project": {"rules": [{"id": "r1", "check": "make lint"}]}},
        "enforced_by set too": {"tests": TESTS, "project": {"rules": [{"id": "r1", "check": "unit", "enforced_by": ["other"]}]}},
        "no string": {"tests": TESTS, "project": {"rules": [{"id": "r1", "check": ["unit"]}]}},
    },
    "sitemap-format": {
        "one": {"format": 1},
        "a later number": {"format": 2},
        "a string": {"format": "1"},
        "zero": {"format": 0},
        "true": {"format": True},
        "schema_version set too": {"format": 1, "schema_version": "1"},
    },
    "spec-change-type": {
        **{f"{old}, beside a risk block": {"change_type": old, "risk": RISK} for old in ("compliance", "data", "deps", "infra", "security")},
        "its dimension declared already": {"change_type": "security", "risk": {**RISK, "dimensions": ["security", "cost"]}},
        "a risk block with no dimensions": {"change_type": "data", "risk": {"summary": "s"}},
        "no risk block, and a dimension to add": {"change_type": "security"},
        "no risk block, and no dimension": {"change_type": "deps"},
        "dimensions that are no list": {"change_type": "infra", "risk": {"summary": "s", "dimensions": "availability"}},
        "a risk that is no mapping": {"change_type": "compliance", "risk": "high"},
        "today's type": {"change_type": "fix", "risk": RISK},
        "no type aidd ever had": {"change_type": "feet", "risk": RISK},
        "no string": {"change_type": ["security"], "risk": RISK},
    },
    "spec-cost-estimate": {
        "beside a risk block": {"risk": RISK, "cost_estimate": {"monthly": 5}},
        "no risk block": {"cost_estimate": {"monthly": 5}},
        "risk.cost_estimate set too": {"risk": {**RISK, "cost_estimate": {"monthly": 1}}, "cost_estimate": {"monthly": 5}},
        "a risk that is no mapping": {"risk": "high", "cost_estimate": {"monthly": 5}},
    },
    "spec-experiment": {
        "a block": {"experiment": {"hypothesis": "h"}},
        "a word": {"experiment": "x"},
    },
    "spec-relations": {
        "blocked_by, implements, and blocks": {
            "relations": [{"type": "blocked_by", "id": "SPEC-8"}, {"type": "implements", "id": "INT-1"}, {"type": "blocks", "id": "SPEC-9"}]
        },
        "an entry with no place": {"relations": [{"type": "duplicates", "id": "SPEC-3"}]},
        "an entry with no id": {"relations": [{"type": "blocked_by"}]},
        "a parent that agrees": {"parent": "INT-1", "relations": [{"type": "implements", "id": "INT-1"}]},
        "a parent that conflicts": {"parent": "INT-2", "relations": [{"type": "implements", "id": "INT-1"}]},
        "blocked_by set too": {"blocked_by": ["SPEC-7"], "relations": [{"type": "blocked_by", "id": "SPEC-8"}]},
        "a blocked_by that is no list": {"blocked_by": "SPEC-7", "relations": [{"type": "blocked_by", "id": "SPEC-8"}]},
        "empty": {"relations": []},
        "no list": {"relations": "SPEC-9"},
    },
    "spec-residual-risk": {
        "beside a risk block": {"risk": RISK, "residual_risk": "low"},
        "no risk block": {"residual_risk": "low"},
        "risk.residual set too": {"risk": {**RISK, "residual": "high"}, "residual_risk": "low"},
    },
    "spec-risk-reversible": {
        "false": {"risk": {**RISK, "reversible": False}},
        "true": {"risk": {**RISK, "reversible": True}},
        "a word": {"risk": {**RISK, "reversible": "no"}},
        "a number": {"risk": {**RISK, "reversible": 0}},
        "irreversible set too": {"risk": {**RISK, "reversible": False, "irreversible": False}},
    },
    "spec-suggested-by": {
        "an agent named for a role": {"suggested_by": "agent:developer"},
        "an agent and its model": {"suggested_by": "agent:claude-code/claude-opus-5-5"},
        "an agent that is no role": {"suggested_by": "agent:nobody"},
        "a person": {"suggested_by": "@maya"},
        "today's role": {"suggested_by": "role:developer"},
    },
    "spec-task-assignee": {
        "an agent named for a role": {"tasks": [{"id": "T1", "assignee": "agent:verifier"}]},
        "a person": {"tasks": [{"id": "T1", "assignee": "@maya"}]},
    },
    "standard-evidence": {
        "evidence and source": {"source": "https://example.com/a", "evidence": "q"},
        "evidence alone": {"evidence": "q"},
        "citation set too": {"evidence": "q", "citation": {"url": "https://example.com/b"}},
    },
    "standard-source": {
        "source alone": {"source": "https://example.com/a"},
    },
}


def merged(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in extra.items():
        out[key] = merged(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else copy.deepcopy(value)
    return out


def placed(pattern: str, value: object, item: dict | None = None) -> dict:
    """The data that holds `value` at `pattern`'s place: `*` is the key `core`, and each list holds one item with an `id` (`item`, or
    a second item when given)."""
    steps = retired_names.pattern_steps(pattern)
    out: dict = {}
    node = out
    for i, (key, each) in enumerate(steps):
        name = "core" if key == "*" else key
        if i == len(steps) - 1:
            node[name] = value
        elif each:
            child = {"id": "i1"}
            node[name] = [child, *([item] if item else [])]
            node = child
        else:
            node = node.setdefault(name, {})
    return out


def last_key(pattern: str) -> str:
    return pattern.rsplit(".", 1)[-1].removesuffix("[]")


def beside(data: dict, pattern: str, key, value: object) -> dict:
    """A copy of `data` with `key(old)` set to `value` in each mapping that holds a key `pattern` names."""
    out = copy.deepcopy(data)
    for path in retired_names.paths_in(out, pattern):
        parent = out
        for step in path[:-1]:
            parent = parent[step]
        parent[key(path[-1])] = value
    return out


def cases():
    """Each (row, variant, data) of the table, for every row of a surface `aidd upgrade` edits."""
    for row in retired_names.rows():
        if row["surface"] not in READERS:
            continue
        base = BASES[row["surface"]]
        forms = FORMS.get(row["id"]) or {"alone": placed(row["old"], "x")}
        for name, extra in forms.items():
            yield row, name, merged(base, extra)
        first = merged(base, next(iter(forms.values())))
        if row["new"] and row["new"] != row["old"]:
            yield row, "the new name alone", merged(base, placed(row["new"], "x"))
            if row["rule"] == "rename":
                new = last_key(row["new"])
                yield row, "both", beside(first, row["old"], lambda old, new=new: new, "y")
        if "[]" in row["old"] and row["new"] and row["rule"] == "rename":
            yield row, "the new name in a neighbouring item", merged(base, placed(row["old"], "x", {"id": "i2", last_key(row["new"]): "y"}))
        yield row, "a look-alike neighbour", beside(first, row["old"], lambda old: f"{old}_note", "a look-alike")
        yield row, "nested where the row does not apply", merged(base, {"elsewhere": {last_key(row["old"]): "x"}})


def written(surface: str, data: dict) -> str:
    """`data` as a file of `surface` holds it: JSON as the prototype tool writes it, or YAML in block layout."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n" if surface in migration_blocks.JSON_SURFACES else strict_yaml.dump(data)


def read_back(surface: str, text: str) -> dict:
    return json.loads(text) if surface in migration_blocks.JSON_SURFACES else documents.parse_yaml(text, "written")


def upgraded(surface: str, data: dict) -> tuple[migrating._Block, set[str]]:
    """What the upgrade makes of a file of `surface` that holds `data`, written as `written` does, and the kinds of line it said."""
    text = written(surface, data)
    block = migrating._Block(f"a {surface}", surface, text, (0, len(text)))
    ctx = migrating._Ctx(specs=dict.fromkeys(KNOWN["specs"]), intents=dict.fromkeys(KNOWN["intents"]))  # type: ignore[arg-type]
    migrating._migrate_block(block, ctx)
    return block, {kind for kind, _ in block.lines}


def reading(surface: str, data: dict) -> object:
    try:
        return READERS[surface](data)
    except retired_names.Refused:
        return REFUSED


class TheUpgradeAndTheReadersAgree(unittest.TestCase):
    def test_every_surface_the_upgrade_edits_has_a_reader_and_every_value_row_its_forms(self):
        # A record is never rewritten, and a standard's id, a flag, and a value a person types are in no file the upgrade edits.
        self.assertEqual(set(READERS), {r["surface"] for r in retired_names.rows()} - {"record", "standard_id", "cli_flag", "cli_value"})
        self.assertEqual(set(FORMS), {r["id"] for r in retired_names.rows() if r["rule"] == "value"})

    def test_the_file_the_upgrade_writes_reads_as_the_old_file_reads_and_a_refusal_is_the_same_refusal(self):
        seen = {"wrote": 0, "refused": 0, "nothing": 0}
        rows_refused = set()
        for row, variant, data in cases():
            surface = row["surface"]
            with self.subTest(row=row["id"], variant=variant):
                block, kinds = upgraded(surface, data)
                read = reading(surface, data)
                if "manual" in kinds:
                    seen["refused"] += 1
                    rows_refused.add(row["id"])
                    self.assertEqual(read, REFUSED, f"the upgrade leaves it for a person, and the reader read {read}: {block.lines}")
                    left = read_back(surface, block.text)
                    self.assertEqual(reading(surface, left), REFUSED, "the file the upgrade left reads as refused too")
                elif "migrate" in kinds:
                    seen["wrote"] += 1
                    self.assertTrue(block.reads_back(), block.text)
                    now = read_back(surface, block.text)
                    self.assertEqual(now, read, "the written file reads as the reader reads the old one")
                    self.assertEqual(reading(surface, now), now, "today's shape reads as it is")
                    again, kinds_again = upgraded(surface, now)
                    self.assertFalse(kinds_again & {"migrate", "manual"}, f"a second upgrade changes nothing: {again.lines}")
                else:
                    seen["nothing"] += 1
                    self.assertEqual(read, data, "no row applies, so the reader changes nothing")
        self.assertGreater(seen["wrote"], 100)
        self.assertGreater(seen["refused"], 40)
        self.assertGreater(seen["nothing"], 40)
        renames = {r["id"] for r in retired_names.rows() if r["rule"] == "rename" and r["surface"] in READERS}
        self.assertLessEqual(renames, rows_refused, "every rename refuses its new name set beside it")

    def test_a_record_is_read_both_ways_and_never_rewritten(self):
        """A record is never rewritten (`aidd upgrade` leaves `.git/aidd/records/`), so its old form reads as its new form does, and an
        old key beside its new one is refused, as an unreadable record is."""
        for row in retired_names.rows("record"):
            with self.subTest(row["id"]):
                new = row["new"]
                if "read_as" in row:
                    for old, now in row["read_as"].items():
                        self.assertEqual(record_files.todays_shape(placed(row["old"], old)), record_files.todays_shape(placed(new, now)))
                    self.assertEqual(record_files.todays_shape(placed(row["old"], 3)), placed(row["old"], 3), "a value it does not list stays")
                else:
                    self.assertEqual(record_files.todays_shape(placed(row["old"], "x")), placed(new, "x"))
                    with self.assertRaises(retired_names.Refused):
                        record_files.todays_shape(merged(placed(row["old"], "x"), placed(new, "y")))
                nested = {"elsewhere": {last_key(row["old"]): "approval"}}
                self.assertEqual(record_files.todays_shape(nested), nested)


class AnUnusualLayout(unittest.TestCase):
    """A file in a valid layout the editor cannot change one key at a time: the upgrade leaves it with a `manual` line, and the reader
    reads it as the same data written in block layout is upgraded, so the person's edit by hand reads the same as the old commit."""

    def test_a_flow_mapping_is_left_for_a_person_and_read_as_its_block_layout_upgrades(self):
        cases = {
            "config": "mcp: {approve_own_tools: true}\n",
            "spec": "type: spec\nid: SPEC-1\nrisk: {summary: s, dimensions: [], reversible: false}\n",
        }
        for surface, text in cases.items():
            with self.subTest(surface):
                block = migrating._Block("f", surface, text, (0, len(text)))
                migrating._migrate_block(block, migrating._Ctx())
                self.assertTrue(any(kind == "manual" for kind, _ in block.lines), block.lines)
                block_layout, _ = upgraded(surface, documents.parse_yaml(text, "f"))
                self.assertEqual(reading(surface, documents.parse_yaml(text, "f")), documents.parse_yaml(block_layout.text, "b"))


class TheInvertingRow(RepoCase):
    """`risk.reversible` became `risk.irreversible` with the opposite value: an old value read under the new name, or the reverse,
    flips a control. Both code paths and the decisions that read the value agree on every form."""

    TABLE = {  # reversible: (irreversible, or REFUSED)
        "true": (True, False),
        "false": (False, True),
        "a word": ("no", REFUSED),
        "a number": (0, REFUSED),
    }

    def spec(self, risk: dict) -> dict:
        return {**BASES["spec"], "route": "major", "change_type": "fix", "risk": {**RISK, **risk}}

    def test_both_code_paths_read_each_form_alike(self):
        for name, (old, want) in self.TABLE.items():
            with self.subTest(name):
                data = self.spec({"reversible": old})
                self.assertEqual(reading("spec", data), REFUSED if want == REFUSED else self.spec({"irreversible": want}))
                block, kinds = upgraded("spec", data)
                self.assertEqual("manual" in kinds, want == REFUSED)
                if want != REFUSED:
                    self.assertEqual(documents.parse_yaml(block.text, "w")["risk"]["irreversible"], want)
        absent = self.spec({})
        self.assertEqual((reading("spec", absent), upgraded("spec", absent)[1]), (absent, set()), "absent: reversible under either name")
        for both in ({"reversible": False, "irreversible": False}, {"reversible": True, "irreversible": True}):
            with self.subTest(both=both):
                self.assertEqual(reading("spec", self.spec(both)), REFUSED, "both keys: no one reading, whatever they say")
                self.assertIn("manual", upgraded("spec", self.spec(both))[1])

    def test_the_required_documents_follow_the_value_not_the_name(self):
        """A major change that cannot be reverted asks for a tech spec, a runbook, and a migration plan. The old `reversible: false`
        asks for them, read in memory or upgraded, and `reversible: true` does not."""
        asked = {}
        for name in ("true", "false"):
            old = self.spec({"reversible": self.TABLE[name][0]})
            written = documents.parse_yaml(upgraded("spec", old)[0].text, "w")
            types = {a.doc_type for a in authoring.required_docs(reading("spec", old), None)}  # type: ignore[arg-type]
            self.assertEqual(types, {a.doc_type for a in authoring.required_docs(written, None)})
            asked[name] = types
        self.assertTrue({"migration-plan", "runbook", "tech-spec"} <= asked["false"] - asked["true"], asked)

    def test_validate_refuses_the_old_name_on_the_head_and_an_approval_commit_reads_the_opposite(self):
        text = spec_text("SPEC-1", status="approved")
        self.assertIn("irreversible: false", text)
        old = text.replace("irreversible: false", "reversible: false")
        errors = workitems.load_object(old, "specs/SPEC-1.md")[2]
        self.assertTrue(any("risk.reversible" in e and "aidd upgrade --yes" in e for e in errors), errors)
        self.assertEqual(workitems.load_object(old, "specs/SPEC-1.md", read_old_shape=True)[0]["risk"]["irreversible"], True)
        self.put(self.root, "specs/SPEC-1.md", old)
        self.commit(self.root, "approved before the upgrade")
        base = governing.specs_at(str(self.root), git(self.root, "rev-parse", "HEAD"), ["specs"])["specs/SPEC-1.md"]
        self.assertIs(base["risk"]["irreversible"], True, "the base view reads the opposite value, never its own under the new name")


class WhatACallerDoesWithARefusal(RepoCase):
    """Each check that reads a commit before an upgrade treats a refused item as one it cannot read, in the direction that stops."""

    def test_an_approved_spec_on_the_base_stops_the_run_and_a_draft_binds_nothing(self):
        for status, stops in (("draft", False), ("ready", False), ("approved", True), ("in_progress", True), ("done", True)):
            with self.subTest(status):
                self.fresh()
                text = spec_text("SPEC-1", status=status).replace("route: normal", "route: normal\nexperiment: x")
                self.put(self.root, "specs/SPEC-1.md", text)
                self.commit(self.root, "base")
                head = git(self.root, "rev-parse", "HEAD")
                if stops:
                    with self.assertRaises(documents.DocumentError) as caught:
                        governing.specs_at(str(self.root), head, ["specs"])
                    self.assertIn("a Spec holds none now", str(caught.exception))
                    self.assertIn("then run `aidd test` again", str(caught.exception), "the next step")
                else:
                    self.assertEqual(governing.specs_at(str(self.root), head, ["specs"]), {})
                errors = workitems.load_object(text, "specs/SPEC-1.md", read_old_shape=True)[2]
                self.assertTrue(any("a Spec holds none now" in e and "aidd upgrade --yes" in e for e in errors), errors)

    def test_an_intent_agreed_before_the_upgrade_stays_agreed_unless_its_agreed_version_is_refused(self):
        """Honest work: an Intent agreed in the old shape and upgraded keeps its agreement, since the upgrade is no revision. One whose
        agreed version held a `context` with text, which a person moves by hand, cannot be read, so the person agrees again."""
        agreed = 'agreed_by: "J <j@example.com>"\nagreed_at: "2026-11-10T09:12:00Z"\n'
        for context, stands in (('""', True), ("terms", False)):
            with self.subTest(context=context):
                self.fresh()
                rel = "specs/INT-1.md"
                old = f'---\ntype: intent\nid: INT-1\ntitle: "Plan"\ngoal: "g by 2027-01-01"\n{agreed}context: {context}\nslices: [{{id: SPEC-1, title: one}}]\n---\n'
                self.put(self.root, rel, old)
                git(self.root, "add", "-A")
                git(self.root, "commit", "-qm", "agree", "--trailer", "Agreed-by: J <j@example.com>")
                today = old.replace(f"context: {context}\n", "").replace(
                    "slices: [{id: SPEC-1, title: one}]", "phases: [{id: P1, name: Plan, slices: [{id: SPEC-1, title: one}]}]"
                )
                self.put(self.root, rel, today)
                self.commit(self.root, "aidd upgrade, and the context moved by hand")
                data = documents.split_front_matter(today, rel)[0]
                self.assertEqual(intent_checks.agreement_warnings(self.root / rel, data, self.root) == [], stands)

    def test_a_config_an_intent_a_record_and_the_work_list_read_a_refusal_as_unreadable(self):
        both = 'aidd_version: "1.0.0"\nmcp:\n  approve_own_tools: true\n  allow_own_tools: false\n'
        self.assertEqual(config.in_todays_shape(both), both, "the config is left as written, so its load fails at the name")
        intent = {"type": "intent", "id": "INT-1", "goal": "g", "context": "terms", "slices": [{"id": "S1"}]}
        self.assertTrue(intents.changes_since(intent, {**intent, "context": ""}), "a version that cannot be read shows no agreement")
        found, bad = work_list.parse_work([("specs/INT-1.md", f"---\n{strict_yaml.dump(intent)}---\n")], read_old_shape=True)
        self.assertEqual((found, [b["path"] for b in bad]), ([], ["specs/INT-1.md"]), "--all-branches shows it as unreadable")
        record = {"id": "r1", "type": "report", "at": "2026-01-01T00:00:00Z", "recorded_at": "2026-01-02T00:00:00Z", "by": "b", "data": {}}
        self.assertTrue(record_files.record_problems(record, reading=True), "a record with no one reading is none")


if __name__ == "__main__":
    unittest.main()
