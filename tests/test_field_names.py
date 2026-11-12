"""One naming convention for the fields a person or an agent writes, and no field kept for its own sake.

`due` is an object's deadline, `<action>_due` a secondary one, `<event>_on` the date an event happened, and a person's
decision is `{decision?, by, decided_on}` with `by` an identity. So a project rule has `review_due`, a flag `cleanup_due`, a
runbook `tested_on`, and a postmortem `incident_on`. A Spec, an Intent, a slice, a proposal, a runbook, and a postmortem name their one `delivery_team`.
The qualification keeps what decides a go/no-go; the proposal drops `confidential` and the outcome's
`at`; the preview drops `seed`; a runbook's RTO and RPO are a number and a unit.
"""

import datetime as dt
import json
import re
import unittest

from helpers import ROOT

from aidd import config
from aidd.workitems import due_dates
from aidd.config import project
from aidd.kernel import json_schema, resources

TODAY = dt.date(2026, 9, 30)
IDENTITY = "urn:aidd:1:common#/$defs/identity"


CODE = re.compile(r"^[a-z][a-z0-9_]*$")
# A property or `$defs` entry whose name is one of these, or ends in one after an underscore, holds a code a script matches.
CODE_FAMILIES = ("code", "status", "state", "result", "decision", "recommendation", "coverage", "method", "scope", "source", "type")
# Where a code family holds values that are not codes, as `{schema file#pointer: reason}`. A new one needs a written reason.
NOT_CODES = {
    "common.schema.json#/$defs/step_code": "a step code is `<object>.<state>`, such as `spec.approve`, or one word",
    "common.schema.json#/$defs/next/properties/code": "a step code, from the list above",
    "spec.schema.json#/$defs/doc/properties/type": "a document type is a file stem, such as `tech-spec`",
    "recall.schema.json#/$defs/match/properties/source": "a source that is one file names its stem, such as `product-brief`",
    "recall.schema.json#/$defs/match/oneOf/2/properties/source": "the same source, in the shape a document match takes",
}


def props(name: str, *path: str) -> dict:
    node = resources.load_json(name)
    for key in path:
        node = node[key]
    return node


