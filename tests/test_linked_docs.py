"""The Spec is the work item; detailed documents link from it (`docs`).

A frozen doc is pinned by content like a design file; a living doc (`frozen: false`) is only checked to exist.
"""

import json
import re
import shutil
import unittest

from helpers import aidd_here, make_repo, PROTOTYPE_DESIGN, PROTOTYPE_EXAMPLE, RepoTemplateCase, ROOT

from aidd.workitems import validation
from aidd.workitems import authoring
from aidd import config
from aidd.workitems import spec_file
from aidd.kernel import documents
from aidd.knowledge import team_registry

SKILL = ROOT / ".agents" / "skills" / "aidd"
ASSETS = SKILL / "assets"
DOC = "specs/SPEC-9/tech-spec-cart.md"
RUNBOOK = "docs/runbooks/cart.md"

SPEC = """---
type: spec
id: SPEC-9
title: Cart totals
change_type: {change_type}
route: {route}
confidence: high
open_questions: []
trace_id: spec-9
rollback: Revert the change.
{extra}
risk:
  summary: Cart totals change.
  dimensions: {dims}
  irreversible: false

tasks:
  - id: SPEC-9-T1
    title: Sum the cart
    scope: {scope}

tests:
  files: [tests/test_cart.py]

  commands:
    - name: cart
      command: [python3, tests/test_cart.py]
      new_behavior: true
      covers: {covers}
{docs}{observe}---

## Request

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

OBSERVE = '\nobserve:\n  window: "1d"\n  rollback_trigger: totals wrong\n'


def docs_yaml(*entries):
    """The Spec's `docs` list: one item per (type, path) entry, with `frozen` when an entry gives it."""
    if not entries:
        return ""
    out = "\ndocs:\n"
    for doc_type, path, *frozen in entries:
        out += f'  - type: {doc_type}\n    path: "{path}"\n' + (f"    frozen: {str(frozen[0]).lower()}\n" if frozen else "")
    return out


