"""The team starts fewer roles by default, and a specialist joins on a flagged concern, never by fan-out.

A flow's `runs` lists every role it may start. These tests hold who starts by default and what brings in the rest, as
facts the registry and the data the commands read can check, so a command names only signals that exist.
"""

import re
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import evals
from aidd.kernel import resources
from aidd.knowledge import team_registry
from aidd.setup import detection

TEAM = ROOT / "plugins" / "aidd-team"


def flow(name: str) -> dict:
    return next(f for f in team_registry.roles()["loop"]["flows"] if f["command"] == name)


def command(name: str) -> str:
    return (TEAM / "commands" / f"{name}.md").read_text(encoding="utf-8")


AREAS = set(resources.load_json("risks.json")["areas"])


class PlanStartsTheArchitectFirstTests(unittest.TestCase):
    """The plan chain cost half the team's eval spend: a product-manager draft, four consults, and a second pass."""

    def test_the_architect_is_the_one_default_consult_and_the_others_follow_its_flags(self):
        runs = flow("plan")["runs"]
        first = runs.index(["architect"])
        later = {r for group in runs[first + 1 :] for r in group}
        self.assertNotIn("architect", later)
        self.assertNotIn("product-manager", later, "no second product-manager pass: the lead folds the cards")
        self.assertTrue(later, "a flagged concern still reaches its specialist")
        handoffs = team_registry.roles()["loop"]["handoffs"]
        (flags,) = [h for h in handoffs if h["from"] == ["architect"] and set(h["to"]) == later]
        self.assertIn("flags", flags["through"])