class Renames(unittest.TestCase):
    def test_a_project_rule_has_review_due(self):
        rule = props("config.schema.json", "$defs", "project_rule", "properties")
        self.assertIn("review_due", rule)
        self.assertNotIn("review_by", rule)
        cfg = config.load_text(
            'aidd_version: "1.0.0"\nprofile: team\nowners:\n  approvers: ["@x"]\nproject:\n  rules:\n    - id: r\n      requirement_level: must\n'
            '      statement: s\n      why: w\n      owner: "@x"\n      review_due: "2026-01-01"\n'
        )
        _, warnings = project.project_findings(cfg, TODAY)
        self.assertTrue(any("review_due 2026-01-01 has passed" in w for w in warnings), warnings)

    def test_a_project_rule_has_a_requirement_level_in_order(self):
        rule = props("config.schema.json", "$defs", "project_rule")
        self.assertEqual(rule["properties"]["requirement_level"]["enum"], ["must", "should", "may"])
        self.assertIn("requirement_level", rule["required"])
        self.assertNotIn("level", rule["properties"])

    def test_a_delegation_has_review_due(self):
        delegation = props("config.schema.json", "properties", "delegation")
        self.assertIn("review_due", delegation["properties"])
        self.assertIn("review_due", delegation["required"])
        self.assertNotIn("review_by", delegation["properties"])

    def test_project_has_no_repo(self):
        self.assertNotIn("repo", props("config.schema.json", "properties", "project", "properties"))

    def test_a_key_with_one_allowed_value_is_not_a_key(self):
        delegation = props("config.schema.json", "properties", "delegation", "properties")
        self.assertNotIn("to", delegation)
        self.assertNotIn("type", props("config.schema.json", "properties", "standards", "items", "properties"))

    def test_the_team_data_names_only_agents_keys_the_config_has(self):
        text = (ROOT / "schemas" / "roles.json").read_text(encoding="utf-8")
        named = set(re.findall(r"`agents\.([a-z_]+)`", text))
        self.assertLessEqual(named, set(props("config.schema.json", "properties", "agents", "properties")))

    def test_no_field_table_in_the_config_page_has_a_blank_meaning(self):
        text = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
        blank = [line for line in text.splitlines() if re.match(r"^\| `[^`]+` \|.* \|  \|$", line)]
        self.assertEqual(blank, [])

    def test_a_flag_has_cleanup_due(self):
        flag = props("spec.schema.json", "$defs", "flag", "properties")
        self.assertIn("cleanup_due", flag)
        self.assertNotIn("cleanup_by", flag)
        objects = [("specs/SPEC-1.md", {"type": "spec", "id": "SPEC-1", "flags": [{"name": "f", "cleanup_due": "2026-01-01"}]})]
        self.assertEqual([f["name"] for _, _, f in due_dates.overdue_flags(objects, TODAY)], ["f"])

    def test_a_runbook_has_tested_on(self):
        rb = props("runbook.schema.json", "properties")
        self.assertIn("tested_on", rb)
        self.assertNotIn("last_tested", rb)
        base = {"aidd_version": "1.0.0", "type": "runbook", "id": "RB-1", "title": "t", "service": "s", "delivery_team": "o", "status": "active"}
        for key in ("rto", "rpo"):
            self.assertEqual(rb[key]["pattern"], r"^\d+(m|h|d)$", key)
            self.assertEqual(json_schema.validate(dict(base, **{key: "4h"}), "runbook.schema.json"), [])
            self.assertTrue(json_schema.validate(dict(base, **{key: "4 hours"}), "runbook.schema.json"))
        self.assertEqual(json_schema.validate(dict(base, tested_on="2026-09-01"), "runbook.schema.json"), [])

    def test_a_postmortem_has_incident_on(self):
        pm = props("postmortem.schema.json")
        self.assertIn("incident_on", pm["properties"])
        self.assertIn("incident_on", pm["required"])
        self.assertNotIn("incident_date", pm["properties"])

    def test_a_decision_is_by_an_identity_on_a_date(self):
        p = props("proposal.schema.json", "properties")
        for key in ("go_no_go", "sign_off", "outcome"):
            self.assertEqual(p[key]["properties"]["by"]["$ref"], IDENTITY, key)
            self.assertIn("decided_on", p[key]["required"], key)
        self.assertNotIn("at", p["outcome"]["properties"])

    def test_a_record_and_a_revision_name_their_instant(self):
        record = props("records.schema.json", "$defs", "record")
        self.assertIn("recorded_at", record["properties"])
        self.assertIn("recorded_at", record["required"])
        revision = props("spec.schema.json", "properties", "revisions", "items", "properties")
        self.assertIn("revised_at", revision)
        for old in (record["properties"], revision):
            self.assertNotIn("at", old)

    def test_who_checked_an_entry_is_an_identity_in_every_schema_that_keeps_one(self):
        for name, path in (
            ("stack.schema.json", ("properties", "checked_by")),
            ("standard.schema.json", ("properties", "checked_by")),
            ("roles.schema.json", ("$defs", "standard", "properties", "checked_by")),
        ):
            node = props(name, *path)
            self.assertEqual(node["$ref"], IDENTITY, name)


class Cuts(unittest.TestCase):
    def test_the_qualification_keeps_what_decides(self):
        q = props("proposal.schema.json", "properties", "qualification")
        self.assertEqual(set(q["properties"]), {"fit", "budget", "authority", "decision_process", "recommendation"})
        self.assertEqual(set(q["required"]), set(q["properties"]))

    def test_no_confidential_no_seed_no_owner_teams(self):
        self.assertNotIn("confidential", props("proposal.schema.json", "properties"))
        self.assertNotIn("seed", props("config.schema.json", "properties", "preview", "properties"))
        for fields in (
            props("intent.schema.json", "properties"),
            props("common.schema.json", "$defs", "slice", "properties"),
            *(props(f"{name}.schema.json", "properties") for name in ("spec", "proposal", "runbook", "postmortem")),
        ):
            self.assertNotIn("owner_teams", fields)
            self.assertNotIn("owner_team", fields)
            self.assertEqual({k: fields["delivery_team"][k] for k in ("type", "minLength")}, {"type": "string", "minLength": 1})
        self.assertNotIn("owner_team", props("spec.schema.json", "required"))
        self.assertIn("delivery_team", props("runbook.schema.json", "required"))
        self.assertEqual(config.types_with_field("delivery_team"), ("spec", "intent", "proposal", "runbook", "postmortem"))

    def test_one_delivery_team_is_checked_against_the_config_and_owns_no_list_of_intents(self):
        team = props("config.schema.json", "properties", "delivery_teams", "additionalProperties")
        self.assertNotIn("intents", team["properties"])
        self.assertNotIn("anyOf", team)
        self.assertEqual(team["required"], ["approvers"])
        self.assertNotIn("default_owner_team", props("config.schema.json", "properties", "owners", "properties"))
        self.assertIn("delivery_team", json.dumps(resources.load_json("status.schema.json")))
        self.assertNotIn("owner_team", json.dumps(resources.load_json("status.schema.json")))

    def test_the_templates_use_the_new_names(self):
        assets = ROOT / ".agents" / "skills" / "aidd" / "assets"
        text = {n: (assets / n).read_text(encoding="utf-8") for n in ("runbook.md", "postmortem.md", "intent.md", "proposal.md", "spec.md")}
        self.assertIn("tested_on", text["runbook.md"])
        self.assertIn("incident_on", text["postmortem.md"])
        for name, body in text.items():
            self.assertNotIn("owner_team", body, name)
        for name in ("runbook.md", "postmortem.md", "proposal.md"):
            self.assertIn('\ndelivery_team: "{{delivery_team}}"', text[name], name)
        for name, body in text.items():
            for old in ("last_tested", "incident_date", "owner_teams", "confidential", "cleanup_by", "\ntimeline:", '\nrisks: "'):
                self.assertNotIn(old, body, (name, old))


