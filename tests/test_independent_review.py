"""Independent review across providers (R76) and the security-guidance file (R211), both opt-in or Claude Code-only
advice that `aidd init --team` carries: the config key, the check where aidd sees the models, and the file it writes."""

import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import config
from aidd.kernel import resources
from aidd.setup import adoption, team_install, uninstalling

DEV, VER, REV = "developer", "verifier", "reviewer"


def adopted(root: Path, agents: str = "") -> None:
    adoption.init(root, adoption.InitOptions(profile="solo", ci="none", links=[], skill=False, harnesses=[], approvers=["@me"]))
    cfg = root / ".aidd" / "config.yaml"
    cfg.write_text(cfg.read_text(encoding="utf-8") + "\nagents:\n" + agents, encoding="utf-8")


class ProviderCheckTests(unittest.TestCase):
    CASES = [
        ("three providers", {DEV: "anthropic/claude-sonnet-5", VER: "openai/gpt-6", REV: "google/gemini-3"}, None),
        ("reviewer apart, verifier shares", {DEV: "anthropic/a", VER: "anthropic/b", REV: "openai/c"}, "the verifier runs on anthropic"),
        ("both share", {DEV: "openai/a", VER: "openai/b", REV: "openai/c"}, "the verifier and the reviewer run on openai"),
        ("a tier covers developer and verifier", {"execution": "openai/a", REV: "anthropic/c"}, "the verifier runs on openai"),
        ("unset models", {}, "the developer, the verifier, and the reviewer have no provider/model"),
        ("inherit is blind", {DEV: "inherit", VER: "openai/b", REV: "openai/c"}, "the developer has no provider/model"),
        ("only the reviewer is set", {REV: "openai/c"}, "the developer and the verifier have no provider/model"),
    ]

    def test_a_wired_harness_that_cannot_select_the_provider_is_named(self):
        models = {DEV: "anthropic/a", VER: "openai/b", REV: "google/c"}
        self.assertIsNone(team_install.independent_review_problem(models, ("opencode",)))
        problem = team_install.independent_review_problem(models, ("claude-code",)) or ""
        self.assertIn("claude-code cannot run the verifier and the reviewer's model", problem)

    def test_the_problem_named_for_each_models_map(self):
        for name, models, expected in self.CASES:
            with self.subTest(name):
                problem = team_install.independent_review_problem(models)
                if expected is None:
                    self.assertIsNone(problem)
                else:
                    self.assertIn(expected, problem or "")


class LeadRuleTests(unittest.TestCase):
    """The lead reads the rule from the team skill and its flows reference; the reviewer and verifier name their model."""

    TEAM = ROOT / "plugins" / "aidd-team"

    def test_the_skill_and_the_flows_reference_carry_the_rule(self):
        skill = (self.TEAM / "skills" / "aidd-team" / "SKILL.md").read_text(encoding="utf-8")
        flows = (self.TEAM / "skills" / "aidd-team" / "references" / "flows.md").read_text(encoding="utf-8")
        section = flows.split("\n## Independent review across providers\n", 1)[1]
        for where, body, names in (
            ("skill", skill, ["agents.independent_review"]),
            ("flows", section, ["agents.independent_review", "Assisted-by", "Needs", "agents.models"]),
        ):
            for name in names:
                with self.subTest(where=where, name=name):
                    self.assertIn(name, body)

    def test_the_reviewer_and_the_verifier_start_their_reports_with_the_model_they_ran_on(self):
        for role in ("reviewer", "verifier"):
            with self.subTest(role=role):
                self.assertIn("<harness>/<model actually used>", (self.TEAM / "agents" / f"{role}.md").read_text(encoding="utf-8"))


class ConfigKeyTests(unittest.TestCase):
    def test_the_key_is_optional_and_a_boolean(self):
        for value, ok in (("true", True), ("false", True), ('"yes"', False), ("1", False)):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                adopted(root, f"  independent_review: {value}\n")
                try:
                    config.load_file(config.CONFIG_PATH, str(root))
                    loaded = True
                except config.ConfigError:
                    loaded = False
                self.assertEqual(loaded, ok)

    def test_the_schema_describes_the_key_as_off_by_default(self):
        prop = resources.load_json("config.schema.json")["properties"]["agents"]["properties"]["independent_review"]
        self.assertEqual(prop["type"], "boolean")
        self.assertIn("Default: off", prop["description"])


