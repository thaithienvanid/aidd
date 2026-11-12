"""The product's living documents: the threat models' index and the check of a Spec's threat delta, the metrics
dictionary a tracking plan folds into, the improvement log's check dates, and the types `aidd new` writes for them."""

import datetime as dt
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import SAMPLE_SPEC, RepoTemplateCase, make_repo, run_cli

from aidd.workitems import living_docs, objects, validation

SPEC = "specs/SPEC-220.md"
MODELS = "docs/security/threat-models"
TODAY = dt.date(2026, 11, 4)


class TableRowsTests(unittest.TestCase):
    def test_rows_by_lowercase_header(self):
        text = "intro\n\n| Event (Object Action) | Owner |\n| --- | --- |\n| `Cart Viewed` | web |\n| Order Completed |\n\nafter\n\n| A |\n| - |\n| 1 |\n"
        self.assertEqual(
            living_docs.table_rows(text),
            [{"event (object action)": "`Cart Viewed`", "owner": "web"}, {"a": "1"}],
        )  # a rule row and a short row are skipped, and a second table has its own header

    def test_an_empty_last_cell_is_a_cell(self):
        self.assertEqual(
            living_docs.table_rows("| Change | Check by | Result |\n| --- | --- | --- |\n| retry | `2026-02-01` ||\n"),
            [{"change": "retry", "check by": "`2026-02-01`", "result": ""}],
        )

    def test_an_overdue_improvement_is_found_with_an_empty_last_cell_and_a_date_in_backticks(self):
        log = "| Change | Check by | Result |\n| --- | --- | --- |\n| retry | `2026-02-01` ||\n"
        self.assertEqual(len(living_docs.overdue_improvements("docs/improvement-log.md", log, dt.date(2026, 3, 1))), 1)


@unittest.skipUnless(shutil.which("git"), "git is required")
class LivingDocsCase(RepoTemplateCase):
    @classmethod
    def build_template(cls, root):
        make_repo(root, "team", branch=None)

    def setUp(self):
        super().setUp()
        here = os.getcwd()
        self.addCleanup(os.chdir, here)
        os.chdir(self.root)

    def write(self, rel: str, text: str) -> Path:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def sample(self, sid: str = "SPEC-220", status: str = "draft", design: str = "", docs: str = "") -> Path:
        """The sample Spec as `sid`, with its stored status, `design` added to its Design, and a `docs` list."""
        text = SAMPLE_SPEC.replace("SPEC-220", sid).replace("\nroute: ", f'\nstatus: "{status}"\nroute: ', 1)
        text = text.replace("One function applies the code to the total.", f"One function applies the code. {design}")
        return self.write(f"specs/{sid}.md", text.replace("tests:\n", docs + "tests:\n", 1))

    def spec(self, extra: str = "", status: str = "draft") -> list[str]:
        """The findings `aidd validate` gives the sample Spec, with `extra` added to its Design."""
        return validation.validate_file(self.sample(status=status, design=extra), SPEC)


class ThreatDeltaTests(LivingDocsCase):
    def findings(self, extra: str, models: dict[str, str] | None = None, status: str = "draft") -> list[str]:
        for name, body in (models or {}).items():
            self.write(f"{MODELS}/{name}.md", body)
        return [f for f in self.spec(extra, status) if "threat" in f]

    def test_each_case(self):
        cases = [
            # (what the Design says, the models on disk, the Spec's status, the component each finding names)
            ("It adds T-CHECKOUT-03.", {}, "draft", ["checkout"]),
            ("It adds T-CHECKOUT-03 and T-CHECKOUT-04.", {}, "draft", ["checkout"]),  # once per component
            ("It adds T-CHECKOUT-03 and T-CART-01.", {}, "draft", ["checkout", "cart"]),
            ("It adds T-USER-API-01.", {}, "draft", ["user-api"]),  # a hyphenated component
            ("It adds T-CHECKOUT-03.", {"checkout": "T-CHECKOUT-03 tampering"}, "ready", []),
            ("It adds T-CHECKOUT-03.", {"checkout": "T-CHECKOUT-01 spoofing"}, "draft", []),  # the model is due once approval is asked
            ("It adds T-CHECKOUT-03.", {"checkout": "T-CHECKOUT-01 spoofing"}, "ready", ["checkout"]),
            ("It adds T-USER-API-01.", {"user-api": "T-USER-API-01"}, "ready", []),
            ("It adds T-CHECKOUT-01.", {"checkout": "T-CHECKOUT-010 spoofing"}, "ready", ["checkout"]),  # a longer id is another id
            ("It adds T-TODO-01.", {}, "draft", []),  # the template's placeholder
            ("It adds no threat.", {}, "ready", []),
        ]
        for design, models, status, expected in cases:
            with self.subTest(design=design, models=list(models), status=status):
                shutil.rmtree(self.root / "docs", ignore_errors=True)
                found = self.findings(design, models, status)
                self.assertEqual(len(found), len(expected), found)
                for component, finding in zip(expected, found, strict=True):
                    self.assertIn(component, finding)
                    self.assertIn(f"{MODELS}/{component}.md", finding)

    def test_the_finding_for_a_missing_model_names_the_command_that_writes_it(self):
        (found,) = self.findings("It adds T-CHECKOUT-03.")
        self.assertIn("aidd new threat-model checkout --spec SPEC-220", found)
        self.assertTrue(found.startswith("warning: "), found)


