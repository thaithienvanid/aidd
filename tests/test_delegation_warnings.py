"""What the delegation warns about and still allows: a `review_due` far ahead, and a delegate that runs on the author's
model. Invariant: a warning never changes the check's outcome, so a delegation set on purpose this way still works, and the
person is told the cost. Both only ever add a line."""

import datetime as dt
import tempfile
import unittest
from pathlib import Path

from helpers import aidd_subprocess, git, hermetic_environ
from test_delegation_check import Case, codes, config_text, note

from aidd import config
from aidd.config import project

TODAY = dt.date(2026, 11, 11)


def due(days: int) -> str:
    return (TODAY + dt.timedelta(days=days)).isoformat()


class ReviewDueTests(unittest.TestCase):
    def test_a_review_date_past_the_horizon_warns_and_one_inside_it_does_not(self):
        horizon = project.DELEGATION_REVIEW_HORIZON_DAYS
        cases = {
            "init's own 90 days": (90, False),
            "one day before the horizon": (horizon - 1, False),
            "the horizon": (horizon, False),
            "one day past it": (horizon + 1, True),
            "far ahead": (3000, True),
            "today": (0, False),
            "already past, which the check itself defers on": (-5, False),
        }
        for name, (days, warns) in cases.items():
            with self.subTest(name):
                warning = config.delegation_review_warning({"review_due": due(days)}, TODAY)
                self.assertEqual(warning is not None, warns)
                if warns:
                    self.assertIn(due(days), warning)
        for name, delegation in {
            "no date": {},
            "a date that is no date": {"review_due": "soon"},
            "a timestamp": {"review_due": "2099-01-01T00:00:00Z"},
        }.items():
            with self.subTest(name):
                self.assertEqual(config.delegation_review_warning(delegation, TODAY) is not None, name == "a timestamp")

    def test_validate_warns_about_a_far_date_and_says_nothing_of_an_ordinary_one(self):
        far = config.load_text(config_text(review_due="2099-01-01"))
        near = config.load_text(config_text(review_due=due(90)))
        self.assertEqual([w for w in project.project_findings(far, TODAY)[1] if "review_due" in w][0][:18], "delegation.review_")
        self.assertEqual(project.project_findings(near, TODAY), ([], []))


class DelegationStillWorksTests(Case):
    def change(self, repo, trailer: str | None = None) -> str:
        repo.write("src/app.py", "print('hello, world')\n")
        code = repo.commit("Say hello to the world", *(["-m", trailer] if trailer else []))
        head = repo.commit("Hand off", "-m", note(code))
        git(self.root, "checkout", "-q", "main")
        return head

    def test_a_far_review_date_set_on_purpose_still_delegates_and_the_check_says_what_it_costs(self):
        repo = self.repo(review_due="2099-01-01")
        result = repo.check(self.change(repo))
        self.assertEqual((result["outcome"], codes(result)), ("eligible", []))
        self.assertTrue(any("review_due" in w for w in result["warnings"]))

    def test_the_command_prints_the_warning_beside_the_answer(self):
        repo = self.repo(review_due="2099-01-01")
        head = self.change(repo)
        out = aidd_subprocess(
            "delegate",
            "check",
            "--action",
            "git.merge",
            "--command",
            f"git merge --no-ff {head}",
            "--head",
            head,
            cwd=self.root,
            env={**hermetic_environ(), "CLAUDECODE": "1"},
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("warning: delegation.review_due", out.stdout)

    def test_a_delegate_on_the_authors_model_warns_and_still_answers(self):
        """Honest case: one person with one model has no other to name. The check warns, never refuses (decision 2)."""
        cases = {
            "the same model": ("anthropic/claude-opus-5-5", "Assisted-by: claude-code/claude-opus-5-5", True),
            "the same model in another case": ("anthropic/Claude-Opus-5-5", "Assisted-by: claude-code/claude-opus-5-5", True),
            "another model": ("anthropic/claude-sonnet-5-5", "Assisted-by: claude-code/claude-opus-5-5", False),
            "another provider": ("openai/gpt-5", "Assisted-by: claude-code/claude-opus-5-5", False),
            "the session's model, which aidd cannot see": ("inherit", "Assisted-by: claude-code/claude-opus-5-5", False),
            "no model set": (None, "Assisted-by: claude-code/claude-opus-5-5", False),
            "no Assisted-by on the commits": ("anthropic/claude-opus-5-5", None, False),
            "an Assisted-by with no model": ("anthropic/claude-opus-5-5", "Assisted-by: claude-code", False),
        }
        for name, (delegate, trailer, warns) in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as d:
                self.root = Path(d).resolve()
                repo = self.repo(top=f"agents:\n  models:\n    delegate: {delegate}\n" if delegate else "")
                result = repo.check(self.change(repo, trailer))
                self.assertEqual((result["outcome"], codes(result)), ("eligible", []))
                self.assertEqual(any("weaker second look" in w for w in result["warnings"]), warns)


if __name__ == "__main__":
    unittest.main()
