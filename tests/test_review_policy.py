"""REVIEW.md: the review policy `aidd init` writes once, and the reviewer and `/aidd-team:review` follow."""

import re
import tempfile
import tomllib
import unittest
from pathlib import Path

from helpers import ROOT

from aidd.setup import uninstalling
from aidd.setup import adoption
from aidd.kernel import resources
from aidd.knowledge import team_registry

TEAM = ROOT / "plugins" / "aidd-team"
TEMPLATE = resources.data_dir("templates") / "REVIEW.md"
POLICY = ROOT / "REVIEW.md"
# The sections each repository fills for itself: its dismissals and its notes. Every other section is the template's.
OWN_SECTIONS = ("Dismissed findings", "Repository notes")


def sections(text: str) -> dict[str, str]:
    """The `## ` sections of a policy, by heading, and the text before the first one under the key ''."""
    parts = re.split(r"^## (.+)$", text, flags=re.MULTILINE)
    return {"": parts[0], **dict(zip(parts[1::2], parts[2::2], strict=True))}


def init(root: Path, **kw) -> list[str]:
    return adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], skill=False, harnesses=[], approvers=["@me"], **kw))


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
        self.assertIn("CI already checks", out)
        self.assertIn("never approve", text)
        self.assertIn(" is a person's decision", text)
        # A generated-block marker in the template would make gen-docs treat an adopter's copy as ours.
        self.assertNotIn("<!-- aidd:gen", text)

    def test_this_repository_keeps_every_shared_section_of_the_template(self):
        """The repository's policy starts from the template, so a rule one holds and the other lacks is drift."""
        template, own = sections(TEMPLATE.read_text(encoding="utf-8")), sections(POLICY.read_text(encoding="utf-8"))
        shared = [name for name in template if name and name not in OWN_SECTIONS]
        self.assertGreater(len(shared), 6)
        self.assertEqual([name for name in own if name and name not in OWN_SECTIONS], shared)
        for name in shared:
            self.assertEqual(own[name], template[name], f"REVIEW.md and templates/REVIEW.md differ in `## {name}`")
        for name in OWN_SECTIONS:
            self.assertIn(name, own)
            self.assertIn(name, template)

    def test_the_wheel_ships_the_templates_folder(self):
        wheel = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]["wheel"]
        self.assertEqual(wheel["sources"]["templates"], "aidd/_data/templates")
        self.assertIn("templates", wheel["only-include"])


class SeverityOwnerTests(unittest.TestCase):
    """REVIEW.md owns what each severity means, and the skill's security table never ranks a class lower than it."""

    # A class the rubric reserves for Critical, and the phrases the skill's table uses for it.
    RESERVED = {"leaks data": ("another tenant's data", "a secret", "data store")}

    def table(self, text: str) -> dict[str, str]:
        rows = (line.strip("| ").split(" | ", 1) for line in text.splitlines() if line.startswith("| "))
        return {rank: meaning for rank, meaning in rows if rank in ("Critical", "High", "Medium", "Low", "Nit")}

    def test_no_class_the_rubric_reserves_for_critical_sits_lower_in_the_skill(self):
        rubric = self.table(TEMPLATE.read_text(encoding="utf-8"))
        skill = self.table((TEAM / "skills" / "code-review" / "references" / "security-findings.md").read_text(encoding="utf-8"))
        self.assertEqual(sorted(skill), ["Critical", "High", "Low", "Medium"])
        for named, phrases in self.RESERVED.items():
            self.assertIn(named, rubric["Critical"])
            for phrase in phrases:
                self.assertIn(phrase, skill["Critical"])
                for lower in ("High", "Medium", "Low"):
                    self.assertNotIn(phrase, skill[lower], f"`{phrase}` ranks {lower} in the skill, and Critical in REVIEW.md")


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
        uninstalling.uninstall(self.root, yes=True)
        self.assertFalse((self.root / "REVIEW.md").exists())
        init(self.root)
        (self.root / "REVIEW.md").write_text(
            (self.root / "REVIEW.md").read_text(encoding="utf-8") + "\n- src/billing needs a second reader.\n", encoding="utf-8"
        )
        actions = uninstalling.uninstall(self.root, yes=True)
        self.assertTrue((self.root / "REVIEW.md").is_file())
        self.assertTrue(any(a.startswith("kept") and "REVIEW.md" in a for a in actions))


class ReviewerTests(unittest.TestCase):
    def test_the_reviewer_and_the_review_command_follow_it(self):
        self.assertIn("REVIEW.md", team_registry.roles()["roles"]["reviewer"]["does"])
        playbook = (TEAM / "agents" / "reviewer.md").read_text(encoding="utf-8").split("## Playbook", 1)[1]
        self.assertIn("REVIEW.md", playbook)
        self.assertIn("never widens what you may do", playbook)
        command = (TEAM / "commands" / "review.md").read_text(encoding="utf-8")
        self.assertIn("`REVIEW.md` at the repository root", command)
        self.assertIn("five nits", command)
        self.assertIn("Never approve", command)


if __name__ == "__main__":
    unittest.main()