class ThreatModelIndexTests(LivingDocsCase):
    def new(self, *args: str) -> tuple[int, str]:
        return run_cli("new", *args)

    def setUp(self):
        super().setUp()
        for sid in ("SPEC-220", "SPEC-221"):
            self.sample(sid)

    def index(self) -> str:
        return (self.root / MODELS / "README.md").read_text(encoding="utf-8")

    def test_the_index_lists_each_model_and_the_specs_that_link_it(self):
        for args in (("checkout", "--spec", "SPEC-220"), ("cart", "--spec", "SPEC-220"), ("checkout", "--spec", "SPEC-221")):
            code, out = self.new("threat-model", *args)
            self.assertEqual(code, 0, out)
        rows = {line.split("|")[1].strip(): line.split("|")[3].strip() for line in self.index().splitlines() if line.startswith("| ") and "---" not in line}
        self.assertEqual(rows, {"Component": "Specs that link it", "cart": "SPEC-220", "checkout": "SPEC-220, SPEC-221"})
        self.assertEqual(sorted(p.name for p in (self.root / MODELS).iterdir()), ["README.md", "cart.md", "checkout.md"])

    def test_a_component_cannot_be_called_readme(self):
        code, out = self.new("threat-model", "readme", "--spec", "SPEC-220")
        self.assertEqual(code, 2, out)
        self.assertFalse((self.root / MODELS).exists())

    def test_validate_says_when_the_index_is_missing_or_stale(self):
        self.new("threat-model", "checkout", "--spec", "SPEC-220")
        self.assertEqual([w for w in validation.check_repo(self.root, TODAY)[1] if "index" in w], [])
        self.write(f"{MODELS}/cart.md", "# Threat model: cart\n")
        stale = [w for w in validation.check_repo(self.root, TODAY)[1] if "index" in w]
        self.assertEqual(len(stale), 1)
        self.assertIn("out of date", stale[0])
        (self.root / MODELS / "README.md").unlink()
        self.assertIn("missing", [w for w in validation.check_repo(self.root, TODAY)[1] if "index" in w][0])
        self.new("threat-model", "cart", "--spec", "SPEC-221", "--no-link")
        self.assertEqual([w for w in validation.check_repo(self.root, TODAY)[1] if "index" in w], [])

    def test_a_readme_a_person_wrote_is_kept_and_never_called_stale(self):
        (self.root / MODELS).mkdir(parents=True)
        (self.root / MODELS / "README.md").write_text("# Our threat models\n", encoding="utf-8")
        self.new("threat-model", "checkout", "--spec", "SPEC-220")
        self.assertEqual(self.index(), "# Our threat models\n")
        self.assertEqual([w for w in validation.check_repo(self.root, TODAY)[1] if "index" in w], [])


class APathOutsideTheRepositoryNamesNoFile(unittest.TestCase):
    """A Spec's docs path is read by `aidd validate`, so one that leads out of the repository must read nothing there."""

    def test_each_path(self):
        with tempfile.TemporaryDirectory() as d:
            root, outside = Path(d) / "repo", Path(d) / "secret"
            (root / "specs").mkdir(parents=True)
            outside.mkdir()
            (outside / "x.md").write_text("## Events\n")
            (root / "specs" / "plan.md").write_text("plan\n")
            os.symlink(outside, root / "specs" / "link")
            os.symlink(outside / "x.md", root / "specs" / "leak.md")  # a file link inside a folder the glob walks
            cases = {
                "specs/plan.md": ["specs/plan.md"],
                "specs/*.md": ["specs/plan.md"],
                "../secret/x.md": [],
                "specs/../../secret/x.md": [],
                str(outside / "x.md"): [],
                "specs/link/x.md": [],
                "specs/link/*.md": [],
                "specs/leak.md": [],
                "specs/**/*.md": ["specs/plan.md"],
            }
            for pattern, want in cases.items():
                with self.subTest(pattern=pattern):
                    self.assertEqual(objects.files_matching(root, pattern), want)


