"""A new tool, MCP server, or permission for an agent routes major.

The AI-agents pack says so, and the threat model agrees: a tool an agent can call widens what the agent can do, so a
prompt injection can reach further, and a tool that reads production data adds the `data` dimension, which forces major.
The path alone says normal (`.mcp.json` is in the `agent_config` area), so the author declares the dimension. The routing
eval and the skill the agent reads must say the same, so none of them admits the looser route."""

from __future__ import annotations

import unittest

import helpers
from aidd import evals, risk

ROOT = helpers.ROOT
NEW_TOOL = "new tool, MCP server, or permission"
ROUTES = ROOT / ".agents" / "skills" / "aidd" / "references" / "routes.md"
PACK = ROOT / "plugins" / "aidd-packs" / "skills" / "ai-agents-and-tools" / "SKILL.md"
LOOSER_THAN_MAJOR = {"minor", "normal"}


def case(case_id: str) -> dict:
    return next(sc for sc in evals.load_scenarios(ROOT / "evals" / "routing") if sc["id"] == case_id)


class ANewToolRoutesMajor(unittest.TestCase):
    def test_the_routing_case_for_a_new_mcp_server_expects_major(self):
        expected = case("c25-mcp-config")["expected"]
        self.assertEqual(expected["route"], "major")
        self.assertFalse(LOOSER_THAN_MAJOR & set(expected.get("accept", [])), "a looser route in `accept` hedges the answer")

    def test_the_path_alone_stays_normal_so_the_dimension_decides(self):
        """The area's route is unchanged: only a declared dimension makes the edit major."""
        self.assertEqual(risk.route_for(risk.rule_set(None), [".mcp.json"]).route, "normal")

    def test_the_skill_the_agent_reads_and_the_pack_both_say_a_new_tool_is_major(self):
        for page in (ROUTES, PACK):
            with self.subTest(page=page.name):
                said = [s for s in helpers.sentences(page.read_text(encoding="utf-8")) if NEW_TOOL in s]
                self.assertTrue(any("major" in s for s in said), f"{page.name} does not say a {NEW_TOOL} is major")


if __name__ == "__main__":
    unittest.main()
