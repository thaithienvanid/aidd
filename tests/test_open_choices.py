"""No overlap: every open choice the catalog fills is declared once, and the pack or practice skill
that opens a choice no longer decides it in its own test commands.

A choice is decided when a test command of its owner names exactly one of the choice's options and not the choice
itself. Naming two options, or naming the choice (`the team's e2e-test runner, by default ...`), leaves it open. A tool
that another pack keeps for its own check stays there: the check reads only the owner's commands.
"""

import copy
import re
import unittest
from unittest import mock

import helpers  # noqa: F401  (puts src/ on the path)

from aidd import docs, resources, standards

# The open choices step 0 declares, by owner, with a word aidd's default must hold.
STEP_0 = {
    "ci-pipeline:formatter": None,
    "ci-pipeline:linter": None,
    "ci-pipeline:type-checker": None,
    "ci-pipeline:test-runner": None,
    "ci-pipeline:package-manager": None,
    "ci-pipeline:dependency-audit": "OSV-Scanner",
    "ci-pipeline:language-version": None,
    "apis-and-services:api-framework": None,
    "apis-and-services:validation-library": None,
    "schema-migration:orm": None,
    "schema-migration:migration-tool": None,
    "web-front-end:web-framework": None,
    "web-front-end:e2e-test": "Playwright",
    "mobile-apps:mobile-framework": "Expo",
    "ai-agents-and-tools:agent-framework": None,
    "ai-agents-and-tools:mcp-server-framework": None,
    "ai-agents-and-tools:trace-backend": "OpenTelemetry",
    "ai-features:llm-gateway": None,
    "cloud-and-infrastructure:hosting-target": None,
    "cloud-and-infrastructure:serverless-compute": None,
    "cloud-and-infrastructure:object-storage": None,
    "cloud-and-infrastructure:database": None,
    "cloud-and-infrastructure:queue": None,
    "cloud-and-infrastructure:iac-tool": "OpenTofu",
    "cloud-and-infrastructure:cost-estimate-tool": "Infracost",
    "cloud-and-infrastructure:policy-tool": "Conftest",
    # The choices the groups below fill: each declared once, so the group builders never declare one twice.
    "web-front-end:component-test": "Testing Library",
    "mobile-apps:mobile-ui-test": "Maestro",
    "test-design:integration-test-services": "Testcontainers",
    "observability:logging-library": "slog",
    "observability:log-retention": None,
    "release-rollout:preview-environment-ttl": None,
    "release-rollout:cost-kill-switch": None,
    "cloud-and-infrastructure:budget-alerts": None,
    "cloud-and-infrastructure:spend-caps": None,
    "cloud-and-infrastructure:egress-and-nat": None,
    "cloud-and-infrastructure:compute-architecture": "arm64",
    "ai-features:llm-budget-mechanism": "SDK",
}


def raw_choices(roles: dict) -> list[tuple[str, str]]:
    """(owner, id) for every declaration, repeats kept: `standards.open_choices` keys by ref and would hide one."""
    out = [(d["slug"], c["id"]) for d in roles["domains"] for c in d.get("open_choices", [])]
    return out + [(name, c["id"]) for name, p in roles.get("practices", {}).items() for c in p.get("open_choices", [])]


