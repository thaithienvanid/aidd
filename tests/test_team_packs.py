"""`aidd init --aidd-team` installs the practice skills and only the domain packs a project calls for, and a person adds one later.

Each skill aidd writes into `.claude/skills/` puts its description in every session's context, so a pack the project never
uses costs that context for nothing. A pack comes from a manifest's dependencies, from a risk area `aidd risk` matches on
a tracked path (each pack's `areas` in schemas/packs.json), from `project.compliance`, from `agents.domain_packs`, or
from a past install. These cases are project shapes, not one stack: no manifest at all, a monorepo with several, a deep
path, an area the config defines, and a domain no file names.
"""

import json
import tempfile
import unittest
from pathlib import Path

from helpers import git

from aidd import config, risk, setup
from aidd.kernel import resources
from aidd.setup import adoption, detection, domain_packs, team_install, uninstalling, upgrading

PACKS = sorted(p["slug"] for p in resources.load_json("packs.json"))
PRACTICES = sorted(p.parent.name for p in (resources.data_dir("team") / "skills").glob("*/SKILL.md") if p.parent.name != "aidd-team")
PACK_SKILLS = sorted(p.parent.name for p in (resources.data_dir("packs") / "skills").glob("*/SKILL.md"))


def installed(root: Path) -> list[str]:
    """The skills aidd wrote into `.claude/skills/`, by name without the `aidd-` prefix."""
    folder = root / ".claude" / "skills"
    return sorted(p.parent.name.removeprefix(team_install.TEAM_PREFIX) for p in folder.glob(f"{team_install.TEAM_PREFIX}*/SKILL.md"))


class TeamPackTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def project(self, files: dict[str, str], config: str = "", actions: list[str] | None = None) -> Path:
        for rel, text in files.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text, encoding="utf-8")
        git(self.root, "init", "-q", "-b", "main")
        done = adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"], skill=False, aidd_team=True))
        if actions is not None:
            actions += done
        if config:
            cfg = self.root / ".aidd" / "config.yaml"
            cfg.write_text(cfg.read_text(encoding="utf-8") + config, encoding="utf-8")
        return self.root

    def test_the_packs_and_the_practice_skills_are_apart_and_every_pack_has_a_skill(self):
        self.assertGreater(len(PRACTICES), 20)
        self.assertEqual(PACK_SKILLS, PACKS, "the aidd-packs plugin holds exactly the packs of schemas/packs.json")
        self.assertEqual(set(PRACTICES) & set(PACKS), set(), "no pack is also a skill of the aidd-team plugin")

    def test_a_packs_risk_areas_are_areas_aidd_knows(self):
        """A built-in area, or one `aidd init` writes into the config for a sensitive folder no built-in area covers."""
        known = set(risk.builtin()["areas"]) | {rule for _, rule, _ in detection.SENSITIVE}
        for pack in resources.load_json("packs.json"):
            with self.subTest(pack["slug"]):
                self.assertLessEqual(set(pack.get("areas", [])), known)

    def test_a_project_with_no_manifest_gets_the_practice_skills_and_no_pack(self):
        root = self.project({"README.md": "# notes\n", "scripts/run.sh": "#!/bin/sh\necho hi\n"})
        self.assertEqual(detection.detect(root)["packs"], [])
        self.assertEqual(installed(root), PRACTICES)

    def test_a_path_in_a_risk_area_brings_its_pack_at_any_depth(self):
        root = self.project({"packages/api/src/billing/charge.ts": "", "README.md": "# x\n"})
        self.assertEqual(installed(root), sorted(PRACTICES + ["payments-and-finance"]))

    def test_the_risk_areas_decide_and_no_folder_list_of_its_own(self):
        """`aidd risk` puts login/ in auth and customers/ in personal_data, so those packs come. No built-in area holds ai/,
        prompts/, or a design tokens/ folder, so with no area in the config they bring nothing, whatever their names suggest."""
        root = self.project({"login/form.html": "", "customers/export.sh": "", "ai/model.txt": "", "prompts/a.txt": "", "tokens/colors.json": ""})
        rs = risk.rule_set(config.load_file(config.CONFIG_PATH, str(root)))
        self.assertEqual(risk.areas_of(rs, "ai/model.txt") + risk.areas_of(rs, "prompts/a.txt") + risk.areas_of(rs, "tokens/colors.json"), [])
        self.assertEqual(domain_packs.choose(root).packs, ["enterprise-controls", "privacy-by-default"])

    def test_the_ai_area_init_writes_brings_the_ai_features_pack(self):
        """No built-in area holds ai/ or prompts/, but `aidd init` writes an `ai` area for them, as `aidd init` from the
        command line passes detection's areas; a config area's name is data a pack maps to."""
        for folder in ("ai", "prompts"):
            with self.subTest(folder), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                (root / folder).mkdir()
                (root / folder / "a.txt").write_text("x", encoding="utf-8")
                git(root, "init", "-q", "-b", "main")
                areas = detection.detect(root)["risk_areas"]
                self.assertEqual([a["name"] for a in areas], ["ai"])
                options = adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"], skill=False, aidd_team=True, risk_areas=areas)
                adoption.init(root, options)
                self.assertEqual(installed(root), sorted(PRACTICES + ["ai-features"]))

    def test_an_area_the_config_defines_brings_the_pack_mapped_to_it(self):
        root = self.project({"identity/keys.py": ""}, "risks:\n  areas:\n    sign_in:\n      paths: ['identity/**']\n")
        self.assertIn("enterprise-controls", domain_packs.choose(root).packs)

    def test_a_monorepo_gets_the_packs_of_every_manifest(self):
        root = self.project(
            {
                "web/package.json": json.dumps({"dependencies": {"react": "^19"}}),
                "api/pyproject.toml": '[project]\nname = "api"\ndependencies = ["fastapi"]\n',
                "worker/go.mod": "module worker\n\nrequire github.com/stripe/stripe-go/v82 v82.1.0\n",
                "infra/main.tf": "",
            }
        )
        want = ["apis-and-services", "cloud-and-infrastructure", "payments-and-finance", "web-front-end"]
        self.assertEqual(detection.detect(root)["packs"], want)
        self.assertEqual(installed(root), sorted(PRACTICES + want))

    def test_a_compliance_target_brings_the_enterprise_controls_pack(self):
        root = self.project({"README.md": "# x\n"}, "project:\n  compliance:\n    targets: [soc2]\n")
        self.assertIn("enterprise-controls", domain_packs.choose(root).packs)

    def test_a_person_adds_a_pack_no_file_names_and_an_upgrade_installs_it(self):
        root = self.project({"README.md": "# claims\n"})
        self.assertNotIn("insurance", installed(root))
        cfg = root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "agents:\n  domain_packs: [insurance]\n", encoding="utf-8")
        upgrading.upgrade(root, yes=True)
        self.assertEqual(installed(root), sorted(PRACTICES + ["insurance"]))

    def test_the_config_refuses_a_name_that_is_no_pack(self):
        base = 'aidd_version: "1.0.0"\nprofile: solo\n'
        self.assertEqual(config.load_text(base + "agents:\n  domain_packs: [insurance]\n").get("agents", "domain_packs"), ["insurance"])
        with self.assertRaisesRegex(config.ConfigError, "domain_packs"):
            config.load_text(base + "agents:\n  domain_packs: [insurence]\n")

    def test_an_upgrade_keeps_a_pack_a_past_install_wrote_and_adds_one_a_new_manifest_calls_for(self):
        root = self.project({"package.json": json.dumps({"dependencies": {"react": "^19"}})})
        self.assertIn("web-front-end", installed(root))
        (root / "package.json").write_text(json.dumps({"dependencies": {"stripe": "^17"}}), encoding="utf-8")
        upgrading.upgrade(root, yes=True)
        self.assertEqual(installed(root), sorted(PRACTICES + ["payments-and-finance", "web-front-end"]))

    def test_the_install_says_what_it_read_and_how_to_add_a_pack(self):
        actions: list[str] = []
        self.project({"README.md": "# x\n", "billing/charge.py": ""}, actions=actions)
        (note,) = [a for a in actions if "domain_packs" in a]
        self.assertIn("payments-and-finance (the payments area: billing/charge.py)", note)
        self.assertIn("aidd upgrade --yes", note)
        actions = []
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        self.root = Path(other.name)
        self.project({"README.md": "# x\n"}, actions=actions)
        (note,) = [a for a in actions if "domain_packs" in a]
        self.assertIn("no domain pack", note)
        self.assertNotIn("nothing here calls for one", note)
        self.assertIn("no manifest", note)

    def test_detection_runs_once_for_an_init(self):
        import contextlib
        import io
        from unittest import mock

        from aidd.cli import app

        (self.root / "README.md").write_text("# x\n", encoding="utf-8")
        git(self.root, "init", "-q", "-b", "main")
        argv = ["init", str(self.root), "--profile", "solo", "--ci", "none", "--harness", "claude-code", "--aidd-team", "--no-skill"]
        with mock.patch.object(detection, "detect", wraps=detection.detect) as detect, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(argv), 0)
        self.assertEqual(detect.call_count, 1)

    def test_the_old_flag_is_an_unknown_option_and_writes_nothing(self):
        import contextlib
        import io

        from aidd.cli import app

        git(self.root, "init", "-q", "-b", "main")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as raised:
            app.main(["init", str(self.root), "--profile", "solo", "--ci", "none", "--harness", "claude-code", "--team"])
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("unknown option --team. Did you mean `--aidd-team`?", err.getvalue())
        self.assertFalse((self.root / ".aidd").exists())

    def test_uninstall_removes_every_pack_aidd_wrote(self):
        root = self.project({"README.md": "# x\n"}, "agents:\n  domain_packs: [health]\n")
        upgrading.upgrade(root, yes=True)
        self.assertIn("health", installed(root))
        uninstalling.uninstall(root, yes=True)
        self.assertEqual(installed(root), [])

    def test_every_pack_and_skill_is_still_a_file_aidd_may_have_written(self):
        """Uninstall and the plugin migration compare against every text aidd may have written, so any pack counts."""
        paths = set(team_install.team_files([], True))
        for name in [*PRACTICES, *PACKS]:
            self.assertIn(f".claude/skills/{team_install.TEAM_PREFIX}{name}/SKILL.md", paths, name)


