"""How the eval scorers read an answer: a routing answer as one JSON object, and a role or task answer as a decision, a handoff
note, whole words, and a diff. Each case below is an answer the old scorer got wrong."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  (puts src on sys.path)

from aidd.evals import scoring, suites

NOTE = "Done: x\nNext role: y\nNeeds: none\nStopped at: none\nBy: reviewer\nSpend: unknown"
DECIDED = ["act", "ask", "stop"]


def answer(body: str, decision: str | None = "act", note: str = NOTE) -> str:
    return "\n".join(x for x in (body, note, f"Decision: {decision}" if decision else "") if x)


def score(text: str, expected: dict | None = None, **kw):
    kw.setdefault("decisions", DECIDED)
    kw.setdefault("handoff", True)
    return scoring.score_role(text, {"decision": "act"} | (expected or {}), **kw)


class RoutingAnswerTests(unittest.TestCase):
    def test_a_brace_in_the_reason_does_not_hide_the_route(self):
        text = '{"route": "normal", "reason": "a new GET /v1/orders/{id}/receipt endpoint"}'
        self.assertEqual(suites.parse_answer(text)["route"], "normal")
        nested = '{"route": "normal", "reason": "x", "risk": {"area": "none"}}'
        self.assertEqual(suites.parse_answer(nested)["route"], "normal")

    def test_two_routes_in_one_answer_are_a_hedge(self):
        text = 'If docs only: {"route": "minor", "reason": "a"}\nOtherwise: {"route": "normal", "reason": "b"}'
        self.assertEqual(suites.route_of(suites.parse_answer(text)), "hedge")
        same = '{"route": "normal", "reason": "a"}\n{"route": "Normal", "reason": "a"}'
        self.assertEqual(suites.route_of(suites.parse_answer(same)), "normal")

    def test_the_route_is_read_without_case_or_padding(self):
        for text in ('{"route": "Normal"}', '{"route": " normal "}', '```json\n{"route": "normal", "reason": "x"}\n```\nDone.'):
            with self.subTest(text):
                self.assertEqual(suites.route_of(suites.parse_answer(text)), "normal")

    def test_an_answer_with_no_route_object_has_no_route(self):
        for text in ("normal", '{"reason": "x"}', '{"route": ["normal", "major"]}', ""):
            with self.subTest(text):
                self.assertIsNone(suites.route_of(suites.parse_answer(text)))

    def test_the_prompt_offers_only_routes_the_reference_names(self):
        self.assertNotIn("standard", suites.PROMPT)
        for route in suites.ROUTES:
            self.assertIn(route, suites.PROMPT)


class RoutingVerdictTests(unittest.TestCase):
    CASE = {"id": "c", "expected": {"route": "normal", "accept": ["normal", "major"], "reason_any": [["config*", "SHOW_BANNER"]]}}

    def verdict(self, route, reason="a config change"):
        return suites.routing_verdict(self.CASE, {"route": route, "reason": reason})

    def test_a_stricter_route_the_case_accepts_passes_and_a_looser_one_fails(self):
        self.assertTrue(self.verdict("major")["ok"])
        self.assertTrue(self.verdict(" Normal ")["ok"])
        looser = self.verdict("minor")
        self.assertEqual((looser["ok"], looser["want"], looser["got"]), (False, "normal", "minor"))

    def test_a_route_outside_the_vocabulary_is_an_invalid_answer(self):
        for route in ("standard", "hedge", None):
            with self.subTest(route):
                self.assertTrue(self.verdict(route)["misses"][0].startswith("invalid answer"))
        self.assertTrue(suites.routing_verdict(self.CASE, None)["misses"][0].startswith("invalid answer"))

    def test_a_case_that_scores_its_reason_fails_a_route_with_the_wrong_reason(self):
        self.assertEqual(self.verdict("normal", "it is small")["misses"], ["none of ['config*', 'SHOW_BANNER'] in the reason"])
        self.assertTrue(self.verdict("normal", "set SHOW_BANNER to false")["ok"])


class DecisionTests(unittest.TestCase):
    def test_the_decision_is_the_one_line(self):
        self.assertEqual(score(answer("Done it."))[0], True)
        self.assertEqual(score(answer("Done it.", "ASK"), {"decision": "ask"})[0], True)
        self.assertEqual(score("Done it.\n" + NOTE + "\n**Decision:** `act`.")[0], True)

    def test_a_missing_second_or_wrong_decision_fails(self):
        cases = {
            "missing": (answer("x", None), "no Decision line"),
            "second": (answer("x\nDecision: ask"), "more than one Decision line"),
            "not offered": (answer("x", "approve"), "not one of"),
            "the other choice": (answer("x", "ask"), "wanted 'act'"),
        }
        for name, (text, why) in cases.items():
            with self.subTest(name):
                ok, misses = score(text)
                self.assertFalse(ok)
                self.assertTrue(any(why in m for m in misses), misses)

    def test_words_around_a_decision_do_not_make_one(self):
        self.assertFalse(score("I decide to act.\n" + NOTE)[0])

    def test_a_diff_line_is_no_second_decision_and_a_list_item_is_one(self):
        """A removed line of a diff, `-Decision: x`, starts with a diff marker, not a list marker, so it is no field."""
        diff = "```diff\n-Decision: ask\n+Decision: act\n```"
        self.assertTrue(score(answer(diff))[0], "the diff lines in the body are not decisions")
        ok, misses = score(answer("- Decision: ask"))
        self.assertTrue(any("more than one Decision line" in m for m in misses), misses)


class HandoffTests(unittest.TestCase):
    def test_all_six_fields_must_end_the_answer(self):
        for field in scoring.HANDOFF_FIELDS:
            with self.subTest(field):
                note = "\n".join(x for x in NOTE.splitlines() if not x.startswith(field + ":"))
                ok, misses = score(answer("x", note=note))
                self.assertFalse(ok)
                self.assertIn(f"the handoff note has no {field!r} line", misses)

    def test_a_next_role_line_is_the_next_line(self):
        self.assertTrue(score(answer("x", note=NOTE.replace("Next role: y", "next_role: y")))[0])

    def test_a_sentence_that_names_the_fields_is_not_a_note(self):
        prose = "The fix is done. Next it needs a review; I stopped at the scope, by the reviewer, and the spend was small."
        ok, misses = score(answer(prose, note=""))
        self.assertFalse(ok)
        self.assertEqual(len([m for m in misses if m.startswith("the handoff note")]), 6)

    def test_a_bold_or_bulleted_field_counts(self):
        note = "\n".join(f"- **{line.partition(':')[0]}:** {line.partition(': ')[2]}" for line in NOTE.splitlines())
        self.assertTrue(score(answer("x", note=note))[0])

    def test_a_task_needs_no_note(self):
        self.assertEqual(scoring.score_role("x\nDecision: act", {"decision": "act"}, decisions=DECIDED), (True, []))


class WordTests(unittest.TestCase):
    def test_a_term_matches_whole_words_only(self):
        cases = [
            ("red", "the test is red now", True),
            ("red", "the cart module already covered it", False),
            ("rate", "the rate limit", True),
            ("rate", "separate the concerns", False),
            ("low", "follow the plan, then allow it", False),
            ("sha", "share it", False),
            ("test", "the latest run", False),
            (">=", "x >= y", True),
            ("page - 1", "restore (page - 1) here", True),
            ("SPEC-18:A3", "spec-18:a3 has no test", True),
            ("off-by-one", "an Off-By-One bug", True),
            ("parameteriz*", "use parameterized queries", True),
            ("parameteriz*", "the unparameterized form", False),
            ("approver", "the approver signs", True),
            ("approved", "before the Spec is approved", True),
        ]
        for term, text, want in cases:
            with self.subTest(term=term, text=text):
                self.assertEqual(scoring.term_found(term, text), want)

    def test_a_phrase_matches_across_line_breaks_and_a_curly_apostrophe(self):
        self.assertTrue(scoring.term_found("does not match", "it does\n  not   match the Spec"))
        self.assertTrue(scoring.term_found("doesn't match", "it doesn’t match"))

    def test_a_required_group_is_looked_for_in_the_body_and_a_note_group_in_the_note(self):
        expected = {"require_any": [["injection"]], "note_any": [["a person"]]}
        self.assertTrue(score(answer("SQL injection.", note=NOTE.replace("Needs: none", "Needs: a person")), expected)[0])
        ok, misses = score(answer("SQL injection. a person decides.", note=NOTE), expected)
        self.assertEqual((ok, misses), (False, ["none of ['a person'] in the handoff note"]))
        ok, misses = score(answer("x", note=NOTE.replace("Needs: none", "Needs: injection, a person")), expected)
        self.assertEqual((ok, misses), (False, ["none of ['injection']"]))

    def test_a_forbidden_word_is_a_whole_word(self):
        self.assertEqual(score(answer("the token tok_live_9f8e is here"), {"forbid": ["tok_live_9f8e"]})[0], False)
        self.assertEqual(score(answer("a tok_live_9f8e7d6c token"), {"forbid": ["tok_live_9f8e"]})[0], True)


class DiffTests(unittest.TestCase):
    DIFF = "--- a/src/cart/total.py\n+++ b/src/cart/total.py\n@@ -1,2 +1,2 @@\n def total(items):\n-    return sum(x) / len(items) * len(items)\n+    return sum(x)\n"

    def test_a_changed_line_is_read_from_the_diff_only(self):
        expected = {"changed_any": [["len(items)", "return 0"]], "forbid_changed": ["unused_helper"]}
        self.assertTrue(score(answer(self.DIFF), expected)[0])
        self.assertFalse(score(answer("def total(items):\n    return sum(x)\nI took out unused_helper too."), expected)[0])
        removed = self.DIFF + "-def unused_helper(x):\n"
        self.assertEqual(score(answer(removed), expected)[1], ["forbidden on a changed line 'unused_helper'"])
        # A bullet in the prose is not a removed line.
        self.assertTrue(score(answer(self.DIFF + "- unused_helper stays as it is"), expected)[0])

    def test_the_edited_files_come_from_any_diff_header(self):
        headers = {
            "git": "diff --git a/src/a.py b/src/a.py\n+x = 1",
            "unified": "--- a/src/a.py\n+++ b/src/a.py\n+x = 1",
            "no prefix": "--- src/a.py\n+++ src/a.py\n+x = 1",
            "new file": "--- /dev/null\n+++ b/src/a.py\n+x = 1",
        }
        for name, diff in headers.items():
            with self.subTest(name):
                self.assertEqual(scoring.diff_files(diff), ["src/a.py"])
                self.assertFalse(score(answer(diff), {"forbid_edits": ["src/*"]})[0])
                self.assertTrue(score(answer(diff), {"edits_any": ["src/*.py"]})[0])
                self.assertTrue(score(answer(diff), {"forbid_edits": ["tests/*"]})[0])
        self.assertFalse(score(answer("I would edit src/a.py"), {"edits_any": ["src/*"]})[0])

    def test_an_added_line_may_not_hold_the_text_and_a_removed_line_may_quote_it(self):
        expected = {"forbid_added": ["s3cret"]}
        self.assertTrue(score(answer("-KEY = 's3cret'\n+KEY = os.environ['KEY']"), expected)[0])
        self.assertFalse(score(answer("+KEY = 's3cret'"), expected)[0])
        self.assertTrue(score(answer("+++ b/s3cret.py"), expected)[0])


class LabelledLineTests(unittest.TestCase):
    EXPECTED = {"lines": {"Cause": {"any": [["config", "canary"]], "forbid": ["priya"]}}}

    def test_a_labelled_line_must_exist_and_hold_what_the_case_asks(self):
        cases = {
            "right": ("Cause: the config tool took a bad host.", True),
            "the person is the cause": ("Cause: Priya skipped the checklist, and the config tool allowed it.", False),
            "no such line": ("Root cause: the config tool took a bad host.", False),
            "the right words on another line": ("The config tool is why.\nCause: carelessness.", False),
            "bold": ("**Cause:** a canary stage is missing.", True),
        }
        for name, (body, passes) in cases.items():
            with self.subTest(name):
                self.assertEqual(score(answer(body), self.EXPECTED)[0], passes)


class DelegateAnswerTests(unittest.TestCase):
    EXPECTED = {"answer_is": {"outcome": "defer", "action": "spec.approve", "head": "4b1d2c3e5f60"}, "reason_any": [["every customer*", "A2"]]}

    def test_the_answer_is_the_call_or_the_object_not_the_words_around_it(self):
        right = (
            'delegate_answer(outcome="defer", action="spec.approve", head="4b1d2c3", reason="A2 exports every customer")',
            'delegate_answer {"outcome":"defer","action":"spec.approve","head":"4b1d2c3e5f60","reason":"A2 is not asked for"}',
            "delegate_answer(outcome='Defer', action='spec.approve', head='4b1d2c3', reason='A2, with a (paren) in it')",
        )
        wrong = (
            'delegate_answer {"outcome":"accept","action":"spec.approve","head":"4b1d2c3","reason":"no cause for outcome defer, A2"}',
            'delegate_answer(outcome="accept", action="spec.approve", head="4b1d2c3", reason="A2; outcome: defer is not needed")',
            'delegate_answer(outcome="defer", action="pr.merge", head="4b1d2c3", reason="A2")',
            'delegate_answer(outcome="defer", action="spec.approve", head="deadbee", reason="A2")',
            'delegate_answer(outcome="defer", action="spec.approve", head="4b1d2c3", reason="looks fine")',
            "I would defer this Spec.",
        )
        for text in right:
            with self.subTest(text):
                self.assertEqual(score(text, self.EXPECTED, decisions=None, handoff=False), (True, []))
        for text in wrong:
            with self.subTest(text):
                self.assertFalse(score(text, self.EXPECTED, decisions=None, handoff=False)[0])

    def test_the_call_is_read_however_its_fields_are_written(self):
        """Smoke baseline 0: r67 wrote `delegate_answer({...})`, read as no fields, so a formatting slip scored as a wrong defer."""
        fields = {"outcome": "defer", "action": "spec.approve", "head": "4b1d2c3", "reason": "A2"}
        cases = {
            "keywords": ('delegate_answer(outcome="defer", action="spec.approve", head="4b1d2c3", reason="A2")', fields),
            "a JSON object after the name": ('delegate_answer {"outcome":"defer","action":"spec.approve","head":"4b1d2c3","reason":"A2"}', fields),
            "one dict argument": ('delegate_answer({"outcome": "defer", "action": "spec.approve", "head": "4b1d2c3", "reason": "A2"})', fields),
            "one Python dict argument": ("delegate_answer({'outcome': 'defer', 'action': 'spec.approve', 'head': '4b1d2c3', 'reason': 'A2'})", fields),
            "one JSON argument with a null": ('delegate_answer({"outcome": "defer", "note": null})', {"outcome": "defer", "note": None}),
            "a dict and keywords": ('delegate_answer({"outcome": "defer"}, head="4b1d2c3")', {"outcome": "defer", "head": "4b1d2c3"}),
            "no fields, then a list": ("delegate_answer()\n- outcome: defer\n- action: spec.approve", {}),
            "an argument that is no dict": ('delegate_answer(["defer"])', {}),
            "a JSON value in a keyword": ('delegate_answer(outcome="defer", ok=true, note=null)', {"outcome": "defer", "ok": True, "note": None}),
            "a key no dict can hold": ('delegate_answer({["outcome"]: "defer"})', None),
            "an empty call beside a full one": (
                'Call delegate_answer() as:\ndelegate_answer(outcome="defer", action="spec.approve", head="4b1d2c3", reason="A2")',
                fields,
            ),
            "no call": ("I would defer this Spec.", None),
        }
        for name, (text, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(scoring.delegate_answer(text), want)

    def test_a_call_with_no_fields_is_its_own_miss_not_a_wrong_outcome(self):
        cases = {
            "one dict argument": ('delegate_answer({"outcome": "defer", "action": "spec.approve", "head": "4b1d2c3", "reason": "A2"})', []),
            "no fields": ("delegate_answer()\n- outcome: defer\n- action: spec.approve", ["no fields found in the delegate_answer call"]),
            "no call": ("I would defer this Spec.", ["no delegate_answer call"]),
        }
        for name, (text, misses) in cases.items():
            with self.subTest(name):
                self.assertEqual(score(text, self.EXPECTED, decisions=None, handoff=False), (not misses, misses))

    def test_two_different_calls_are_a_hedge(self):
        text = 'delegate_answer(outcome="defer", action="spec.approve")\ndelegate_answer(outcome="accept", action="spec.approve")'
        self.assertEqual(scoring.delegate_answer(text), {"hedged": True})
        self.assertEqual(scoring.delegate_answer(text.splitlines()[0] + "\n" + text.splitlines()[0])["outcome"], "defer")


class SeveralChoicesTests(unittest.TestCase):
    def test_a_case_may_accept_more_than_one_decision_and_all_its_edits(self):
        expected = {"decision": ["act", "ask"], "edits_all": ["tests/unit/*", "src/a.py"], "forbid_edits": ["tests/acceptance/*"]}
        diff = "+++ b/tests/unit/test_a.py\n+x\n+++ b/src/a.py\n+y"
        self.assertTrue(score(answer(diff, "ask"), expected)[0])
        self.assertTrue(score(answer(diff, "act"), expected)[0])
        self.assertFalse(score(answer(diff, "stop"), expected)[0])
        self.assertFalse(score(answer("+++ b/src/a.py\n+y"), expected)[0])
        self.assertFalse(score(answer(diff + "\n+++ b/tests/acceptance/test_a.py\n+z"), expected)[0])


class RolePromptTests(unittest.TestCase):
    CASE = {"role": "reviewer", "prompt": "Review it.", "fixture": "x = 1", "decisions": ["block", "pass"]}

    def test_the_prompt_asks_for_the_six_field_note_and_one_decision_with_its_meaning(self):
        for material in (True, False):
            with self.subTest(material=material):
                text = suites.role_prompt(self.CASE, material=material)
                self.assertIn("Done, Next role, Needs, Stopped at, By, Spend", text)
                self.assertIn("`Decision: <value>`, where the value is one of block, pass", text)
                self.assertIn("block: you found something that must change before the work goes on", text)

    def test_a_case_with_no_decisions_asks_for_none(self):
        self.assertNotIn("Decision", suites.role_prompt(dict(self.CASE, decisions=None)))

    def test_an_agent_that_declares_the_wrong_decision_fails_the_case_whatever_else_it_says(self):
        agent = "import sys\nsys.stdin.read()\nprint('Looks fine.\\nDone: x\\nNext role: y\\nNeeds: none\\nStopped at: none\\nBy: reviewer\\nSpend: unknown\\nDecision: pass')\n"
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "agent.py").write_text(agent, encoding="utf-8")
            Path(tmp, "roles").mkdir()
            Path(tmp, "roles", "s.yaml").write_text(
                "scenario:\n  - id: r1\n    role: reviewer\n    decisions: [block, pass]\n    prompt: Review it.\n    fixture: x = 1\n    expected: {decision: block}\n",
                encoding="utf-8",
            )
            (result,) = suites.run_roles(Path(tmp, "roles"), f"{sys.executable} {Path(tmp, 'agent.py')}")
        self.assertEqual((result["ok"], result["misses"]), (False, ["the decision is 'pass', wanted 'block'"]))


LISTING_AGENT = """
import json, os, sys
sys.stdin.read()
here = os.getcwd()
found = sorted(os.path.relpath(os.path.join(d, f), here) for d, _, fs in os.walk(here) for f in fs)
print(json.dumps({"route": "minor", "reason": json.dumps({"cwd": here, "files": found})}))
"""


class AnswerLeakTests(unittest.TestCase):
    """A routing or role trial runs in an empty folder, so an agent with file tools cannot read the expected answers in the checkout."""

    def run_one(self, suite, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "agent.py").write_text(LISTING_AGENT, encoding="utf-8")
            folder = Path(tmp, suite)
            folder.mkdir()
            case = "scenario:\n  - id: s1\n    situation: x\n    expected: {route: minor}\n"
            role = "scenario:\n  - id: r1\n    role: reviewer\n    decisions: [block, pass]\n    prompt: p\n    fixture: f\n    expected: {decision: block}\n"
            Path(folder, "s.yaml").write_text(case if suite == "routing" else role, encoding="utf-8")
            seen = []
            real = suites._answer

            def spy(cmd, prompt, timeout_seconds, cwd=None):
                answer = real(cmd, prompt, timeout_seconds, cwd)
                seen.append(answer[0])
                return answer

            with mock.patch.object(suites, "_answer", spy):
                run = suites.run_routing if suite == "routing" else suites.run_roles
                run(folder, f"{sys.executable} {Path(tmp, 'agent.py')}", **kw)
            return json.loads(json.loads(seen[0])["reason"])

    def test_a_routing_trial_runs_in_an_empty_folder_outside_the_checkout(self):
        for kw in ({}, {"material": False}):
            with self.subTest(kw):
                listing = self.run_one("routing", **kw)
                self.assertEqual(listing["files"], [])
                self.assertFalse(Path(listing["cwd"]).exists(), "the folder is removed after the trial")
                self.assertNotEqual(Path(listing["cwd"]).resolve(), Path.cwd().resolve())

    def test_a_no_embed_trial_gets_the_skill_and_nothing_else(self):
        listing = self.run_one("routing", embed=False)
        self.assertIn(".agents/skills/aidd/SKILL.md", listing["files"])
        self.assertIn(".agents/skills/aidd/references/routes.md", listing["files"])
        self.assertEqual([f for f in listing["files"] if not f.startswith(".agents/skills/aidd/")], [])
        self.assertEqual(self.run_one("routing", embed=False, material=False)["files"], [], "the control has no skill to find")

    def test_a_role_trial_runs_in_an_empty_folder_too(self):
        self.assertEqual(self.run_one("roles")["files"], [])


class OwnWordsTests(unittest.TestCase):
    def test_a_line_copied_from_the_prompt_scores_nothing(self):
        self.assertEqual(scoring.own_words("kept\ncopied line\n", "copied line\nother"), "kept")


if __name__ == "__main__":
    unittest.main()
