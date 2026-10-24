"""The delivery defaults (rollout rings, migrations, fix windows, severities, pipeline time, review dates): each one lives with the skill or the template that owns it, as a
default a team may edit, and the review date of a living doc is checked like a runbook's `tested_on`."""

from __future__ import annotations

import datetime as dt
import re
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import config
from aidd.setup import doctor_checks
from aidd.kernel import resources

SKILLS = ROOT / "plugins" / "aidd-team" / "skills"
ASSETS = ROOT / ".agents" / "skills" / "aidd" / "assets"
CFG = 'aidd_version: "1.0.0"\nprofile: team\n{extra}owners:\n  approvers: ["@a"]\n'
TODAY = dt.date(2026, 10, 9)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def practice_standards(slug: str) -> set[str]:
    return {s if isinstance(s, str) else s["id"] for s in resources.load_json("roles.json")["practices"][slug]["standards"]}


class RolloutRings(unittest.TestCase):
    """A shadow ring for risky logic, thresholds set before each ring, and metrics split by flag state."""

    def test_the_flags_reference_has_the_shadow_ring(self):
        text = read(SKILLS / "release-rollout" / "references" / "flags-and-experiments.md")
        rings = section(text, "## Rings")
        for word in ("pricing", "billing", "permissions", "no side effects", "old result", "before", "flag state"):
            self.assertIn(word, rings, word)
        self.assertIn("| Ring |", rings)

    def test_the_runbook_rollout_has_a_ring_and_threshold_table(self):
        rollout = section(read(ASSETS / "runbook.md"), "## Rollout")
        header = next(ln for ln in rollout.splitlines() if ln.startswith("| Ring"))
        for column in ("Audience", "Go threshold", "No-go threshold", "Watch for"):
            self.assertIn(column, header, column)
        self.assertIn("| 0. Shadow |", rollout)


class MigrationTests(unittest.TestCase):
    """The previous app version runs on the new schema, and a backfill run twice gives the same result."""

    def test_the_two_rows(self):
        commands = section(read(SKILLS / "schema-migration" / "SKILL.md"), "## Test commands")
        self.assertRegex(commands, r"\| Previous version on the new schema \|[^\n]*previous release")
        self.assertRegex(commands, r"\| Backfill run twice \|[^\n]*same result")


class FixWindows(unittest.TestCase):
    """Fix windows by severity as editable defaults, a KEV entry counts as Critical, and both standards are dated."""

    def test_the_windows(self):
        text = read(SKILLS / "dependency-upgrade" / "references" / "sizing.md")
        windows = section(text, "## Fix windows")
        for row in ("| Critical (9.0 to 10.0), or in the KEV catalog | 48 hours |", "| High (7.0 to 8.9) | 7 days |", "| Medium (4.0 to 6.9) | 30 days |"):
            self.assertIn(row, windows, row)
        self.assertIn("default", windows.lower())
        self.assertIn("BOD 26-04", windows)

    def test_cvss_and_kev_are_dated_standards(self):
        reg = resources.load_json("roles.json")["standards"]
        for sid, edition in (("cvss", "v4.0"), ("cisa-kev-catalog", None)):
            entry = reg[sid]
            self.assertTrue(entry.get("checked"), sid)
            self.assertTrue(entry["evidence"]["quote"], sid)
            if edition:
                self.assertEqual(entry["edition"], edition)
            self.assertIn(sid, practice_standards("dependency-upgrade"))


class Severities(unittest.TestCase):
    """Default meanings of sev1 to sev3, the higher one when unsure, and when a postmortem is due."""

    def test_the_updates_reference(self):
        text = read(SKILLS / "incident-response" / "references" / "updates.md")
        sev = section(text, "## Severity")
        for word in ("sev1", "sev2", "sev3", "declare the higher", "20%", "5 working days", "default"):
            self.assertIn(word, sev, word)

    def test_the_glossary(self):
        row = next(ln for ln in read(ROOT / "docs" / "GLOSSARY.md").splitlines() if ln.startswith("| Severity |"))
        for word in ("sev1", "sev2", "sev3", "higher", "postmortem"):
            self.assertIn(word, row, word)


