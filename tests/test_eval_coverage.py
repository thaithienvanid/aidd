"""Role eval coverage: every role operation (a role at one loop step) has a case, except the known gaps below.

KNOWN_GAPS only shrinks. A case for a gap closes it, so remove the gap here in the same change; a new gap, from a role that
gains a step or a case that changes its step, fails until a case covers it.
"""

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT

from aidd import evals
from aidd.evals import scoring, suites
from aidd.docsgen import generate
from aidd.kernel import resources
from aidd.evals import claims
from aidd.evals import role_coverage

KNOWN_GAPS: set[tuple[str, str]] = set()


def scenarios() -> list[dict]:
    return evals.load_scenarios(ROOT / "evals" / "roles")


class CoverageTests(unittest.TestCase):
    def test_every_case_names_a_step_its_role_works_in(self):
        self.assertEqual(evals.role_case_problems(scenarios()), [])

    def test_the_operations_with_no_case_are_the_known_gaps(self):
        gaps = {op for op, ids in role_coverage.cases_by_operation(scenarios()).items() if not ids}
        self.assertEqual(
            (sorted(gaps - KNOWN_GAPS), sorted(KNOWN_GAPS - gaps)),
            ([], []),
            "the first list is a new gap: write a case for it. The second is a closed gap: remove it from KNOWN_GAPS",
        )

    def test_the_cases_run_in_the_order_of_their_numbers(self):
        numbers = [int(sc["id"][1:].partition("-")[0]) for sc in scenarios()]
        self.assertEqual(numbers, sorted(numbers), "add a case where its number places it")

    def test_every_case_loads_with_a_pass_bar_a_person_can_read(self):
        for sc in scenarios():
            with self.subTest(sc["id"]):
                expected = sc["expected"]
                self.assertTrue(sc["prompt"].strip() and sc["fixture"].strip())
                self.assertLessEqual(set(expected), scoring.EXPECTED_KEYS)
                for key in ("require", "require_any", "names_any", "note_any", "forbid", "changed_any", "reason_any"):
                    groups = expected.get(key, [])
                    for group in groups:
                        words = group if isinstance(group, list) else [group]
                        self.assertTrue(words and all(isinstance(x, str) and x.strip() for x in words), group)
                self.assertFalse(set(expected.get("forbid", [])) & set(expected.get("require", [])))

    def test_every_case_scores_one_decision_from_a_set_it_offers_or_a_delegate_answer(self):
        for sc in scenarios():
            with self.subTest(sc["id"]):
                if "answer_is" in sc["expected"]:
                    self.assertNotIn("decisions", sc, "a delegate case is scored on its answer object")
                    continue
                offered, wanted = sc["decisions"], sc["expected"]["decision"]
                wanted = [wanted] if isinstance(wanted, str) else wanted
                self.assertLessEqual(set(offered), set(suites.DECISION_MEANING), "name each value in DECISION_MEANING")
                self.assertTrue(len(offered) >= 2 and set(wanted) <= set(offered))
                if set(wanted) == set(offered):  # the right answers split on the decision, so a diff or a labelled line must carry the control
                    self.assertTrue({"lines", "forbid_edits", "edits_any", "edits_all"} & set(sc["expected"]), sc["id"])

    def test_no_claim_a_case_requires_is_a_word_the_fixture_plants(self):
        """`require_any` is for a claim the answer makes, so it never holds a word the fixture or the prompt hands over; `names_any` is
        for the fixture's own things. A plain word is letters, spaces, and hyphens; an identifier with a digit or a symbol is exempt."""
        for sc in scenarios():
            for group in sc["expected"].get("require_any", []):
                planted = [t for t in group if not re.search(r"[^A-Za-z '*-]", t) and scoring.term_found(t, sc["fixture"] + "\n" + sc["prompt"])]
                self.assertEqual(planted, [], f"{sc['id']}: move the group to names_any, or pick a word the fixture lacks")

    def test_each_case_has_a_near_miss_and_an_alternative_that_a_live_run_scores_right(self):
        samples = json.loads((ROOT / "evals" / "roles" / "samples.json").read_text(encoding="utf-8"))
        samples.pop("_comment")
        cases = {sc["id"]: sc for sc in scenarios()}
        self.assertEqual(list(samples), list(cases), "a sample pair for each case, in the cases' order")
        format_only = ("the handoff note", "no Decision", "more than one Decision")  # a case with `handoff: false` fails no wrong answer on its note
        for cid, pair in samples.items():
            sc = cases[cid]
            prompt = suites.role_prompt(sc)
            for kind in ("wrong", "right"):
                self.assertTrue(pair[kind] and all(isinstance(x, str) for x in pair[kind]), f"{cid}: {kind} is a list of answers")
                for n, text in enumerate(pair[kind]):
                    with self.subTest(f"{cid} {kind} {n}"):
                        ok, misses = suites.score_role(
                            suites.own_words(text, prompt), sc["expected"], decisions=sc.get("decisions"), handoff=sc.get("handoff", True)
                        )
                        self.assertEqual(ok, kind == "right", misses)
                        if kind == "wrong":
                            self.assertFalse(all(m.startswith(format_only) for m in misses), "a wrong answer fails on its defect, not on its format")

    def test_the_operations_are_the_registrys_steps_per_role(self):
        data = role_coverage.role_operations()
        self.assertEqual(len(data), len(set(data)))
        self.assertIn(("developer", "Implement"), data)
        self.assertIn(("sre", "Roll out"), data)
        self.assertTrue(KNOWN_GAPS <= set(data), "a known gap names an operation the registry no longer has")

    def test_each_case_counts_once_and_a_bad_step_counts_nowhere(self):
        cases = {
            "a case for its step": ({"id": "a", "role": "developer", "step": "Implement"}, ["a"], 0),
            "a step the role does not work in": ({"id": "b", "role": "developer", "step": "Review"}, [], 1),
            "no step": ({"id": "c", "role": "developer"}, [], 1),
            "an unknown role": ({"id": "d", "role": "nobody", "step": "Plan"}, [], 1),
        }
        for name, (case, ids, problems) in cases.items():
            with self.subTest(name):
                self.assertEqual(role_coverage.cases_by_operation([case])[("developer", "Implement")], ids)
                self.assertEqual(len(evals.role_case_problems([case])), problems)

    def test_the_table_has_a_row_per_operation_and_zero_marks_a_gap(self):
        rows = evals.role_coverage_table([{"id": "a", "role": "developer", "step": "Implement"}]).splitlines()
        self.assertEqual(len(rows), 2 + len(role_coverage.role_operations()))
        self.assertIn("| developer | Implement | 1 |", rows)
        self.assertIn("| sre | Roll out | 0 |", rows)

    def test_the_readme_places_each_role_case_in_the_step_its_case_names(self):
        r13 = next(sc for sc in scenarios() if sc["id"].startswith("r13-"))
        readme = (ROOT / "evals" / "roles" / "README.md").read_text(encoding="utf-8")
        self.assertIn(f"the SRE, in {r13['step']}: a vague rollback trigger", readme)

    def test_gen_docs_refuses_to_count_a_case_with_a_bad_step(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "evals" / "roles").mkdir(parents=True)
            (Path(tmp) / "evals" / "roles" / "scenarios.yaml").write_text("id: x\nrole: developer\nstep: Review\n", encoding="utf-8")
            with mock.patch.object(resources, "repo_root", return_value=Path(tmp)):
                with self.assertRaisesRegex(ValueError, "x: `step` is 'Review'"):
                    generate.render("evals:role-coverage")
        self.assertIn("| Role | Step | Cases |", generate.render("evals:role-coverage"))

    def test_a_missing_handoff_note_fails_only_the_cases_about_the_note(self):
        """`handoff: false` scores a right answer that ends with no note. The note stays required where the case is about it (r01, r15, r71),
        where a note check reads it (`note_any`), and on every held-out case, which no one edits."""
        held = {sc["id"] for sc in scenarios() if sc.get("tier") == "held-out"}
        about_the_note = {"r01", "r15", "r71"}
        for sc in scenarios():
            token = sc["id"].split("-")[0]
            if sc.get("handoff") is False:
                self.assertNotIn(sc["id"], held, sc["id"])
                self.assertNotIn(token, about_the_note, sc["id"])
                self.assertNotIn("note_any", sc["expected"], sc["id"])
            elif sc["id"] not in held and token not in about_the_note:
                self.assertIn("note_any", sc["expected"], f"{sc['id']}: a case that reads the note keeps it required; any other says `handoff: false`")
        right = "Found the defect.\nDecision: block"
        sc = {"decisions": ["block", "pass"], "expected": {"decision": "block"}}
        self.assertTrue(suites.score_role(right, sc["expected"], decisions=sc["decisions"], handoff=False)[0])
        self.assertFalse(suites.score_role(right, sc["expected"], decisions=sc["decisions"], handoff=True)[0])


