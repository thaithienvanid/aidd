"""The Spec is the work item; detailed documents link from it (`[[docs]]`).

A frozen doc is pinned by content like a design file; a living doc (`frozen = false`) is only checked to exist.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT, RepoTemplateCase, aidd_subprocess, example, git, make_repo

from aidd import config as cfgmod
from aidd import digest, guard, model, nextstep, repo, resources, rules, runner
from aidd.verify import verify

SKILL = ROOT / ".agents" / "skills" / "aidd"
ASSETS = SKILL / "assets"
DOC = "docs/specs/SPEC-9/tech-spec-cart.md"
RUNBOOK = "docs/runbooks/cart.md"

SPEC = """+++
aidd_version = "1.0.0"
kind = "spec"
id = "SPEC-9"
title = "Cart totals"
owner_team = "shop"
type = "{type}"
route = "{route}"
confidence = "high"
open_questions = []
trace_id = "spec-9"
assisted_by = []
rollback = "Revert the change."
{extra}
[risk]
summary = "Cart totals change."
dimensions = {dims}
reversible = true

[[tasks]]
id = "SPEC-9-T1"
title = "Sum the cart"
scope = {scope}

[tests]
files = ["tests/test_cart.py"]

[[tests.commands]]
name = "cart"
command = ["python3", "tests/test_cart.py"]
new_behavior = true
covers = {covers}
{docs}{observe}+++

## Intent

Make the cart total right.

## Acceptance

{acceptance}

## Design

Sum the items in src/cart/total.py; nothing else changes.

## Policy conflicts

none

## Rollback

Revert.
"""

OBSERVE = '\n[observe]\nwindow = "1d"\nrollback_trigger = "totals wrong"\n'


def docs_toml(*entries):
    out = ""
    for kind, path, *frozen in entries:
        out += f'\n[[docs]]\nkind = "{kind}"\npath = "{path}"\n' + (f"frozen = {str(frozen[0]).lower()}\n" if frozen else "")
    return out


def spec_text(*entries, route="normal", ctype="feat", dims="[]", scope='["src/cart/"]', acceptance=2, covers=None, extra=""):
    ids = [f"A{i}" for i in range(1, acceptance + 1)]
    return SPEC.format(
        type=ctype,
        route=route,
        extra=extra,
        dims=dims,
        scope=scope,
        covers=json.dumps(covers if covers is not None else ids),
        docs=docs_toml(*entries),
        observe=OBSERVE if route == "major" else "",
        acceptance="\n".join(f"- {i}: behaviour {i}" for i in ids),
    )


def errors(found):
    return [e for e in found if not e.startswith("warning: ")]


def warnings(found):
    return [e for e in found if e.startswith("warning: ")]


class SchemaAndModelTests(unittest.TestCase):
    """The schema and the model: linked docs validate, frozen docs join the hash, and lint keeps them out of Task scope."""

    def load(self, text):
        return model.load_object(text, "specs/SPEC-9.md")

    def test_docs_validate_and_design_files_still_do(self):
        text = spec_text(("tech-spec", DOC), ("runbook", RUNBOOK, False), extra='decisions = ["docs/adr/0001-carts.md"]\n')
        text = text.replace("[tests]", '[design]\nfiles = ["docs/design/SPEC-9/**"]\n\n[tests]', 1)
        data, _, errs = self.load(text)
        self.assertEqual(errors(errs), [])
        self.assertEqual([d["kind"] for d in data["docs"]], ["tech-spec", "runbook"])
        self.assertLessEqual(
            {"tech-spec", "test-plan", "design-spec", "adr", "threat-model", "api", "runbook", "slo", "compliance", "other"}, set(model.DOC_KINDS)
        )
        _, _, errs = self.load(spec_text(("wiki", DOC)))
        self.assertTrue(any("docs" in e for e in errors(errs)), errs)
        _, _, errs = self.load(spec_text(("tech-spec", DOC)).replace('path = "docs/', 'owner = "x"\npath = "docs/', 1))
        self.assertTrue(errors(errs), "an unknown key in a [[docs]] entry is an error")

    def test_frozen_docs_join_the_hash_and_living_docs_do_not(self):
        text = spec_text(("tech-spec", DOC), ("runbook", RUNBOOK, False))
        text = text.replace("[tests]", '[design]\nfiles = ["docs/design/SPEC-9/**"]\n\n[tests]', 1)
        data, _ = model.split_front_matter(text)
        self.assertEqual(model.frozen_docs(data), [DOC])
        self.assertEqual(model.design_paths(data), ["docs/design/SPEC-9/**", DOC])
        self.assertIn(DOC, model.frozen_paths(data))
        self.assertNotIn(RUNBOOK, model.frozen_paths(data))
        tree = {"specs/SPEC-9.md": "1" * 40, "tests/test_cart.py": "2" * 40, DOC: "3" * 40, RUNBOOK: "4" * 40}
        h = model.spec_hash(text, tree)
        self.assertNotEqual(h, model.spec_hash(text, tree | {DOC: "5" * 40}))
        self.assertEqual(h, model.spec_hash(text, tree | {RUNBOOK: "5" * 40}))
        # A Spec without [[docs]] hashes as before: its design paths are its design files.
        plain, _ = model.split_front_matter(spec_text())
        self.assertEqual(model.design_paths(plain), [])

    def test_lint_keeps_frozen_docs_out_of_task_scope(self):
        _, _, errs = self.load(spec_text(("tech-spec", DOC), scope='["src/cart/", "docs/specs/**"]'))
        self.assertTrue(any("overlaps frozen doc" in e and DOC in e for e in errs), errs)
        _, _, errs = self.load(spec_text(("tech-spec", "**")))
        self.assertTrue(any("matches every path" in e for e in errs), errs)
        # A living doc is implementation like any other file: a Task may change it.
        _, _, errs = self.load(spec_text(("runbook", RUNBOOK, False), scope='["src/cart/", "docs/runbooks/"]'))
        self.assertEqual(errors(errs), [])


class GateTests(unittest.TestCase):
    """Conformance case 18-linked-docs and its mutations pin the gate's behavior; this runs it directly too."""

    def test_a_frozen_doc_is_reviewed_with_the_spec(self):
        d = verify(example("18-linked-docs"))
        self.assertEqual(d.decision, "pass", [f"{f.level} {f.code}" for f in d.findings])
        self.assertEqual(d.record["changed_lines"], 83)
        self.assertTrue((ROOT / "examples" / "18-linked-docs" / "mutations" / "living-doc-outside-the-scope.json").is_file())

    def test_the_spec_phase_includes_frozen_docs(self):
        frozen = ["specs/SPEC-9.md", "tests/test_cart.py", DOC]
        self.assertTrue(rules.spec_phase(["specs/SPEC-9.md", DOC], frozen, [["src/cart/"]]))


