"""Each grader of the live suites is proven before a model runs: it fails a wrong sample, it reads like the live runner reads it, and a case with a wrong answer only a judge fails says so.

`claude plugin eval` grades a live run, which costs a model call, so a grader that passes a wrong answer or fails a right
one makes every score it adds meaningless. The sample tests (test_plugin_eval_samples, test_team_eval_samples) score stored
transcripts with the graders that need no model. This adds three rules over every case of both suites:

- A deterministic grader is caught: some wrong sample names it in `fails`, so it is shown to fail a wrong answer. A right sample
  and an alternative, written differently, pass it (the sample tests hold that).
- A regex means the same to the live runner as to these tests. The runner reads JavaScript, and the tests read Python.
- A case with a wrong sample that no deterministic grader fails carries the tag `grading:prose-only`, and no other case does,
  so the cases a model must judge are data and not a guess.
"""

import json
import re
import shutil
import subprocess
import unittest

from helpers import ROOT

from aidd import evals
from aidd.evals import suites
from test_plugin_eval_samples import DETERMINISTIC, PLUGIN
from test_plugin_eval_samples import graders as plugin_graders
from test_plugin_eval_samples import samples as plugin_samples
from test_plugin_evals import front_matter, written_triggers
from test_team_eval_samples import TEAM, non_trigger
from test_team_eval_samples import graders as team_graders
from test_team_eval_samples import samples as team_samples

JUDGE_NEEDED = "grading:judge-needed"
# What Python's `re` reads and JavaScript does not, or reads as something else.
NOT_JAVASCRIPT_ESCAPES = set("AZzhGHRXKpP")
FLAGS = set("im")  # the flags the sample tests score; the live runner also reads others


def plugin_cases() -> list[str]:
    return sorted(p.name for p in PLUGIN.iterdir() if p.is_dir() and p.name != "results")


def suite_entries():
    """(suite, case, the deterministic graders by name, the sample entry) for every case that keeps samples in samples.json."""
    for case in plugin_cases():
        yield "plugin", case, plugin_graders(case), plugin_samples()[case]
    for path in non_trigger():
        yield "team", path.name, team_graders(path), team_samples()[path.name]


def javascript_problems(pattern: str, flags: str = "") -> list[str]:
    """Each construct in a regex that Python reads and JavaScript does not: `\\A`, `\\Z`, an inline flag group, a Python named
    group, an atomic group, a possessive quantifier, or `$` for the end of the text when the `m` flag is off (Python also
    matches it before a final newline, JavaScript does not). A character class is skipped, where these are plain characters."""
    problems, i, in_class, after_quantifier = [], 0, False, False
    for extra in sorted(set(flags) - FLAGS):
        problems.append(f"flag {extra!r}: the tests score only {''.join(sorted(FLAGS))}")
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\":
            if not in_class and pattern[i + 1 : i + 2] in NOT_JAVASCRIPT_ESCAPES:
                problems.append(f"\\{pattern[i + 1]} at {i}: not an escape in JavaScript")
            i, after_quantifier = i + 2, False
            continue
        if in_class:
            in_class = ch != "]"
        elif ch == "[":
            in_class = True
        elif ch == "(" and pattern[i + 1 : i + 2] == "?":
            if not re.match(r"\?(?::|=|!|<=|<!|<[A-Za-z])", pattern[i + 1 :]):
                problems.append(f"{pattern[i : i + 4]!r} at {i}: a group JavaScript does not read")
        elif ch == "+" and after_quantifier:
            problems.append(f"possessive quantifier at {i}")
        elif ch == "$" and "m" not in flags:
            problems.append(f"$ at {i} with no m flag: use (?![\\s\\S]) for the end of the text")
        after_quantifier = not in_class and ch in "*+?}" and not (ch == "?" and pattern[i - 1 : i] == "(")
        i += 1
    return problems


def all_regexes():
    """(where, pattern, flags) for every regex in both suites, the generated trigger cases too."""
    for suite in (PLUGIN, TEAM):
        folders = [p for p in suite.iterdir() if p.is_dir() and p.name != "results"]
        if suite == TEAM:
            folders = [p for p in folders if not p.name.startswith(("loads-", "skips-", "held-out-"))] + [p for p in written_triggers().iterdir() if p.is_dir()]
        for case in folders:
            for path in sorted((case / "graders").glob("*.md")):
                g, _ = front_matter(path)
                if g["type"] == "regex":
                    yield f"{suite.name}/{case.name}/{path.stem}", g["pattern"], g.get("flags", "")
                for ref in (g, g.get("before"), g.get("after")):
                    if isinstance(ref, dict) and "input_match" in ref:
                        yield f"{suite.name}/{case.name}/{path.stem} input_match", ref["input_match"], ""