class MissingPackTests(unittest.TestCase):
    """Nothing is lost in the cut: a pack the repository needs and lacks is named where a person or an agent looks."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / "README.md").write_text("# x\n", encoding="utf-8")
        git(self.root, "init", "-q", "-b", "main")

    def adopt(self, aidd_team: bool = True) -> None:
        adoption.init(self.root, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["claude-code"], skill=False, aidd_team=aidd_team))
        (self.root / "billing").mkdir()
        (self.root / "billing" / "charge.py").write_text("", encoding="utf-8")
        git(self.root, "add", "-A")

    def hints(self) -> list[str]:
        from helpers import aidd_here

        run = aidd_here("risk", "--json", "--paths", "billing/charge.py", cwd=self.root)
        self.assertEqual(run.returncode, 0, run.stderr)
        return json.loads(run.stdout)["hints"]

    def test_risk_names_a_pack_its_area_needs_and_the_install_lacks(self):
        self.adopt()
        (hint,) = [h for h in self.hints() if "payments-and-finance" in h]
        self.assertIn("agents.domain_packs", hint)
        self.assertIn("aidd upgrade --yes", hint)
        cfg = self.root / ".aidd" / "config.yaml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + "agents:\n  domain_packs: [payments-and-finance]\n", encoding="utf-8")
        upgrading.upgrade(self.root, yes=True)
        # An installed pack is named to load, by the name its project skill has: loading never depends on the skill listing.
        (hint,) = [h for h in self.hints() if "domain pack" in h]
        self.assertEqual(hint, "load the domain pack `aidd-payments-and-finance` (the payments area) with the Skill tool before you edit it")

    def enable(self, *plugins: str) -> None:
        settings = self.root / ".claude" / "settings.json"
        data = json.loads(settings.read_text(encoding="utf-8")) if settings.is_file() else {}
        settings.parent.mkdir(exist_ok=True)
        settings.write_text(json.dumps(data | {"enabledPlugins": {f"{p}@aidd": True for p in plugins}}), encoding="utf-8")

    def test_risk_says_nothing_without_the_team(self):
        self.adopt(aidd_team=False)
        self.assertEqual([h for h in self.hints() if "domain pack" in h], [])

    def test_with_the_team_plugin_risk_names_the_pack_to_load_or_how_to_get_it(self):
        """The aidd-team plugin carries no pack: the pack is the aidd-packs plugin's, which a project enables when it calls for one."""
        self.adopt(aidd_team=False)
        self.enable("aidd-team")
        (hint,) = [h for h in self.hints() if "domain pack" in h]
        self.assertEqual(
            hint,
            "the domain pack `aidd-packs:payments-and-finance` (the payments area) is not installed, so the roles work without it; "
            "to add it, run `claude plugin install aidd-packs@aidd --scope project`",
        )
        self.enable("aidd-team", "aidd-packs")
        (hint,) = [h for h in self.hints() if "domain pack" in h]
        self.assertEqual(hint, "load the domain pack `aidd-packs:payments-and-finance` (the payments area) with the Skill tool before you edit it")

    def test_the_roles_reference_lists_every_pack_and_how_to_add_one(self):
        self.adopt()
        text = (self.root / team_install.TEAM_ROLES_REF).read_text(encoding="utf-8")
        self.assertIn("## Domain packs", text)
        self.assertIn("agents.domain_packs", text)
        for slug in PACKS:
            self.assertIn(f"| `{slug}` |", text, slug)

    def test_doctor_warns_when_the_repository_calls_for_a_pack_it_lacks(self):
        self.adopt()
        warns = lambda: [m for level, m in setup.doctor(self.root) if level == "warn" and "domain pack" in m]  # noqa: E731
        self.assertIn("payments-and-finance", " ".join(warns()))
        upgrading.upgrade(self.root, yes=True)
        self.assertEqual(warns(), [])

    def test_doctor_warns_when_the_team_plugin_is_on_and_the_packs_plugin_is_not(self):
        self.adopt(aidd_team=False)
        self.enable("aidd-team")
        warns = lambda: [m for level, m in setup.doctor(self.root) if level == "warn" and "domain pack" in m]  # noqa: E731
        (warn,) = warns()
        self.assertIn("payments-and-finance (the payments area: billing/charge.py)", warn)
        self.assertIn("claude plugin install aidd-packs@aidd --scope project", warn)
        self.enable("aidd-team", "aidd-packs")
        self.assertEqual(warns(), [])


if __name__ == "__main__":
    unittest.main()