def case_rows() -> list[dict]:
    return evals.suite_cases(ROOT)


class ClaimTests(unittest.TestCase):
    """Every case of the four suites names the claim it proves, its tier, and a line saying what it proves."""

    def test_every_case_names_a_claim_a_tier_and_what_it_proves(self):
        self.assertEqual(evals.case_problems(case_rows(), evals.claims_file(ROOT)), [])

    def test_a_row_carries_its_tags_so_no_caller_reads_the_front_matter_again(self):
        rows = case_rows()
        self.assertTrue(all(isinstance(r["tags"], list) for r in rows))
        written = [r for r in rows if r["suite"] == "team" and r["id"].startswith("loads-")]
        self.assertTrue(written)
        for row in written:
            self.assertIn("trigger", row["tags"], row["id"])
            self.assertIn(f"tier:{row['tier']}", row["tags"], row["id"])

    def test_the_claims_with_no_case_are_the_known_gaps(self):
        new, closed = claims.claim_gaps(case_rows(), evals.claims_file(ROOT))
        self.assertEqual(
            (new, closed), ([], []), "the first list is a claim no case proves: write a case. The second is a closed gap: remove it from known_gaps"
        )

    def test_the_held_out_tier_is_the_locked_held_out_cases(self):
        rows = case_rows()
        locked = {(e["suite"], e["case"]) for e in json.loads((ROOT / "evals" / "held-out.lock.json").read_text(encoding="utf-8"))["cases"]}
        self.assertEqual({(r["suite"], r["id"]) for r in rows if r["tier"] == "held-out"}, locked)
        for r in rows:
            if r["suite"] in ("plugin", "team"):
                self.assertEqual(r["tier"] == "held-out", r["id"].startswith("held-out-"), r["id"])
                self.assertEqual(r["tier"] == "description-change", r["id"].startswith(("loads-", "skips-")), r["id"])

    def test_no_smoke_case_is_held_out_and_the_smoke_tier_stays_small(self):
        smoke = [r for r in case_rows() if r["tier"] == "smoke"]
        self.assertTrue(all(not r["id"].startswith("held-out-") for r in smoke))
        self.assertLessEqual(len(smoke), 30, "the smoke tier runs on every change to the skill, an agent file, or a flow: keep it cheap")

    def test_the_checker_names_each_defect(self):
        good = {"suite": "routing", "id": "a", "claims": ["action:pr.merge"], "tier": "smoke", "proves": "x"}
        cases = {
            "a good row": (good, 0),
            "no claim": (dict(good, claims=[]), 1),
            "a claim with no kind": (dict(good, claims=["merge"]), 1),
            "an unknown kind": (dict(good, claims=["thing:x"]), 1),
            "an action that risks.json lacks": (dict(good, claims=["action:no.such"]), 1),
            "no tier": (dict(good, tier=None), 1),
            "a tier that is not one": (dict(good, tier="always"), 1),
            "nothing it proves": (dict(good, proves=" "), 1),
        }
        for name, (row, count) in cases.items():
            with self.subTest(name):
                self.assertEqual(len(evals.case_problems([row])), count)

    def test_a_required_claim_with_no_case_is_new_and_a_gap_a_case_covers_is_closed(self):
        rows = [{"suite": "team", "id": "a", "claims": ["control:x", "route:auth"], "tier": "full", "proves": "p"}]
        file = {
            "controls": {"x": {"source": "AGENTS.md", "statement": "s"}, "y": {"source": "AGENTS.md", "statement": "s"}},
            "known_gaps": {"control:y": "why", "control:x": "stale"},
        }
        new, closed = claims.claim_gaps(rows, file)
        self.assertIn("action:code.edit", new, "every action in risks.json is required")
        self.assertNotIn("route:auth", new)
        self.assertIn("route:payments", new, "every area in risks.json is required")
        self.assertNotIn("control:y", new)
        self.assertEqual(closed, ["control:x"])

    def test_the_table_has_a_row_per_claim_and_a_gap_reads_zero_with_its_reason(self):
        rows = [{"suite": "team", "id": "a", "claims": ["control:x"], "tier": "smoke", "proves": "p"}]
        table = evals.claim_coverage_table(rows, {"known_gaps": {"control:y": "no case yet"}}).splitlines()
        self.assertEqual(table[2], "| `control:x` | 1 | 1 | 0 | 0 | 0 |  |")
        self.assertEqual(table[3], "| `control:y` | 0 | 0 | 0 | 0 | 0 | no case yet |")


if __name__ == "__main__":
    unittest.main()
