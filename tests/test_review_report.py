"""A review sees both directions and says how it knows (R12): the closed values of a finding's fields live in schemas/roles.json,
the reviewer and the security engineer carry them, every report keeps its verdict and one line per finding together at its
head so a cut-off report still holds them, and no role clears a scratch folder with `rm -rf`.

The invariants:
- every review report gives, for each finding, one closed value of `question`, `origin`, and `shown`, and a verdict whose counts
  equal the lines (`scoring.review_report_misses`, no model);
- cutting a report anywhere after its finding lines leaves the verdict and every finding;
- the developer and the verifier carry the scratch rule, and no role file or the skill tells an agent to run `rm -rf` or to
  remove a worktree.
"""

import copy
import random
import re
import unittest

from helpers import ROOT

from aidd.docsgen import generate
from aidd.evals import scoring
from aidd.kernel import json_schema, resources
from aidd.knowledge import team_registry

TEAM = ROOT / "plugins" / "aidd-team"
SKILL = ROOT / ".agents" / "skills" / "aidd" / "SKILL.md"
OUTPUT = TEAM / "skills" / "code-review" / "references" / "review-output.md"
POLICIES = (ROOT / "REVIEW.md", ROOT / "templates" / "REVIEW.md")
REPORT = team_registry.roles()["loop"]["review_report"]
FIELDS = REPORT["fields"]
SEVERITIES = REPORT["severity"]
REVIEWERS = ("reviewer", "security-engineer")


def read(path) -> str:
    return path.read_text(encoding="utf-8")


def agent_text(key: str) -> str:
    return read(TEAM / "agents" / f"{key}.md")


def with_preloaded(key: str) -> str:
    """The text a role starts with: its agent file and each skill it preloads."""
    parts = [agent_text(key)]
    for name in team_registry.roles()["roles"][key]["preload"]:
        parts.append(read(SKILL if name == "aidd" else TEAM / "skills" / name / "SKILL.md"))
    return "\n".join(parts)


def line(severity="High", question="blocks", origin="regression", shown="ran", where="src/parse.py:88", what="a finding") -> str:
    return f"{severity} | {question} | {origin} | {shown} | {where} | {what}"


def report(rows: list[str], verdict: str | None = None, before: tuple[str, ...] = ("claude-code/a-model",), after: str = "Detail follows.") -> str:
    """A report in the shape REVIEW.md gives, built from finding rows; the verdict counts what the rows carry."""
    cells = [[p.strip() for p in r.split("|", 5)] for r in rows]
    counts = {v: sum(v in c[1:3] for c in cells) for f in ("question", "origin") for v in FIELDS[f]}
    blocking = sum(c[0].lower() in ("critical", "high") for c in cells)
    said = verdict or f"Verdict: blocking {blocking}. " + ", ".join(f"{k} {v}" for k, v in counts.items()) + "."
    return "\n".join([*before, said, *(f"{i}. {r}" for i, r in enumerate(rows, 1)), "", after]) + "\n"


class ClosedValuesTests(unittest.TestCase):
    def test_the_fields_are_in_the_order_a_finding_line_gives_them(self):
        self.assertEqual(list(FIELDS), ["question", "origin", "shown"])
        self.assertEqual(list(FIELDS["question"]), ["lets through", "blocks"])
        self.assertEqual(list(FIELDS["origin"]), ["regression", "new gap", "older gap"])
        self.assertEqual(list(FIELDS["shown"]), ["ran", "read"])

    def test_the_schema_closes_the_shape(self):
        data = resources.load_json("roles.json")
        self.assertEqual(json_schema.validate(data, "roles.schema.json"), [])
        for name, broken in {
            "no severity": lambda d: d["loop"]["review_report"].pop("severity"),
            "no fields": lambda d: d["loop"]["review_report"].pop("fields"),
            "an empty meaning": lambda d: d["loop"]["review_report"]["fields"]["shown"].__setitem__("ran", ""),
            "an extra key": lambda d: d["loop"]["review_report"].__setitem__("extra", 1),
            "a duplicate severity": lambda d: d["loop"]["review_report"]["severity"].append("High"),
        }.items():
            with self.subTest(name):
                bad = copy.deepcopy(data)
                broken(bad)
                self.assertNotEqual(json_schema.validate(bad, "roles.schema.json"), [])

    def test_the_severities_are_the_ranks_of_the_policy(self):
        for path in POLICIES:
            with self.subTest(path.relative_to(ROOT).as_posix()):
                table = read(path).split("## Severity", 1)[1].split("\n## ", 1)[0]
                ranks = re.findall(r"^\| (Critical|High|Medium|Low|Nit) \|", table, re.M)
                self.assertEqual(ranks, [s for s in SEVERITIES if s != "needs validation"])

    def test_the_reference_table_is_the_data(self):
        table = generate.render("roles:review-report")
        self.assertIn(table, read(OUTPUT))
        for field, values in FIELDS.items():
            for value, meaning in values.items():
                self.assertIn(f"| `{field}` | `{value}` | {meaning} |", table)

    def test_the_policy_gives_the_same_values(self):
        for path in POLICIES:
            section = read(path).split("## Report", 1)[1].split("\n## ", 1)[0]
            for field, values in FIELDS.items():
                self.assertIn(f"`{field}`", section, path.name)
                for value in values:
                    self.assertIn(f"`{value}`", section, f"{path.name}: {field} {value}")