class InstallNoteTests(unittest.TestCase):
    def warn_lines(self, agents: str) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            adopted(root, agents)
            actions: list[str] = []
            team_install.install_team(root, actions, harnesses=["claude-code"])
            return [a for a in actions if a.startswith("warn") and "independent_review" in a]

    def test_the_install_says_so_only_when_the_key_is_on_and_the_models_fall_short(self):
        mixed = '  models:\n    developer: "anthropic/claude-sonnet-5"\n    verifier: "openai/gpt-6"\n    reviewer: "openai/gpt-6"\n'
        same = '  models:\n    execution: "anthropic/claude-sonnet-5"\n    reasoning: "anthropic/claude-opus-5-5"\n'
        cases = [
            ("off by default", mixed, 0),
            ("on, but Claude Code cannot run openai", "  independent_review: true\n" + mixed, 1),
            ("on and one provider", "  independent_review: true\n" + same, 1),
            ("on and no models", "  independent_review: true\n", 1),
            ("off and one provider", "  independent_review: false\n" + same, 0),
        ]
        for name, agents, expected in cases:
            with self.subTest(name):
                self.assertEqual(len(self.warn_lines(agents)), expected)


class SecurityGuidanceTests(unittest.TestCase):
    """`.claude/claude-security-guidance.md` is the file the security-guidance plugin documents (8 KB with the user's own)."""

    def test_the_file_is_written_once_kept_after_an_edit_and_removed_by_uninstall_when_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            adopted(root)
            path = root / team_install.SECURITY_GUIDANCE
            team_install.install_team(root, [], harnesses=[])
            self.assertEqual(path.read_text(encoding="utf-8"), team_install.security_guidance_text())
            path.write_text("# mine\n", encoding="utf-8")
            actions: list[str] = []
            team_install.install_team(root, actions, harnesses=[])
            self.assertEqual(path.read_text(encoding="utf-8"), "# mine\n")
            self.assertTrue(any(a.startswith("kept") and "claude-security-guidance" in a for a in actions))
            team_install.install_team(root, [], force=True, harnesses=[])
            self.assertEqual(path.read_text(encoding="utf-8"), "# mine\n", "--force keeps the project's own rules too")
            uninstalling.uninstall(root, yes=True)
            self.assertTrue(path.exists(), "a changed copy is the project's, so uninstall keeps it")
            path.write_text(team_install.security_guidance_text(), encoding="utf-8")
            uninstalling.uninstall(root, yes=True)
            self.assertFalse(path.exists())

    def test_each_rule_comes_from_the_secure_coding_skill(self):
        skill = (ROOT / "plugins" / "aidd-team" / "skills" / "secure-coding" / "SKILL.md").read_text(encoding="utf-8")
        for term in ("trust boundary", "allow-list", "shell command", "deny by default", "metadata address", "secret manager", "lockfile"):
            with self.subTest(term=term):
                self.assertIn(term, team_install.security_guidance_text())
                self.assertIn(term, skill)

    def test_the_file_fits_the_plugins_cap_with_room_for_the_projects_own_rules(self):
        self.assertLess(len(team_install.security_guidance_text().encode()), 2 * 1024)  # the plugin's cap is 8 KB for every location together

    def test_a_project_without_aidds_claude_files_still_gets_it_when_claude_code_is_wired(self):
        for claude_files, harnesses, written in ((False, ["claude-code"], True), (False, ["codex"], False), (True, [], True)):
            with self.subTest(claude_files=claude_files, harnesses=harnesses), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                adopted(root)
                team_install.install_team(root, [], claude_files=claude_files, harnesses=harnesses)
                self.assertEqual((root / team_install.SECURITY_GUIDANCE).is_file(), written)

    def test_the_developer_and_the_security_engineer_both_recommend_the_plugin(self):
        roles = resources.load_json("roles.json")["roles"]
        for role in ("developer", "security-engineer"):
            with self.subTest(role=role):
                entry = next((e for e in roles[role]["extends"] if e["name"] == "security-guidance"), None)
                self.assertIsNotNone(entry)
                self.assertEqual(entry["install"], "claude plugin install security-guidance@claude-plugins-official")
                self.assertEqual(entry["tier"], "official")
                self.assertIn("claude-security-guidance.md", entry["adds"])


if __name__ == "__main__":
    unittest.main()
