"""REVIEW.md: the review policy `aidd init` writes once, and the reviewer and `/aidd-team:review` follow."""

import tempfile
import tomllib
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import repo, resources

TEAM = ROOT / "plugins" / "aidd-team"
TEMPLATE = resources.data_dir("templates") / "REVIEW.md"


def init(root: Path, **kw) -> list[str]:
    return repo.init(root, profile="solo", ci="none", links=[], skill=False, harnesses=[], approvers=["@me"], **kw)


class TemplateTests(unittest.TestCase):
    def test_the_template_states_the_policy(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        for pass_ in ("**Bugs.**", "**Security.**", "**Conformance.**"):
            self.assertIn(pass_, text)
        self.assertIn("Acceptance", text.split("**Conformance.**", 1)[1].split("\n\n", 1)[0])
        severity = text.split("## Severity", 1)[1].split("\n## ", 1)[0]
        for level in ("Critical", "High", "Medium", "Low", "Nit"):
            self.assertIn(f"| {level} |", severity)
        critical = next(ln for ln in severity.splitlines() if ln.startswith("| Critical |"))
        for reserved in ("breaks behavior", "leaks data", "breaches a policy"):
            self.assertIn(reserved, critical)
        self.assertIn("at most 5 nits", text)
        self.assertIn("as a count", text)
        out = text.split("## Out of scope", 1)[1]
        self.assertIn("Generated files", out)
        self.assertIn("CI already enforces", out)
        self.assertIn("never approve", text)
        self.assertIn(" is a person's decision", text)
        # A generated-block marker in the template would make gen-docs treat an adopter's copy as ours.
        self.assertNotIn("<!-- aidd:gen", text)

    def test_the_wheel_ships_the_templates_folder(self):
        wheel = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]["wheel"]
        self.assertEqual(wheel["sources"]["templates"], "aidd/_data/templates")
        self.assertIn("templates", wheel["only-include"])


class InitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_init_writes_it_once_and_never_replaces_it(self):
        actions = init(self.root)
        policy = self.root / "REVIEW.md"
        self.assertEqual(policy.read_text(encoding="utf-8"), TEMPLATE.read_text(encoding="utf-8"))
        self.assertTrue(any(a.startswith("wrote") and a.endswith("REVIEW.md") for a in actions))
        policy.write_text("# Our review policy\n", encoding="utf-8")
        actions = init(self.root, force=True)
        self.assertEqual(policy.read_text(encoding="utf-8"), "# Our review policy\n")
        self.assertTrue(any(a.startswith("kept") and "REVIEW.md" in a for a in actions))

    def test_an_existing_policy_is_kept(self):
        (self.root / "REVIEW.md").write_text("mine\n", encoding="utf-8")
        init(self.root)
        self.assertEqual((self.root / "REVIEW.md").read_text(encoding="utf-8"), "mine\n")

    def test_uninstall_removes_it_unchanged_and_keeps_it_edited(self):
        init(self.root)
        repo.uninstall(self.root, yes=True)
        self.assertFalse((self.root / "REVIEW.md").exists())
        init(self.root)
        (self.root / "REVIEW.md").write_text(
            (self.root / "REVIEW.md").read_text(encoding="utf-8") + "\n- src/billing needs a second reader.\n", encoding="utf-8"
        )
        actions = repo.uninstall(self.root, yes=True)
        self.assertTrue((self.root / "REVIEW.md").is_file())
        self.assertTrue(any(a.startswith("kept") and "REVIEW.md" in a for a in actions))


class ReviewerTests(unittest.TestCase):
    def test_the_reviewer_and_the_review_command_follow_it(self):
        self.assertIn("REVIEW.md", resources.roles()["roles"]["reviewer"]["does"])
        playbook = (TEAM / "agents" / "reviewer.md").read_text(encoding="utf-8").split("## Playbook", 1)[1]
        self.assertIn("REVIEW.md", playbook)
        self.assertIn("never widens what you may do", playbook)
        command = (TEAM / "commands" / "review.md").read_text(encoding="utf-8")
        self.assertIn("`REVIEW.md` at the repository root", command)
        self.assertIn("five nits", command)
        self.assertIn("Never approve", command)


if __name__ == "__main__":
    unittest.main()