class RolesCarryBothDirectionsTests(unittest.TestCase):
    def rule(self) -> str:
        found = [x for x in resources.load_json("roles.json")["loop"]["contract"] if isinstance(x, dict) and "`lets through`" in x["rule"]]
        self.assertEqual(len(found), 1)
        return found[0]["rule"]

    def test_the_reviewer_and_the_security_engineer_carry_the_rule_and_no_other_role_does(self):
        carriers = [k for k in team_registry.roles()["order"] if self.rule() in agent_text(k)]
        self.assertEqual(carriers, sorted(REVIEWERS, key=team_registry.roles()["order"].index))

    def test_each_carries_both_questions_the_fields_and_the_size_of_the_head(self):
        for key in REVIEWERS:
            with self.subTest(key):
                text = agent_text(key)
                for question in FIELDS["question"]:
                    self.assertIn(f"`{question}`", text)
                for field in FIELDS:
                    self.assertIn(f"`{field}`", text)
                self.assertIn("under 300 words", text)

    def test_the_reference_it_names_holds_every_value_and_an_example_that_passes_the_check(self):
        text = read(OUTPUT)
        for values in FIELDS.values():
            for value in values:
                self.assertIn(f"`{value}`", text)
        for key in REVIEWERS:
            self.assertIn("references/review-output.md", agent_text(key))
        self.assertIn("references/review-output.md", read(TEAM / "skills" / "code-review" / "SKILL.md"))
        merge = read(TEAM / "commands" / "review.md").split("$ARGUMENTS", 1)[1].split("\n5. ", 1)[1].split("\n6. ", 1)[0]
        self.assertIn("references/review-output.md", merge, "the lead's merged report keeps the same head")

    def test_the_reviewer_cannot_write_so_the_rule_is_the_shape_alone(self):
        tools = re.search(r"^tools: (.+)$", agent_text("reviewer"), re.M).group(1)
        self.assertFalse({"Write", "Edit"} & set(re.split(r",\s*", tools)))
        self.assertIn("You write no file", " ".join(team_registry.shared_rules_for("reviewer")))
        self.assertNotIn("scratch", self.rule())


class ScratchRuleTests(unittest.TestCase):
    def test_the_developer_and_the_verifier_make_a_new_scratch_folder_and_name_a_literal_target(self):
        for key in ("developer", "verifier"):
            with self.subTest(key):
                text = with_preloaded(key)
                for must in ("mktemp -d", "never reuse", "literal path"):
                    self.assertIn(must, text.lower())

    def test_no_role_file_or_the_skill_tells_an_agent_to_clear_a_folder_or_remove_a_worktree(self):
        pages = [*sorted((TEAM / "agents").glob("*.md")), SKILL]
        for page in pages:
            for sentence in re.split(r"(?<=[.;:])\s+|\n", read(page)):
                with self.subTest(page=page.name, sentence=sentence[:60]):
                    if "rm -rf" in sentence:
                        self.assertRegex(sentence, r"(?i)\b(never|no)\b")
                    self.assertNotIn("worktree remove", sentence)


ROWS = [line(), line("Medium", "lets through", "older gap", "read"), line("Low", "blocks", "new gap", "ran"), line("Nit", "lets through", "regression", "ran")]


