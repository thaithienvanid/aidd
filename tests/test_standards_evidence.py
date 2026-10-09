"""Standards evidence: the standards check takes only real evidence, the registry cites the current
OWASP LLM IDs, and the public pages label what is built apart from what is proven."""

import contextlib
import datetime as dt
import io
import json
import re
import unittest
from unittest import mock

from helpers import ROOT

from aidd import cli, evals, mcp, resources

SENTENCE = "Use human-in-the-loop control to require a human to approve high-impact actions before they are taken."
PAGE = "https://genai.owasp.org/download/56857/"


def entry(i: int, quote: str = SENTENCE, url: str = PAGE, day: str = "2026-09-28") -> dict:
    return {"id": f"s{i}", "name": f"Standard {i}", "checked": day, "where": "role x", "evidence": {"url": url, "quote": quote, "retrieved": day}}


def eval_standards(entries: list[dict], table: dict | None = None) -> tuple[int, str]:
    """`aidd eval standards` on these entries (and this raw table), with the real registry's extensions."""
    out = io.StringIO()
    resources.roles()  # cached before the raw table is replaced
    raw = {"standards": table if table is not None else {}}
    with (
        mock.patch.object(evals, "standards", lambda: entries),
        mock.patch.object(evals.resources, "load_json", lambda name, real=resources.load_json: raw if name == "roles.json" else real(name)),
        contextlib.redirect_stdout(out),
    ):
        code = cli.main(["eval", "standards"])
    return code, out.getvalue()


class EvidenceConfirmsTests(unittest.TestCase):
    """Evidence confirms a date only when it quotes a full sentence from a page with a path."""

    def test_a_sentence_from_a_document_confirms(self):
        self.assertTrue(evals.confirms(entry(1)))

    def test_titles_fragments_and_homepages_do_not(self):
        for quote, url in (
            ("Pod Security Standards | Kubernetes", "https://kubernetes.io/docs/concepts/security/pod-security-standards/"),
            ("OWASP GenAI LLM Top 10 2026", "https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/"),
            ("Version 2026-07-28 (latest)", "https://modelcontextprotocol.io/specification/versioning"),
            ("The ML Test Score: A Rubric for ML Production Readiness and Technical Debt Reduction", "https://research.google/pubs/pub46555/"),
            (SENTENCE, "https://genai.owasp.org/"),
            (SENTENCE, "https://genai.owasp.org"),
        ):
            self.assertFalse(evals.confirms(entry(1, quote, url)), (quote, url))
        same = entry(1, "Standard one for the purpose of this particular test.")
        same["name"] = "Standard one for the purpose of this particular test"
        self.assertFalse(evals.confirms(same), "a quote that is the entry's own name")

    def test_an_extension_quote_may_be_the_line_that_names_its_pin(self):
        sha = "85598ba6e1256f7ebf4867b95d63b833c4549264"
        ext = {"name": "GitHub MCP", "pin": f"v1.12.2 ({sha})", "checked": "2026-09-29"}
        ext["evidence"] = {
            "url": "https://api.github.com/repos/github/github-mcp-server/commits/v1.12.2",
            "quote": f'"sha": "{sha}",',
            "retrieved": "2026-09-29",
        }
        self.assertTrue(evals.confirms(ext))
        ext["evidence"]["quote"] = '"sha": "0000000000000000000000000000000000000000",'
        self.assertFalse(evals.confirms(ext))


class BulkDateTests(unittest.TestCase):
    """A shared checked date with unconfirmed entries fails `aidd eval standards`."""

    def test_two_entries_one_title_quote_on_one_day_is_a_bulk_date(self):
        entries = [entry(1), entry(2, "OWASP GenAI LLM Top 10 2026")]
        with mock.patch.object(evals, "standards", lambda: entries):
            self.assertEqual(evals.bulk_checked_dates(threshold=0), [("2026-09-28", 1)])
        entries[1] = entry(2)
        with mock.patch.object(evals, "standards", lambda: entries):
            self.assertEqual(evals.bulk_checked_dates(threshold=0), [])

    def test_the_eval_fails_on_a_bulk_date_and_passes_on_confirmed_entries(self):
        today = dt.date.today().isoformat()
        titles = [entry(i, "OWASP GenAI LLM Top 10 2026", day=today) for i in range(21)]
        code, out = eval_standards(titles)
        self.assertEqual(code, 1, out)
        self.assertIn(f"21 entries share the checked date {today}", out)
        code, out = eval_standards([entry(i, day=today) for i in range(21)])
        self.assertEqual(code, 0, out)

    def test_a_reviewed_date_claims_no_check_and_is_not_counted(self):
        entries = [{"id": f"p{i}", "name": f"P{i}", "reviewed": "2026-09-25", "where": "role x"} for i in range(30)]
        with mock.patch.object(evals, "standards", lambda: entries):
            self.assertEqual(evals.bulk_checked_dates(), [])