def regex_jobs(g: dict, sample: dict) -> list[tuple[str, str, str]]:
    """(pattern, flags, text) for each regex a deterministic grader applies to a sample: a regex grader on its target, and an input
    match on the JSON of each call of its tool."""
    from test_plugin_eval_samples import trace

    if g["type"] == "regex":
        target = g.get("target", "last_message")
        text = (
            "\n".join(sample.get("created", []))
            if target == "files"
            else sample["files"][target["path"]]
            if isinstance(target, dict)
            else trace(sample)
            if target == "trace"
            else sample["reply"]
        )
        return [(g["pattern"], g.get("flags", ""), text)]
    refs = [g] if g["type"] == "tool_used" else [g["before"], g["after"]] if g["type"] == "tool_order" else []
    return [
        (ref["input_match"], "", json.dumps(c["input"], ensure_ascii=False))
        for ref in refs
        if isinstance(ref, dict) and "input_match" in ref
        for c in sample["calls"]
        if c["tool"] == ref["tool"]
    ]


class GraderProofTests(unittest.TestCase):
    def test_every_deterministic_grader_is_caught_by_a_wrong_sample(self):
        """A grader no wrong sample fails is unproven: it might pass anything. A case with no sample at all fails the sample tests first."""
        unproven = []
        for suite, case, graders, entry in suite_entries():
            caught = {name for wrong in entry["wrong"] for name in wrong["fails"]}
            unproven += [f"{suite}/{case}: {name}" for name in graders if name not in caught]
        self.assertEqual(unproven, [], "add a wrong sample that fails each grader, or remove a grader nothing needs")

    def test_every_deterministic_grader_passes_the_right_sample_and_an_alternative(self):
        for suite, case, graders, entry in suite_entries():
            with self.subTest(f"{suite}/{case}"):
                self.assertGreaterEqual(len(entry.get("alternatives", [])), 1, "a second right answer, written differently")
                self.assertTrue(graders)
                self.assertTrue(set(graders) <= set(g for g in graders), case)
        self.assertEqual({g["type"] for _, _, graders, _ in suite_entries() for g in graders.values()} - DETERMINISTIC, set())

    def test_every_regex_reads_the_same_in_javascript_and_python(self):
        found = [f"{where}: {problem}" for where, pattern, flags in all_regexes() for problem in javascript_problems(pattern, flags)]
        self.assertEqual(found, [], "the live runner reads JavaScript: no \\A or \\Z, inline flags, Python groups, or $ without the m flag")

    def test_every_regex_matches_every_sample_alike_in_node_when_it_is_installed(self):
        """The live runner is a JavaScript program, so where Node is here, each regex grader and each input match is run on each
        sample text in both engines and must give one answer. This ran 6,000 checks with no difference when it was written."""
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node is not installed; test_every_regex_reads_the_same_in_javascript_and_python holds the syntax")
        jobs = []
        for _, _, graders, entry in suite_entries():
            for sample in [entry["right"], *entry["wrong"], *entry.get("alternatives", [])]:
                for g in graders.values():
                    jobs += regex_jobs(g, sample)
        python = [re.search(p, t, (re.I if "i" in f else 0) | (re.M if "m" in f else 0)) is not None for p, f, t in jobs]
        script = "const j=JSON.parse(require('fs').readFileSync(0,'utf8'));console.log(JSON.stringify(j.map(x=>new RegExp(x.p,x.f).test(x.t))))"
        out = subprocess.run(
            [node, "-e", script], input=json.dumps([{"p": p, "f": f, "t": t} for p, f, t in jobs]), capture_output=True, text=True, timeout=300
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual([jobs[i][0][:60] for i, (a, b) in enumerate(zip(python, json.loads(out.stdout), strict=True)) if a != b], [])

    def test_the_checker_finds_each_construct_javascript_reads_differently(self):
        cases = {
            "a plain pattern": (r"^status: approved$", "m", 0),
            "an anchor at the start": (r"\Afoo", "", 1),
            "an anchor at the end": (r"foo\Z", "", 1),
            "an inline flag": (r"(?i)foo", "", 1),
            "an inline flag group": (r"(?i:foo)", "", 1),
            "a Python named group": (r"(?P<x>foo)", "", 1),
            "an atomic group": (r"(?>foo)", "", 1),
            "a possessive quantifier": (r"a*+b", "", 1),
            "a lazy quantifier": (r"a*?b|a+?b|a??b|a{2}?b", "", 0),
            "a lookahead and a lookbehind": (r"(?=a)(?!b)(?<=c)(?<!d)e", "", 0),
            "a named group in JavaScript's spelling": (r"(?<x>foo)", "", 0),
            "a dollar with no m flag": (r"foo$", "", 1),
            "a dollar in a class": (r"[$]foo", "", 0),
            "an escaped dollar": (r"foo\$", "", 0),
            "a plus in a class after a star": (r"[*+]+", "", 0),
            "the end of the text": (r"foo(?![\s\S])", "", 0),
            "a flag the tests do not score": (r"foo", "s", 1),
            "a backslash then an A": (r"\\A", "", 0),
        }
        for name, (pattern, flags, count) in cases.items():
            with self.subTest(name):
                self.assertEqual(len(javascript_problems(pattern, flags)), count, javascript_problems(pattern, flags))

    def test_a_case_with_a_wrong_answer_only_a_judge_fails_says_so_and_no_other_does(self):
        marked, judged = set(), set()
        for suite, case, _, entry in suite_entries():
            tags = front_matter(ROOT / "evals" / suite / case / "prompt.md")[0]["tags"]
            if JUDGE_NEEDED in tags:
                marked.add(f"{suite}/{case}")
            if any(not wrong["fails"] for wrong in entry["wrong"]):
                judged.add(f"{suite}/{case}")
        self.assertEqual(
            (sorted(judged - marked), sorted(marked - judged)),
            ([], []),
            f"the first list has a wrong answer only a judge fails: add the tag {JUDGE_NEEDED} to its prompt. The second is tagged, and no wrong answer needs a judge",
        )

    def test_each_routing_case_accepts_its_right_answers_and_refuses_its_wrong_ones(self):
        """The routing grader is a route and the words of a reason. Each case has a right answer, one in other words where it scores
        its reason, and a wrong one: another route, or the right route with a reason that misses a group."""
        samples = json.loads((ROOT / "evals" / "routing" / "samples.json").read_text(encoding="utf-8"))
        samples.pop("_comment")
        cases = {sc["id"]: sc for sc in evals.load_scenarios(ROOT / "evals" / "routing")}
        self.assertEqual(list(samples), list(cases), "a sample set for each routing case, in the cases' order")
        for case_id, entry in samples.items():
            sc = cases[case_id]
            with self.subTest(case_id):
                self.assertTrue(entry["wrong"], "a wrong answer")
                for answer in [*entry["right"], *entry.get("alternatives", [])]:
                    self.assertTrue(suites.routing_verdict(sc, answer)["ok"], answer)
                for answer in entry["wrong"]:
                    self.assertFalse(suites.routing_verdict(sc, answer)["ok"], answer)
                if sc["expected"].get("reason_any"):
                    self.assertTrue(entry.get("alternatives"), "a case that scores its reason has a second right wording")

    def test_the_batched_merge_case_wants_the_final_merge_to_main_to_ask(self):
        """a18: `main` anywhere in the reason passed 'this merge needs no approval, and neither does the final merge to main'."""
        sc = next(c for c in evals.load_scenarios(ROOT / "evals" / "routing") if c["id"] == "c70-batched-intent-spec-merge")
        good = "This merge needs no approval, and the final merge to main asks."
        wrong = "This merge needs no approval, and neither does the final merge to main."
        self.assertTrue(suites.routing_verdict(sc, {"route": "normal", "reason": good})["ok"])
        self.assertFalse(suites.routing_verdict(sc, {"route": "normal", "reason": wrong})["ok"])

    def test_the_prose_only_tag_is_one_the_claim_reader_keeps(self):
        text = json.dumps(front_matter(ROOT / "evals" / "plugin" / "spec-before-code" / "prompt.md")[0]["tags"])
        self.assertIn("tier:smoke", text)


if __name__ == "__main__":
    unittest.main()