def _resolved(ref: str, name: str) -> tuple[dict, str]:
    """The node a `$ref` points at, and the schema file it sits in."""
    file, _, frag = ref.partition("#")
    name = resources.schema_file(file) if file else name
    node = resources.load_json(name)
    for part in frag.split("/")[1:]:
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node, name


def _values(node: dict, name: str, seen: frozenset = frozenset()) -> set[str]:
    """Every string a schema node allows through `enum`, `const`, a `$ref`, `items`, or a choice of schemas."""
    out = {v for v in node.get("enum", []) if isinstance(v, str)}
    if isinstance(node.get("const"), str):
        out.add(node["const"])
    ref = node.get("$ref")
    if ref and (name, ref) not in seen:
        target, home = _resolved(ref, name)
        out |= _values(target, home, seen | {(name, ref)})
    for key in ("items", "additionalProperties"):
        if isinstance(node.get(key), dict):
            out |= _values(node[key], name, seen)
    for key in ("anyOf", "oneOf", "allOf"):
        for choice in node.get(key, []):
            out |= _values(choice, name, seen)
    return out


def _in_family(key: str) -> bool:
    return any(key == f or key.endswith("_" + f) for f in CODE_FAMILIES)


def code_families(name: str, node: object, pointer: str = "#") -> dict[str, set[str]]:
    """Each property or `$defs` entry of a schema that is in a code family, by `file#pointer`, with the strings it allows."""
    found: dict[str, set[str]] = {}
    if isinstance(node, dict):
        for holder in ("properties", "$defs"):
            for key, sub in (node.get(holder) or {}).items() if isinstance(node.get(holder), dict) else ():
                if _in_family(key) and isinstance(sub, dict):
                    found[f"{name}{pointer}/{holder}/{key}"] = _values(sub, name)
        for key, sub in node.items():
            found.update(code_families(name, sub, f"{pointer}/{key}"))
    elif isinstance(node, list):
        for i, sub in enumerate(node):
            found.update(code_families(name, sub, f"{pointer}/{i}"))
    return found


class Families(unittest.TestCase):
    """The naming families, held by the schemas. A code is snake_case, so a script that matches one meets one spelling rule."""

    def codes(self) -> dict[str, set[str]]:
        found: dict[str, set[str]] = {}
        for path in sorted((ROOT / "schemas").glob("*.schema.json")):
            found.update(code_families(path.name, json.loads(path.read_text(encoding="utf-8"))))
        return found

    def test_every_code_is_snake_case(self):
        found = self.codes()
        for anchor in (
            "delegate-check.schema.json#/$defs/reason_code",
            "common.schema.json#/$defs/stop_code",
            "recall.schema.json#/properties/method",
            "proposal.schema.json#/properties/claims/items/properties/scope",
            "roles.schema.json#/properties/loop/properties/capabilities/properties/processes/items/properties/coverage",
        ):
            self.assertTrue(found.get(anchor), f"the walk must reach {anchor}")
        bad = {where: sorted(v for v in values if not CODE.match(v)) for where, values in found.items() if where not in NOT_CODES}
        self.assertEqual({where: values for where, values in bad.items() if values}, {}, "a code matches ^[a-z][a-z0-9_]*$")

    def test_each_exception_is_a_family_that_holds_values(self):
        found = self.codes()
        for where, reason in NOT_CODES.items():
            self.assertTrue(reason.strip(), where)
            self.assertTrue(any(not CODE.match(v) for v in found.get(where, ())), f"{where} holds only codes now: drop the exception")