class MetricsDictionaryTests(LivingDocsCase):
    PLAN = "# Tracking plan\n\nSpec: SPEC-220.\n\n## Events\n\n| Event (Object Action) | Trigger |\n| --- | --- |\n{rows}\n"
    DICTIONARY = "# Metrics\n\n## Events\n\n| Event (Object Action) | Trigger |\n| --- | --- |\n| `Cart Viewed` | the cart opens |\n"

    def findings(self, plan_rows: str, dictionary: str | None, status: str) -> list[str]:
        shutil.rmtree(self.root / "docs", ignore_errors=True)
        self.write("specs/SPEC-220/tracking-plan-cart.md", self.PLAN.format(rows=plan_rows))
        if dictionary is not None:
            self.write("docs/product/metrics.md", dictionary)
        docs = 'docs:\n  - type: tracking-plan\n    path: "specs/SPEC-220/tracking-plan-cart.md"\n'
        return [f for f in validation.validate_file(self.sample(status=status, docs=docs), SPEC) if "metrics dictionary" in f]

    def test_each_case(self):
        known = "| Cart Viewed | opens |"
        cases = [
            # (the plan's event rows, the dictionary, the Spec's status, the events the finding names)
            (known, self.DICTIONARY, "ready", []),
            ("| Order Completed | pays |", self.DICTIONARY, "ready", ["Order Completed"]),
            ("| Order Completed | pays |", self.DICTIONARY, "draft", []),  # due once approval is asked
            ("| Order Completed | pays |", None, "ready", []),  # no dictionary, no fold
            ("| TODO Viewed | tbd |", self.DICTIONARY, "ready", []),
        ]
        for rows, dictionary, status, expected in cases:
            with self.subTest(rows=rows, dictionary=dictionary is not None, status=status):
                found = self.findings(rows, dictionary, status)
                self.assertEqual(len(found), len(expected), found)
                for event in expected:
                    self.assertIn(event, found[0])


class ServiceCardTests(LivingDocsCase):
    SLO = "# SLO delta\n\nSpec: SPEC-220.\n\n## SLI changes\n\n| SLI | Change | Was | Becomes | Window |\n| --- | --- | --- | --- | --- |\n{rows}\n"
    CARD = "# Service: payments\n\n## SLOs\n\n| SLI | Target | Window |\n| --- | --- | --- |\n| Checkout answered under 300 ms | 99.5% | 28 days |\n"

    def findings(self, slo_rows: str | None, card: str | None, status: str = "ready") -> list[str]:
        shutil.rmtree(self.root / "docs", ignore_errors=True)
        docs = ""
        if slo_rows is not None:
            self.write("specs/SPEC-220/slo-payments.md", self.SLO.format(rows=slo_rows))
            docs = 'docs:\n  - type: slo\n    path: "specs/SPEC-220/slo-payments.md"\n'
        if card is not None:
            self.write("docs/services/payments.md", card)
        return [f for f in validation.validate_file(self.sample(status=status, docs=docs), SPEC) if "service card" in f]

    def test_each_case(self):
        folded = "| Checkout answered under 300 ms | add | none | 99.5% | 28 days |"
        cases = [
            # (the SLO doc's rows or None for no SLO doc, the card or None for no card, the Spec's status, the SLIs the finding names)
            (folded, self.CARD, "ready", []),
            ("| Checkout answered under 300 ms | tighten | 99.5% | 99.9% | 28 days |", self.CARD, "ready", ["Checkout answered under 300 ms"]),
            ("| Search answered under 1 s | add | none | 99% | 28 days |", self.CARD, "ready", ["Search answered under 1 s"]),
            (folded, None, "ready", ["Checkout answered under 300 ms"]),  # no card: nowhere to fold
            (folded, self.CARD.replace("99.5%", "99.0%"), "ready", ["Checkout answered under 300 ms"]),
            (None, self.CARD, "ready", []),  # no SLO doc, nothing to fold
            ("| Checkout answered under 300 ms | retire | 99.5% | none | 28 days |", None, "ready", []),  # a retired SLI sets no target
            ("| TODO: an SLI | add | none | 99.5% | 28 days |", None, "ready", []),  # a placeholder is not a fact
            ("| Search answered under 1 s | add | none | 99% | 28 days |", self.CARD, "draft", []),  # due once approval is asked
        ]
        for rows, card, status, expected in cases:
            with self.subTest(rows=rows, card=card is not None, status=status):
                found = self.findings(rows, card, status)
                self.assertEqual(len(found), len(expected), found)
                for sli in expected:
                    self.assertIn(sli, found[0])
                    self.assertIn("specs/SPEC-220/slo-payments.md", found[0])
                    self.assertIn("docs/services", found[0])