class PipelineTime(unittest.TestCase):
    """A PR pipeline under 10 minutes at the 90th percentile, slower is a defect, and how to measure it."""

    def test_the_target(self):
        text = read(SKILLS / "ci-pipeline" / "SKILL.md")
        self.assertRegex(text, r"under 10 minutes at the 90th percentile")
        self.assertIn("defect", text)
        self.assertIn("| Pipeline time |", section(text, "## Test commands"))


def repo_with(extra: str = "") -> tempfile.TemporaryDirectory:
    d = tempfile.TemporaryDirectory()
    (Path(d.name) / ".aidd").mkdir()
    (Path(d.name) / ".aidd" / "config.yaml").write_text(CFG.format(extra=extra), encoding="utf-8")
    return d


def living(reviewed_on: str | None) -> str:
    front = f'---\nreviewed_on: "{reviewed_on}"\n---\n\n' if reviewed_on else ""
    return front + "# Glossary: shop\n\n| Term | Meaning | Avoid |\n| --- | --- | --- |\n"


class ReviewDates(unittest.TestCase):
    """An optional `reviewed_on` on a living doc; `aidd doctor` warns when it is older than the limit."""

    def warnings(self, files: dict[str, str], extra: str = "") -> list[str]:
        with repo_with(extra) as d:
            root = Path(d)
            for rel, text in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text, encoding="utf-8")
            cfg = config.load_file(config.CONFIG_PATH, d)
            return [m for level, m in doctor_checks.review_checks(root, cfg, today=TODAY) if level == "warn"]

    def test_a_stale_repository_doc_is_warned(self):
        self.assertEqual(
            self.warnings({"docs/GLOSSARY.md": living("2026-01-01")}),
            [
                "docs/GLOSSARY.md: last reviewed 2026-01-01, 281 days ago (limit 180); a person reviews it, fixes or deletes what is stale, and updates reviewed_on"
            ],
        )
        self.assertEqual(self.warnings({"docs/GLOSSARY.md": living("2026-06-01")}), [])  # 130 days: fresh

    def test_it_is_optional(self):
        self.assertEqual(self.warnings({"docs/GLOSSARY.md": living(None), "docs/architecture/README.md": "# Architecture\n"}), [])

    def test_the_config_sets_the_limit(self):
        self.assertEqual(len(self.warnings({"docs/vendors.md": living("2026-06-01")}, "docs:\n  max_review_age_days: 90\n")), 1)
        with self.assertRaises(config.ConfigError):
            config.load_text(CFG.format(extra="docs:\n  max_review_age_days: 0\n"))
        self.assertEqual(config.load_text(CFG.format(extra="")).max_review_age_days, 180)

    def test_a_doc_a_spec_links_as_living_is_checked_and_a_frozen_one_is_not(self):
        spec = (
            '---\naidd_version: "1.0.0"\nkind: spec\nid: SPEC-1\ntitle: Checkout\n\n'
            "docs:\n  - kind: slo\n    path: specs/SPEC-1/slo-checkout.md\n    frozen: false\n"
            "  - kind: tech-spec\n    path: specs/SPEC-1/tech-spec-checkout.md\n---\n"
        )
        found = self.warnings(
            {
                "specs/SPEC-1.md": spec,
                "specs/SPEC-1/slo-checkout.md": living("2025-12-01"),
                "specs/SPEC-1/tech-spec-checkout.md": living("2025-12-01"),
            }
        )
        self.assertEqual([m.split(":", 1)[0] for m in found], ["specs/SPEC-1/slo-checkout.md"])

    def test_a_date_that_is_not_a_date_is_warned(self):
        self.assertEqual(self.warnings({"docs/data-map.md": living("soon")}), ["docs/data-map.md: reviewed_on 'soon' is not a date"])

    def test_doctor_reports_it(self):
        with repo_with() as d:
            (Path(d) / "docs").mkdir()
            (Path(d) / "docs" / "GLOSSARY.md").write_text(living("2025-01-01"), encoding="utf-8")
            found = doctor_checks.doctor(Path(d), today=TODAY)
            self.assertTrue(any(level == "warn" and re.search(r"GLOSSARY\.md: last reviewed 2025-01-01", m) for level, m in found), found)


if __name__ == "__main__":
    unittest.main()