def spec_text(*entries, route="normal", ctype="feat", dims="[]", scope='["src/cart/"]', acceptance=2, covers=None, extra=""):
    ids = [f"A{i}" for i in range(1, acceptance + 1)]
    return SPEC.format(
        change_type=ctype,
        route=route,
        extra=extra,
        dims=dims,
        scope=scope,
        covers=json.dumps(covers if covers is not None else ids),
        docs=docs_yaml(*entries),
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
        return spec_file.load_object(text, "specs/SPEC-9.md")

    def test_docs_validate_and_design_files_still_do(self):
        text = spec_text(
            ("tech-spec", DOC), ("runbook", RUNBOOK, False), ("design-files", "specs/SPEC-9/design/**"), extra="adrs: [docs/decisions/0001-carts.md]\n"
        )
        data, _, errs = self.load(text)
        self.assertEqual(errors(errs), [])
        self.assertEqual([d["type"] for d in data["docs"]], ["tech-spec", "runbook", "design-files"])
        self.assertLessEqual(
            {"tech-spec", "test-plan", "design-spec", "adr", "threat-model", "api", "runbook", "slo", "compliance-record", "other"}, set(config.DOC_TYPES)
        )
        _, _, errs = self.load(spec_text(("wiki", DOC)))
        self.assertTrue(any("docs" in e for e in errors(errs)), errs)
        bad = spec_text(("tech-spec", DOC)).replace(f'path: "{DOC}', f'owner: x\npath: "{DOC}', 1)
        self.assertNotEqual(bad, spec_text(("tech-spec", DOC)))
        _, _, errs = self.load(bad)
        self.assertTrue(errors(errs), "an unknown key in a `docs` entry is an error")

    def test_lint_keeps_frozen_docs_out_of_task_scope(self):
        _, _, errs = self.load(spec_text(("tech-spec", DOC), scope='["src/cart/", "specs/**"]'))
        self.assertTrue(any("overlaps frozen doc" in e and DOC in e for e in errs), errs)
        _, _, errs = self.load(spec_text(("tech-spec", "**")))
        self.assertTrue(any("matches every path" in e for e in errs), errs)
        # A living doc is implementation like any other file: a Task may change it.
        _, _, errs = self.load(spec_text(("runbook", RUNBOOK, False), scope='["src/cart/", "docs/runbooks/"]'))
        self.assertEqual(errors(errs), [])


class TemplateTests(unittest.TestCase):
    """Each type's template: it names its Spec, holds one threat-table shape, and leaves the contract to the Spec."""

    def test_each_type_has_a_template_that_names_its_spec(self):
        for name in ("tech-spec.md", "test-plan.md", PROTOTYPE_DESIGN, "adr.md", "threat-model.md"):
            self.assertIn("{{spec}}", (ASSETS / name).read_text(encoding="utf-8"), name)  # an absolute path stays as it is
        tech = (ASSETS / "tech-spec.md").read_text(encoding="utf-8")
        for heading in (
            "## Alternatives considered",
            "## Cross-cutting concerns",
            "### Security and privacy",
            "### Compliance",
            "### Observability",
            "### Testing",
            "## Quality attributes",
            "## Pre-mortem",
        ):
            self.assertIn(heading, tech)
        self.assertNotRegex(tech, r"(?im)^##+ .*(light|test strategy|open questions)")
        plan = (ASSETS / "test-plan.md").read_text(encoding="utf-8")
        for word in ("A1", "Level", "mocked", "data", "P0", "Exit", "covers"):
            self.assertIn(word, plan)
        ui = PROTOTYPE_EXAMPLE.read_text(encoding="utf-8")
        for state in ("empty", "loading", "error", "success"):
            self.assertIn(f'data-state="{state}"', ui)
        self.assertIn("data-testid=", ui)
        self.assertIn(":root", ui)
        self.assertNotRegex(ui, r"<(?:script|link)[^>]+(?:src|href)=\"https?://", "the prototype is self-contained")
        adr = (ASSETS / "adr.md").read_text(encoding="utf-8")
        for heading in (
            "## Context",
            "## Decision drivers",
            "## Considered options",
            "## Decision outcome",
            "### Consequences",
            "### Reopen when",
            "### Confirmation",
        ):
            self.assertIn(heading, adr)
        # Every decision names what would reopen it, in the short form too: its TODO is a frozen doc's TODO, which
        # `aidd validate` warns of before Spec approval freezes it.
        reopen = adr.split("### Reopen when", 1)[1].split("\n### ", 1)[0]
        self.assertIn("TODO", reopen)
        self.assertNotIn("full form only", reopen)
        for status in ("proposed", "accepted", "superseded"):
            self.assertIn(status, adr)
        tm = (ASSETS / "threat-model.md").read_text(encoding="utf-8")
        for q in ("What are we working on?", "What can go wrong?", "What are we going to do about it?", "Did we do a good enough job?"):
            self.assertIn(q, tm)
        self.assertIn("```mermaid", tm)
        self.assertIn("| Threat (STRIDE or LINDDUN) |", tm)
        self.assertIn("Residual risk", tm)
        self.assertNotIn("\n## Rollout\n", (ASSETS / "runbook.md").read_text(encoding="utf-8"))  # the standing procedure, not one change's plan

    def test_no_frozen_template_holds_a_field_filled_after_approval(self):
        """A sign-off or a status written after Spec approval would void it: they live in the living acceptance record."""
        frozen = [k for k in authoring.DOC_TEMPLATES if k not in authoring.LIVING_DOCS and k not in authoring.UNLINKED_DOCS]
        for doc_type in frozen:
            text = (ASSETS / authoring.DOC_TEMPLATES[doc_type]).read_text(encoding="utf-8")
            with self.subTest(doc_type=doc_type):
                self.assertNotRegex(text, r"(?im)^#+ .*sign-off", doc_type)
                self.assertNotRegex(text, r"(?m)^Status: ", doc_type)
        acceptance = (ASSETS / "acceptance.md").read_text(encoding="utf-8")
        for row in ("## Sign-offs", "| User acceptance (test plan) |", "| DPO advice and decision (DPIA) |"):
            self.assertIn(row, acceptance)
        self.assertIn("acceptance record", (ASSETS / "compliance-record.md").read_text(encoding="utf-8"))
        self.assertIn("acceptance record", (ASSETS / "test-plan.md").read_text(encoding="utf-8"))

    def test_one_threat_table_shape(self):
        head = "| Threat (STRIDE or LINDDUN) | Trust boundary or asset | Risk | Mitigation | Acceptance id | Owner |"
        ref = (SKILL / "references" / "spec-returns.md").read_text(encoding="utf-8")
        for text in (ref, (ASSETS / "threat-model.md").read_text(encoding="utf-8")):
            self.assertIn(head, text)
        # One home for each threat: the DPIA cites the model's LINDDUN rows by id, and never copies the table.
        risks = (ASSETS / "compliance-record.md").read_text(encoding="utf-8").split("### Risks and mitigations", 1)[1].split("\n### ", 1)[0]
        self.assertNotIn(head, risks)
        self.assertIn("threat model", risks)
        tm = (ASSETS / "threat-model.md").read_text(encoding="utf-8")
        for linddun in ("Linking", "Identifying", "Non-repudiation", "Detecting", "Data disclosure", "Unawareness", "Non-compliance"):
            self.assertRegex(tm, rf"\| T-[A-Z]+-\d\d {linddun}", linddun)  # each threat keeps its id: T-<COMPONENT>-NN
        self.assertIn("| Owner |", (ASSETS / "compliance-record.md").read_text(encoding="utf-8").split("## Obligations", 1)[1].split("\n## ", 1)[0])

    def test_traceability_is_covers_and_the_rollout_is_the_specs(self):
        for name in ("spec.md", "spec-short.md", "tech-spec.md", "test-plan.md"):
            text = (ASSETS / name).read_text(encoding="utf-8")
            self.assertNotIn("Red on base |", text, name)
            self.assertNotIn("| Command (`covers`) |", text, name)
        self.assertNotIn("\n## Rollout\n", (ASSETS / "spec.md").read_text(encoding="utf-8"))
        self.assertIn("(`## Rollout`)", (SKILL / "references" / "spec-release.md").read_text(encoding="utf-8"))
        short = (ASSETS / "spec-short.md").read_text(encoding="utf-8")
        for heading in ("## Request", "## Context", "## Acceptance", "## Design", "## Policy conflicts", "## Rollback"):
            self.assertIn(heading, short)
        self.assertNotIn("Alternatives", short.split("---", 2)[2])
        plan = (ASSETS / "test-plan.md").read_text(encoding="utf-8")
        for item in ("Suspension and resumption", "Staffing", "Schedule", "Estimate", "Stakeholders"):
            self.assertIn(item, plan)

    def test_the_spec_holds_the_contract_and_links_the_rest(self):
        full = (ASSETS / "spec.md").read_text(encoding="utf-8")
        for heading in ("## Alternatives considered", "## Cross-cutting concerns", "## Pre-mortem"):
            self.assertNotIn(heading, full)
        self.assertIn("# docs:", full)
        for doc_type in ("tech-spec", "test-plan", "threat-model", "adr", "runbook"):
            self.assertIn(doc_type, full.split("---", 2)[1])
        short = (ASSETS / "spec-short.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(short.splitlines()), 75)
        ref = (SKILL / "references" / "spec-docs.md").read_text(encoding="utf-8")
        self.assertIn("<!-- aidd:gen fields:doc -->", ref)
        self.assertIn("aidd new tech-spec", (SKILL / "references" / "example.md").read_text(encoding="utf-8"))


@unittest.skipUnless(shutil.which("git"), "git is required")
class NewDocTests(RepoTemplateCase):
    """`aidd new <type> <topic> --spec ID` writes the doc, fills the back-link, and links it from the Spec."""

    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", spec="02-normal-feature:specs/SPEC-220.md")

    def new(self, *args):
        run = aidd_here("new", *args, cwd=self.root)
        return run.returncode, run.stdout + run.stderr

    def spec(self):
        return (self.root / "specs" / "SPEC-220.md").read_text(encoding="utf-8")

    def test_a_doc_is_written_and_linked(self):
        code, out = self.new("tech-spec", "Rate limit", "--spec", "SPEC-220")
        self.assertEqual(code, 0, out)
        rel = "specs/SPEC-220/tech-spec-rate-limit.md"
        self.assertIn(rel, out)
        self.assertIn("SPEC-220", (self.root / rel).read_text(encoding="utf-8"))
        self.assertIn(f"docs:\n  - type: tech-spec\n    path: {rel}\n", self.spec())
        _, _, errs = spec_file.load_object(self.spec(), "specs/SPEC-220.md")
        self.assertEqual(errors(errs), [])
        data, _ = documents.split_front_matter(self.spec())
        self.assertIn(rel, spec_file.frozen_docs(data))
        code, out = self.new("test-plan", "limits", "--spec", "SPEC-220", "--doc-folder", "checkout")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / "specs/checkout/test-plan-limits.md").is_file())
        code, out = self.new("design-spec", "limit banner", "--spec", "SPEC-220", "--prototype")
        self.assertEqual(code, 0, out)
        self.assertIn("SPEC-220", (self.root / "specs/SPEC-220/design/prototype.html").read_text(encoding="utf-8"))
        code, out = self.new("threat-model", "limits", "--spec", "SPEC-220")
        self.assertEqual(code, 0, out)
        self.assertEqual([d["type"] for d in documents.split_front_matter(self.spec())[0]["docs"]], ["tech-spec", "test-plan", "design-spec", "threat-model"])

    def test_a_test_plan_is_the_specs_own_or_with_living_the_components(self):
        """One type at two scopes, as the threat model is one per component: `--living` writes the component's plan once and links
        it with `frozen: false`; a later Spec only links it again. A type with no living form refuses the flag."""
        code, out = self.new("test-plan", "checkout", "--spec", "SPEC-220")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.root / "specs/SPEC-220/test-plan-checkout.md").is_file())
        self.assertIn("frozen `docs` entry", out)
        rel = "docs/testing/test-plans/checkout.md"
        code, out = self.new("test-plan", "checkout", "--spec", "SPEC-220", "--living")
        self.assertEqual(code, 0, out)
        text = (self.root / rel).read_text(encoding="utf-8")
        self.assertIn("SPEC-220", text)
        self.assertIn("reviewed_on:", text)
        self.assertIn("ISO/IEC/IEEE 29119-3", text)
        self.assertIn(f"  - type: test-plan\n    path: {rel}\n    frozen: false", self.spec())
        code, out = self.new("test-plan", "checkout", "--spec", "SPEC-220", "--living")
        self.assertEqual(code, 0, out)
        self.assertIn("linked again", out)
        self.assertEqual(self.spec().count(rel), 1)
        code, out = self.new("adr", "x", "--spec", "SPEC-220", "--living")
        self.assertNotEqual(code, 0)
        self.assertIn("--living is for test-plan; adr has no living form", out)
        code, out = self.new("threat-model", "x", "--spec", "SPEC-220", "--living")
        self.assertNotEqual(code, 0)
        self.assertIn("a threat model takes its component as the topic", out)

    def test_aidd_new_spec_names_the_living_flag_for_the_living_plan(self):
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\nproject:\n  compliance:\n    targets: [soc2]\n", encoding="utf-8")
        code, out = self.new("spec", "Cart tax", "--route", "normal", "--paths", "src/cart/total.py")
        self.assertEqual(code, 0, out)
        self.assertIn("test-plan (expected: route normal, compliance on); test-plan --living (expected: route normal, compliance on)", out)

    def test_the_old_folder_flag_is_an_unknown_option(self):
        code, out = self.new("test-plan", "limits", "--spec", "SPEC-220", "--area", "checkout")
        self.assertEqual(code, 2, out)
        self.assertIn("unknown option --area", out)
        self.assertFalse((self.root / "specs/checkout").exists())

    def test_a_specialist_writes_a_doc_without_touching_the_spec(self):
        """One writer per file: `--no-link` writes the doc and leaves the Spec to the architect, who links it."""
        before = self.spec()
        code, out = self.new("threat-model", "limits", "--spec", "SPEC-220", "--no-link")
        self.assertEqual(code, 0, out)
        rel = "docs/security/threat-models/limits.md"  # the component's living model, never one per Spec
        self.assertIn("SPEC-220", (self.root / rel).read_text(encoding="utf-8"))
        self.assertEqual(self.spec(), before)
        self.assertIn(f"docs:\n  - type: threat-model\n    path: {rel}\n    frozen: false", out)
        self.assertIn("not linked", out)
        code, out = self.new("slo", "latency", "--spec", "SPEC-220", "--no-link")
        self.assertEqual(code, 0, out)
        self.assertNotIn("frozen: false", out)  # a delta, frozen with its Spec: the service card is the living file
        self.assertEqual(self.spec(), before)
        code, out = self.new("runbook", "RB-1", "--title", "Roll out limits", "--spec", "SPEC-220", "--no-link")
        self.assertEqual(code, 0, out)
        self.assertIn("type: runbook", out)
        self.assertEqual(self.spec(), before)
        code, out = self.new("request", "pitch", "--no-link")
        self.assertNotEqual(code, 0)
        self.assertIn("'request' is not a choice", out)  # no such type, so nothing is written or linked

    def test_adrs_are_numbered(self):
        self.assertEqual(self.new("adr", "Use a token bucket", "--spec", "SPEC-220")[0], 0)
        self.assertTrue((self.root / "docs/decisions/0001-use-a-token-bucket.md").is_file())
        (self.root / "docs/decisions/0007-older.md").write_text("# older\n", encoding="utf-8")
        self.assertEqual(self.new("adr", "Keep state in memory", "--spec", "SPEC-220")[0], 0)
        self.assertTrue((self.root / "docs/decisions/0008-keep-state-in-memory.md").is_file())
        self.assertIn("path: docs/decisions/0008-keep-state-in-memory.md", self.spec())

    def test_the_docs_dir_moves_the_official_docs_and_a_spec_keeps_its_own_and_an_unknown_spec_stops(self):
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\ndocs:\n  dir: documentation\n", encoding="utf-8")
        self.assertEqual(self.new("tech-spec", "limits", "--spec", "SPEC-220")[0], 0)
        self.assertTrue((self.root / "specs/SPEC-220/tech-spec-limits.md").is_file())  # beside the Spec, wherever docs/ is
        self.assertEqual(self.new("adr", "token buckets", "--spec", "SPEC-220")[0], 0)
        self.assertTrue((self.root / "documentation/decisions/0001-token-buckets.md").is_file())  # an ADR is an official doc
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
        return validation.validate_file(p, "specs/SPEC-9.md")

    def missing_types(self, found):
        return sorted({m.group(1) for w in warnings(found) for m in [re.search(r"links no (?:frozen |living )?(\S+) doc", w)] if m})

    def test_every_path_exists(self):
        found = self.check(spec_text(("tech-spec", DOC), extra="adrs: [docs/decisions/0001-x.md, https://example.com/adr/1]\n"))
        errs = errors(found)
        self.assertTrue(any(DOC in e and "does not exist" in e for e in errs), found)
        self.assertTrue(any("docs/decisions/0001-x.md" in e and "does not exist" in e for e in errs), found)
        self.assertEqual(len([e for e in errs if "does not exist" in e]), 2, found)  # those two: a URL is never checked as a path
        found = self.check(spec_text(("tech-spec", DOC), ("runbook", RUNBOOK, False)), {DOC: "# Tech spec\n\nSpec: SPEC-9.\n", RUNBOOK: "# Runbook\n"})
        self.assertEqual(errors(found), [])

    def test_design_files_are_listed_not_written_so_no_finding_asks_for_a_file_text_or_back_link(self):
        """A `design-files` entry lists mockups and flows: a glob that matches nothing yet, a picture, and a flow that holds a TODO and
        never names the Spec are all as `design.files` was, so no finding names them."""
        design = "specs/SPEC-9/design"
        files = {f"{design}/shot.png": "TODO", f"{design}/flow.md": "# Flow\n\nTODO\n| Acceptance id |\n| --- |\n| A9 |\n"}
        for name, listed in {"matches nothing yet": {}, "matches files that hold placeholders": files}.items():
            with self.subTest(name):
                found = self.check(spec_text(("design-files", f"{design}/**"), route="major", ctype="feat", scope='["src/web/"]'), listed)
                self.assertEqual([f for f in found if "design" in f and "SPEC-9/design" in f], [], found)
                self.assertNotIn("design-spec", self.missing_types(found), "design files stand in for a design spec")

    def test_a_design_files_entry_cannot_be_living_and_a_wide_one_is_refused(self):
        _, _, errs = spec_file.load_object(spec_text(("design-files", "specs/SPEC-9/design/**", False)), "specs/SPEC-9.md")
        self.assertTrue(any("always frozen" in e and "design/**" in e for e in errs), errs)
        _, _, errs = spec_file.load_object(spec_text(("design-files", "**")), "specs/SPEC-9.md")
        self.assertTrue(any("matches every path" in e and "design folder" in e for e in errs), errs)
        _, _, errs = spec_file.load_object(spec_text(("design-files", "src/cart/**")), "specs/SPEC-9.md")
        self.assertTrue(any("overlaps design file" in e for e in errs), errs)

    def test_the_design_mapping_is_no_key_of_a_spec_and_the_error_names_it(self):
        text = spec_text().replace("\ntests:", '\ndesign:\n  files: ["specs/SPEC-9/design/**"]\n\ntests:', 1)
        _, _, errs = spec_file.load_object(text, "specs/SPEC-9.md")
        self.assertTrue(any("unknown field 'design'" in e for e in errs), errs)

    def test_unchecked_launch_boxes_in_the_spec_warn_while_in_review(self):
        rollout = "\n## Rollout\n\n### Launch readiness\n\n<!-- - [ ] a comment -->\n\n- [ ] Comms\n- [x] Docs\n- [ ] Support\n\n### Next\n\n- [ ] Other\n"
        in_review = spec_text().replace("confidence: high", "confidence: high\nstatus: in_review", 1) + rollout
        shown = [w for w in warnings(self.check(in_review)) if "launch-readiness" in w]
        self.assertEqual(len(shown), 1, shown)
        self.assertIn("2 unchecked", shown[0])
        ticked = in_review.replace("- [ ] Comms", "- [x] Comms").replace("- [ ] Support", "- [x] Support")
        self.assertFalse(any("launch-readiness" in w for w in warnings(self.check(ticked))))
        self.assertFalse(any("launch-readiness" in w for w in warnings(self.check(spec_text() + rollout))), "only while the Spec is in review")

    def test_a_spec_in_review_with_no_rollout_has_no_launch_warning(self):
        in_review = spec_text().replace("confidence: high", "confidence: high\nstatus: in_review", 1)
        self.assertFalse(any("launch-readiness" in w for w in warnings(self.check(in_review))))

    def test_a_frozen_doc_names_its_spec_and_leaves_no_todo(self):
        found = self.check(spec_text(("tech-spec", DOC)), {DOC: "# Tech spec\n\nTODO: the design.\n"})
        self.assertEqual(errors(found), [])
        self.assertTrue(any(DOC in w and "TODO" in w for w in warnings(found)), found)
        self.assertTrue(any(DOC in w and "SPEC-9" in w for w in warnings(found)), found)
        found = self.check(spec_text(("tech-spec", DOC)), {DOC: "# Tech spec\n\nSpec: SPEC-9.\n"})
        self.assertFalse(any(DOC in w for w in warnings(found)), found)

    def test_a_linked_doc_cites_only_the_specs_own_acceptance_ids(self):
        """Acceptance ids come from the Spec: a specialist's row that coins one warns, in a doc of this Spec or, for this
        Spec's id, in a living threat model that other Specs share."""
        record, model = "specs/SPEC-9/compliance-record-export.md", "docs/security/threat-models/cart.md"
        table = "| Control id | Obligation | Acceptance id |\n| --- | --- | --- |\n"
        rows = "| Threat | Mitigation | Acceptance id |\n| --- | --- | --- |\n"
        files = {
            record: f"# Compliance\n\nSpec: SPEC-9.\n\n{table}| EC-10 | GDPR Art. 25 | A2 |\n| EC-11 | GDPR Art. 32 | A7 |\n",
            # A bare id in a shared model, and another Spec's id, belong to other Specs: neither warns here.
            model: f"# Threat model\n\n{rows}| T-CART-01 | bind | SPEC-9/A1 |\n| T-CART-02 | expire | SPEC-9/A8 |\n"
            "| T-CART-03 | log | SPEC-4/A8 |\n| T-CART-04 | rate | SPEC-4/A6 |\n| T-CART-05 | lock | A9 |\n",
            DOC: f"# Tech spec\n\nSpec: SPEC-9.\n\n## Security and privacy\n\n{rows}| T-CART-01 | bind | A5 |\n",
        }
        found = warnings(self.check(spec_text(("compliance-record", record), ("threat-model", model, False), ("tech-spec", DOC)), files))
        coined = sorted(m.group(0) for w in found for m in [re.search(r"(?<=names )A\d+\b(?=, which the Spec)", w)] if m)
        self.assertEqual(coined, ["A5", "A7", "A8"], found)
        self.assertTrue(any(record in w and "A7" in w for w in found), found)

    def test_with_compliance_on_the_living_component_plan_is_asked_for_apart_from_the_specs_own(self):
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\nproject:\n  compliance:\n    targets: [soc2]\n", encoding="utf-8")
        plan, living = "specs/SPEC-9/test-plan-cart.md", "docs/testing/test-plans/cart.md"
        body = "# Test plan\n\nSpec: SPEC-9.\n\n## Test approach\n\n| Acceptance id | Level |\n| --- | --- |\n| A1 | unit |\n| A2 | unit |\n"
        shared = "# Test plan\n\nThe component's.\n\n## Test approach\n\n| Case | Traces to |\n| --- | --- |\n| C-1 | SPEC-4/A7 |\n"

        def asked(*entries):
            found = self.check(spec_text(*entries), {plan: body, living: shared})
            return sorted(("living" if "links no living" in w else "frozen") for w in warnings(found) if "test-plan doc" in w)

        text = " ".join(warnings(self.check(spec_text(), {plan: body, living: shared})))
        self.assertIn(
            "links no living test-plan doc; `aidd new test-plan <component> --living --spec SPEC-9`, which writes docs/testing/test-plans/<component>.md", text
        )
        self.assertIn("links no frozen test-plan doc; `aidd new test-plan <topic> --spec SPEC-9`", text)
        self.assertNotIn("does not stand in", text)
        only = " ".join(warnings(self.check(spec_text(("test-plan", living, False)), {plan: body, living: shared})))
        self.assertIn("links no frozen test-plan doc (a living plan does not stand in for it)", only)
        self.assertEqual(asked(), ["frozen", "living"])
        self.assertEqual(asked(("test-plan", plan)), ["living"])
        self.assertEqual(asked(("test-plan", plan), ("test-plan", living, False)), [])
        self.assertEqual(asked(("test-plan", living, False)), ["frozen"])  # the component's plan does not stand in for the Spec's own
        found = self.check(spec_text(("test-plan", plan), ("test-plan", living, False)), {plan: body, living: shared})
        self.assertFalse(any(living in w for w in warnings(found)), found)  # a living plan holds other Specs' ids

    def test_the_test_plan_matches_the_acceptance(self):
        plan = "specs/SPEC-9/test-plan-cart.md"
        body = "# Test plan\n\nSpec: SPEC-9.\n\n## Test approach\n\n| Acceptance id | Level |\n| --- | --- |\n| A1 | unit |\n| A3 | e2e |\n"
        found = self.check(spec_text(("test-plan", plan), covers=["A1"]), {plan: body})
        shown = [w for w in warnings(found) if plan in w]
        self.assertTrue(any("A3" in w and "Acceptance" in w for w in shown), shown)
        self.assertTrue(any("A2" in w and "test plan" in w for w in shown), shown)
        self.assertFalse(any("A1" in w for w in shown), shown)
        body = body.replace("| A3 | e2e |", "| A2 | e2e |")
        found = self.check(spec_text(("test-plan", plan), covers=["A1"]), {plan: body})
        self.assertTrue(any("A2" in w and "covers" in w for w in warnings(found) if plan in w), found)

    def test_the_matrix_warns_on_major_and_on_normal_with_a_trigger(self):
        self.assertEqual(self.missing_types(self.check(spec_text(acceptance=8))), [])
        self.assertEqual(self.missing_types(self.check(spec_text(route="major", ctype="fix", dims='["availability"]'))), ["runbook", "tech-spec", "test-plan"])
        # A major change always needs a test plan; a count of Acceptance items is no trigger.
        self.assertEqual(
            self.missing_types(self.check(spec_text(route="major", ctype="feat", dims='["security"]', acceptance=12, scope='["src/web/"]'))),
            ["design-spec", "runbook", "tech-spec", "test-plan", "threat-model"],
        )
        # A feature with no user-facing path in scope (a CLI or back-end one) gets no design-spec warning.
        self.assertNotIn("design-spec", self.missing_types(self.check(spec_text(route="major", ctype="feat"))))
        self.assertIn("design-spec", self.missing_types(self.check(spec_text(route="major", ctype="feat", scope='["app/Checkout.tsx"]'))))
        with_design = spec_text(("design-files", "specs/SPEC-9/design/**"), route="major", ctype="feat", scope='["src/web/"]')
        self.assertNotIn("design-spec", self.missing_types(self.check(with_design)))
        # On normal only the threat model and, on the privacy dimension, the compliance record (its DPIA) warn; the rest are suggestions.
        # Privacy forces major, so `aidd validate` refuses that Spec's route before it reads the matrix, which still says so.
        on_normal, _ = documents.split_front_matter(spec_text(dims='["privacy"]', acceptance=6))
        warned = sorted(a.doc_type for a in authoring.required_docs(on_normal, None) if a.level == "warn")
        self.assertEqual(warned, ["compliance-record", "threat-model"])
        self.assertTrue(any("route normal is below major" in e for e in self.check(spec_text(dims='["privacy"]', acceptance=6))))
        data, _ = documents.split_front_matter(spec_text(acceptance=12, ctype="feat"))
        self.assertEqual([(a.doc_type, a.level) for a in authoring.required_docs(data, None) if a.doc_type == "test-plan"], [("test-plan", "suggest")])

    def test_the_spec_own_sections_count_and_the_config_overrides(self):
        inline = spec_text(route="major", ctype="fix", dims='["availability"]').replace(
            "## Rollback", "## Alternatives considered\n\nDo nothing.\n\n## Pre-mortem\n\nIt broke.\n\n## Rollout\n\nOne merge.\n\n## Rollback", 1
        )
        self.assertEqual(self.missing_types(self.check(inline)), ["test-plan"])
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "\ndocs:\n  disabled:\n    runbook: a library with no deployment\n", encoding="utf-8")
        self.assertEqual(self.missing_types(self.check(spec_text(route="major", ctype="fix", dims='["availability"]'))), ["tech-spec", "test-plan"])


