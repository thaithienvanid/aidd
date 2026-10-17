"""Hygiene checks on the registry and the documents generated from or hand-written beside it.

They are cheap, run offline, and check the relationship between two places that hold the same fact:
a rule that names a relationship must check both sides of it.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

import helpers
from helpers import ROOT, repo_files

from aidd.kernel import resources
from aidd.knowledge import team_registry

STEP = "Plan|Specify|Implement|Verify|Review|Ship|Learn"
TEXT_SUFFIXES = (".md", ".py", ".json", ".yml", ".yaml", ".toml", ".sh", ".txt", ".rego")


def strip_fences(text: str) -> str:
    """Drop fenced code blocks, so a Mermaid diagram's per-step role list is not read as a roster."""
    out, fence = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
            continue
        if not fence:
            out.append(line)
    return "\n".join(out)


def tracked_text_files() -> list[Path]:
    return [ROOT / f for f in repo_files() if f.endswith(TEXT_SUFFIXES) and (ROOT / f).is_file()]


class PlainNamesTests(unittest.TestCase):
    def test_the_two_human_approvals_are_named_in_plain_words(self):
        """The loop says Spec approval and Merge approval, never numbered gate codes a newcomer must learn first."""
        hits = []
        for f in tracked_text_files():
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if re.search(r"\bG[12]\b", line):
                    hits.append(f"{f.relative_to(ROOT)}:{i}")
        self.assertEqual(hits, [])

    def test_a_fix_names_the_command_that_gives_the_route(self):
        """ "Assess again" names no command: a fix says to run `aidd gate --paths` again, which shows the route."""
        hits = []
        for f in tracked_text_files():
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if re.search(r"\bassess(?:es)? (?:it )?again\b", line, re.I) and f.name != Path(__file__).name:
                    hits.append(f"{f.relative_to(ROOT)}:{i}")
        self.assertEqual(hits, [])


class ConflictMarkerTests(unittest.TestCase):
    def test_no_committed_merge_conflict_markers(self):
        """A conflict marker in a runbook an agent is told to follow (llms-install.md) would be read as instructions."""
        hits = []
        for f in tracked_text_files():
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if re.match(r"^(<{7}( |$)|={7}$|>{7}( |$))", line):
                    hits.append(f"{f.relative_to(ROOT)}:{i}")
        self.assertEqual(hits, [])