class MovedIdTests(unittest.TestCase):
    """A standard that records a renumbering makes every other citation of an old ID fail."""

    TABLE = {
        "owasp-llm-top-10": {"name": "OWASP Top 10 for LLM Applications", "notes": "renumbered from 2025 (Excessive Agency LLM06 to LLM03)"},
        "least-privilege": {"name": "Least privilege", "source": "https://genai.owasp.org/llmrisk/llm062025-excessive-agency/"},
    }

    def test_a_source_that_still_cites_the_old_id_fails(self):
        with mock.patch.object(evals.resources, "load_json", lambda name: {"standards": self.TABLE}):
            found = evals.stale_id_citations()
        self.assertEqual([(s["id"], s["token"], s["new"]) for s in found], [("least-privilege", "llm062025", "LLM03")])
        code, out = eval_standards([], self.TABLE)
        self.assertEqual(code, 1, out)
        self.assertIn("least-privilege: cites llm062025", out)

    def test_the_current_id_passes(self):
        table = json.loads(json.dumps(self.TABLE))
        table["least-privilege"]["source"] = "https://genai.owasp.org/resource/owasp-genai-llm-top-10-2026/"
        with mock.patch.object(evals.resources, "load_json", lambda name: {"standards": table}):
            self.assertEqual(evals.stale_id_citations(), [])