class RunnerAndBudgetTests(unittest.TestCase):
    """`aidd test --changed` and the branch budget read frozen docs as they read design files."""

    def test_a_frozen_doc_change_selects_the_spec_commands(self):
        data, _ = model.split_front_matter(spec_text(("tech-spec", DOC), ("runbook", RUNBOOK, False)))
        cmd = data["tests"]["commands"][0]
        self.assertEqual(runner.select_changed([(cmd, "spec")], data, [DOC]), [(cmd, "spec")])
        self.assertEqual(runner.select_changed([(cmd, "spec")], data, [RUNBOOK]), [])

    def test_the_branch_budget_leaves_out_frozen_docs(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "specs").mkdir()
            (Path(d) / "specs" / "SPEC-9.md").write_text(spec_text(("tech-spec", DOC), ("runbook", RUNBOOK, False)), encoding="utf-8")
            cfg = cfgmod.load_text('aidd_version = "1.0.0"\nprofile = "team"\n\n[owners]\napprovers = ["@x"]\n')
            reviewed = rules._reviewed_on_branch(d, cfg, ["specs/SPEC-9.md"])
            self.assertIn(DOC, reviewed)
            self.assertNotIn(RUNBOOK, reviewed)


@unittest.skipUnless(shutil.which("git"), "git is required")
class GuardTests(RepoTemplateCase):
    """The owner of a frozen doc writes it until Spec approval, and nobody after."""

    TECH, THREAT, PLAN = "docs/specs/SPEC-220/tech-spec-limit.md", "docs/specs/SPEC-220/threat-model-limit.md", "docs/specs/SPEC-220/test-plan-limit.md"

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec="02-normal-feature:specs/SPEC-220.md")
        p = root / "specs" / "SPEC-220.md"
        entries = docs_toml(("tech-spec", cls.TECH), ("threat-model", cls.THREAT), ("test-plan", cls.PLAN))
        p.write_text(p.read_text(encoding="utf-8").replace("\n[tests]", entries + "\n[tests]", 1), encoding="utf-8")

    def decide(self, role, path):
        return guard.check_edit(str(self.root), path, role)[0]

    def test_each_doc_has_its_owner_before_spec_approval(self):
        self.assertEqual([self.decide("architect", p) for p in (self.TECH, self.THREAT, self.PLAN)], ["allow", "deny", "deny"])
        self.assertEqual([self.decide("security-engineer", p) for p in (self.TECH, self.THREAT, self.PLAN)], ["deny", "allow", "deny"])
        self.assertEqual([self.decide("tester", p) for p in (self.TECH, self.THREAT, self.PLAN)], ["deny", "deny", "allow"])
        self.assertEqual([self.decide(r, self.TECH) for r in ("developer", None)], ["deny", "allow"])

    def test_nobody_edits_a_frozen_doc_after_spec_approval(self):
        p = self.root / "specs" / "SPEC-220.md"
        p.write_text(p.read_text(encoding="utf-8").replace('route = "normal"', 'route = "normal"\nstatus = "ready"', 1), encoding="utf-8")
        for role, path in (("architect", self.TECH), ("security-engineer", self.THREAT), (None, self.PLAN)):
            decision, reason = guard.check_edit(str(self.root), path, role)
            self.assertEqual(decision, "deny", (role, path))
            self.assertIn("ask for Spec approval again", reason)