class RetiredNameTests(unittest.TestCase):
    def test_no_role_is_renamed_in_the_registry_but_not_in_the_prose(self):
        """A retired role name (`product-owner`, now `product-manager`) stays out of the registry and the prose.

        A schema description is the worst case: `gen-docs` renders it into the skill every harness reads,
        so the stale name comes back on the next regeneration.
        """
        pat = re.compile(r"product[ _-]owner", re.I)
        hits = []
        for f in tracked_text_files():
            if "test_registry_hygiene" in f.name:
                continue
            for i, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if pat.search(line):
                    hits.append(f"{f.relative_to(ROOT)}:{i}: {line.strip()[:90]}")
        self.assertEqual(hits, [])

    def test_every_hand_written_list_of_roles_names_exactly_the_registry(self):
        """Five files carry a hand-typed fourteen-name list; only one was test-held, so the rename missed four."""
        order = set(team_registry.roles()["order"])
        checked = 0
        for f in tracked_text_files():
            text = strip_fences(f.read_text(encoding="utf-8", errors="replace"))
            # A comma-separated run that names at least eight role keys is a hand-maintained list.
            for run in re.findall(r"[a-z][a-z0-9, `-]{40,}", text):
                found = {k for k in order if k in run}
                # Eleven or more is a roster; fewer is a legitimate subset such as "the five builders".
                if len(found) >= 11:
                    checked += 1
                    self.assertEqual(found, order, f"{f.relative_to(ROOT)} lists {sorted(order - found)} as missing and {sorted(found - order)} as extra")
        self.assertGreaterEqual(checked, 3, "found no hand-written role lists; this check has gone stale")

    def test_no_document_describes_a_role_by_a_vendor_model_name(self):
        """Roles carry a harness-neutral `tier`; the SKU lives only in team_registry.MODELS_BY_HARNESS.

        `assisted_by` examples legitimately name a model, so the check is scoped to the role tables and prose.
        Two places carry the derived alias on purpose: an agent file's `model:` frontmatter, which Claude
        Code reads, and the generated role and model tables, both rendered from team_registry.MODELS_BY_HARNESS.
        """
        allowed = {"src/aidd/knowledge/team_registry.py", "tests/test_team.py", "tests/test_registry_hygiene.py"}
        generated = re.compile(r"<!-- aidd:gen (?:role:[a-z-]+|roles:models|roles:tiers|roles:lead) -->.*?<!-- aidd:end -->", re.S)
        hits = []
        for f in tracked_text_files():
            rel = f.relative_to(ROOT).as_posix()
            if rel in allowed or "CHANGELOG" in rel:
                continue
            if rel.startswith("tests/"):
                continue  # a test fixture legitimately writes `model: opus` to prove uninstall keeps an edit
            text = generated.sub("", f.read_text(encoding="utf-8", errors="replace"))
            for i, line in enumerate(text.splitlines(), 1):
                if rel.startswith("plugins/aidd-team/agents/") and re.fullmatch(r"model: [a-z]+", line):
                    continue
                if re.search(r"\b(?:opus|sonnet|haiku)\b(?![.-])", line) and "assisted_by" not in line and "Assisted-by" not in line:
                    hits.append(f"{rel}:{i}: {line.strip()[:90]}")
        self.assertEqual(hits, [])


class RegistryConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.data = team_registry.roles()

    def test_a_test_command_name_is_unique_across_every_domain_pack(self):
        """Two packs both emitted `PII scan`; a change loading both produced an unmergeable Spec.

        A contract rule tells a role to put the pack's commands into `[[tests.commands]]`, and
        `gates.gate_tests_declared` fails on a repeated name.
        """
        seen: dict[str, str] = {}
        for dom in self.data["domains"]:
            for t in dom.get("tests", []):
                self.assertNotIn(t["name"], seen, f"{seen.get(t['name'])} and {dom['slug']} both name a test {t['name']!r}")
                seen[t["name"]] = dom["slug"]

    def test_no_role_carries_the_same_standard_twice(self):
        """A currency sweep that rewords an entry instead of replacing it leaves both behind."""

        def words(s: str) -> set[str]:
            return {w for w in re.findall(r"[a-z0-9]{4,}", s.lower()) if w not in {"and", "for", "the", "with", "that", "from"}}

        for key, role in self.data["roles"].items():
            stds = role["standards"]
            self.assertEqual(len(stds), len({s["name"] for s in stds}), f"{key} has an exactly duplicated name")
            for i, a in enumerate(stds):
                for b in stds[i + 1 :]:
                    wa, wb = words(a["name"]), words(b["name"])
                    if not wa or not wb:
                        continue
                    jaccard = len(wa & wb) / len(wa | wb)
                    if len(wa & wb) < 5:
                        continue  # short names collide on shared prefixes without being the same document
                    self.assertLess(jaccard, 0.75, f"{key}: near-duplicate standards\n  {a['name'][:90]}\n  {b['name'][:90]}")

    def test_a_role_acts_only_in_the_steps_the_registry_gives_it(self):
        """The product-manager's playbook had it reading `outcome.result` at Learn; its steps are ["Plan"].

        The contract rule "Work only in your loop steps" applies, and `docs/TEAM.md` said the opposite of the
        playbook, so whichever the agent read decided whether it stayed in its lane.
        """
        # Only the playbook is checked, and only for a self-referential instruction. Registry prose
        # legitimately names other steps when it describes a handoff ("ready for Review", "re-enters
        # the loop at Plan"), so scanning it produces false positives and teaches nobody anything.
        pat = re.compile(rf"\bat ({STEP}) you\b|\byou [^.]*?\bat ({STEP})\b", re.I)
        for key in self.data["order"]:
            text = (ROOT / "plugins" / "aidd-team" / "agents" / f"{key}.md").read_text(encoding="utf-8")
            body = text.split("## Playbook", 1)[-1]
            for m in pat.finditer(body):
                step = m.group(1) or m.group(2)
                if re.search(r"\b(not|never|neither|nor)\b", m.group(0), re.I):
                    continue  # "you do not act at Learn" states the boundary; it does not cross it
                self.assertIn(
                    step.capitalize() if step.isupper() else step,
                    [s for s in self.data["roles"][key]["steps"]],
                    f"{key}'s playbook has it acting at {step!r}; its steps are {self.data['roles'][key]['steps']}",
                )

    def test_every_role_has_a_tier_and_a_reason_that_ends_like_a_sentence(self):
        for key, role in self.data["roles"].items():
            self.assertIn(role["tier"], helpers.TIER_MEANING, key)
            self.assertTrue(role["tier_reason"].endswith("."), key)
            self.assertGreater(len(role["tier_reason"]), 40, f"{key}'s tier_reason is too thin to justify the tier")

    def test_the_two_loops_partition_the_loop_steps(self):
        loops = self.data["loop"]["loops"]
        steps = set(self.data["loop"]["steps"])
        outer, inner = set(loops["outer_steps"]), set(loops["inner_steps"])
        self.assertEqual(outer | inner, steps)
        self.assertEqual(outer & inner, set())
        self.assertEqual(len(loops["gates"]), 2)

    def test_maturity_is_applied_consistently_to_the_same_artifact(self):
        """MCP 2026-07-28 was `emerging` for the architect and unmarked for the security engineer.

        The contract rule "Proven methods first" makes the flag consequential: an emerging entry may be applied only when the
        change needs what the established one cannot give, with the reason recorded.
        """
        flags: dict[str, set] = {}

        def collect(entries):
            for s in entries:
                blob = f"{s['name']} {s.get('edition', '')}"
                for key in ("MCP specification revision", "OWASP Top 10 for Agentic Applications", "OWASP GenAI LLM Top 10 2026", "AGENTS.md"):
                    if key in blob:
                        flags.setdefault(key, set()).add(s.get("maturity"))

        for role in self.data["roles"].values():
            collect(role["standards"])
        for dom in self.data["domains"]:
            collect(dom["standards"])
        for key, values in flags.items():
            self.assertLessEqual(len(values), 1, f"{key!r} is marked {values} in different places")