class ImprovementLogTests(LivingDocsCase):
    HEAD = "| Date | Improvement | Evidence | Type | Metric it should move | Check by | Result |\n| --- | --- | --- | --- | --- | --- | --- |\n"

    def warnings(self, row: str) -> list[str]:
        self.write("docs/retros/improvement-log.md", self.HEAD + row + "\n")
        # The review a logged improvement owes; an unedited template row is named by the placeholder warning instead.
        return [w for w in validation.check_repo(self.root, TODAY)[1] if "improvement" in w and "placeholders" not in w]

    def test_the_template_row_is_a_placeholder_not_a_due_review(self):
        self.write("docs/retros/improvement-log.md", self.HEAD + "| YYYY-MM-DD | TODO | TODO | TODO | TODO | YYYY-MM-DD | | \n")
        found = [w for w in validation.check_repo(self.root, TODAY)[1] if "improvement-log" in w]
        self.assertEqual(len(found), 1, found)
        self.assertIn("placeholders", found[0])

    def test_each_case(self):
        cases = [
            ("| 2026-09-01 | Smaller Specs | retro | method | cycle time | 2026-10-15 | | ", 1),
            ("| 2026-09-01 | Smaller Specs | retro | method | cycle time | 2026-10-15 | kept: 4 days to 3 | ", 0),
            ("| 2026-09-01 | Smaller Specs | retro | method | cycle time | 2026-12-01 | | ", 0),  # not yet due
            ("| 2026-09-01 | Smaller Specs | retro | method | cycle time | 2026-11-04 | | ", 0),  # due today
            ("| YYYY-MM-DD | TODO | TODO | TODO | TODO | YYYY-MM-DD | | ", 0),  # the template's row
        ]
        for row, count in cases:
            with self.subTest(row=row):
                found = self.warnings(row)
                self.assertEqual(len(found), count, found)
        self.assertIn("Smaller Specs", self.warnings(cases[0][0])[0])

    def test_no_log_no_finding(self):
        self.assertEqual([w for w in validation.check_repo(self.root, TODAY)[1] if "improvement" in w], [])


class NewKindsTests(LivingDocsCase):
    def test_a_repository_document_has_one_home_and_one_copy(self):
        homes = {
            "product-brief": "docs/product/brief.md",
            "metrics-dictionary": "docs/product/metrics.md",
            "control-register": "docs/compliance/control-register.md",
            "improvement-log": "docs/retros/improvement-log.md",
        }
        for doc_type, rel in homes.items():
            with self.subTest(doc_type=doc_type):
                code, out = run_cli("new", doc_type)
                self.assertEqual(code, 0, out)
                text = (self.root / rel).read_text(encoding="utf-8")
                self.assertNotIn("{{", text)
                code, out = run_cli("new", doc_type)
                self.assertNotEqual(code, 0, "one per repository")
                self.assertIn("exists", out)
                code, _ = run_cli("new", doc_type, "--spec", "SPEC-220")
                self.assertNotEqual(code, 0, "the repository's, not a Spec's")

    def test_a_service_is_one_file_and_belongs_to_no_spec(self):
        code, out = run_cli("new", "service-card", "Payments API")
        self.assertEqual(code, 0, out)
        text = (self.root / "docs/services/payments-api.md").read_text(encoding="utf-8")
        self.assertNotIn("{{", text)
        self.assertEqual(run_cli("new", "service-card", "payments-api")[0], 2)
        self.assertEqual(run_cli("new", "service-card", "other", "--spec", "SPEC-220")[0], 2)
        self.assertEqual(run_cli("new", "service-card", "other", "--no-link")[0], 2)

    def test_each_unlinked_document_says_what_to_do_next(self):
        from aidd import config, workitems

        for doc_type in workitems.UNLINKED_DOCS:
            self.assertTrue(config.item_type_rows()[doc_type]["next"], doc_type)
            self.assertTrue(config.item_type_rows()[doc_type]["without_spec"], doc_type)


if __name__ == "__main__":
    unittest.main()