# The other families. Each rule lists what it allows as `{property name or schema file#pointer: reason}`, and a name stands for
# every property of that name. A reason is never blank, and an exception that no property needs any more fails, so none outlives its cause.
LEVEL = "risks.schema.json#/$defs/level"
LEVEL_ALLOWED = {
    "requirement_level": "BCP 14's `must`, `should`, and `may`: how firmly a project rule binds, which is no risk level",
}
KIND_ALLOWED: dict[str, str] = {}
BOOLEAN_PREFIXES = ("is_", "has_", "no_", "not_")
BOOLEAN_ALLOWED = {
    "no_red": "it mirrors the `--no-red` flag that sets it",
}
# A count, a quantity in a unit, or a bound. `count` alone is the one in an object that names what it counts.
INTEGER_WORDS = ("count", "seconds", "minutes", "hours", "days", "bytes", "percent", "tokens", "chars")
INTEGER_PREFIXES = ("max_", "min_")
# An object whose integers are all counts, so each needs no `_count` of its own.
COUNTING_OBJECTS = {
    "counts": "each integer counts the entries that ended in one status",
    "limits": "each integer is a bound on one kind of work",
    "progress": "`finished` out of `total` is a count of the object's own parts",
    "retrospective_every": "the days or the merged changes between two retrospectives: each integer counts one of them",
}
INTEGER_ALLOWED = {
    "reruns": "a limit as pytest-rerunfailures names it",
    "exit": "a process's exit status, which a runner's documentation gives as a number, and the evidence reports as it came",
    "tests": "JUnit's count of tests, which the evidence reports as it came",
    "failed": "JUnit's count of failed tests",
    "skipped": "JUnit's count of skipped tests",
    "unknown_spend_steps": "how many steps of a run have no known spend: the name the plan's table of names fixes for the handoff note's run block",
    "behind": "how many commits the head is past the tested one: a distance in commits",
    "line": "a line number, a position in a file",
    "index": "an item's position in its list",
    "round": "the number of a prototype round: an ordinal, which names it",
    "decided_round": "the number of the round a person decided on: an ordinal",
    "x": "a pixel position of a comment's box",
    "y": "a pixel position of a comment's box",
    "width": "a pixel size of a comment's box",
    "height": "a pixel size of a comment's box",
}
DATE_NAMES = ("due", "until", "sunset")
DATE_ALLOWED = {
    "checked": "the standards library's own word for the day an entry was last checked, with `published`",
}
INSTANT_ALLOWED: dict[str, str] = {}
NOT_A_DATE_ALLOWED = {
    "depends_on": "a relation: it names the Tasks this one waits for",
    "waiting_on": "a relation: it names the work an item waits for",
    "starts_on": "a flow starts on these steps: a relation to steps, not a date",
    "stopped_at": "the stop code a handoff note ends on, a published name in every agent file: a rename needs its own change",
}
# A `_by` field holds one of these, or is allowed by name.
IDENTITIES = {
    IDENTITY: "an identity: `@user`, `@org/team`, `agent:<name>`, or an email",
    "common.schema.json#/$defs/approved_by": "a person's identity in git's trailer form",
}
BY_ALLOWED = {
    "blocked_by": "it names the work item that blocks this one",
    "consumed_by": "it names the interface's consumers, other work items",
    "enforced_by": "it names the check that enforces a standard",
    "filled_by": "it names the standard that fills a choice",
    "provided_by": "it names the Spec that provides an interface",
    "replaced_by": "it names the standard that replaces this one",
    "opened_by": "it names the command that writes and opens a document's page",
    "closed_by": "it names who may close a thing that can be open: the opener, the lead, or a person (a key of `closers` in schemas/lifecycles.json)",
    "found_by": "it names the commands, or the lead's close-out, that find a thing left open (keys of `finders` in schemas/lifecycles.json)",
    "read_by": "it names the roles that read a document",
    "written_by": "it names the role that writes a document",
    "decided_by": "it names the roles that decide, in prose",
    "assisted_by": "it names a harness and a model, `claude-code/<model>`, which is no person",
    "set_by": "who set a delegation, as `Name <email>` for the `On-behalf-of` trailer, not an identity",
    "records.schema.json#/$defs/record/properties/by": "a record's actor, `agent:` or `person:`, with control characters refused",
    "roles.schema.json#/properties/loop/properties/capabilities/properties/processes/items/properties/by": "the roles that carry a process out",
}
CONST_ALLOWED = {
    "type": "a work item's type discriminator",
    "schema_version": "the version marker every JSON output carries",
    "levels": "risks.json lists the closed vocabulary its rules use, and the schema pins it",
    "branches": "risks.json lists the closed vocabulary its rules use, and the schema pins it",
    "roles.schema.json#/properties/loop/properties/autopilot/properties/command": "it has the shape of a flow's `command`, which the team reference reads the same way",
    "status.schema.json#/properties/items/items/properties/last_test_run/properties/dirty_tree": "a flag present only when true: absence says clean",
}
# A schema inside one of these holds a condition or a choice, where a single value is how a discriminator works.
CONDITIONAL = ("/if/", "/then/", "/else/", "/oneOf/", "/anyOf/", "/allOf/")
SCHEMA_MAPS = ("properties", "patternProperties", "$defs")
SCHEMA_ONE = ("items", "additionalProperties", "propertyNames", "not", "if", "then", "else", "contains")
SCHEMA_LISTS = ("anyOf", "oneOf", "allOf", "prefixItems")