class StandardsProvenanceTests(unittest.TestCase):
    """The standards registry: one table, one edition per document, and a date that says who looked."""

    def setUp(self):
        self.raw = resources.load_json("roles.json")
        self.table = self.raw["standards"]

    def refs(self):
        for key, role in self.raw["roles"].items():
            yield f"role {key}", role["standards"]
        for dom in self.raw["domains"]:
            yield f"domain {dom['slug']}", dom["standards"]
        for name, practice in self.raw["practices"].items():
            yield f"practice {name}", practice["standards"]

    def test_every_reference_names_an_entry_and_every_entry_is_used(self):
        used = set()
        for where, refs in self.refs():
            for ref in refs:
                sid = ref if isinstance(ref, str) else ref["id"]
                self.assertIn(sid, self.table, where)
                self.assertRegex(sid, r"^[a-z0-9][a-z0-9-]*$")
                used.add(sid)
        self.assertEqual(set(self.table) - used, set(), "an entry nobody applies")

    def test_a_versioned_entry_has_a_source_and_a_checker_shows_evidence(self):
        # The schema says so too (if edition then source; if checked_by then evidence).
        for sid, s in self.table.items():
            if s.get("edition"):
                self.assertTrue(s.get("source", "").startswith("https://"), f"{sid} has an edition and no source")
            if s.get("checked_by"):
                ev = s.get("evidence") or {}
                self.assertTrue(ev.get("url", "").startswith("https://") and ev.get("quote") and ev.get("retrieved"), sid)
                self.assertEqual(ev["retrieved"], s["checked"], f"{sid}: checked on a day nobody retrieved the source")

    def test_a_document_several_roles_apply_is_one_entry(self):
        """EU AI Act six times, ASVS, the Top 10, and Twelve-Factor three times, and OpenAPI 3.1.2 against 3.1.0."""
        for sid in ("eu-ai-act", "owasp-asvs", "owasp-top-10-cwe-top-25", "twelve-factor-app", "openapi", "openlineage", "open-data-contract-standard"):
            users = [where for where, refs in self.refs() for r in refs if (r if isinstance(r, str) else r["id"]) == sid]
            self.assertGreaterEqual(len(users), 2, sid)
        names = [s["name"] for s in self.table.values()]
        self.assertEqual(len(names), len(set(names)), "two entries carry the same document name")
        for s in self.table.values():
            if "OWASP ASVS" in s["name"] or "Twelve-Factor" in s["name"] or s["name"].startswith("EU AI Act"):
                self.assertIn(s["name"], ("OWASP ASVS", "The Twelve-Factor App", "EU AI Act"))

    def test_the_editions_the_audit_found_wrong_are_corrected(self):
        text = " | ".join(s.get("edition", "") for s in self.table.values())
        for stale in ("27018:2019", "27017:2015", "OpenFeature specification v1.0", "SP 1270 (April 2022)", "ACS 2026-08-03"):
            self.assertNotIn(stale, text)
        # OpenAPI was once recorded at 3.1.x while 3.2 was out: the edition is 3.2 or later, and the source is that edition's page.
        openapi = self.table["openapi"]
        self.assertGreaterEqual(tuple(int(n) for n in openapi["edition"].split(".")), (3, 2, 0))
        self.assertTrue(openapi["source"].endswith(f"/v{openapi['edition']}.html"), openapi["source"])


class StandardsSubstanceTests(unittest.TestCase):
    """A role applies established practice with an authoritative source, not one paper or one blog post."""

    def test_no_role_standard_rests_on_a_single_preprint(self):
        for key, role in team_registry.roles()["roles"].items():
            for s in role["standards"]:
                self.assertNotIn("arxiv.org", s.get("source", ""), f"{key}: {s['name'][:60]}")
                self.assertNotIn("blog", s.get("source", ""), f"{key}: {s['name'][:60]}")

    def test_the_single_study_entries_are_gone(self):
        table = resources.load_json("roles.json")["standards"]
        for sid in ("ai-review-is-faster-not-better", "llm-as-judge"):
            self.assertNotIn(sid, table)

    def test_fedramp_names_the_current_program_and_marks_rev5_legacy(self):
        table = resources.load_json("roles.json")["standards"]
        rev5, fx = table["fedramp-rev-5-baselines-where-they"], table["fedramp-20x"]
        self.assertIn("legacy", rev5["notes"])
        self.assertTrue(rev5["source"].startswith("https://www.fedramp.gov/") and "legacy" in rev5["source"], rev5["source"])
        self.assertTrue(fx["evidence"]["url"].startswith("https://www.fedramp.gov/20x"), fx["evidence"]["url"])
        # The current program's edition names its rules and their year; the legacy entry points to it.
        self.assertRegex(fx["edition"], r"\bRules for 20\d\d\b")
        self.assertIn(fx["edition"].split(":", 1)[0], rev5["notes"])