class RegistryTests(unittest.TestCase):
    """The registry itself."""

    def setUp(self):
        self.table = resources.load_json("roles.json")["standards"]

    def test_the_registry_has_no_bulk_date_and_no_stale_id(self):
        self.assertEqual(evals.bulk_checked_dates(), [])
        self.assertEqual(evals.stale_id_citations(), [])

    def test_owasp_llm_ids_are_the_current_editions(self):
        # Invariants a new edition keeps: every OWASP LLM id the registry cites carries the edition's year, the
        # edition was published on or before the day it was checked, and the renumbering the notes list is a
        # permutation of real ids.
        top10 = self.table["owasp-llm-top-10"]
        year = re.fullmatch(r"(\d{4}) edition", top10["edition"]).group(1)
        self.assertEqual(top10["published"][:4], year)
        self.assertLessEqual(top10["published"], top10["checked"])
        self.assertIn(f"-{year}/", top10["source"])
        cited = re.findall(r"LLM\d{2}:(\d{4})", json.dumps(self.table))
        self.assertTrue(cited)
        self.assertEqual(set(cited), {year})
        moves = re.findall(r"\b(LLM\d{2}) to (LLM\d{2})\b", top10["notes"])
        self.assertTrue(moves)
        self.assertEqual(len({a for a, _ in moves}), len(moves))
        self.assertEqual(len({b for _, b in moves}), len(moves))
        for a, b in moves:
            self.assertTrue(1 <= int(a[3:]) <= 10 and 1 <= int(b[3:]) <= 10, (a, b))
        # The least-privilege entry cites Excessive Agency by the id this edition gives it.
        agency = self.table["least-privilege-per-tool-and-human"]
        excessive = re.search(r"Excessive Agency LLM\d{2} to (LLM\d{2})", top10["notes"]).group(1)
        self.assertIn(f"{excessive}:{year}", agency["notes"])
        self.assertNotRegex(json.dumps(self.table), rf"llm\d{{2}}{int(year) - 1}")
        for text in (ROOT / "plugins/aidd-team/skills/ai-agents-and-tools/SKILL.md", ROOT / "docs/TEAM.md"):
            self.assertNotIn("LLM06 in the 2025 list the evidence cites", text.read_text(encoding="utf-8"))

    def test_opentelemetry_genai_ships_no_sample_commit(self):
        notes = self.table["opentelemetry-genai-semconv"]["notes"]
        self.assertTrue(notes.startswith("no tagged release"), notes)
        self.assertIn("record the commit you tested in the Spec", notes)
        self.assertNotRegex(json.dumps(self.table["opentelemetry-genai-semconv"]), r"\b[0-9a-f]{40}\b")

    def test_one_mcp_row_for_the_servers_a_team_ships_without_aidd_internals(self):
        """One MCP row, without `aidd mcp`'s own revisions: which revisions aidd speaks is
        aidd's release fact (docs/ENTERPRISE.md), not a standard a team applies to the servers it builds."""
        self.assertNotIn("model-context-protocol-and-agent2agent-a2a", self.table)
        # New servers follow the revision the specification entry is checked at, whichever that is.
        revision = re.fullmatch(r"(\d{4}-\d{2}-\d{2}) revision", self.table["mcp-specification"]["edition"]).group(1)
        self.assertTrue(self.table["mcp-specification"]["source"].endswith(f"/{revision}"))
        self.assertIn(f"new MCP servers follow {revision}", self.table["mcp-specification"]["notes"])
        self.assertIn("A2A", self.table["mcp-specification"]["name"])
        pack = (ROOT / "plugins/aidd-team/skills/ai-agents-and-tools/SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("aidd mcp", pack)
        self.assertNotIn(mcp.SUPPORTED[0], json.dumps(self.table["mcp-specification"]))


class OverviewTableTests(unittest.TestCase):
    """The domain overview tables hold one row per standard, with its name, bare edition, and date; the notes
    stay in the packs, so no cell grows into a paragraph."""

    def test_each_standard_in_the_overview_is_one_row_of_name_edition_date(self):
        domains = resources.roles()["domains"]
        for path in (ROOT / "docs/TEAM.md", ROOT / "plugins/aidd-team/skills/aidd-team/references/domain-packs.md"):
            text = path.read_text(encoding="utf-8")
            block = text.split("<!-- aidd:gen roles:domains -->", 1)[1].split("<!-- aidd:end -->", 1)[0]
            lines = [line for line in block.splitlines() if line.startswith("| ")]
            self.assertTrue(lines[0].endswith("| Standard | Edition | Checked |"), lines[0])
            rows = [line.removeprefix("| ").removesuffix(" |").split(" | ") for line in lines[2:]]
            starts = [i for i, cells in enumerate(rows) if cells[0]]
            self.assertEqual([rows[i][0] for i in starts], [d["name"] for d in domains], path.name)
            for d, start, end in zip(domains, starts, [*starts[1:], len(rows)], strict=True):
                group = rows[start:end]
                self.assertEqual(len(group), len(d["standards"]), (path.name, d["name"]))
                for cells, s in zip(group, d["standards"], strict=True):
                    self.assertEqual(cells[3], s["name"], (path.name, s["id"]))
                    self.assertEqual(cells[4], s.get("release") or "—", (path.name, s["id"]))
                    self.assertRegex(cells[5], r"^(?:checked|reviewed) \d{4}-\d{2}-\d{2}$", (path.name, s["id"]))
                    for cell in cells:
                        self.assertLessEqual(len(cell), 300, (path.name, s["id"], cell[:80]))
                        self.assertNotIn("(published ", cell, (path.name, s["id"]))
                        if len(s.get("notes", "")) > 40:  # a note of a word or two ("current") can also be part of a name
                            self.assertNotIn(s["notes"], cell, (path.name, s["id"]))


class PageTests(unittest.TestCase):
    """The secure-coding default, the README's maturity sentence, and the enterprise platform table."""

    def test_secure_coding_defaults_to_four_rules(self):
        text = (ROOT / "plugins/aidd-team/skills/secure-coding/SKILL.md").read_text(encoding="utf-8")
        implement = text.split("## Implement", 1)[1].split("\n## ", 1)[0]
        default, full = implement.split("**When the Task names this skill, or the route is major**", 1)
        for heavy in ("configuration boundary", "lint", "fuzz", "SAST", "secret scanning"):
            self.assertNotIn(heavy, default, heavy)
        for rule in ("trust boundary", "parameterized", "Authorization is checked on every path", "Secrets"):
            self.assertIn(rule, default, rule)
        for heavy in ("configuration boundary", "lint rule"):
            self.assertIn(heavy, full, heavy)
        tests = text.split("## Test commands", 1)[1].split("\n## ", 1)[0]
        default_tests, full_tests = tests.split("When the Task names this skill, or the route is major", 1)
        for heavy in ("Semgrep", "fuzz", "gitleaks", "lint"):
            self.assertNotIn(heavy, default_tests, heavy)
            self.assertIn(heavy, full_tests, heavy)

    def test_the_readme_states_the_release_criterion(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("is complete but not yet tagged", text)
        self.assertIn("unreleased and Beta until it is tagged, published, and one pull request has passed this repository's own live gate", text)

    def test_the_platform_table_separates_built_from_exercised_live(self):
        text = (ROOT / "docs/ENTERPRISE.md").read_text(encoding="utf-8")
        section = text.split("## 11. Platform coverage", 1)[1].split("\n## ", 1)[0]
        self.assertIn("| Platform | Implemented | Exercised live |", section)
        rows = {
            line.split(" | ")[0].strip("| "): line.rstrip(" |").rsplit(" | ", 1)[1]
            for line in section.splitlines()
            if line.startswith("| ") and "---" not in line
        }
        self.assertTrue(rows["GitHub.com"].startswith("no"), rows["GitHub.com"])
        self.assertIn("experimental", rows["GitLab"])


if __name__ == "__main__":
    unittest.main()