def schema_nodes(node: object, pointer: str = "#", label: str = ""):
    """Each schema of a file as `(pointer, node, label)`, `label` being the nearest property or `$defs` name above it."""
    if not isinstance(node, dict):
        return
    yield pointer, node, label
    for holder in SCHEMA_MAPS:
        for key, sub in (node.get(holder) if isinstance(node.get(holder), dict) else {}).items():
            yield from schema_nodes(sub, f"{pointer}/{holder}/{key}", key)
    for holder in SCHEMA_ONE:
        yield from schema_nodes(node.get(holder), f"{pointer}/{holder}", label)
    for holder in SCHEMA_LISTS:
        for i, sub in enumerate(node.get(holder) if isinstance(node.get(holder), list) else ()):
            yield from schema_nodes(sub, f"{pointer}/{holder}/{i}", label)


def schema_properties(name: str, root: dict):
    """Each property a file declares as `(where, key, node, label of its object)`."""
    for pointer, node, label in schema_nodes(root):
        for key, sub in (node.get("properties") if isinstance(node.get("properties"), dict) else {}).items():
            if isinstance(sub, dict):
                yield f"{name}{pointer}/properties/{key}", key, sub, label


def _canonical(ref: str, name: str) -> str:
    file, _, frag = ref.partition("#")
    return f"{resources.schema_file(file) if file else name}#{frag}"


def reach(node: dict, name: str, into_items: bool = False, seen: frozenset = frozenset()) -> tuple[set[str], set[str]]:
    """What a property is, through its `$ref`s and choices (and its list items, if asked): its `type` and `format` words, and the schemas it refs."""
    words = {str(node[k]) for k in ("type", "format") if isinstance(node.get(k), str)}
    refs: set[str] = set()
    if isinstance(node.get("$ref"), str) and (name, node["$ref"]) not in seen:
        refs.add(_canonical(node["$ref"], name))
        target, home = _resolved(node["$ref"], name)
        more_words, more_refs = reach(target, home, into_items, seen | {(name, node["$ref"])})
        words |= more_words
        refs |= more_refs
    for sub in [c for k in ("anyOf", "oneOf", "allOf") for c in node.get(k, [])]:
        more_words, more_refs = reach(sub, name, into_items, seen)
        words |= more_words
        refs |= more_refs
    if into_items and isinstance(node.get("items"), dict):
        refs |= reach(node["items"], name, into_items, seen)[1]
    return words, refs


