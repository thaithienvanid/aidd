"""The standards library: opinionated standards and stacks, the open choices they fill, and the company's policy.

Generic tests run over every library file (`standards/<group>/<topic>.md`, `stacks/<name>.toml`), so a new entry
needs no new test code: the schema, `fills` naming a declared open choice, one standard per choice and ecosystem, stack
ids that exist and are active, tool ownership, the size cap, duplication against the packs, renames and deprecation,
and the method never being an open choice. Each check also has a failing case on a fixture library here.

Then the commands: `aidd standard add|list` and `aidd stack add|list` vendor a copy, record its id, aidd's version, and
hash, and follow `standards_policy`; `aidd upgrade` refreshes an unedited copy; `aidd doctor` reports drift, edited
copies, policy breaches, and deprecated or renamed ids.
"""

import contextlib
import datetime as dt
import json
import re
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import helpers
from helpers import ROOT, git

from aidd import __version__, config
from aidd.knowledge import recheck_report
from aidd.knowledge import release_feeds
from aidd.knowledge import bounded_fetch
from aidd.knowledge import upkeep
from aidd.docsgen import pack_render
from aidd.setup import doctor_checks
from aidd.setup import upgrading
from aidd.knowledge import standards, team_registry
from aidd.config import baseline, standards_policy
from aidd.kernel import documents, json_schema, resources, strict_yaml

SEED = {"python/ruff-lint-format", "python/mypy-typing", "python/uv-tooling"}
TOP = 'aidd_version: "1.0.0"\nprofile: team\n'
# Where a fixture's `checked` version was read: a checked date needs both.
READ_AT = {"source": "https://example.org/releases", "evidence": "Version 1.0.0 is out."}
HEAD = TOP + 'owners:\n  approvers: ["@org/leads"]\ntests:\n  - name: unit\n    command: [make, test]\n'


def front(**over) -> str:
    """A valid library standard's file, with fields replaced or (None) removed."""
    meta = {
        "id": "python/demo",
        "type": "opinionated",
        "fills": ["ci-pipeline:linter"],
        "roles": ["developer"],
        "why": "A reason.",
        "reviewed": "2026-10-01",
        "maturity": "established",
        "status": "active",
        "default": True,
    }
    body = over.pop("body", "# Demo\n\nOne short line.\n")
    for k, v in over.items():
        if v is None:
            meta.pop(k, None)
        else:
            meta[k] = v
    return "---\n" + strict_yaml.dump(meta) + "---\n\n" + body


def toml_value(v) -> str:
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {toml_value(x)}" for k, x in v.items()) + " }"
    if isinstance(v, list):
        return "[" + ", ".join(toml_value(x) for x in v) + "]"
    return json.dumps(v)


class Fixture:
    """A library folder and a stacks folder in a temporary directory."""

    def __init__(self, tmp: Path):
        self.lib = tmp / "standards"
        self.stk = tmp / "stacks"
        self.lib.mkdir()
        self.stk.mkdir()
        (self.lib / "renames.yaml").write_text("renames: {}\n", encoding="utf-8")

    def standard(self, text: str, rel: str | None = None) -> None:
        meta, _ = documents.split_front_matter(text, "x")
        path = self.lib / (rel or f"{meta['id']}.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def stack(self, name: str, body: str) -> None:
        (self.stk / f"{name}.yaml").write_text(f'name: {name}\ndescription: d\nreviewed: "2026-10-01"\n' + body, encoding="utf-8")

    def problems(self) -> list[str]:
        return standards.library_problems(self.lib, self.stk, today=dt.date(2026, 10, 7))


class LibraryTests(unittest.TestCase):
    """Over every file aidd ships: adding a standard or a stack needs no new test code."""

    def test_the_library_and_the_stacks_have_no_problem(self):
        self.assertEqual(standards.library_problems(), [])

    def test_the_seed_stays_and_every_standard_is_checked(self):
        # The catalog grows the library; the three proven Python standards and the python-cli stack stay exactly as seeded.
        lib = standards.standards_library()
        self.assertLessEqual(SEED, set(lib))
        self.assertIn("python-cli", standards.stacks())
        self.assertEqual(set(standards.stack_standards("python-cli", standards.stacks())), SEED)
        for s in lib.values():
            self.assertEqual(s.meta["type"], "opinionated")
            self.assertTrue(s.meta.get("implements"), s.id)  # each links the pack rule it implements
            self.assertTrue(s.meta.get("checked"), s.id)  # checked at the source on a day
            if s.meta.get("tool"):  # a tool's version is a field, read at its release feed
                self.assertTrue(s.meta.get("checked_version"), s.id)

    def test_every_library_file_matches_its_schema_and_its_path(self):
        root = resources.data_dir("standards")
        for path in sorted(root.glob("*/*.md")):
            meta, _ = documents.split_front_matter(path.read_text(encoding="utf-8"), path.name)
            self.assertEqual(json_schema.validate(meta, "standard.schema.json"), [], path)
            self.assertEqual(f"{meta['id']}.md", path.relative_to(root).as_posix())
        for path in sorted(resources.data_dir("stacks").glob("*.yaml")):
            data = documents.parse_yaml(path.read_text(encoding="utf-8"), path.name)
            self.assertEqual(json_schema.validate(data, "stack.schema.json"), [], path)
            self.assertEqual(data["name"], path.stem)

    def test_no_registry_id_looks_like_a_library_id(self):
        # So `standards_policy` can tell them apart by form: an industry standard can never pass as an opinionated one.
        self.assertFalse([k for k in team_registry.roles()["standards"] if standards_policy.LIBRARY_ID.match(k)])

    def test_every_open_choice_has_one_default_and_is_never_the_method(self):
        choices = standards.open_choices()
        self.assertIn("ci-pipeline:linter", choices)
        for ref, c in choices.items():
            self.assertTrue(c["default"].strip(), ref)
            self.assertGreaterEqual(len(c["options"]), 2, ref)
        self.assertEqual(standards.method_problems(choices), [])

    def test_the_summary_line_counts_in_good_english(self):
        from aidd.cli import arguments

        self.assertEqual(arguments.counted(1, "stack"), "1 stack")
        self.assertEqual(arguments.counted(3, "library standard"), "3 library standards")

    def test_the_standards_check_counts_who_checked_the_library(self):
        # Every library standard is in one trust tier, and `aidd eval standards` prints the count of each.
        import io

        from aidd.cli import app

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            app.main(["eval", "standards"])
        counts = standards.trust_counts([s.meta for s in standards.standards_library().values()])
        self.assertEqual(sum(counts.values()), len(standards.standards_library()))
        want = f"Library trust: {counts['checked by an agent']} checked by an agent, {counts['reviewed by a person']} reviewed by a person"
        self.assertIn(want, out.getvalue())

    def test_the_library_is_packaged_like_the_other_data(self):
        self.assertEqual(resources._LAYOUT["standards"], "standards")
        self.assertEqual(resources._LAYOUT["stacks"], "stacks")
        wheel = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]
        self.assertIn("standards", wheel["wheel"]["only-include"])
        self.assertIn("stacks/", wheel["sdist"]["include"])