class PracticeSkillTests(unittest.TestCase):
    def test_every_practice_skill_states_when_not_to_load_it(self):
        """A description with only a positive trigger fires on work the skill cannot help with."""
        practices = {p for r in team_registry.roles()["roles"].values() for p in r.get("practices", [])}
        self.assertEqual(
            practices,
            {d.name for d in (ROOT / "plugins/aidd-team/skills").iterdir() if d.is_dir() and d.name in practices},
            "a practice in the registry has no directory",
        )
        for slug in sorted(practices):
            text = (ROOT / "plugins/aidd-team/skills" / slug / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("**Use it when**", text, slug)
            self.assertIn("**Do not use when**", text, f"{slug} has no negative trigger")

    def test_two_skills_a_task_would_load_together_do_not_repeat_a_test_command_list(self):
        """`threat-model` and `secure-coding` are the natural pair for a security Task, and a Task may name two.

        Three of five commands were verbatim identical, so loading both wasted the context and invited
        two `[[tests.commands]]` entries a reader would give the same name.
        """

        def commands(slug: str) -> str:
            text = (ROOT / "plugins/aidd-team/skills" / slug / "SKILL.md").read_text(encoding="utf-8")
            m = re.search(r"## Test commands.*?\n+(.*?)(?=\n## |\Z)", text, re.S)
            return m.group(1).lower() if m else ""

        shared = {"semgrep", "codeql", "gitleaks", "osv-scanner", "pip-audit", "zap"}
        a = {w for w in re.findall(r"[a-z0-9-]{4,}", commands("threat-model")) if w in shared}
        b = {w for w in re.findall(r"[a-z0-9-]{4,}", commands("secure-coding")) if w in shared}
        self.assertLessEqual(len(a & b), 1, f"threat-model and secure-coding still both list {sorted(a & b)}")


class DocumentStructureTests(unittest.TestCase):
    def test_every_markdown_table_has_its_delimiter_row_second(self):
        """Two GLOSSARY rows were inserted above the header, so they rendered as a paragraph of pipes."""
        for f in tracked_text_files():
            if not f.name.endswith(".md"):
                continue
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            blocks, cur, fence = [], [], False
            for line in lines:
                if line.lstrip().startswith("```"):
                    fence = not fence
                if not fence and line.startswith("|"):
                    cur.append(line)
                    continue
                if cur:
                    blocks.append(cur)
                    cur = []
            if cur:
                blocks.append(cur)
            for b in blocks:
                if len(b) < 2:
                    continue  # a single pipe line is prose, not a table
                if re.fullmatch(r"\|(\s*\|)+", b[0].strip()):
                    continue  # a layout table of link cards, not a data table
                self.assertRegex(b[1].strip(), r"^\|[\s|:-]+\|$", f"{f.relative_to(ROOT)}: a table's second row is not a delimiter: {b[1][:60]!r}")
                self.assertNotRegex(b[0].strip(), r"^\|[\s|:-]+\|$", f"{f.relative_to(ROOT)}: a table starts with its delimiter, so it has no header")

    def test_the_controls_matrix_cites_the_llm_top_10_edition_the_registry_declares(self):
        """CONTROLS.md used the 2025 IDs after the registry recorded the 2026 renumbering, so LLM03 meant
        two different risks in two files of one release."""
        controls = (ROOT / "docs/CONTROLS.md").read_text(encoding="utf-8")
        header = re.search(r"OWASP LLM Top 10 \((\d{4})\)", controls)
        self.assertIsNotNone(header, "CONTROLS.md no longer names an OWASP LLM Top 10 edition")
        registry = json.dumps(team_registry.roles())
        self.assertIn(header.group(1), {"2026"}, f"CONTROLS.md cites the {header.group(1)} edition")
        self.assertIn("2026 edition", registry)
        # Excessive Agency moved from LLM06 to LLM03 in the 2026 renumbering.
        self.assertIn("LLM03 Excessive Agency", controls)
        self.assertNotIn("LLM06 Excessive Agency", controls)


if __name__ == "__main__":
    unittest.main()