class Fields(unittest.TestCase):
    """Rules over every property of every schema, so a level, a flag, a count, a date, and who decided each keep one family."""

    props: list[tuple[str, str, dict, str]] = []

    @classmethod
    def setUpClass(cls):
        for path in sorted((ROOT / "schemas").glob("*.schema.json")):
            cls.props += list(schema_properties(path.name, json.loads(path.read_text(encoding="utf-8"))))

    def broken(self, rule: str, allowed: dict[str, str], breaks) -> None:
        """Fail on a property that `breaks(key, node, home, where, label)` flags and `allowed` does not excuse, or on an unused excuse."""
        found = [(where, key) for where, key, node, label in self.props if breaks(key, node, where.split("#")[0], where, label)]
        loose = sorted(where for where, key in found if where not in allowed and key not in allowed)
        self.assertEqual(loose, [], f"{rule}: fix the field, or allow it with a reason")
        used = {w for w, _ in found} | {k for _, k in found}
        for excuse, reason in allowed.items():
            self.assertTrue(reason.strip(), f"{excuse} needs a reason")
            self.assertIn(excuse, used, f"{excuse} breaks {rule!r} no more: drop the exception")

    def test_the_walk_reaches_the_properties(self):
        keys = {key for _, key, _, _ in self.props}
        self.assertGreater(len(self.props), 1000)
        self.assertLessEqual({"review_due", "requirement_level", "approved_by", "reruns", "stops_when", "schema_version"}, keys)

    def test_level_is_a_risk_level(self):
        def breaks(key, node, home, where, label):
            return (key == "level" or key.endswith("_level")) and LEVEL not in reach(node, home)[1]

        self.broken("`level` names only a risk level", LEVEL_ALLOWED, breaks)

    def test_no_property_is_named_kind(self):
        self.broken("aidd says `type`, never `kind`", KIND_ALLOWED, lambda key, node, home, where, label: key == "kind")

    def test_a_flag_has_no_is_has_no_or_not_prefix(self):
        def breaks(key, node, home, where, label):
            return "boolean" in reach(node, home)[0] and key.startswith(BOOLEAN_PREFIXES)

        self.broken("a flag names the fact, not `is_`, `has_`, `no_`, or `not_`", BOOLEAN_ALLOWED, breaks)

    def test_an_integer_is_a_count_a_quantity_or_a_bound(self):
        def breaks(key, node, home, where, label):
            if "integer" not in reach(node, home)[0]:
                return False
            named = any(key == w or key.endswith("_" + w) for w in INTEGER_WORDS) or key.startswith(INTEGER_PREFIXES)
            return not named and label not in COUNTING_OBJECTS

        self.broken("an integer is a `_count`, a unit, `max_`/`min_`, or sits in a counting object", INTEGER_ALLOWED, breaks)

    def test_each_counting_object_holds_integers(self):
        for label, reason in COUNTING_OBJECTS.items():
            self.assertTrue(reason.strip(), label)
            self.assertTrue(
                any(lab == label and "integer" in reach(node, where.split("#")[0])[0] for where, _, node, lab in self.props),
                f"{label} counts nothing now: drop it",
            )

    def test_a_date_ends_in_on_or_due(self):
        def breaks(key, node, home, where, label):
            return "date" in reach(node, home)[0] and not (key.endswith(("_on", "_due")) or key in DATE_NAMES)

        self.broken("a date ends in `_on` or `_due`", DATE_ALLOWED, breaks)

    def test_an_instant_ends_in_at(self):
        def breaks(key, node, home, where, label):
            return "date-time" in reach(node, home)[0] and not key.endswith("_at")

        self.broken("an instant ends in `_at`", INSTANT_ALLOWED, breaks)

    def test_a_name_ending_in_on_or_at_is_a_date_or_an_instant(self):
        def breaks(key, node, home, where, label):
            words = reach(node, home)[0]
            return (key.endswith("_on") and "date" not in words) or (key.endswith("_at") and "date-time" not in words)

        self.broken("`_on` is a date and `_at` an instant", NOT_A_DATE_ALLOWED, breaks)

    def test_a_by_field_is_an_identity(self):
        def breaks(key, node, home, where, label):
            return (key == "by" or key.endswith("_by")) and not {_canonical(i, "") for i in IDENTITIES} & reach(node, home, True)[1]

        self.broken("a `_by` field refs an identity", BY_ALLOWED, breaks)

    def test_no_property_holds_only_a_const(self):
        def breaks(key, node, home, where, label):
            return "const" in node and set(node) <= {"const", "type", "description"} and not any(c in where for c in CONDITIONAL)

        self.broken("a property that can hold only one value is no property", CONST_ALLOWED, breaks)

    def test_each_lock_says_whether_it_freezes_or_tightens(self):
        schema = resources.load_json("config.schema.json")
        locks = schema["properties"]["locks"]["items"]["anyOf"][0]["enum"]
        self.assertGreater(len(locks), 3)
        for key in locks:
            node = schema["properties"][key]
            text = node.get("description") or _resolved(node["$ref"], "config.schema.json")[0].get("description", "")
            self.assertRegex(text, r"(?i)\block (freezes|tightens)\b", f"`{key}` is lockable, so its description says how a lock acts")


if __name__ == "__main__":
    unittest.main()