class RolesTests(unittest.TestCase):
    """Who writes each linked doc."""

    def test_each_doc_type_has_a_writer(self):
        roles = team_registry.roles()["roles"]
        want = {
            "architect": ("{docs:tech-spec}", "{docs:adr}", "{docs:api}"),
            "verifier": ("{docs:test-plan}",),
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
        for key in ("verifier", "reviewer"):
            self.assertIn("QA engineer", roles[key]["industry"], key)
            self.assertIn("SDET", roles[key]["industry"], key)
        for key in want:
            self.assertIn("linked-docs", roles[key]["reads"], key)


class DocsTests(unittest.TestCase):
    """The Spec reference and the guides say what is frozen and what is living."""

    def read(self, rel):
        return (ROOT / rel).read_text(encoding="utf-8")

    def test_the_method_and_the_guides(self):
        spec = self.read(".agents/skills/aidd/references/spec-docs.md")
        for word in ("`docs`", "`frozen`", "Living", "spec.revise"):
            self.assertIn(word, spec)
        team = self.read("docs/TEAM.md").split("## Living architecture docs", 1)[1].split("\n## ", 1)[0]
        self.assertIn("frozen: false", team)
        self.assertIn("tech-spec", self.read("docs/CLI.md"))
        self.assertIn("<!-- aidd:gen fields:config-docs -->", self.read("docs/CONFIG.md"))


if __name__ == "__main__":
    unittest.main()