class LibraryCheckTests(unittest.TestCase):
    """Each generic check fails on a fixture library that breaks it."""

    def setUp(self):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.f = Fixture(tmp)

    def assertProblem(self, needle: str):
        found = self.f.problems()
        self.assertTrue(any(needle in p for p in found), found)

    def test_a_valid_fixture_has_no_problem(self):
        self.f.standard(front())
        self.f.stack("demo", "standards: [python/demo]\n")
        self.assertEqual(self.f.problems(), [])

    def test_the_schema_and_the_path(self):
        self.f.standard(front(why=None))
        self.assertProblem("missing required field 'why'")
        self.f.standard(front(id="python/other"), rel="python/demo2.md")
        self.assertProblem("does not match its path")

    def test_a_checked_date_needs_its_source_and_evidence(self):
        # A date alone is a bare assertion: the page it was read at and the sentence read there come with it.
        self.f.standard(front(checked="2026-10-01", **READ_AT))
        self.assertEqual(self.f.problems(), [])
        for missing in ("source", "evidence"):
            with self.subTest(missing=missing):
                self.f.standard(front(checked="2026-10-01", **{k: v for k, v in READ_AT.items() if k != missing}))
                self.assertProblem(f"missing required field '{missing}'")

    def test_fills_must_name_a_declared_open_choice(self):
        self.f.standard(front(fills=["ci-pipeline:colour-of-the-bikeshed"]))
        self.assertProblem("fills ci-pipeline:colour-of-the-bikeshed, which no pack or practice skill declares")

    def test_several_options_per_choice_and_ecosystem_with_one_default(self):
        # The library may hold several options for one choice; aidd's default among them is one flag, on one of them.
        self.f.standard(front())
        self.f.standard(front(id="python/demo2", default=None))
        self.assertEqual(self.f.problems(), [])
        self.f.standard(front(id="python/demo2"))
        self.assertProblem("ci-pipeline:linter for python has 2 defaults (python/demo, python/demo2); keep one")
        self.f.standard(front(id="python/demo2", default=False))
        self.f.standard(front(default=False))
        self.assertProblem("ci-pipeline:linter for python has no default; set `default: true` on one of python/demo, python/demo2")
        self.f.standard(front())
        self.f.standard(front(id="node/demo"))  # another ecosystem has its own default for the same choice
        self.assertEqual(self.f.problems(), [])
        self.f.standard(front(id="python/old", status="deprecated", replaced_by="python/demo"))
        self.assertProblem("python/old: a deprecated standard is never a default")

    def test_the_default_is_a_flag_on_the_standard(self):
        self.f.standard(front(default="yes"))
        self.assertProblem("default")

    def test_checked_by_names_an_agent_or_a_person_and_needs_its_date(self):
        # Who read the source on the `checked` day: `agent:<harness>/<model>`, or a person as `@login` or `email:<address>`
        # (the approver identity forms), and never without the date.
        for who in ("agent:claude-code/claude-opus-5-5", "@thaithienvanid", "email:lead@example.com"):
            with self.subTest(who=who):
                self.f.standard(front(checked="2026-10-01", checked_by=who, **READ_AT))
                self.assertEqual(self.f.problems(), [])
        for who in ("claude", "agent:claude-code", "human:@thaithienvanid", "human:", "@", "email:lead", "robot:x/y"):
            with self.subTest(who=who):
                self.f.standard(front(checked="2026-10-01", checked_by=who, **READ_AT))
                self.assertProblem("checked_by")
        self.f.standard(front(checked_by="agent:claude-code/claude-opus-5-5"))
        self.assertProblem("missing required field 'checked'")

    def test_the_trust_tier_comes_from_checked_by(self):
        # A catalog entry is agent-checked until a person reviews it: no `checked_by` counts as an agent's check.
        self.assertEqual(standards.trust_tier({}), "checked by an agent")
        self.assertEqual(standards.trust_tier({"checked_by": "agent:claude-code/claude-opus-5-5"}), "checked by an agent")
        self.assertEqual(standards.trust_tier({"checked_by": "@thaithienvanid"}), "reviewed by a person")
        self.assertEqual(standards.trust_tier({"checked_by": "email:lead@example.com"}), "reviewed by a person")
        self.assertEqual(standards.trust_tier({"checked_by": "human:@thaithienvanid"}), "checked by an agent")  # not an identity form
        lib = {"python/a": front(), "python/b": front(checked_by="@lead")}
        counts = standards.trust_counts([documents.split_front_matter(t, "x")[0] for t in lib.values()])
        self.assertEqual(counts, {"checked by an agent": 1, "reviewed by a person": 1})

    def test_a_stack_holds_only_existing_active_standards_and_extends_one_level(self):
        self.f.standard(front())
        self.f.standard(front(id="python/old", fills=["ci-pipeline:formatter"], status="deprecated", replaced_by="python/demo"))
        self.f.stack("a", "standards: [python/demo, python/ghost]\n")
        self.assertProblem("stack a: python/ghost is no library standard")
        self.f.stack("a", "standards: [python/old]\n")
        self.assertProblem("stack a: python/old is deprecated")
        self.f.stack("a", "standards: [python/demo]\n")
        self.f.stack("b", "extends: a\nstandards: [python/demo]\n")
        self.f.stack("c", "extends: b\nstandards: [python/demo]\n")
        self.assertProblem("stack c extends b, which extends a: a stack extends one other stack, one level")
        self.f.stack("c", "extends: c\nstandards: [python/demo]\n")
        self.assertProblem("stack c extends itself")
        self.f.stack("c", "extends: ghost\nstandards: [python/demo]\n")
        self.assertProblem("stack c extends ghost, which is no stack")

    def test_a_stack_picks_one_standard_per_choice(self):
        self.f.standard(front())
        self.f.standard(front(id="node/lint"))
        self.f.standard(front(id="python/lint2", default=False), rel="python/lint2.md")
        self.f.stack("pick", "standards: [python/lint2]\n")  # an option other than the default is a valid pick
        self.assertEqual(self.f.problems(), [])
        self.f.stack("two", "standards: [python/demo, python/lint2]\n")
        self.assertProblem("stack two: python/demo and python/lint2 both fill ci-pipeline:linter; a stack picks one")
        # Whatever folder each standard lives in.
        self.f.stack("two", "standards: [python/demo, node/lint]\n")
        self.assertProblem("stack two: python/demo and node/lint both fill ci-pipeline:linter; a stack picks one")

    def test_tool_ownership(self):
        tool = {"name": "ruff", "registry": "pypi", "package": "ruff"}
        version = {"tool": tool, "checked_version": "1.0.0", "checked": "2026-10-01", "version_policy": "current_stable", **READ_AT}
        self.f.standard(front(**version))
        self.f.standard(front(id="python/fmt", fills=["ci-pipeline:formatter"], **version))
        self.assertProblem("the tool ruff is owned by 2 library standards")
        pinned = {"name": "actionlint", "registry": "github", "package": "rhysd/actionlint"}
        self.f.standard(front(id="python/fmt", fills=["ci-pipeline:formatter"], **{**version, "tool": pinned}))
        self.assertProblem("aidd-team:ci-pipeline already pins the tool actionlint")

    def test_the_size_cap(self):
        self.f.standard(front(body="# Long\n\n" + "word " * (standards.WORD_CAP + 1)))
        self.assertProblem(f"the cap is {standards.WORD_CAP}")

    def test_a_library_file_never_restates_a_pack(self):
        copied = "Set `permissions:` per job to the minimum. Pin every action and image by SHA or digest, the version in a comment."
        self.f.standard(front(body=f"# Copy\n\n{copied}\n"))
        self.assertProblem("restates aidd-team:ci-pipeline")
        self.f.standard(front(body="# A\n\nRun the same pinned tool in CI and in the pre-commit hook on every single change.\n"))
        self.f.standard(front(id="node/b", body="# B\n\nRun the same pinned tool in CI and in the pre-commit hook on every single change.\n"))
        self.assertProblem("python/demo repeats node/b")

    def test_renames_and_deprecation(self):
        self.f.standard(front())
        (self.f.lib / "renames.yaml").write_text('renames:\n  "python/demo": python/new\n', encoding="utf-8")
        found = self.f.problems()
        self.assertTrue(any("renames python/demo, which is still a library file" in p for p in found), found)
        self.assertTrue(any("renames to python/new, which is no library standard" in p for p in found), found)
        self.f.standard(front(id="python/old", fills=["ci-pipeline:formatter"], status="deprecated"))
        self.assertProblem("missing required field 'replaced_by'")
        self.f.standard(front(id="python/old", fills=["ci-pipeline:formatter"], status="deprecated", replaced_by="python/gone"))
        self.assertProblem("python/old is replaced by python/gone, which is no active library standard")

    def test_implements_names_a_pack_or_skill_rule(self):
        self.f.standard(front(implements="product-defaults:dev_basics"))
        self.assertEqual(self.f.problems(), [])
        self.f.standard(front(implements="product-defaults:no_such_default"))
        self.assertProblem("implements product-defaults:no_such_default")
        self.f.standard(front(implements="nowhere:rule"))
        self.assertProblem("implements nowhere:rule")

    def test_an_enforcing_command_runs_the_pinned_version(self):
        tool = {"name": "ruff", "registry": "pypi", "package": "ruff"}
        ok = {"tool": tool, "checked_version": "1.0.0", "checked": "2026-10-01", "version_policy": "current_stable", "pin": "1.0.0", **READ_AT}
        self.f.standard(front(**ok, enforced_by=[{"name": "lint", "command": ["uvx", "ruff@0.9.0", "check", "."]}]))
        self.assertProblem("runs ruff 0.9.0, not its pin 1.0.0")

    def test_dates_are_never_in_the_future_and_a_review_comes_due(self):
        self.f.standard(front(reviewed="2027-01-01"))
        self.assertProblem("reviewed 2027-01-01 is in the future")
        # Each comes due at its own spread of the cadence: the default less up to a quarter, from its id (upkeep.spread).
        self.f.standard(front(reviewed="2025-10-01"))
        self.assertProblem(f"reviewed 2025-10-01, over {upkeep.spread('python/demo', 365)} days ago")
        self.f.standard(front(reviewed="2026-07-01", maturity="emerging"))
        self.assertProblem(f"reviewed 2026-07-01, over {upkeep.spread('python/demo', 90)} days ago")
        self.assertEqual(standards.LIBRARY_REVIEW_EVERY_DAYS, upkeep.REVIEW_EVERY_DAYS)

    def test_reviews_checked_on_one_day_come_due_across_a_quarter_of_the_cadence(self):
        offsets = {365 - upkeep.spread(f"group/topic-{n}", 365) for n in range(200)}
        self.assertTrue(all(0 <= o < 365 // 4 for o in offsets), offsets)
        self.assertGreater(len(offsets), 60, "spread across the window, not bunched on a few days")
        self.assertEqual(upkeep.spread("a/b", 365), upkeep.spread("a/b", 365), "the same id, the same day, everywhere")

    def test_implements_names_a_whole_rule(self):
        self.f.standard(front(implements="ci-pipeline:Dependencies declared and locked"))
        self.assertEqual(self.f.problems(), [])
        self.f.standard(front(implements="ci-pipeline:Workflow lint"))  # a test command's row
        self.assertEqual(self.f.problems(), [])
        for part in ("ci-pipeline:locked", "ci-pipeline:Dependencies", "ci-pipeline:the"):
            self.f.standard(front(implements=part))
            self.assertProblem(f"implements {part}")

    def test_implements_never_names_a_standards_citation(self):
        # The Standards table cites what the field agrees on; it holds no rule, so a library standard never links to it.
        # Nor does a table's header row, or the Standards heading itself.
        for ref in ("ci-pipeline:SLSA", "ci-pipeline:The Twelve-Factor App", "ci-pipeline:Standards", "ci-pipeline:Standard", "ci-pipeline:Command"):
            with self.subTest(ref=ref):
                self.f.standard(front(implements=ref))
                self.assertProblem(f"implements {ref}")
        self.f.standard(front(implements="ci-pipeline:Twelve-Factor"))  # a rule's own heading still resolves
        self.assertEqual(self.f.problems(), [])

    def test_the_method_is_never_an_open_choice(self):
        bad = {"x:commit-format": {"owner": "x", "id": "commit-format", "question": "Which commit format?", "default": "d", "options": ["a", "b"]}}
        self.assertTrue(standards.method_problems(bad))
        bad = {"x:review": {"owner": "x", "id": "review", "question": "Who gives the Merge approval?", "default": "d", "options": ["a", "b"]}}
        self.assertTrue(standards.method_problems(bad))
        # The default and the options are read too, with the whole method vocabulary.
        for default, options in (
            ("Use Conventional Commits.", ["a", "b"]),
            ("d", ["squash merge", "rebase"]),
            ("d", ["one reviewer", "two"]),
            ("A sign-off from the lead.", ["a", "b"]),
            ("d", ["a Spec per change", "none"]),
            ("d", ["Assisted-by trailers", "none"]),
        ):
            bad = {"x:tool": {"owner": "x", "id": "tool", "question": "Which tool?", "default": default, "options": options}}
            self.assertTrue(standards.method_problems(bad), (default, options))


class PolicyTests(unittest.TestCase):
    def load(self, text: str, parent: str | None = None) -> config.Config:
        if parent is None:
            return config.load_text(HEAD + text)
        child = TOP + "extends: [{path: p.yaml}]\n" + HEAD.removeprefix(TOP) + text
        return config.load_text(child, prefetched={"p.yaml": HEAD + parent})

    def test_an_industry_standard_is_refused(self):
        for key in ("require", "exclude"):
            with self.assertRaises(config.ConfigError) as cm:
                self.load(f"standards_policy:\n  {key}: [wcag]\n")
            self.assertIn("'wcag' is an industry standard", str(cm.exception))
            self.assertIn("only waived per project, with a reason and an expiry", str(cm.exception))
        with self.assertRaises(config.ConfigError) as cm:
            self.load("standards_policy:\n  replace: {wcag: ours}\n")
        self.assertIn("'wcag' is an industry standard", str(cm.exception))
        with self.assertRaises(config.ConfigError):
            self.load('standards_policy:\n  replace: {"not a library id": ours}\n')

    def test_opinionated_ids_are_accepted(self):
        cfg = self.load("standards_policy:\n  require: [python/uv-tooling]\n  exclude: [python/mypy-typing]\n  allow_stacks: [python-cli]\n")
        self.assertEqual(cfg.standards_policy["require"], ["python/uv-tooling"])

    def test_a_child_adds_and_tightens_and_never_loosens(self):
        parent = 'standards_policy:\n  require: [python/uv-tooling]\n  exclude: [python/mypy-typing]\n  replace: {"python/ruff-lint-format": lint}\n  allow_stacks: [python-cli, other]\n'
        child = (
            "standards_policy:\n  require: [python/mypy-typing, python/ruff-lint-format]\n  exclude: [python/uv-tooling]\n"
            '  replace: {"python/ruff-lint-format": mine}\n  allow_stacks: [python-cli, extra]\n'
        )
        cfg = self.load(child, parent)
        p = cfg.standards_policy
        self.assertEqual(p["require"], ["python/uv-tooling"])  # a parent's require stays; the child cannot require what it excludes or replaces
        self.assertEqual(p["exclude"], ["python/mypy-typing"])  # nor exclude what it requires
        self.assertEqual(p["replace"], {"python/ruff-lint-format": "lint"})
        self.assertEqual(p["allow_stacks"], ["python-cli"])  # narrowed, never widened
        joined = "\n".join(cfg.warnings)
        for needle in ("python/mypy-typing", "python/uv-tooling", "python/ruff-lint-format", "extra"):
            self.assertIn(needle, joined)

    def test_a_child_can_add_where_the_parent_is_silent(self):
        cfg = self.load("standards_policy:\n  exclude: [python/uv-tooling]\n", "standards_policy:\n  require: [python/mypy-typing]\n")
        self.assertEqual(cfg.standards_policy, {"require": ["python/mypy-typing"], "exclude": ["python/uv-tooling"]})


class ConfigRefusalTests(unittest.TestCase):
    def test_an_industry_standard_is_never_a_project_entry(self):
        with self.assertRaises(config.ConfigError) as cm:
            config.load_text(HEAD + 'standards:\n  - name: a\n    path: docs/a.md\n    roles: ["*"]\n    type: industry\n')
        self.assertIn("an industry standard lives only in the registry (schemas/roles.json)", str(cm.exception))
        self.assertEqual(
            config.load_text(HEAD + 'standards:\n  - name: a\n    path: docs/a.md\n    roles: ["*"]\n    type: opinionated\n').standards[0]["type"],
            "opinionated",
        )

    def test_a_wrong_type_in_the_policy_is_a_clean_error(self):
        for bad in ("require: python/uv-tooling", "require: [1]", "replace: [python/uv-tooling]", "standards_policy: 3"):
            text = HEAD + (f"{bad}\n" if bad.startswith("standards_policy") else f"standards_policy:\n  {bad}\n")
            with self.assertRaises(config.ConfigError, msg=bad):
                config.load_text(text)


class Repo:
    """A git repository with an aidd config, for the commands."""

    def __init__(self, tmp: Path, extra: str = ""):
        self.root = tmp / "repo"
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        (self.root / ".aidd").mkdir()
        self.config.write_text(HEAD + extra, encoding="utf-8")

    @property
    def config(self) -> Path:
        return self.root / ".aidd" / "config.yaml"

    def cli(self, *argv: str) -> tuple[int, str]:
        with contextlib.chdir(self.root):
            return helpers.run_cli(*argv)

    def cfg(self) -> config.Config:
        return config.load_file(config.CONFIG_PATH, str(self.root))

    def doctor(self) -> list[tuple[str, str]]:
        return [x for x in doctor_checks.doctor(self.root) if "standard" in x[1] or "stack" in x[1]]


class AddTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()

    def test_add_vendors_the_copy_the_entry_and_its_tests(self):
        r = Repo(self.tmp)
        code, out = r.cli("standard", "add", "python/ruff-lint-format")
        self.assertEqual(code, 0, out)
        lib = standards.standards_library()["python/ruff-lint-format"]
        copy = r.root / "docs" / "standards" / "python" / "ruff-lint-format.md"
        self.assertEqual(copy.read_text(encoding="utf-8"), lib.text)
        cfg = r.cfg()
        entry = next(s for s in cfg.standards if s["name"] == "python-ruff-lint-format")
        self.assertEqual(entry["type"], "opinionated")
        self.assertEqual(entry["fills"], ["ci-pipeline:linter", "ci-pipeline:formatter"])
        self.assertEqual(entry["vendored"], {"id": "python/ruff-lint-format", "aidd_version": __version__, "sha256": lib.sha256})
        self.assertEqual(entry["enforced_by"], ["std.python.ruff-lint-format.lint", "std.python.ruff-lint-format.format"])
        tests = {t["name"]: t for t in cfg.get("tests")}
        self.assertEqual(tests["std.python.ruff-lint-format.lint"]["command"], ["uvx", "ruff@0.16.10", "check", "."])
        self.assertEqual(tests["std.python.ruff-lint-format.lint"]["when_changed"], lib.meta["when_changed"])
        self.assertIn("unit", tests)  # the project's own tests stay
        self.assertEqual([x for x in r.doctor() if x[0] != "ok"], [])
        # Adding it again changes nothing.
        before = r.config.read_text(encoding="utf-8")
        code, out = r.cli("standard", "add", "python/ruff-lint-format")
        self.assertEqual((code, r.config.read_text(encoding="utf-8")), (0, before), out)
        self.assertIn("already", out)

    def test_add_refuses_what_the_policy_or_the_library_does_not_allow(self):
        policy = 'standards_policy:\n  exclude: [python/mypy-typing]\n  replace: {"python/uv-tooling": our-env}\n'
        r = Repo(self.tmp, policy)
        before = r.config.read_text(encoding="utf-8")
        for argv, needle in (
            (("python/mypy-typing",), "excludes python/mypy-typing"),
            (("python/uv-tooling",), "replaces python/uv-tooling with its own standard our-env"),
            (("wcag",), "wcag is an industry standard"),
            (("python/ghost",), "no library standard python/ghost"),
            (("python/ruff-lint-format", "python/mypy-typing"), "excludes python/mypy-typing"),  # all or nothing
        ):
            code, out = r.cli("standard", "add", *argv)
            self.assertEqual(code, 2, out)
            self.assertIn(needle, out)
            self.assertEqual(r.config.read_text(encoding="utf-8"), before)
        self.assertFalse((r.root / "docs" / "standards").exists())

    def test_add_never_writes_through_a_link(self):
        r = Repo(self.tmp)
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        (r.root / "docs").mkdir()
        try:
            (r.root / "docs" / "standards").symlink_to(elsewhere, target_is_directory=True)
        except OSError:  # Windows without the privilege to make a link
            self.skipTest("this machine cannot make a symbolic link")
        before = r.config.read_text(encoding="utf-8")
        code, out = r.cli("standard", "add", "python/uv-tooling")
        self.assertEqual(code, 2, out)
        self.assertIn("outside the repository or behind a link", out)
        self.assertEqual((list(elsewhere.iterdir()), r.config.read_text(encoding="utf-8")), ([], before))

    def test_add_refuses_a_second_standard_for_one_choice(self):
        fake = dict(standards.standards_library())
        twin = standards.Standard(id="python/twin", meta={**fake["python/mypy-typing"].meta, "id": "python/twin"}, body="", text="x", rel="python/twin.md")
        fake["python/twin"] = twin
        r = Repo(self.tmp)
        self.assertEqual(r.cli("standard", "add", "python/mypy-typing")[0], 0)
        with mock.patch.object(standards, "standards_library", return_value=fake):
            code, out = r.cli("standard", "add", "python/twin")
        self.assertEqual(code, 2, out)
        self.assertIn("python-mypy-typing already fills ci-pipeline:type-checker for python", out)

    def test_a_renamed_id_resolves_and_a_deprecated_one_is_refused(self):
        r = Repo(self.tmp)
        with mock.patch.object(standards, "renames", return_value={"python/ruff": "python/ruff-lint-format"}):
            code, out = r.cli("standard", "add", "python/ruff")
        self.assertEqual(code, 0, out)
        self.assertIn("python/ruff was renamed to python/ruff-lint-format", out)
        fake = dict(standards.standards_library())
        old = fake["python/mypy-typing"]
        fake["python/mypy-typing"] = standards.Standard(
            old.id, {**old.meta, "status": "deprecated", "replaced_by": "python/uv-tooling"}, old.body, old.text, old.rel
        )
        with mock.patch.object(standards, "standards_library", return_value=fake):
            code, out = r.cli("standard", "add", "python/mypy-typing")
        self.assertEqual(code, 2, out)
        self.assertIn("python/mypy-typing is deprecated; add python/uv-tooling", out)

    def test_stack_add_vendors_each_standard_and_merges_the_radar(self):
        r = Repo(self.tmp, "project:\n  stack:\n    adopt: [PostgreSQL]\n    hold: [MongoDB]\n")
        code, out = r.cli("stack", "add", "python-cli")
        self.assertEqual(code, 0, out)
        cfg = r.cfg()
        vendored = {s["vendored"]["id"]: s["vendored"] for s in cfg.standards if "vendored" in s}
        self.assertEqual(set(vendored), SEED)
        self.assertEqual({v["stack"] for v in vendored.values()}, {"python-cli"})
        self.assertEqual(cfg.get("project", "stack", "adopt"), ["PostgreSQL", "Python", "uv", "Ruff", "mypy"])
        self.assertEqual(cfg.get("project", "stack", "hold"), ["MongoDB"])
        self.assertEqual(json_schema.validate(documents.parse_yaml(r.config.read_text(encoding="utf-8"), "c"), "config.schema.json"), [])
        code, out = r.cli("stack", "add", "python-cli")
        self.assertEqual(code, 0, out)  # again: nothing new
        self.assertEqual(r.cfg().get("project", "stack", "adopt"), ["PostgreSQL", "Python", "uv", "Ruff", "mypy"])

    def test_stack_add_writes_the_radar_when_there_is_none(self):
        r = Repo(self.tmp, "project:\n  hosting: one VPS\n")
        self.assertEqual(r.cli("stack", "add", "python-cli")[0], 0)
        self.assertEqual(r.cfg().get("project", "stack", "adopt"), ["Python", "uv", "Ruff", "mypy"])
        self.assertEqual(r.cfg().get("project", "hosting"), "one VPS")

    def test_stack_add_follows_allow_stacks(self):
        r = Repo(self.tmp, "standards_policy:\n  allow_stacks: [python-api]\n")
        code, out = r.cli("stack", "add", "python-cli")
        self.assertEqual(code, 2, out)
        self.assertIn("allows only the stacks python-api", out)
        code, out = r.cli("stack", "add", "ghost")
        self.assertEqual(code, 2, out)
        self.assertIn("no stack ghost", out)

    def test_list_shows_the_choices_the_library_and_the_policy(self):
        r = Repo(self.tmp, "standards_policy:\n  exclude: [python/mypy-typing]\n")
        r.cli("standard", "add", "python/uv-tooling")
        code, out = r.cli("standard", "list", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json_schema.validate(json.loads(out), "standard-list.schema.json"), [])
        self.assertEqual(json.loads(out)["schema_version"], "1")
        rows = {x["id"]: x for x in json.loads(out)["standards"]}
        self.assertEqual(set(rows), set(standards.standards_library()))  # every library standard is listed
        self.assertLessEqual(SEED, set(rows))
        self.assertEqual(rows["python/mypy-typing"]["policy"], "excluded")
        self.assertIs(rows["python/ruff-lint-format"]["default"], True)  # aidd's default for the choices it fills
        choice = next(c for c in json.loads(out)["open_choices"] if c["ref"] == "ci-pipeline:linter")
        self.assertEqual(choice["default_by_ecosystem"]["python"], "python/ruff-lint-format")  # one per ecosystem
        self.assertEqual(choice["pack"], "ci-pipeline")
        self.assertTrue(choice["default_answer"])
        for old in ("owner", "default", "defaults"):
            self.assertNotIn(old, choice)
        self.assertTrue(rows["python/uv-tooling"]["added"])
        self.assertIn("ci-pipeline:linter", {c["ref"] for c in json.loads(out)["open_choices"]})
        self.assertEqual(rows["python/ruff-lint-format"]["trust"], standards.trust_tier(standards.standards_library()["python/ruff-lint-format"].meta))
        code, out = r.cli("standard", "list")
        self.assertIn("python/ruff-lint-format", out)
        self.assertIn("excluded", out)
        # Where an ecosystem has options for a choice, the default among them is marked; with one option, nothing is.
        self.assertIn("iac/opentofu (default), iac/terraform", out)
        self.assertIn("typescript/biome-lint-format (default), typescript/eslint-prettier", out)
        self.assertNotIn("python/ruff-lint-format (default)", out)
        self.assertNotIn("go/golangci-lint (default)", out)
        lib = dict(standards.standards_library())
        m = lib["python/mypy-typing"]
        lib["python/pyright"] = standards.Standard("python/pyright", {**m.meta, "id": "python/pyright", "default": False}, m.body, m.text, "python/pyright.md")
        lib["python/uv-tooling"] = standards.Standard(
            "python/uv-tooling", {**lib["python/uv-tooling"].meta, "checked_by": "@lead"}, "", "", "python/uv-tooling.md"
        )
        with mock.patch.object(standards, "standards_library", return_value=lib):
            code, out = r.cli("standard", "list")
        self.assertIn("Library: python/mypy-typing (default), python/pyright, typescript/tsc-strict.", out.replace("dotnet/analyzers-nullable, ", ""))
        # Each library standard says who checked it: an agent, until a person reviews it.
        line = {ln.split(":", 1)[0].strip(): ln for ln in out.splitlines() if ln.startswith("  ") and "/" in ln.split(":", 1)[0]}
        self.assertIn("reviewed by a person", line["python/uv-tooling"])
        self.assertIn("checked by an agent", line["python/mypy-typing"])
        code, out = r.cli("stack", "list")
        self.assertEqual(code, 0, out)
        self.assertIn("python-cli", out)
        code, out = r.cli("stack", "list", "--json")
        self.assertEqual(json_schema.validate(json.loads(out), "stack-list.schema.json"), [])
        self.assertEqual(json.loads(out)["schema_version"], "1")
        by_name = {x["name"]: x for x in json.loads(out)["stacks"]}  # looked up by name: the catalog adds stacks before it
        self.assertEqual(by_name["python-cli"]["standards"], ["python/uv-tooling", "python/ruff-lint-format", "python/mypy-typing"])


class SafeWriteTests(unittest.TestCase):
    """`add` never overwrites a person's file, and writes everything or nothing."""

    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()

    def test_add_refuses_to_overwrite_a_persons_file(self):
        r = Repo(self.tmp)
        mine = r.root / "docs" / "standards" / "python" / "uv-tooling.md"
        mine.parent.mkdir(parents=True)
        mine.write_text("# Our own uv rules\n", encoding="utf-8")
        before = r.config.read_text(encoding="utf-8")
        for argv in (("standard", "add", "python/mypy-typing", "python/uv-tooling"), ("stack", "add", "python-cli")):
            code, out = r.cli(*argv)
            self.assertEqual(code, 2, out)
            self.assertIn("docs/standards/python/uv-tooling.md exists and is not aidd's copy; move it, or name it in `standards_policy.replace`", out)
            self.assertEqual((mine.read_text(encoding="utf-8"), r.config.read_text(encoding="utf-8")), ("# Our own uv rules\n", before))
            self.assertFalse((mine.parent / "mypy-typing.md").exists())
        # A file that already holds the library text is adopted.
        mine.write_text(standards.standards_library()["python/uv-tooling"].text, encoding="utf-8")
        self.assertEqual(r.cli("standard", "add", "python/uv-tooling")[0], 0)

    def test_add_refuses_a_name_or_a_test_the_config_already_has(self):
        r = Repo(self.tmp, 'standards:\n  - name: python-uv-tooling\n    path: docs/own.md\n    roles: ["*"]\n')
        code, out = r.cli("standard", "add", "python/uv-tooling")
        self.assertEqual(code, 2, out)
        self.assertIn("the config already has a `standards` entry named python-uv-tooling", out)
        (self.tmp / "b").mkdir()
        r = Repo(self.tmp / "b", '  - name: std.python.uv-tooling.lock\n    command: ["true"]\n')
        code, out = r.cli("standard", "add", "python/uv-tooling")
        self.assertEqual(code, 2, out)
        self.assertIn("the config already has a `tests` entry named std.python.uv-tooling.lock", out)

    def test_a_failed_write_leaves_everything_as_it_was(self):
        r = Repo(self.tmp)
        lib = dict(standards.standards_library())
        u = lib["python/uv-tooling"]
        first = standards.Standard(
            "aaa/first", {**u.meta, "id": "aaa/first", "fills": ["ci-pipeline:linter"], "enforced_by": []}, u.body, u.text, "aaa/first.md"
        )
        lib["aaa/first"] = first
        (r.root / "docs" / "standards").mkdir(parents=True)
        (r.root / "docs" / "standards" / "python").write_text("a file where a folder must go\n", encoding="utf-8")
        before = r.config.read_text(encoding="utf-8")
        with mock.patch.object(standards, "standards_library", return_value=lib):
            code, out = r.cli("standard", "add", "aaa/first", "python/uv-tooling")
        self.assertEqual(code, 2, out)
        self.assertIn("nothing added: cannot write docs/standards/python/uv-tooling.md", out)
        self.assertNotIn("Errno", out)
        self.assertEqual(r.config.read_text(encoding="utf-8"), before)
        self.assertEqual(sorted(p.name for p in (r.root / "docs" / "standards").iterdir()), ["python"])  # no copy, no temp file, no new folder
        self.assertEqual(sorted(p.name for p in r.config.parent.iterdir()), ["config.yaml"])

    def test_upgrade_never_moves_a_renamed_copy_onto_a_persons_file(self):
        r = Repo(self.tmp)
        r.cli("standard", "add", "python/uv-tooling")
        theirs = r.root / "docs" / "standards" / "python" / "env.md"
        theirs.write_text("# ours\n", encoding="utf-8")
        lib = dict(standards.standards_library())
        old = lib.pop("python/uv-tooling")
        lib["python/env"] = standards.Standard("python/env", {**old.meta, "id": "python/env"}, old.body, old.text, "python/env.md")
        before = r.config.read_text(encoding="utf-8")
        with (
            mock.patch.object(standards, "standards_library", return_value=lib),
            mock.patch.object(standards, "renames", return_value={"python/uv-tooling": "python/env"}),
        ):
            actions = upgrading.upgrade(r.root, yes=True)
        self.assertTrue(any("docs/standards/python/env.md exists and is not aidd's copy" in a for a in actions), actions)
        self.assertEqual(theirs.read_text(encoding="utf-8"), "# ours\n")
        self.assertTrue((r.root / "docs" / "standards" / "python" / "uv-tooling.md").is_file())
        self.assertIn("python/uv-tooling", r.config.read_text(encoding="utf-8"))
        self.assertEqual(before.count("# aidd:standard"), r.config.read_text(encoding="utf-8").count("# aidd:standard"))

    def test_upgrade_refreshes_only_a_copy_under_the_standards_folder(self):
        r = Repo(self.tmp)
        r.cli("standard", "add", "python/uv-tooling")
        text = r.config.read_text(encoding="utf-8").replace("path: docs/standards/python/uv-tooling.md", "path: src/main.py")
        r.config.write_text(text, encoding="utf-8")
        (r.root / "src").mkdir()
        (r.root / "src" / "main.py").write_text("print('mine')\n", encoding="utf-8")
        lib = dict(standards.standards_library())
        u = lib["python/uv-tooling"]
        lib["python/uv-tooling"] = standards.Standard(u.id, u.meta, u.body, u.text + "\nNewer.\n", u.rel)
        with mock.patch.object(standards, "standards_library", return_value=lib), mock.patch.object(standards, "__version__", "1.1.0"):
            actions = upgrading.upgrade(r.root, yes=True)
        self.assertEqual((r.root / "src" / "main.py").read_text(encoding="utf-8"), "print('mine')\n")
        self.assertTrue(any("src/main.py: not under docs/standards/" in a for a in actions), actions)


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()

    def test_an_edited_copy_and_drift(self):
        r = Repo(self.tmp)
        r.cli("standard", "add", "python/uv-tooling", "python/mypy-typing")
        copy = r.root / "docs" / "standards" / "python" / "uv-tooling.md"
        copy.write_text(copy.read_text(encoding="utf-8") + "\nOne more rule.\n", encoding="utf-8")
        found = r.doctor()
        self.assertIn(
            (
                "warn",
                "standards 'python-uv-tooling': the copy of python/uv-tooling was edited; never edit a copy: restore it, or write your own standard and name it in `standards_policy.replace`",
            ),
            found,
        )
        lib = dict(standards.standards_library())
        old = lib["python/mypy-typing"]
        lib["python/mypy-typing"] = standards.Standard(old.id, old.meta, old.body, old.text + "\nNew in this aidd.\n", old.rel)
        # A newer library comes with a newer aidd: within one version, the library never changes.
        with mock.patch.object(standards, "standards_library", return_value=lib), mock.patch.object(standards, "__version__", "1.1.0"):
            found = r.doctor()
        self.assertIn(("warn", "standards 'python-mypy-typing': aidd 1.1.0 ships a newer python/mypy-typing; `aidd upgrade --yes` refreshes the copy"), found)

    def test_an_edited_copy_is_found_when_its_recorded_hash_was_edited_too(self):
        r = Repo(self.tmp, "standards_policy:\n  require: [python/uv-tooling]\n")
        r.cli("standard", "add", "python/uv-tooling")
        copy = r.root / "docs" / "standards" / "python" / "uv-tooling.md"
        weaker = copy.read_text(encoding="utf-8").replace("fails the change", "is fine")
        copy.write_text(weaker, encoding="utf-8")
        text = r.config.read_text(encoding="utf-8")
        r.config.write_text(re.sub(r'sha256 = "[0-9a-f]{64}"', f'sha256 = "{standards.digest(weaker)}"', text), encoding="utf-8")
        fails = [m for level, m in r.doctor() if level == "fail"]
        self.assertIn(
            "standards policy: python-uv-tooling is an edited copy of python/uv-tooling, which the company requires as it is; restore the copy", fails
        )

    def test_a_weakened_entry_is_reported(self):
        cases = (
            ("command: [uv, lock, --check]", 'command: ["true"]'),
            ("    enforced_by: [std.python.uv-tooling.lock]\n", ""),
            ("    when_changed: [pyproject.toml, uv.lock]\n    enforced_by", '    when_changed: ["nothing/**"]\n    enforced_by'),
        )
        for old, new in cases:
            with self.subTest(old=old):
                tmp = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
                r = Repo(tmp, "standards_policy:\n  require: [python/uv-tooling]\n")
                r.cli("standard", "add", "python/uv-tooling")
                self.assertEqual([m for level, m in r.doctor() if level == "fail"], [])
                text = r.config.read_text(encoding="utf-8")
                self.assertIn(old, text)
                r.config.write_text(text.replace(old, new, 1), encoding="utf-8")
                fails = [m for level, m in r.doctor() if level == "fail"]
                self.assertTrue(any("python-uv-tooling: its config entry no longer matches python/uv-tooling" in m for m in fails), fails)
        # Without the policy, the same finding is a warning.
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        r = Repo(tmp)
        r.cli("standard", "add", "python/uv-tooling")
        r.config.write_text(r.config.read_text(encoding="utf-8").replace("command: [uv, lock, --check]", 'command: ["true"]'), encoding="utf-8")
        warns = [m for level, m in r.doctor() if level == "warn"]
        self.assertTrue(
            any("its config entry no longer matches python/uv-tooling" in m and "the `tests` entry std.python.uv-tooling.lock" in m for m in warns), warns
        )

    def test_a_copy_that_is_not_utf8_is_an_edited_copy(self):
        r = Repo(self.tmp)
        r.cli("standard", "add", "python/uv-tooling")
        copy = r.root / "docs" / "standards" / "python" / "uv-tooling.md"
        copy.write_bytes(b"\xff\xfe not text")
        found = r.doctor()
        self.assertTrue(any("the copy of python/uv-tooling was edited" in m for _, m in found), found)
        actions = upgrading.upgrade(r.root, yes=True)
        self.assertTrue(any("kept docs/standards/python/uv-tooling.md" in a for a in actions), actions)
        self.assertEqual(copy.read_bytes(), b"\xff\xfe not text")

    def test_policy_breaches_fail(self):
        r = Repo(self.tmp)
        r.cli("stack", "add", "python-cli")
        text = r.config.read_text(encoding="utf-8")
        r.config.write_text(
            text + '\nstandards_policy:\n  exclude: [python/mypy-typing]\n  replace: {"python/uv-tooling": our-env}\n'
            "  require: [python/ruff-lint-format, go/gofmt]\n  allow_stacks: [python-api]\n",
            encoding="utf-8",
        )
        fails = [m for level, m in r.doctor() if level == "fail"]
        self.assertIn("standards policy: python-mypy-typing copies python/mypy-typing, which the company excludes; remove it", fails)
        self.assertIn("standards policy: python-uv-tooling copies python/uv-tooling, which the company replaces with its own standard our-env", fails)
        self.assertIn("standards policy: the company requires go/gofmt; `aidd standard add go/gofmt`", fails)
        self.assertIn(
            "standards policy: python-ruff-lint-format came with the stack python-cli, which the company does not allow (allow_stacks: python-api)", fails
        )
        self.assertFalse(any("python/ruff-lint-format;" in m for m in fails))  # present, so the requirement holds
        # A project never loosens a required standard by editing its copy.
        copy = r.root / "docs" / "standards" / "python" / "ruff-lint-format.md"
        copy.write_text(copy.read_text(encoding="utf-8").replace("A finding fails the change.", "Findings are fine."), encoding="utf-8")
        fails = [m for level, m in r.doctor() if level == "fail"]
        self.assertIn(
            "standards policy: python-ruff-lint-format is an edited copy of python/ruff-lint-format, which the company requires as it is; restore the copy",
            fails,
        )

    def test_deprecated_and_renamed_ids(self):
        r = Repo(self.tmp)
        r.cli("standard", "add", "python/uv-tooling", "python/mypy-typing")
        lib = dict(standards.standards_library())
        old = lib.pop("python/uv-tooling")
        lib["python/env"] = standards.Standard("python/env", {**old.meta, "id": "python/env"}, old.body, old.text, "python/env.md")
        m = lib["python/mypy-typing"]
        lib["python/mypy-typing"] = standards.Standard(m.id, {**m.meta, "status": "deprecated", "replaced_by": "python/env"}, m.body, m.text, m.rel)
        with (
            mock.patch.object(standards, "standards_library", return_value=lib),
            mock.patch.object(standards, "renames", return_value={"python/uv-tooling": "python/env"}),
        ):
            found = r.doctor()
        self.assertIn(("warn", "standards 'python-uv-tooling': python/uv-tooling was renamed to python/env; `aidd upgrade --yes` moves the copy"), found)
        self.assertIn(
            (
                "warn",
                "standards 'python-mypy-typing': python/mypy-typing is deprecated, replaced by python/env; `aidd standard add python/env`, then remove this one",
            ),
            found,
        )

    def test_two_standards_for_one_choice_are_warned(self):
        # The library may hold several options for a choice; a project adopts one. A second one, written past
        # `aidd standard add` (which refuses it), is a warning that names aidd's default.
        r = Repo(self.tmp)
        r.cli("standard", "add", "python/mypy-typing")
        lib = dict(standards.standards_library())
        m = lib["python/mypy-typing"]
        other = standards.Standard(
            "python/pyright", {**m.meta, "id": "python/pyright", "default": False}, m.body, m.text + "\nAnother option.\n", "python/pyright.md"
        )
        lib[other.id] = other
        copy = r.root / "docs" / "standards" / "python" / "pyright.md"
        copy.write_text(other.text, encoding="utf-8")
        r.config.write_text(standards.add_block(r.config.read_text(encoding="utf-8"), other, "docs"), encoding="utf-8")
        with mock.patch.object(standards, "standards_library", return_value=lib):
            found = r.doctor()
        self.assertIn(
            (
                "warn",
                "standards 'python-pyright': python-mypy-typing already fills ci-pipeline:type-checker for python; keep one standard per choice "
                "(aidd's default: python/mypy-typing)",
            ),
            found,
        )

    def test_a_sound_set_is_ok_and_an_unknown_choice_is_warned(self):
        r = Repo(self.tmp, 'standards:\n  - name: own\n    path: docs/own.md\n    roles: ["*"]\n    fills: [ci-pipeline:nope]\n')
        (r.root / "docs").mkdir()
        (r.root / "docs" / "own.md").write_text("# own\n", encoding="utf-8")
        found = r.doctor()
        self.assertIn(("warn", "standards 'own': fills ci-pipeline:nope, which no pack or practice skill declares (`aidd standard list` names them)"), found)


class UpgradeTests(unittest.TestCase):
    def test_upgrade_refreshes_an_unedited_copy_and_keeps_an_edited_one(self):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        r = Repo(tmp)
        r.cli("standard", "add", "python/uv-tooling", "python/mypy-typing")
        edited = r.root / "docs" / "standards" / "python" / "uv-tooling.md"
        edited.write_text(edited.read_text(encoding="utf-8") + "\nmine\n", encoding="utf-8")
        lib = dict(standards.standards_library())
        m = lib["python/mypy-typing"]
        newer = m.text.replace('pin: "2.4.0"', 'pin: "2.4.1"').replace("mypy==2.4.0", "mypy==2.4.1")
        meta, body = documents.split_front_matter(newer, "x")
        lib["python/mypy-typing"] = standards.Standard(m.id, meta, body, newer, m.rel)
        with mock.patch.object(standards, "standards_library", return_value=lib), mock.patch.object(standards, "__version__", "1.1.0"):
            before = r.config.read_text(encoding="utf-8")
            dry = upgrading.upgrade(r.root, yes=False)
            self.assertEqual(r.config.read_text(encoding="utf-8"), before)
            self.assertTrue(any("python/mypy-typing" in a for a in dry), dry)
            actions = upgrading.upgrade(r.root, yes=True)
        self.assertTrue(any("kept docs/standards/python/uv-tooling.md: the copy was edited" in a for a in actions), actions)
        copy = r.root / "docs" / "standards" / "python" / "mypy-typing.md"
        self.assertEqual(copy.read_text(encoding="utf-8"), newer)
        cfg = r.cfg()
        entry = next(s for s in cfg.standards if s["name"] == "python-mypy-typing")
        self.assertEqual(entry["vendored"]["sha256"], standards.digest(newer))
        self.assertEqual({t["name"]: t["command"] for t in cfg.get("tests")}["std.python.mypy-typing.types"], ["uv", "run", "--with", "mypy==2.4.1", "mypy"])


class ConfiguredDirTests(unittest.TestCase):
    """One normal form for a folder the config names, so a pattern or a path built from it matches git's paths."""

    def test_the_normaliser(self):
        from aidd.kernel import globs

        cases = {
            "docs": "docs",
            "docs/": "docs",
            "./docs": "docs",
            "././docs//": "docs",
            "a//b": "a/b",
            "a/./b": "a/b",
            "./a/./b/.": "a/b",
            ".": ".",
            "./": ".",
            "": ".",
        }
        for raw, want in cases.items():
            self.assertEqual(globs.normal_dir(raw), want, raw)
        # No caller can build a pattern over the whole repository from a folder.
        for top in (".", "./", "", "././"):
            with self.assertRaises(ValueError, msg=top):
                globs.under(top, "standards/**")
        self.assertEqual(globs.under("./custom/", "standards/**"), "custom/standards/**")
        self.assertEqual(globs.under("docs", "feedback/x.md"), "docs/feedback/x.md")

    def test_the_config_gives_the_normal_form(self):
        for raw, want in (("./custom", "custom"), ("docs/", "docs"), ("a//./b", "a/b")):
            self.assertEqual(config.load_text(HEAD + f"docs:\n  dir: {json.dumps(raw)}\n").docs_dir, want, raw)
        self.assertEqual(config.load_text(HEAD).docs_dir, "docs")

    def test_a_copy_under_a_dot_slash_docs_dir_has_a_plain_path(self):
        tmp = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        r = Repo(tmp, "docs:\n  dir: ./custom/\n")
        code, out = r.cli("standard", "add", "python/uv-tooling")
        self.assertEqual(code, 0, out)
        self.assertTrue((r.root / "custom" / "standards" / "python" / "uv-tooling.md").is_file())
        self.assertEqual(next(s for s in r.cfg().standards if s["name"] == "python-uv-tooling")["path"], "custom/standards/python/uv-tooling.md")
        self.assertEqual([x for x in r.doctor() if x[0] != "ok"], [])


ROOT_FORMS = (".", "./", "././", "./.", "", "/", ".//")
FOLDER_FORMS = ("x", "./x", "x/", "./x/", "a/b", "./a/./b//", ".hidden", "a/.", "x.y")
FOLDER_KEYS = {
    "docs": lambda v: f"docs:\n  dir: {json.dumps(v)}\n",
    "specs_dir": lambda v: f"specs_dir: {json.dumps(v)}\n",
    "proposals_dir": lambda v: f"proposals_dir: {json.dumps(v)}\n",
}


def with_folder(key: str, value: str) -> str:
    """A config that sets one folder key."""
    return HEAD + FOLDER_KEYS[key](value)


class FolderWideningTests(unittest.TestCase):
    """No value a config accepts for a folder widens a role area or a rule to the whole repository."""

    def test_the_repository_top_is_refused_for_every_folder(self):
        for key in FOLDER_KEYS:
            for value in ROOT_FORMS:
                with self.subTest(key=key, value=value), self.assertRaises(config.ConfigError):
                    config.load_text(with_folder(key, value))

    def test_a_folder_that_slips_past_the_schema_is_refused_by_name(self):
        from aidd.kernel import json_schema as schemamod

        for key, value in (("docs", "."), ("specs_dir", "./"), ("proposals_dir", "./.")):
            with mock.patch.object(schemamod, "validate", return_value=[]), self.assertRaises(config.ConfigError) as cm:
                config.load_text(with_folder(key, value))
            self.assertIn("the repository's top", str(cm.exception))
            self.assertIn("dir" if key == "docs" else key, str(cm.exception))

    def test_no_accepted_value_builds_a_pattern_over_everything(self):
        from aidd.guard import role_areas
        from aidd.gate import routing
        from aidd.kernel import globs

        for key in FOLDER_KEYS:
            for value in FOLDER_FORMS:
                with self.subTest(key=key, value=value):
                    cfg = config.load_text(with_folder(key, value))
                    patterns = [p for ps in role_areas.placeholder_fill(cfg, [], None).values() for p in ps]
                    patterns += [globs.under(cfg.specs_dir, x) for x in ("*/explore/*/exploration.md", "explore/*/exploration.md")]
                    patterns += [globs.under(cfg.docs_dir, "feedback/**")]
                    patterns += [p for r in routing.active_rules(cfg) for p in r["paths"]]
                    wide = [p for p in patterns if p in ("**", "*", "**/*") or globs.is_catch_all(p) and not p.startswith("**/")]
                    self.assertEqual(wide, [])
                    self.assertEqual(routing.proposal_only(["src/app.py"], cfg), [])
                    self.assertFalse(globs.match_any([globs.under(cfg.specs_dir, "**"), globs.under(cfg.proposals_dir, "**")], "src/app.py"))


class SpecsAndProposalsDirTests(unittest.TestCase):
    """`specs_dir: ./specs` and `proposals_dir: ./proposals` behave exactly like `specs` and `proposals`."""

    DOTTED = "specs_dir: ./specs\nproposals_dir: ./proposals/\n"

    def test_the_config_gives_the_normal_form(self):
        cfg = config.load_text(TOP + self.DOTTED + HEAD.removeprefix(TOP))
        self.assertEqual((cfg.specs_dir, cfg.proposals_dir), ("specs", "proposals"))
        with self.assertRaises(config.ConfigError):
            config.load_text(TOP + 'specs_dir: "."\n' + HEAD.removeprefix(TOP))

    def test_a_spec_is_found_in_the_diff(self):
        from aidd.workitems import branch_specs

        files = [{"path": "specs/SPEC-1.md"}, {"path": "src/a.py"}]
        spec = "---\nkind: spec\n---\n"
        for folder in ("specs", "./specs", "specs/", "./specs/"):
            self.assertEqual(branch_specs.find_spec_in_diff(files, folder, lambda p: spec), "specs/SPEC-1.md", folder)
        with self.assertRaises(ValueError):  # the repository's top is never the Specs folder
            branch_specs.find_spec_in_diff([{"path": "SPEC-1.md"}], ".", lambda p: spec)

    def test_the_proposals_only_route_is_the_same(self):
        from aidd.gate import routing

        paths = ["proposals/PROP-1/proposal.md", "proposals/PROP-1/share/deck.pdf"]
        for extra in ("", "proposals_dir: ./proposals\n", "proposals_dir: proposals/\n"):
            cfg = config.load_text(TOP + extra + HEAD.removeprefix(TOP))
            self.assertEqual(routing.proposal_only(paths, cfg), paths, extra)
            self.assertEqual(routing.proposal_only([*paths, "src/a.py"], cfg), [], extra)

    def test_the_guard_reads_the_folders_the_same_way(self):
        from aidd.guard import edit_check

        verdicts = []
        for extra in ("", self.DOTTED):
            tmp = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
            root = helpers.make_repo(tmp / "repo", "team", spec="02-normal-feature:specs/SPEC-220.md", status="ready")
            cfg = root / ".aidd" / "config.yaml"
            text = cfg.read_text(encoding="utf-8")
            cfg.write_text(text.replace("\n", "\n" + extra, 1), encoding="utf-8")
            self.assertEqual(config.load_file(config.CONFIG_PATH, str(root)).specs_dir, "specs")
            cases = (
                ("tests/checkout/test_rate_limit.py", "developer"),  # frozen by the Spec
                ("src/checkout/rate_limit/limiter.py", "developer"),  # inside the Task's scope
                ("src/billing/invoice.py", "developer"),  # outside it
                ("specs/SPEC-221.md", "product-manager"),  # the Specs folder
                ("proposals/PROP-1/proposal.md", "delivery-manager"),  # the proposals folder
            )
            verdicts.append([edit_check.check_edit(str(root), rel, role)[0] for rel, role in cases])
        self.assertEqual(verdicts[0], ["deny", "allow", "deny", "allow", "allow"])
        self.assertEqual(verdicts[1], verdicts[0])


class RouteTests(unittest.TestCase):
    """An edit under the standards folder routes normal at least, so an edited copy needs a person's Spec approval."""

    def assess(self, path: str, extra: str = "") -> str:
        from aidd.gate import routing

        return routing.assess_paths(config.load_text(HEAD + extra), [path]).required_route

    def test_the_standards_folder_routes_normal(self):
        self.assertIn("baseline:standards", {r["name"] for r in baseline.baseline_data()["risk_rules"]})
        for path in ("docs/standards/python/uv-tooling.md", "docs/standards/api-errors.md", "services/api/docs/standards/x.md"):
            self.assertEqual(self.assess(path), "normal", path)
        self.assertEqual(self.assess("docs/guide.md"), "minor")
        # A repository whose docs live elsewhere: its own standards folder routes normal too.
        self.assertEqual(self.assess("handbook/standards/python/uv-tooling.md", "docs:\n  dir: handbook\n"), "normal")
        self.assertEqual(self.assess("handbook/standards/python/uv-tooling.md"), "minor")

    def test_a_dot_or_a_dot_slash_docs_dir_still_routes_normal(self):
        for docs_dir, path in (("./custom", "custom/standards/x.md"), ("./a//./b/", "a/b/standards/x.md")):
            self.assertEqual(self.assess(path, f"docs:\n  dir: {json.dumps(docs_dir)}\n"), "normal", docs_dir)

    def test_the_cases_for_a_dot_docs_dir_pin_it(self):
        by = {name: d for name, d, _ in helpers.replayed_corpus()}
        self.assertEqual(by["01-minor-docs/standards-copy-with-docs-dir-dot-slash"].codes(), ["fail route.too_low"])
        self.assertEqual(by["02-normal-feature/standards-with-docs-dir-dot-slash-inside-a-normal-spec"].decision, "pass")
        # A folder at the repository's top is refused: the gate fails on the config, never widens a rule.
        for name in (
            "01-minor-docs/docs-dir-at-the-top-is-refused",
            "01-minor-docs/proposals-dir-at-the-top-is-refused",
            "02-normal-feature/specs-dir-at-the-top-is-refused",
        ):
            self.assertEqual(by[name].codes(), ["fail config.invalid"], name)

    def test_a_pass_and_a_fail_case_pin_it(self):
        by = {name: d for name, d, _ in helpers.replayed_corpus()}
        failing = by["01-minor-docs/standards-copy-in-a-minor-change"]
        self.assertEqual(failing.codes(), ["fail route.too_low"])
        self.assertIn("baseline:standards", next(f.message for f in failing.findings if f.code == "route.too_low"))
        self.assertEqual(by["02-normal-feature/standards-copy-inside-a-normal-spec"].decision, "pass")


class OpenChoicesDocsTests(unittest.TestCase):
    """Each pack's and skill's open choices are in its SKILL.md, or, when the skill is preloaded or near its cap, in its
    generated `references/open-choices.md`, which the role reference links. A preloaded skill gains no bytes."""

    def test_each_owner_shows_its_choices_where_they_fit(self):
        team = resources.data_dir("team")
        roles_ref = (team / "skills" / "aidd-team" / "references" / "roles.md").read_text(encoding="utf-8")
        by_owner: dict[str, list[dict]] = {}
        for c in standards.open_choices().values():
            by_owner.setdefault(c["owner"], []).append(c)
        self.assertIn("ci-pipeline", by_owner)
        for owner, choices in by_owner.items():
            skill = (team / "skills" / owner / "SKILL.md").read_text(encoding="utf-8")
            ref = team / "skills" / owner / "references" / "open-choices.md"
            where = ref.read_text(encoding="utf-8") if pack_render.open_choices_placement(owner) == "reference" else skill
            for c in choices:
                self.assertIn(f"`{c['id']}`", where, owner)
                self.assertIn(c["default"], where, owner)
            if pack_render.open_choices_placement(owner) == "reference":
                self.assertNotIn("Open choices", skill, owner)
                self.assertIn(f"`aidd-team:{owner}` (its `references/open-choices.md`)", roles_ref)
        self.assertEqual(pack_render.open_choices_placement("ci-pipeline"), "reference")  # preloaded by the platform engineer

    def test_a_skill_without_choices_has_no_reference_for_them(self):
        team = resources.data_dir("team")
        owners = {c["owner"] for c in standards.open_choices().values()}
        for path in (team / "skills").glob("*/references/open-choices.md"):
            self.assertIn(path.parent.parent.name, owners)


class CatalogPageTests(unittest.TestCase):
    def test_the_standards_page_lists_the_choices_the_library_and_the_stacks(self):
        text = (ROOT / "docs" / "STANDARDS.md").read_text(encoding="utf-8")
        for block in ("standards:open-choices", "standards:library", "standards:stacks"):
            self.assertIn(f"<!-- aidd:gen {block} -->", text)
        for s in standards.standards_library().values():
            self.assertIn(f"`{s.id}`", text)
            if s.meta.get("checked_version"):  # a stdlib or toolchain practice has no tool version of its own
                self.assertIn(s.meta["checked_version"], text)
            self.assertIn(s.meta["checked"], text)
        self.assertIn("### python", text)
        self.assertIn("`python-cli`", text)
        self.assertIn("`ci-pipeline:linter`", text)

    def test_the_choices_table_marks_the_default_where_a_choice_has_options(self):
        lib = dict(standards.standards_library())
        m = lib["python/mypy-typing"]
        lib["python/pyright"] = standards.Standard("python/pyright", {**m.meta, "id": "python/pyright", "default": False}, m.body, m.text, "python/pyright.md")
        with mock.patch.object(standards, "standards_library", return_value=lib):
            table = standards.catalog_choices()
        row = next(line for line in table.splitlines() if line.startswith("| `ci-pipeline:type-checker`"))
        self.assertIn("`python/mypy-typing` (default), `python/pyright`", row)
        self.assertNotIn("`typescript/tsc-strict` (default)", row)  # the only option in its ecosystem


class ReleaseFeedTests(unittest.TestCase):
    """The weekly standards check reads each library tool's release feed and flags a newer major than checked_version."""

    def test_each_feed_has_one_address(self):
        cases = {
            ("pypi", "ruff"): "https://pypi.org/pypi/ruff/json",
            ("npm", "@biomejs/biome"): "https://registry.npmjs.org/@biomejs%2Fbiome/latest",
            ("crates", "cargo-deny"): "https://crates.io/api/v1/crates/cargo-deny",
            ("maven", "org.flywaydb:flyway-core"): "https://repo1.maven.org/maven2/org/flywaydb/flyway-core/maven-metadata.xml",
            ("nuget", "xunit.v3"): "https://api.nuget.org/v3-flatcontainer/xunit.v3/index.json",
            ("go", "github.com/Masterminds/semver"): "https://proxy.golang.org/github.com/!masterminds/semver/@latest",
            ("github", "astral-sh/uv"): "https://api.github.com/repos/astral-sh/uv/releases/latest",
        }
        for (registry, package), url in cases.items():
            self.assertEqual(release_feeds.feed_url(registry, package), url)

    def test_each_feed_answer_gives_its_latest_version(self):
        answers = {
            "pypi": '{"info": {"version": "1.2.3"}}',
            "npm": '{"version": "1.2.3"}',
            "crates": '{"crate": {"max_stable_version": "1.2.3", "max_version": "2.0.0-rc.1"}}',
            "maven": "<metadata><versioning><latest>1.2.4-SNAPSHOT</latest><release>1.2.3</release></versioning></metadata>",
            "nuget": '{"versions": ["1.0.0", "1.2.3", "2.0.0-preview.1"]}',
            "go": '{"Version": "v1.2.3"}',
            "github": '{"tag_name": "v1.2.3"}',
        }
        for registry, body in answers.items():
            self.assertEqual(release_feeds.latest_version(registry, body), "1.2.3", registry)
        # PyPI lists every release after `info`, so a long answer cut at the byte limit still names the newest one.
        cut = '{"info": {"author": "x", "version": "1.2.3", "yanked": false}, "releases": {"0.1": [{"version": "0.1"'
        self.assertEqual(release_feeds.latest_version("pypi", cut), "1.2.3")

    def test_each_path_segment_is_encoded(self):
        self.assertEqual(release_feeds.feed_url("pypi", "a/../b"), "https://pypi.org/pypi/a%2F..%2Fb/json")
        self.assertEqual(release_feeds.feed_url("github", "o/r?x=1"), "https://api.github.com/repos/o/r%3Fx%3D1/releases/latest")
        self.assertEqual(release_feeds.feed_url("maven", "org.x:a/b"), "https://repo1.maven.org/maven2/org/x/a%2Fb/maven-metadata.xml")

    def test_a_package_name_fits_its_feed(self):
        def check(registry: str, package: str) -> list[str]:
            meta, _ = documents.split_front_matter(standards.standards_library()["python/uv-tooling"].text, "x")
            return json_schema.validate({**meta, "tool": {"name": "uv", "registry": registry, "package": package}}, "standard.schema.json")

        for registry, package in (
            ("pypi", "ruff"),
            ("npm", "@biomejs/biome"),
            ("maven", "org.flywaydb:flyway-core"),
            ("go", "golang.org/x/vuln"),
            ("github", "astral-sh/uv"),
        ):
            self.assertEqual(check(registry, package), [], (registry, package))
        for registry, package in (("pypi", "a/b"), ("npm", "../x"), ("maven", "flyway"), ("github", "uv"), ("crates", "a b"), ("nuget", "x/y"), ("go", "nope")):
            self.assertTrue(check(registry, package), (registry, package))

    def test_an_odd_feed_answer_is_unreachable_never_a_crash(self):
        self.assertIsNone(release_feeds.latest_version("npm", "[1, 2]"))
        self.assertIsNone(release_feeds.latest_version("crates", '"text"'))
        entries = [{"id": "python/x", "tool": "x", "registry": "nuget", "url": "https://api.nuget.org/x", "checked_version": "1.0.0"}]
        for body in (b'{"versions": 5}', b'{"versions": [{"a": 1}]}', b"[" * 100000 + b"]" * 100000):
            rows = release_feeds.check_releases(entries, fetcher=lambda url, b=body: bounded_fetch.Fetched(200, url, "application/json", b, False))
            self.assertEqual(rows[0]["status"], "unreachable", body[:20])

    def test_a_newer_major(self):
        self.assertTrue(release_feeds.newer_major("2.4.0", "3.0.0"))
        self.assertFalse(release_feeds.newer_major("2.4.0", "2.9.1"))
        self.assertTrue(release_feeds.newer_major("0.16.10", "0.17.0"))  # before 1.0, a minor breaks
        self.assertFalse(release_feeds.newer_major("0.16.10", "0.16.11"))
        self.assertFalse(release_feeds.newer_major("1.0.0", "0.9.0"))

    def test_the_check_flags_a_newer_major_and_never_fails_on_the_network(self):
        entries = release_feeds.release_entries()
        # One feed entry per library standard that names a tool, the seed among them.
        self.assertEqual({e["id"] for e in entries}, {s.id for s in standards.standards_library().values() if s.meta.get("tool")})
        self.assertLessEqual(SEED, {e["id"] for e in entries})

        def fetcher(url: str):
            if "ruff" in url:
                return bounded_fetch.Fetched(200, url, "application/json", b'{"info": {"version": "0.17.0"}}', False)
            if "mypy" in url:
                return bounded_fetch.Fetched(200, url, "application/json", b'{"info": {"version": "2.4.9"}}', False)
            raise bounded_fetch.FetchError("no route")

        rows = {r["id"]: r for r in release_feeds.check_releases(entries, fetcher=fetcher)}
        self.assertEqual(rows["python/ruff-lint-format"]["status"], "newer_major")
        self.assertEqual(rows["python/ruff-lint-format"]["latest"], "0.17.0")
        self.assertEqual(rows["python/mypy-typing"]["status"], "ok")
        self.assertEqual(rows["python/uv-tooling"]["status"], "unreachable")
        result = {
            "schema_version": "1",
            "checked_on": "2026-10-07",
            "limits": {"timeout_seconds": 1, "max_seconds": 1, "max_bytes": 1, "concurrency": 1},
            "counts": {"ok": 0, "moved": 0, "missing": 0, "unreachable": 0},
            "results": [],
            "releases": list(rows.values()),
        }
        self.assertEqual(json_schema.validate(result, "knowledge.schema.json"), [])
        self.assertEqual(recheck_report.exit_code(result, strict=True), 1)  # a newer major turns the weekly run red
        self.assertEqual(recheck_report.exit_code(result, strict=False), 0)
        self.assertIn("| newer major | `python/ruff-lint-format` |", recheck_report.markdown(result))


class PreReleaseAndPolicyTests(unittest.TestCase):
    """The release-feed check reads stable releases only, and an LTS standard is judged against the newest LTS."""

    def test_a_pre_release_is_known_by_its_marker(self):
        for v in (
            "1.0.0-M1",
            "4.0.0.RC1",
            "2.0.0a1",
            "2.0.0b2",
            "1.0.dev3",
            "6.0.0-preview.1",
            "1.0.0-SNAPSHOT",
            "1.0.0-alpha",
            "1.0.0-beta.2",
            "25-ea",
            "11.0.100-rc.1.26425.128",
            "3.0.0-canary.4",
            "5.0.0.CR2",
            "go1.28rc1",
            "2.0.0-next.1",
        ):
            self.assertTrue(release_feeds.is_prerelease(v), v)
        for v in ("1.2.3", "v1.2.3", "33.0.0-jre", "1.0.post1", "5.3.0.Final", "2.7.18", "go1.27.2", "1.0.0.RELEASE", "10.0.12"):
            self.assertFalse(release_feeds.is_prerelease(v), v)

    def test_a_feed_never_names_a_pre_release_as_the_latest(self):
        maven = "<metadata><versioning><release>4.0.0-M1</release><versions><version>3.5.0</version><version>4.0.0-M1</version><version>4.0.0-RC1</version></versions></versioning></metadata>"
        self.assertEqual(release_feeds.latest_version("maven", maven), "3.5.0")
        pypi = '{"info": {"version": "2.0.0rc1"}, "releases": {"1.9.0": [], "2.0.0rc1": []}}'
        self.assertEqual(release_feeds.latest_version("pypi", pypi), "1.9.0")
        self.assertIsNone(release_feeds.latest_version("npm", '{"version": "3.0.0-beta.1"}'))
        self.assertIsNone(release_feeds.latest_version("go", '{"Version": "v2.0.0-alpha.1"}'))
        self.assertIsNone(release_feeds.latest_version("github", '{"tag_name": "v2.0.0-preview.3"}'))
        self.assertEqual(release_feeds.latest_version("nuget", '{"versions": ["1.0.0", "2.0.0-dev.1", "3.0.0.RC1"]}'), "1.0.0")
        entries = [{"id": "java/x", "tool": "x", "registry": "maven", "url": "https://repo1.maven.org/x", "checked_version": "3.5.0"}]
        rows = release_feeds.check_releases(entries, fetcher=lambda url: bounded_fetch.Fetched(200, url, "text/xml", maven.encode(), False))
        self.assertEqual((rows[0]["status"], rows[0]["latest"]), ("ok", "3.5.0"))  # a milestone of 4.0 is never a newer major


NODE = json.dumps(
    [
        {"version": "v27.0.0-rc.1", "lts": False},
        {"version": "v26.11.1", "lts": False},
        {"version": "v24.21.0", "lts": "Krypton"},
        {"version": "v22.20.0", "lts": "Jod"},
    ]
)
DOTNET = json.dumps(
    {
        "releases-index": [
            {
                "channel-version": "11.0",
                "latest-release": "11.0.0-rc.1",
                "latest-runtime": "11.0.0-rc.1.1",
                "latest-sdk": "11.0.100-rc.1.1",
                "support-phase": "go-live",
                "release-type": "sts",
            },
            {
                "channel-version": "10.0",
                "latest-release": "10.0.12",
                "latest-runtime": "10.0.12",
                "latest-sdk": "10.0.401",
                "support-phase": "active",
                "release-type": "lts",
            },
            {
                "channel-version": "9.0",
                "latest-release": "9.0.20",
                "latest-runtime": "9.0.20",
                "latest-sdk": "9.0.318",
                "support-phase": "maintenance",
                "release-type": "sts",
            },
        ]
    }
)
ADOPTIUM = '{"available_lts_releases": [8, 11, 17, 21, 25], "most_recent_feature_release": 27, "most_recent_lts": 25, "tip_version": 28}'
GO = json.dumps([{"version": "go1.28rc1", "stable": False}, {"version": "go1.27.2", "stable": True}, {"version": "go1.26.9", "stable": True}])
PYTHON = json.dumps(
    [
        {"name": "Python 3.14.8", "version": 3, "pre_release": False, "is_published": True},
        {"name": "Python 3.15.0a3", "version": 3, "pre_release": True, "is_published": True},
        {"name": "Python 3.9.25", "version": 3, "pre_release": False, "is_published": True},
        {"name": "Python install manager 26.3", "version": 3, "pre_release": False, "is_published": True},
        {"name": "Python 2.7.18", "version": 2, "pre_release": False, "is_published": True},
    ]
)


class ToolchainFeedTests(unittest.TestCase):
    """The official toolchain feeds: go.dev, nodejs.org, the .NET release index, Adoptium, and python.org."""

    def test_each_toolchain_feed_has_one_address(self):
        cases = {
            ("go.dev", "go"): "https://go.dev/dl/?mode=json",
            ("nodejs.org", "node"): "https://nodejs.org/dist/index.json",
            ("dotnet", "sdk"): "https://builds.dotnet.microsoft.com/dotnet/release-metadata/releases-index.json",
            ("adoptium", "temurin"): "https://api.adoptium.net/v3/info/available_releases",
            ("python.org", "cpython"): "https://www.python.org/api/v2/downloads/release/?is_published=true",
        }
        for (registry, package), url in cases.items():
            self.assertEqual(release_feeds.feed_url(registry, package), url)
        self.assertEqual(set(release_feeds.FEEDS), set(release_feeds.FEED_NAMES))

    def test_each_toolchain_feed_gives_its_latest_stable_release_by_policy(self):
        lts, stable = "latest_lts", "current_stable"
        self.assertEqual(release_feeds.latest_version("nodejs.org", NODE, lts), "24.21.0")
        self.assertEqual(release_feeds.latest_version("nodejs.org", NODE, stable), "26.11.1")
        self.assertEqual(release_feeds.latest_version("dotnet", DOTNET, lts, "sdk"), "10.0.401")
        self.assertEqual(release_feeds.latest_version("dotnet", DOTNET, lts, "runtime"), "10.0.12")
        self.assertEqual(release_feeds.latest_version("dotnet", DOTNET, stable, "runtime"), "10.0.12")  # 11.0 is a release candidate
        self.assertEqual(release_feeds.latest_version("adoptium", ADOPTIUM, lts), "25")
        self.assertEqual(release_feeds.latest_version("adoptium", ADOPTIUM, stable), "27")
        self.assertEqual(release_feeds.latest_version("go.dev", GO, stable), "1.27.2")
        self.assertEqual(release_feeds.latest_version("python.org", PYTHON, stable), "3.14.8")

    def test_a_go_or_python_release_is_its_minor(self):
        # Go 1.x and Python 3.x name each major release by the minor number.
        self.assertTrue(release_feeds.newer_major("1.27.1", "1.28.0", "go.dev"))
        self.assertFalse(release_feeds.newer_major("1.27.1", "1.27.2", "go.dev"))
        self.assertTrue(release_feeds.newer_major("3.14.8", "3.15.0", "python.org"))
        self.assertFalse(release_feeds.newer_major("24.21.0", "24.22.0", "nodejs.org"))

    def test_an_lts_standard_is_not_flagged_by_a_newer_non_lts_release(self):
        def rows(registry: str, body: str, checked: str, policy: str, package: str) -> dict:
            e = {
                "id": "x/y",
                "tool": "t",
                "registry": registry,
                "url": "https://example.org/feed",
                "checked_version": checked,
                "version_policy": policy,
                "package": package,
            }
            got = release_feeds.check_releases([e], fetcher=lambda url: bounded_fetch.Fetched(200, url, "application/json", body.encode(), False))
            return got[0]

        self.assertEqual(rows("nodejs.org", NODE, "24.21.0", "latest_lts", "node")["status"], "ok")
        self.assertEqual(rows("nodejs.org", NODE, "24.21.0", "current_stable", "node")["status"], "newer_major")
        self.assertEqual(rows("adoptium", ADOPTIUM, "25", "latest_lts", "temurin")["status"], "ok")
        self.assertEqual(rows("adoptium", ADOPTIUM, "21", "latest_lts", "temurin")["status"], "newer_major")
        self.assertEqual(rows("dotnet", DOTNET, "10.0.401", "latest_lts", "sdk")["status"], "ok")
        self.assertEqual(rows("go.dev", GO, "1.26.9", "current_stable", "go")["status"], "newer_major")

    def test_the_schema_takes_each_toolchain_feed_and_its_package(self):
        def check(registry: str, package: str) -> list[str]:
            meta, _ = documents.split_front_matter(standards.standards_library()["python/uv-tooling"].text, "x")
            return json_schema.validate({**meta, "tool": {"name": "uv", "registry": registry, "package": package}}, "standard.schema.json")

        for registry, package in (
            ("go.dev", "go"),
            ("nodejs.org", "node"),
            ("dotnet", "sdk"),
            ("dotnet", "runtime"),
            ("adoptium", "temurin"),
            ("python.org", "cpython"),
        ):
            self.assertEqual(check(registry, package), [], (registry, package))
        for registry, package in (("go.dev", "golang"), ("nodejs.org", "nodejs"), ("dotnet", "aspnet"), ("adoptium", "openjdk"), ("python.org", "pypy")):
            self.assertTrue(check(registry, package), (registry, package))

    def test_each_language_version_standard_names_its_toolchain_feed(self):
        want = {
            "go/go-version": ("go", "go.dev", "go"),
            "typescript/node-lts": ("node", "nodejs.org", "node"),
            "dotnet/dotnet-lts": ("dotnet", "dotnet", "sdk"),
            "java/java-lts": ("java", "adoptium", "temurin"),
            "python/python-version": ("python", "python.org", "cpython"),
        }
        lib = standards.standards_library()
        for sid, (name, registry, package) in want.items():
            tool = lib[sid].meta.get("tool") or {}
            self.assertEqual((tool.get("name"), tool.get("registry"), tool.get("package")), (name, registry, package), sid)
            self.assertTrue(lib[sid].meta.get("checked_version"), sid)
            self.assertIn(lib[sid].meta["checked_version"].removeprefix("v"), lib[sid].meta["evidence"], sid)  # read there, never typed


if __name__ == "__main__":
    unittest.main()