class OneOwnerForTheSecurityEngineersAreasTests(unittest.TestCase):
    """M1: the security engineer's trigger areas are one list, on the role, and each command reads it."""

    BLOCK = "<!-- aidd:gen areas:security-engineer -->"

    def test_the_list_names_areas_aidd_risk_knows(self):
        listed = resources.load_json("roles.json")["roles"]["security-engineer"]["starts_on_areas"]
        detected = {rule for _names, rule, _dims in detection.SENSITIVE}
        self.assertLessEqual(set(listed), AREAS | detected)
        self.assertIn("STARTS_ON_AREAS", resources.load_json("roles.json")["roles"]["security-engineer"]["starts_when"])
        self.assertNotIn("STARTS_ON_AREAS", team_registry.roles()["roles"]["security-engineer"]["starts_when"])

    def test_every_command_that_starts_it_on_an_area_reads_the_list(self):
        listed = set(resources.load_json("roles.json")["roles"]["security-engineer"]["starts_on_areas"])
        readers = 0
        for path in sorted((TEAM / "commands").glob("*.md")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not re.search(r"security[ -]engineer", line):
                    continue
                outside = line.split(self.BLOCK, 1)[0] + line.split("<!-- aidd:end -->", 1)[-1] if self.BLOCK in line else line
                named = set(re.findall(r"`([a-z_]+)`", outside)) & listed
                with self.subTest(path.name, line=line[:60]):
                    # Only `dependencies` may stand alone, where review narrows it to the package changes.
                    self.assertLessEqual(named, {"dependencies"}, "name the areas through the generated block")
                readers += self.BLOCK in line
        self.assertGreaterEqual(readers, 3)


@unittest.skipUnless(shutil.which("git"), "git is required")
class OnboardStartsWhatDetectionFindsTests(unittest.TestCase):
    """M5: the SRE starts in onboarding on any file that builds, ships, or runs the code, and detection lists them by type."""

    def test_detection_lists_each_type_of_operations_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in (".circleci/config.yml", "Jenkinsfile", "azure-pipelines.yml", "svc/Dockerfile", "svc/k8s/app.yaml", "infra/main.tf", "deploy.sh"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("x\n", encoding="utf-8")
            found = {(o["path"], o["type"]) for o in detection.detect(root)["operations"]}
        self.assertLessEqual(
            {
                (".circleci/config.yml", "ci"),
                ("Jenkinsfile", "ci"),
                ("azure-pipelines.yml", "ci"),
                ("svc/Dockerfile", "container"),
                ("svc/k8s/app.yaml", "infrastructure"),
                ("infra/main.tf", "infrastructure"),
                ("deploy.sh", "deploy"),
            },
            found,
        )

    def test_a_repository_with_none_lists_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "app.py").write_text("print(1)\n", encoding="utf-8")
            self.assertEqual(detection.detect(Path(tmp))["operations"], [])

    def test_the_architect_always_runs_and_starts_first(self):
        self.assertEqual(flow("onboard")["runs"][0][0], "architect")


class TheAskingRoleLoadsTheBusinessPackTests(unittest.TestCase):
    """The domain expert folded into the packs: the role that would have asked for its card loads the business pack
    itself, so the domain's rules still reach the plan, the Spec, and the review, and its eval cases moved with it."""

    def test_no_role_speaks_for_the_domain_and_the_askers_apply_the_pack(self):
        data = team_registry.roles()
        self.assertNotIn("domain-expert", data["roles"])
        self.assertFalse((TEAM / "agents" / "domain-expert.md").exists())
        for key in ("architect", "reviewer"):
            agent = (TEAM / "agents" / f"{key}.md").read_text(encoding="utf-8")
            self.assertIn("business pack", agent.split("<!-- aidd:end -->", 1)[1], key)
        self.assertIn("A domain concern starts no role", command("specify"))
        self.assertIn("Name the business packs the work sits in", command("plan"))

    def test_the_domain_cases_moved_to_the_roles_that_load_the_pack(self):
        cases = evals.load_scenarios(ROOT / "evals" / "roles")
        moved = [c for c in cases if c["claim"].endswith(".names-the-domain-rules")]
        self.assertTrue(moved)
        self.assertEqual({c["role"] for c in moved}, {"architect", "reviewer"})
        self.assertEqual({c["step"] for c in moved}, {"Plan", "Specify", "Review"}, "each step the domain expert worked keeps a case")
        self.assertTrue(all(c["step"] == "Review" for c in moved if c["role"] == "reviewer"))


class RetroHoldsTheCoachAndTheUpkeepTests(unittest.TestCase):
    """The agile coach and `/maintain` folded into `/retro`: the SRE runs both parts, and the coach's method and standards
    live in the retrospective practice skill, so no capability left with the role."""

    def test_one_learn_flow_on_a_cadence_runs_the_sre(self):
        data = team_registry.roles()
        self.assertNotIn("agile-coach", data["roles"])
        self.assertNotIn("maintain", [f["command"] for f in data["loop"]["flows"]])
        self.assertFalse((TEAM / "commands" / "maintain.md").exists())
        self.assertEqual(flow("retro")["runs"], [["sre"], ["product-manager"]], "the SRE writes it, the product manager drafts its Specs")
        self.assertIn("docs/rfcs/**", data["roles"]["sre"]["writes"])
        self.assertIn("retrospective", data["roles"]["sre"]["practices"])
        self.assertEqual(data["loop"]["documents"]["improvement-log"]["written_by"], "sre")
        self.assertIn("docs/retros/**", data["roles"]["sre"]["writes"])

    def test_the_practice_skill_holds_the_method(self):
        skill = (TEAM / "skills" / "retrospective" / "SKILL.md").read_text(encoding="utf-8")
        for must in ("speed metric with a quality one", "At most three improvements", "never a person", "No action is a valid result"):
            self.assertIn(must, skill, must)
        self.assertIn("aidd-team:retrospective skill", command("retro"))
        self.assertIn("`upkeep`", command("retro"))


class FlowsFoldIntoModesTests(unittest.TestCase):
    """Four flows became modes of the flow that owns their step, so a person learns fewer commands and loses no step:
    refine is the plan's, explore the Specify's, rework the Implement's, and the upkeep the retrospective's."""

    def test_each_folded_flow_is_a_mode_of_its_owner_in_the_data_and_the_command(self):
        flows = team_registry.roles()["loop"]["flows"]
        commands = [f["command"] for f in flows]
        for gone in ("refine", "explore", "rework", "maintain"):
            self.assertNotIn(gone, commands, gone)
            self.assertFalse((TEAM / "commands" / f"{gone}.md").exists(), gone)
        modes = {(f["command"], m["name"]) for f in flows for m in f.get("modes", [])}
        self.assertLessEqual({("plan", "refine"), ("specify", "explore"), ("implement", "rework"), ("retro", "upkeep")}, modes)
        for owner, mode in modes:
            text = command(owner)
            front = text.split("---")[1]
            with self.subTest(owner=owner, mode=mode):
                self.assertIn(f"\n## {mode.capitalize()} mode\n", text)
                self.assertIn(f"`/aidd-team:{owner} {mode}", text)
                self.assertIn(mode, front.split("argument-hint:", 1)[1], "the argument hint names the mode")
                # Codex and Antigravity render only the description, so it names the mode too.
                self.assertIn(mode, front.split("description:", 1)[1].split("\n", 1)[0])
                body = text.split("<!-- aidd:end -->", 1)[1].lstrip()
                self.assertTrue(body.startswith("Choose the mode by the argument's shape"), "the mode rule comes first")
                mode_roles = {r for f in flows if f["command"] == owner for m in f["modes"] if m["name"] == mode for g in m["runs"] for r in g}
                section = text.split(f"\n## {mode.capitalize()} mode\n", 1)[1]
                self.assertTrue(all(f"`aidd-team:{r}`" in section for r in mode_roles), mode_roles)

    def test_the_plans_own_chain_starts_no_delivery_manager_and_its_cards_go_to_the_lead(self):
        self.assertNotIn("delivery-manager", {r for g in flow("plan")["runs"] for r in g})
        data = team_registry.roles()
        cards = [h for h in data["loop"]["handoffs"] if h["artifact"] == ["perspective"] and h["through"].startswith("a perspective card")]
        self.assertTrue(cards)
        self.assertTrue(all(to.startswith("the author") for h in cards for to in h["to"]))
        self.assertNotIn("perspective", data["roles"]["product-manager"]["reads"])

    def test_the_rework_step_still_starts_a_flow_and_verify_still_runs_on_its_new_head(self):
        self.assertIn("rework", [m["name"] for m in flow("implement")["modes"]])
        rework = command("implement").split("\n## Rework mode\n", 1)[1]
        self.assertIn("`/aidd-team:review`", rework)
        self.assertIn("verifier", {r for g in flow("review")["runs"] for r in g})

    def test_the_exploration_cli_stays(self):
        from aidd.cli import grammar

        self.assertIn("explore", grammar.ADD_COMMAND, "`aidd explore` renders the comparison page the explore mode presents")

    def test_client_delivery_says_what_it_belongs_to(self):
        for name in ("propose", "handover"):
            self.assertIn("Part of client delivery", command(name), name)


if __name__ == "__main__":
    unittest.main()