class StepZeroTests(unittest.TestCase):
    def test_every_step_0_choice_is_declared_with_its_default(self):
        choices = standards.open_choices()
        for ref, word in STEP_0.items():
            self.assertIn(ref, choices)
            if word:
                self.assertIn(word, choices[ref]["default"], ref)
                self.assertIn(word, " ".join(choices[ref]["options"]), ref)

    def test_the_defaults_name_no_version_and_the_cost_guards_say_their_rule(self):
        # Versions live in library standards, read at their source; a default never types one.
        choices = standards.open_choices()
        version = re.compile(r"\bv?\d+\.\d+|\b[A-Za-z][\w.+-]* v?\d+\b(?!\s*(?:percent|days|,|%))")
        for ref, c in choices.items():
            for text in (c["default"], *c["options"]):
                self.assertNotRegex(text, version, ref)
        self.assertRegex("JUnit 5", version)  # the form the check exists for
        self.assertNotRegex("At 50, 80, and 100 percent", version)
        self.assertIn("50, 80, and 100 percent", choices["cloud-and-infrastructure:budget-alerts"]["default"])
        self.assertIn("forecast", choices["cloud-and-infrastructure:budget-alerts"]["default"])
        self.assertIn("hard cap", choices["cloud-and-infrastructure:spend-caps"]["default"])
        self.assertIn("No NAT gateway", choices["cloud-and-infrastructure:egress-and-nat"]["default"])
        self.assertIn("tested runbook", choices["release-rollout:cost-kill-switch"]["default"])

    def test_a_requirement_is_a_pack_rule_and_only_its_mechanism_a_choice(self):
        packs = {d["slug"]: d for d in resources.roles()["domains"]}
        caps = [r for r in packs["ai-features"]["checklist"] if "(LLM06)" in r["item"]]
        self.assertEqual(len(caps), 1)
        for need in ("max tokens per call", "a budget per user", "the provider's spend limit"):
            self.assertIn(need, caps[0]["item"])
        self.assertIn("owasp-llm-top-10", caps[0]["cites"])
        choices = standards.open_choices()
        self.assertNotIn("ai-features:llm-spend-caps", choices)
        self.assertIn("ai-features:llm-budget-mechanism", choices)
        self.assertNotIn("release-rollout:kill-switch", choices)  # the feature-flag kill switch stays release-rollout's own
        self.assertIn("cost", choices["release-rollout:cost-kill-switch"]["question"])
        ref = resources.data_dir("team") / "skills" / "observability" / "references" / "telemetry-cost.md"
        self.assertIn("Every log group has a set retention", ref.read_text(encoding="utf-8"))
        self.assertNotIn("OPA Gatekeeper", " ".join(choices["cloud-and-infrastructure:policy-tool"]["options"]))

    def test_each_open_choice_is_declared_once(self):
        found = raw_choices(resources.roles())
        self.assertEqual(len(found), len(set(found)), "a pack or skill declares a choice twice")
        ids = [cid for _, cid in found]
        self.assertEqual(sorted(i for i in set(ids) if ids.count(i) > 1), [], "two packs or skills declare the same choice")
        self.assertEqual(standards.choice_problems(), [])

    def test_no_pack_still_decides_a_choice_it_opens(self):
        self.assertEqual(standards.deciding_problems(), [])

    def test_the_library_checks_run_the_choice_checks(self):
        roles = copy.deepcopy(resources.roles())
        pack = next(d for d in roles["domains"] if d["slug"] == "web-front-end")
        pack["open_choices"].append(dict(pack["open_choices"][0]))
        with mock.patch.object(resources, "roles", lambda: roles):
            self.assertTrue(any("declares the choice" in p for p in standards.library_problems()))

    def test_every_owner_shows_its_new_choices(self):
        # Generated: in the SKILL.md, or in references/open-choices.md for a preloaded skill (no preloaded byte added).
        for ref in STEP_0:
            owner = ref.split(":")[0]
            self.assertIsNotNone(docs.open_choices_placement(owner), owner)
        for owner in ("ci-pipeline", "schema-migration", "ai-features", "cloud-and-infrastructure"):
            self.assertEqual(docs.open_choices_placement(owner), "reference", owner)

    def test_a_pack_no_role_preloads_links_the_choices_it_keeps_in_a_reference(self):
        # mobile-apps is near its cap, and no role lists it: its own References section and the roles reference link it.
        skills = resources.data_dir("team") / "skills"
        link = "- [references/open-choices.md](references/open-choices.md)"
        self.assertEqual(docs.open_choices_placement("mobile-apps"), "reference")
        self.assertIn(link, (skills / "mobile-apps" / "SKILL.md").read_text(encoding="utf-8"))
        roles_ref = (skills / "aidd-team" / "references" / "roles.md").read_text(encoding="utf-8")
        self.assertIn("`aidd-team:mobile-apps` (its `references/open-choices.md`)", roles_ref)
        # A preloaded pack gains no bytes: only the roles reference links its choices.
        self.assertNotIn(link, (skills / "cloud-and-infrastructure" / "SKILL.md").read_text(encoding="utf-8"))


def roles_with(owner_tests: list[str], options: list[str], cid: str = "e2e-test") -> dict:
    """A registry with one pack that opens `cid` and runs these test commands."""
    return {
        "domains": [
            {
                "slug": "web-front-end",
                "tests": [{"name": f"t{i}", "how": how} for i, how in enumerate(owner_tests)],
                "open_choices": [{"id": cid, "question": "Which?", "default": options[0], "options": options}],
            }
        ],
        "practices": {},
    }


class DecidingCheckTests(unittest.TestCase):
    OPTIONS = ["Playwright", "Cypress (component and e2e)", "WebdriverIO"]

    def problems(self, *how: str) -> list[str]:
        return standards.deciding_problems(roles_with(list(how), self.OPTIONS), texts={})

    def test_one_option_alone_decides_the_choice(self):
        found = self.problems("`@playwright/test` (1.63.0) in a fresh context")
        self.assertEqual(len(found), 1)
        self.assertIn("web-front-end:e2e-test", found[0])
        self.assertIn("Playwright", found[0])

    def test_naming_the_choice_or_two_options_leaves_it_open(self):
        self.assertEqual(self.problems("the team's `e2e-test` runner, by default `@playwright/test` (1.63.0)"), [])
        self.assertEqual(self.problems("Playwright or Cypress in a fresh context"), [])
        self.assertEqual(self.problems("unit tests"), [])

    def test_an_option_is_matched_by_its_name_as_a_whole_word(self):
        # "Cypress (component and e2e)" is matched as "Cypress"; a word that only contains an option is not.
        self.assertEqual(len(self.problems("cypress run")), 1)
        self.assertEqual(self.problems("playwrightish"), [])

    def test_a_practice_skill_is_read_from_its_test_commands(self):
        roles = {
            "domains": [],
            "practices": {"ci-pipeline": {"open_choices": [{"id": "test-runner", "question": "Which?", "default": "pytest", "options": ["pytest", "Vitest"]}]}},
        }
        table = "## Test commands\n\n| Command | Proves | How |\n| --- | --- | --- |\n| Unit | it works | `uvx pytest==9.0.0` |\n\n## Stop if\n"
        found = standards.deciding_problems(roles, texts={"ci-pipeline": table})
        self.assertEqual(len(found), 1)
        self.assertIn("ci-pipeline:test-runner", found[0])
        self.assertEqual(standards.deciding_problems(roles, texts={"ci-pipeline": table.replace("`uvx", "the `test-runner`, `uvx")}), [])

    def test_a_choice_declared_twice_is_reported(self):
        roles = roles_with([], self.OPTIONS)
        roles["domains"][0]["open_choices"].append(dict(roles["domains"][0]["open_choices"][0]))
        roles["practices"] = {"test-design": {"open_choices": [{"id": "e2e-test", "question": "Which?", "default": "x", "options": ["x", "y"]}]}}
        found = standards.choice_problems(roles)
        self.assertTrue(any("web-front-end declares the choice e2e-test 2 times" in p for p in found), found)
        self.assertTrue(any("e2e-test is declared by 2 packs or skills" in p for p in found), found)


if __name__ == "__main__":
    unittest.main()