class TemplateTests(unittest.TestCase):
    """Each kind's template: it names its Spec, holds one threat-table shape, and leaves the contract to the Spec."""

    def test_each_kind_has_a_template_that_names_its_spec(self):
        for name in ("tech-spec.md", "test-plan.md", "prototype.html", "adr.md", "threat-model.md"):
            self.assertIn("{{spec}}", (ASSETS / name).read_text(encoding="utf-8"), name)
        tech = (ASSETS / "tech-spec.md").read_text(encoding="utf-8")
        for heading in (
            "## Alternatives considered",
            "## Cross-cutting concerns",
            "### Security and privacy",
            "### Compliance",
            "### Observability",
            "## Pre-mortem",
        ):
            self.assertIn(heading, tech)
        self.assertRegex(tech, r"(?im)^##+ .*light")
        plan = (ASSETS / "test-plan.md").read_text(encoding="utf-8")
        for word in ("A1", "Level", "mocked", "Fixtures", "P0", "Definition of done", "covers"):
            self.assertIn(word, plan)
        ui = (ASSETS / "prototype.html").read_text(encoding="utf-8")
        for state in ("empty", "loading", "error", "success"):
            self.assertIn(f'data-state="{state}"', ui)
        self.assertIn("data-testid=", ui)
        self.assertIn(":root", ui)
        self.assertNotRegex(ui, r"<(?:script|link)[^>]+(?:src|href)=\"https?://", "the prototype is self-contained")
        adr = (ASSETS / "adr.md").read_text(encoding="utf-8")
        for heading in ("## Context", "## Decision drivers", "## Considered options", "## Decision outcome", "### Consequences", "### Confirmation"):
            self.assertIn(heading, adr)
        for status in ("proposed", "accepted", "superseded"):
            self.assertIn(status, adr)
        tm = (ASSETS / "threat-model.md").read_text(encoding="utf-8")
        for q in ("What are we working on?", "What can go wrong?", "What are we going to do about it?", "Did we do a good enough job?"):
            self.assertIn(q, tm)
        self.assertIn("```mermaid", tm)
        self.assertIn("| Threat (STRIDE or LINDDUN) |", tm)
        self.assertIn("Residual risk", tm)
        self.assertIn("## Rollout", (ASSETS / "runbook.md").read_text(encoding="utf-8"))

    def test_no_frozen_template_holds_a_field_filled_after_approval(self):
        """A sign-off or a status written after Spec approval would void it: they live in the living acceptance record."""
        frozen = [k for k in repo.DOC_TEMPLATES if k not in repo.LIVING_DOCS and k not in repo.UNLINKED_DOCS]
        for kind in frozen:
            text = (ASSETS / repo.DOC_TEMPLATES[kind]).read_text(encoding="utf-8")
            with self.subTest(kind=kind):
                self.assertNotRegex(text, r"(?im)^#+ .*sign-off", kind)
                self.assertNotRegex(text, r"(?m)^Status: ", kind)
        acceptance = (ASSETS / "acceptance.md").read_text(encoding="utf-8")
        for row in ("## Sign-offs", "| User acceptance (test plan) |", "| DPO advice and decision (DPIA) |"):
            self.assertIn(row, acceptance)
        self.assertIn("acceptance record", (ASSETS / "compliance.md").read_text(encoding="utf-8"))
        self.assertIn("acceptance record", (ASSETS / "test-plan.md").read_text(encoding="utf-8"))

    def test_one_threat_table_shape(self):
        head = "| Threat (STRIDE or LINDDUN) | Trust boundary or asset | Mitigation | Acceptance id | Owner |"
        ref = (SKILL / "references" / "spec.md").read_text(encoding="utf-8")
        for text in (ref, (ASSETS / "threat-model.md").read_text(encoding="utf-8"), (ASSETS / "compliance.md").read_text(encoding="utf-8")):
            self.assertIn(head, text)
        tm = (ASSETS / "threat-model.md").read_text(encoding="utf-8")
        for linddun in ("Linking", "Identifying", "Non-repudiation", "Detecting", "Data disclosure", "Unawareness", "Non-compliance"):
            self.assertIn(f"| {linddun}", tm, linddun)
        self.assertIn("| Owner |", (ASSETS / "compliance.md").read_text(encoding="utf-8").split("## Obligations", 1)[1].split("\n## ", 1)[0])

    def test_traceability_is_covers_and_the_rollout_is_the_runbooks(self):
        for name in ("spec.md", "spec-short.md", "tech-spec.md", "test-plan.md"):
            text = (ASSETS / name).read_text(encoding="utf-8")
            self.assertNotIn("Red on base |", text, name)
            self.assertNotIn("| Command (`covers`) |", text, name)
        self.assertNotIn("## Rollout", (ASSETS / "spec.md").read_text(encoding="utf-8"))
        self.assertIn("## Rollout", (ASSETS / "runbook.md").read_text(encoding="utf-8"))
        short = (ASSETS / "spec-short.md").read_text(encoding="utf-8")
        for heading in ("## Intent", "## Context", "## Acceptance", "## Design", "## Policy conflicts", "## Rollback"):
            self.assertIn(heading, short)
        self.assertNotIn("Alternatives", short.split("+++", 2)[2])
        plan = (ASSETS / "test-plan.md").read_text(encoding="utf-8")
        for item in ("Suspension and resumption", "Staffing and roles", "Schedule", "Deliverables"):
            self.assertIn(item, plan)

    def test_the_spec_holds_the_contract_and_links_the_rest(self):
        full = (ASSETS / "spec.md").read_text(encoding="utf-8")
        for heading in ("## Alternatives considered", "## Cross-cutting concerns", "## Pre-mortem"):
            self.assertNotIn(heading, full)
        self.assertIn("# [[docs]]", full)
        for kind in ("tech-spec", "test-plan", "threat-model", "adr", "runbook"):
            self.assertIn(kind, full.split("+++", 2)[1])
        short = (ASSETS / "spec-short.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(short.splitlines()), 75)
        ref = (SKILL / "references" / "spec.md").read_text(encoding="utf-8")
        self.assertIn("<!-- aidd:gen fields:doc -->", ref)
        self.assertIn("aidd new tech-spec", (SKILL / "references" / "example.md").read_text(encoding="utf-8"))


@unittest.skipUnless(shutil.which("git"), "git is required")
class NewDocTests(RepoTemplateCase):
    """`aidd new <kind> <topic> --spec ID` writes the doc, fills the back-link, and links it from the Spec."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec="02-normal-feature:specs/SPEC-220.md")

    def new(self, *args):
        run = aidd_subprocess("new", *args, cwd=self.root)
        return run.returncode, run.stdout + run.stderr

    def spec(self):
        return (self.root / "specs" / "SPEC-220.md").read_text(encoding="utf-8")

    def test_a_doc_is_written_and_linked(self):
        code, out = self.new("tech-spec", "Rate limit", "--spec", "SPEC-220")
        self.assertEqual(code, 0, out)
        rel = "docs/specs/SPEC-220/tech-spec-rate-limit.md"
        self.assertIn(rel, out)
        self.assertIn("SPEC-220", (self.root / rel).read_text(encoding="utf-8"))
        self.assertIn(f'[[docs]]\nkind = "tech-spec"\npath = "{rel}"\n', self.spec())
        _, _, errs = model.load_object(self.spec(), "specs/SPEC-220.md")
        self.assertEqual(errors(errs), [])
        data, _ = model.split_front_matter(self.spec())
        self.assertIn(rel, model.frozen_docs(data))
        code, out = self.new("test-plan", "limits", "--spec", "SPEC-220", "--area", "checkout")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / "docs/specs/checkout/test-plan-limits.md").is_file())
        code, out = self.new("design-spec", "limit banner", "--spec", "SPEC-220", "--prototype")
        self.assertEqual(code, 0, out)
        self.assertIn("SPEC-220", (self.root / "docs/design/SPEC-220/prototype.html").read_text(encoding="utf-8"))
        code, out = self.new("threat-model", "limits", "--spec", "SPEC-220")
        self.assertEqual(code, 0, out)
        self.assertEqual([d["kind"] for d in model.split_front_matter(self.spec())[0]["docs"]], ["tech-spec", "test-plan", "design-spec", "threat-model"])

    def test_a_specialist_writes_a_doc_without_touching_the_spec(self):
        """One writer per file: `--no-link` writes the doc and leaves the Spec to the architect, who links it."""
        before = self.spec()
        code, out = self.new("threat-model", "limits", "--spec", "SPEC-220", "--no-link")
        self.assertEqual(code, 0, out)
        rel = "docs/specs/SPEC-220/threat-model-limits.md"
        self.assertIn("SPEC-220", (self.root / rel).read_text(encoding="utf-8"))
        self.assertEqual(self.spec(), before)
        self.assertIn(f'[[docs]]\nkind = "threat-model"\npath = "{rel}"', out)
        self.assertIn("not linked", out)
        code, out = self.new("slo", "latency", "--spec", "SPEC-220", "--no-link")
        self.assertEqual(code, 0, out)
        self.assertIn("frozen = false", out)
        self.assertEqual(self.spec(), before)
        code, out = self.new("runbook", "RB-1", "--title", "Roll out limits", "--spec", "SPEC-220", "--no-link")
        self.assertEqual(code, 0, out)
        self.assertIn('kind = "runbook"', out)
        self.assertEqual(self.spec(), before)
        code, out = self.new("brief", "pitch", "--no-link")
        self.assertNotEqual(code, 0)
        self.assertIn("--no-link", out)

    def test_adrs_are_numbered(self):
        self.assertEqual(self.new("adr", "Use a token bucket", "--spec", "SPEC-220")[0], 0)
        self.assertTrue((self.root / "docs/adr/0001-use-a-token-bucket.md").is_file())
        (self.root / "docs/adr/0007-older.md").write_text("# older\n", encoding="utf-8")
        self.assertEqual(self.new("adr", "Keep state in memory", "--spec", "SPEC-220")[0], 0)
        self.assertTrue((self.root / "docs/adr/0008-keep-state-in-memory.md").is_file())
        self.assertIn('path = "docs/adr/0008-keep-state-in-memory.md"', self.spec())

    def test_the_config_moves_the_folder_and_an_unknown_spec_stops(self):
        cfg = self.root / ".aidd" / "config.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + '\n[docs]\ndir = "documentation"\n', encoding="utf-8")
        self.assertEqual(self.new("tech-spec", "limits", "--spec", "SPEC-220")[0], 0)
        self.assertTrue((self.root / "documentation/specs/SPEC-220/tech-spec-limits.md").is_file())
        code, out = self.new("tech-spec", "limits", "--spec", "SPEC-404")
        self.assertNotEqual(code, 0)
        self.assertIn("SPEC-404", out)


@unittest.skipUnless(shutil.which("git"), "git is required")
class ValidateTests(RepoTemplateCase):
    """`aidd validate` on linked docs: paths, back-links, the test plan, and the required-docs matrix."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", branch=None)

    def check(self, text, files=None):
        for rel, body in (files or {}).items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(body, encoding="utf-8")
        p = self.root / "specs" / "SPEC-9.md"
        p.parent.mkdir(exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return repo.validate_file(p, "specs/SPEC-9.md")

    def missing_kinds(self, found):
        return sorted({m.group(1) for w in warnings(found) for m in [re.search(r"links no (\S+) doc", w)] if m})

    def test_every_path_exists(self):
        found = self.check(spec_text(("tech-spec", DOC), extra='decisions = ["docs/adr/0001-x.md", "https://example.com/adr/1"]\n'))
        errs = errors(found)
        self.assertTrue(any(DOC in e and "does not exist" in e for e in errs), found)
        self.assertTrue(any("docs/adr/0001-x.md" in e and "does not exist" in e for e in errs), found)
        self.assertFalse(any("example.com" in e for e in errs), found)
        found = self.check(spec_text(("tech-spec", DOC), ("runbook", RUNBOOK, False)), {DOC: "# Tech spec\n\nSpec: SPEC-9.\n", RUNBOOK: "# Runbook\n"})
        self.assertEqual(errors(found), [])

    def test_a_frozen_doc_names_its_spec_and_leaves_no_todo(self):
        found = self.check(spec_text(("tech-spec", DOC)), {DOC: "# Tech spec\n\nTODO: the design.\n"})
        self.assertEqual(errors(found), [])
        self.assertTrue(any(DOC in w and "TODO" in w for w in warnings(found)), found)
        self.assertTrue(any(DOC in w and "SPEC-9" in w for w in warnings(found)), found)
        found = self.check(spec_text(("tech-spec", DOC)), {DOC: "# Tech spec\n\nSpec: SPEC-9.\n"})
        self.assertFalse(any(DOC in w for w in warnings(found)), found)

    def test_the_test_plan_matches_the_acceptance(self):
        plan = "docs/specs/SPEC-9/test-plan-cart.md"
        body = "# Test plan\n\nSpec: SPEC-9.\n\n## Acceptance criteria\n\n| AC | Level |\n| --- | --- |\n| A1 | unit |\n| A3 | e2e |\n"
        found = self.check(spec_text(("test-plan", plan), covers=["A1"]), {plan: body})
        shown = [w for w in warnings(found) if plan in w]
        self.assertTrue(any("A3" in w and "Acceptance" in w for w in shown), shown)
        self.assertTrue(any("A2" in w and "test plan" in w for w in shown), shown)
        self.assertFalse(any("A1" in w for w in shown), shown)
        body = body.replace("| A3 | e2e |", "| A2 | e2e |")
        found = self.check(spec_text(("test-plan", plan), covers=["A1"]), {plan: body})
        self.assertTrue(any("A2" in w and "covers" in w for w in warnings(found) if plan in w), found)

    def test_the_matrix_warns_on_major_only(self):
        self.assertEqual(self.missing_kinds(self.check(spec_text(acceptance=8))), [])
        self.assertEqual(self.missing_kinds(self.check(spec_text(route="major", ctype="fix"))), ["runbook", "tech-spec"])
        # A test plan is asked for by its triggers (here 10 Acceptance items).
        self.assertEqual(
            self.missing_kinds(self.check(spec_text(route="major", ctype="feat", dims='["security"]', acceptance=10, scope='["src/web/"]'))),
            ["design-spec", "runbook", "tech-spec", "test-plan", "threat-model"],
        )
        # A feature with no user-facing path in scope (a CLI or back-end one) gets no design-spec warning.
        self.assertNotIn("design-spec", self.missing_kinds(self.check(spec_text(route="major", ctype="feat"))))
        self.assertIn("design-spec", self.missing_kinds(self.check(spec_text(route="major", ctype="feat", scope='["app/Checkout.tsx"]'))))
        with_design = spec_text(route="major", ctype="feat", scope='["src/web/"]').replace(
            "[tests]", '[design]\nfiles = ["docs/design/SPEC-9/**"]\n\n[tests]', 1
        )
        self.assertNotIn("design-spec", self.missing_kinds(self.check(with_design)))
        # On normal only the threat model and, on the privacy dimension, the compliance doc (its DPIA) warn; the rest are suggestions.
        self.assertEqual(self.missing_kinds(self.check(spec_text(dims='["privacy"]', acceptance=6))), ["compliance", "threat-model"])
        data, _ = model.split_front_matter(spec_text(acceptance=10, ctype="feat"))
        self.assertIn(("test-plan", "suggest"), [(k, level) for k, level, _ in repo.required_docs(data, 10, None)])

    def test_the_spec_own_sections_count_and_the_config_overrides(self):
        inline = spec_text(route="major", ctype="fix").replace(
            "## Rollback", "## Alternatives considered\n\nDo nothing.\n\n## Pre-mortem\n\nIt broke.\n\n## Rollout\n\nOne merge.\n\n## Rollback", 1
        )
        self.assertEqual(self.missing_kinds(self.check(inline)), [])
        cfg = self.root / ".aidd" / "config.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\n[docs.required.runbook]\nroutes = []\n", encoding="utf-8")
        self.assertEqual(self.missing_kinds(self.check(spec_text(route="major", ctype="fix"))), ["tech-spec"])