class ReportShapeTests(unittest.TestCase):
    """`review_report_misses` over the input space: none, one, many findings; each field out of its set; the boundaries."""

    def misses(self, text: str) -> list[str]:
        return scoring.review_report_misses(text)

    def test_honest_reports_pass(self):
        cases = {
            "no findings, all zero": report([]),
            "one finding": report(ROWS[:1]),
            "many findings": report(ROWS),
            "a model line before the verdict": report(ROWS[:2], before=("claude-code/a-model", "Model: an anonymous caller controls the path")),
            "bold verdict": report(ROWS[:1]).replace("Verdict:", "**Verdict:**"),
            "bullets": report(ROWS[:1]).replace("\n1. ", "\n- "),
            "paren numbers": report(ROWS[:1]).replace("\n1. ", "\n1) "),
            "lower-case severity": report([line("high")]),
            "needs validation, no severity": report([line("needs validation", "lets through", "older gap", "read")]),
            "a read High with its input and test": report([line("High", "lets through", "new gap", "read", what="input: `a=b`; test: none yet")]),
            "extra spaces": report(ROWS[:1]).replace(" | ", "  |  "),
            "no detail at all": report(ROWS[:1], after="").rstrip("\n") + "\n",
        }
        for name, text in cases.items():
            with self.subTest(name):
                self.assertEqual(self.misses(text), [])

    def test_each_defect_is_named(self):
        base = report(ROWS[:2])
        cases = {
            "no verdict": (base.replace("Verdict:", "Summary:"), "no `Verdict:` line"),
            "the verdict too late": (report(ROWS[:1], before=("a", "b", "c")), "no `Verdict:` line"),
            "an empty answer": ("", "no `Verdict:` line"),
            "a question outside the set": (report([line(question="maybe")]), "question 'maybe'"),
            "an origin outside the set": (report([line(origin="new")]), "origin 'new'"),
            "a shown outside the set": (report([line(shown="guessed")]), "shown 'guessed'"),
            "a severity outside the set": (report([line(severity="Severe")]), "severity 'Severe'"),
            "no file and line": (report([line(where="the parser")]), "not a file:line"),
            "too few parts": (report(["High | blocks | regression"]), "of 6 parts"),
            "a read High with no input or test": (report([line("High", "blocks", "regression", "read")]), "needs 'input:'"),
            "a read Critical with no test": (report([line("Critical", "blocks", "regression", "read", what="input: x")]), "needs 'test:'"),
            "a count that is wrong": (base.replace("lets through 1", "lets through 2"), "says lets through 2, the lines carry 1"),
            "a count that is missing": (base.replace(", blocks 1", ""), "no count for 'blocks'"),
            "a blocking count that is wrong": (base.replace("blocking 1", "blocking 0"), "says blocking 0, the lines carry 1"),
            "a finding after the detail": (base + "2. Low | blocks | new gap | ran | src/a.py:1 | late\n", "after the detail began"),
        }
        for name, (text, expected) in cases.items():
            with self.subTest(name):
                self.assertTrue(any(expected in m for m in self.misses(text)), self.misses(text))

    def test_the_head_is_under_300_words_and_the_detail_has_no_limit(self):
        def head_words(pad: int) -> int:
            text = report([line(what=" ".join(["word"] * pad))])
            return len(text.split("\n\n")[0].split("\n", 1)[1].split())

        base = head_words(1) - 1  # the words around the padding
        for total, ok in ((150, True), (298, True), (299, True), (300, False), (301, False), (400, False)):
            with self.subTest(head_words=total):
                text = report([line(what=" ".join(["word"] * (total - base)))])
                self.assertEqual(head_words(total - base), total)
                self.assertEqual(self.misses(text) == [], ok)
        self.assertEqual(self.misses(report(ROWS[:1], after="detail " * 2000)), [])

    def test_a_report_cut_anywhere_after_its_finding_lines_still_passes(self):
        text = report(ROWS, after="Detail, finding by finding. " * 40)
        head_end = text.index("\n\n") + 1
        for cut in range(head_end, len(text) + 1, 7):
            with self.subTest(cut=cut):
                self.assertEqual(self.misses(text[:cut]), [])
        self.assertNotEqual(self.misses(text[: text.index("2. ")]), [], "a cut inside the head loses a count the verdict gave")

    def test_a_generated_set_of_reports_agrees_with_the_counts(self):
        rng = random.Random(12)
        for n in range(60):
            rows = [
                line(rng.choice(SEVERITIES[:5]), rng.choice(list(FIELDS["question"])), rng.choice(list(FIELDS["origin"])), "ran", f"src/m{i}.py:{i + 1}")
                for i in range(rng.randint(0, 9))
            ]
            text = report(rows)
            with self.subTest(n=n, findings=len(rows)):
                self.assertEqual(self.misses(text), [])
                if rows:
                    spoiled = text.replace(f"blocks {sum('| blocks |' in r for r in rows)}", "blocks 99", 1)
                    self.assertNotEqual(self.misses(spoiled), [])

    def test_the_examples_in_the_policy_and_the_reference_pass(self):
        for path in POLICIES:
            block = re.search(r"```text\n(Verdict:.*?)\n```", read(path), re.S)
            self.assertIsNotNone(block, path.name)
            self.assertEqual(self.misses("claude-code/a-model\n" + block.group(1)), [], path.name)
        after = re.findall(r"^\| [^|]+ \| (`.*`) \|$", read(OUTPUT).split("| Before | After |", 1)[1], re.M)
        self.assertEqual(len(after), 2)
        example = "\n".join(x.strip("`").replace("\\|", "|") for x in after)
        self.assertEqual(self.misses(example), [])

    def test_an_eval_case_asks_for_the_shape_by_one_key(self):
        good, bad = report(ROWS[:1]), "Do not merge: this has serious problems."
        self.assertEqual(scoring.score_role(good, {"review_report": True}), (True, []))
        ok, misses = scoring.score_role(bad, {"review_report": True})
        self.assertFalse(ok)
        self.assertTrue(misses)
        self.assertEqual(scoring.score_role(bad, {}), (True, []), "a case that does not ask for the shape never fails on it")
        self.assertIn("review_report", scoring.EXPECTED_KEYS)


if __name__ == "__main__":
    unittest.main()