class DigestTests(unittest.TestCase):
    """The Spec approval summary lists each frozen doc."""

    def test_the_summary_lists_each_frozen_doc_with_its_lines(self):
        text = spec_text(("tech-spec", DOC), ("runbook", RUNBOOK, False))
        out = digest.spec_digest(text, "specs/SPEC-9.md", "/aidd approve-spec SPEC-9 abc", files={DOC: "a\nb\nc\n"})
        self.assertIn(f"{DOC} (3 lines)", out)
        self.assertNotIn(RUNBOOK, out)
        self.assertTrue(out.endswith("/aidd approve-spec SPEC-9 abc"))


class RolesTests(unittest.TestCase):
    """Who writes each linked doc."""

    def test_each_doc_kind_has_a_writer(self):
        roles = resources.roles()["roles"]
        want = {
            "architect": ("{docs:tech-spec}", "{docs:adr}", "{docs:api}"),
            "tester": ("{docs:test-plan}",),
            "product-designer": ("{docs:design-spec}",),
            "security-engineer": ("{docs:threat-model}",),
            "sre": ("{docs:runbook}", "{docs:slo}"),
        }
        for key, placeholders in want.items():
            for ph in placeholders:
                self.assertIn(ph, roles[key]["writes"], key)
        sec = roles["security-engineer"]
        self.assertIn("before Spec approval", sec["starts_when"])
        self.assertIn("threat-model", sec["done_when"])
        for key in ("tester", "verifier", "reviewer"):
            self.assertIn("QA engineer", roles[key]["industry"], key)
            self.assertIn("SDET", roles[key]["industry"], key)
        for key in want:
            self.assertIn("linked-docs", roles[key]["reads"], key)


@unittest.skipUnless(shutil.which("git"), "git is required")
class OverlapTests(unittest.TestCase):
    """Two open Specs that freeze the same doc hear about it first."""

    def test_a_shared_frozen_doc_is_an_overlap(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d).resolve()
            make_repo(root, "team", branch=None)
            shared = "docs/architecture/checkout.md"
            for branch, sid, scope in (("alice/limits", "SPEC-1", "src/limits/**"), ("bob/totals", "SPEC-2", "src/totals/**")):
                git(root, "switch", "-qc", branch, "main")
                (root / "specs").mkdir(exist_ok=True)
                (root / "specs" / f"{sid}.md").write_text(
                    f'+++\naidd_version = "1.0.0"\nkind = "spec"\nid = "{sid}"\nstatus = "ready"\n\n[[tasks]]\nid = "{sid}-T1"\nscope = ["{scope}"]\n'
                    f'\n[[docs]]\nkind = "other"\npath = "{shared}"\n+++\n',
                    encoding="utf-8",
                )
                git(root, "add", "-A")
                git(root, "commit", "-qm", f"spec: {sid}")
            whats = [s["what"] for s in nextstep.plan(root) if s["code"] == "overlap"]
            self.assertEqual(len(whats), 1, whats)
            self.assertIn("SPEC-2", whats[0])
            self.assertIn("SPEC-1", whats[0])
            self.assertIn(shared, whats[0])


class DocsTests(unittest.TestCase):
    """The method and the guides say what is frozen and what is living."""

    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_the_method_and_the_guides(self):
        method = self.read("docs/METHOD.md").split("### 4.2 Spec", 1)[1].split("\n### 4.3", 1)[0]
        for word in ("[[docs]]", "frozen", "living", "aidd new tech-spec"):
            self.assertIn(word, method)
        team = self.read("docs/TEAM.md").split("## Living architecture docs", 1)[1].split("\n## ", 1)[0]
        self.assertIn("frozen = false", team)
        self.assertIn("aidd new tech-spec", self.read("docs/HOW-TO.md"))
        self.assertIn("tech-spec", self.read("docs/CLI.md"))
        self.assertIn("<!-- aidd:gen fields:config-docs -->", self.read("docs/CONFIG.md"))


if __name__ == "__main__":
    unittest.main()
