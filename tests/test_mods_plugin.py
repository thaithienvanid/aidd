"""The aidd-mods plugin: a mod that shows what the aidd CLI prints, and records the decisions a person makes.

Its behavior is tested by its own `*.test.tsx` under `claude plugin test` (ci.yml). These tests hold what must never
change whatever the mod draws: it runs read-only commands, and writes only through aidd's own commands. An approval or
a land (`--confirmed`) comes from the person's own typed words, or, when the request did not come from their keyboard,
after their answer in the engine's dialog. An update or an install runs only after its dialog. It never pushes,
commits, submits a prompt, spawns, or reaches the network, and the engine's generated type files stay out of git.
"""

from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODS = ROOT / "plugins" / "aidd-mods"
HOOKS = MODS / "hooks"

# `aidd` commands that only read; `git rev-parse` names the branch. `aidd upgrade` with no flag is a dry run.
READ_ONLY = {
    ("aidd", "list"),
    ("aidd", "loop", "--show"),
    ("aidd", "autopilot", "status"),
    ("aidd", "goal", "list"),
    ("git", "rev-parse"),
    ("git", "check-ref-format"),  # whether `/aidd explore` names a branch git accepts
    ("git", "symbolic-ref", "-q", "--short", "HEAD"),
    ("aidd", "self-update", "--check"),
    ("aidd", "init", "--dry-run"),
    ("aidd", "publish", "--show"),  # what would leave this machine; publishing itself is aidd's prompt hook and the agent's
}
# The writes `/aidd update` and `/aidd init` make, each only after its dialog. `claude plugin update` brings each aidd
# plugin to its newest commit.
AFTER_A_DIALOG = {("aidd", "self-update"), ("aidd", "upgrade", "--yes"), ("aidd", "init"), ("claude", "plugin", "update", "--json")}
# `/aidd explore <topic>` moves the worktree to its explore branch: from the person's keyboard, or after the dialog
# (askFirst), as the typed `explore branch <topic>` does through aidd's own prompt hook.
EXPLORE_SWITCH = ("git", "switch")
# Engine calls a display never needs: each writes, starts a turn or an agent, runs a model, or reaches the network.
NEVER = ("$.fs.write", "$.prompt.submit", "$.tool.call", "$.agent.spawn", "$.model.", "$.http.", "$.process.spawn", "$.session.append", "$.command.run(")


def source() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(HOOKS.glob("*.ts*")) if ".test." not in p.name)


class ModsPluginTests(unittest.TestCase):
    def test_the_manifest_and_the_marketplace_agree(self):
        manifest = json.loads((MODS / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        entry = next(p for p in market["plugins"] if p["name"] == "aidd-mods")
        self.assertEqual((manifest["name"], entry["source"]), ("aidd-mods", "./plugins/aidd-mods"))
        # No `version` anywhere: Claude Code versions each plugin by its commit, so an update always brings the latest.
        for plugin in (manifest, *market["plugins"]):
            self.assertNotIn("version", plugin, plugin["name"])
        for text in (manifest["description"], entry["description"]):
            self.assertIn("Claude Code 2.1.295 or later", text)  # the oldest version its tests ran on

    def test_its_one_module_exists_and_its_tests_sit_beside_it(self):
        modules = json.loads((HOOKS / "hooks.json").read_text(encoding="utf-8"))["modules"]
        self.assertEqual(modules, ["./register.tsx"])
        self.assertTrue((HOOKS / "register.tsx").is_file())
        self.assertTrue(list(HOOKS.glob("*.test.tsx")))

    def test_it_runs_only_read_only_commands_and_the_confirmed_approvals(self):
        text = source()
        runs = re.findall(r"run\(\$, root, \[([^\]]*)\]", text)
        self.assertGreaterEqual(len(runs), 4, "the argv lists moved: update this test with them")
        writes = []
        for argv in runs:
            words = tuple(re.findall(r"'([^']*)'", argv))
            decides = (("aidd", "approve", "spec"), ("aidd", "approve", "merge"), ("aidd", "approve", "all"))
            if words[:3] in decides or words[:2] in (("aidd", "land"), ("aidd", "proposal")):
                self.assertTrue({"--show", "--confirmed"} & set(words), words)  # never the terminal form
                if "--confirmed" in words:
                    writes.append(words[1] if words[1] in ("land", "proposal") else words[2])
                continue
            if words == ("aidd", "approve", "stop"):
                continue  # it only takes something back: a standing approval
            if words in AFTER_A_DIALOG or words == ("aidd", "upgrade") or words[:2] == EXPLORE_SWITCH:
                continue
            self.assertTrue(any(words[: len(ok)] == ok for ok in READ_ONLY), words)
        self.assertEqual(sorted(writes), ["all", "land", "merge", "proposal", "spec"], writes)
        helper = text[text.index("async function exploreFromCommand(") :]
        helper = helper[: helper.index("\n}\n")]
        self.assertLess(helper.index("askFirst && !(await confirmed("), helper.index("'git', 'switch'"))  # the dialog first
        self.assertEqual(text.count("$.process.run("), 1, "every command goes through run(), which this test reads")
        for argv in runs:
            if argv.startswith(("'aidd', 'approve', ", "'aidd', 'land', ")) or argv == "'aidd', 'publish', '--show'":
                continue  # held above: --show or --confirmed only; publish only shows what would leave
            for word in ("merge", "land", "publish", "push", "commit"):
                self.assertNotIn(f"'{word}'", argv, word)

    def test_the_approval_comes_only_from_a_typed_prompt_and_the_persons_answer(self):
        text = source()
        # Only a prompt the engine stamped as typed at this terminal, and not a hidden one or a slash command.
        self.assertIn("const typedHere = e.origin.kind === 'composer' && !e.isMeta && !e.command", text)
        self.assertIn("if (typedHere && isLand(e.text))", text)
        self.assertIn("const asked = typedHere ? approvalIds(e.text) : null", text)
        self.assertIn("const standing = typedHere ? standingAsked(e.text) : null", text)
        # The person's own typed words are the decision; a request from anywhere else asks in the dialog first, and
        # only its exact Approve label confirms, the safe answer offered first.
        self.assertIn("const askFirst = e.origin.kind !== 'composer'", text)
        helper = text[text.index("async function confirmed(") :]
        helper = helper[: helper.index("\n}\n")]
        self.assertIn("options: [NOT_NOW, APPROVE] })) === APPROVE", helper)
        for flow in (
            "async function approveFromPrompt",
            "async function approveMergeFromPrompt",
            "async function landFromPrompt",
            "async function standingFromPrompt",
        ):
            body = text[text.index(flow) :]
            body = body[: body.index("\n}\n")]
            self.assertLess(body.index("if (askFirst && !(await confirmed("), body.index("'--confirmed'"), flow)
        # An update and an install write only after their dialog.
        for flow, write in (
            ("async function updateFromCommand", "'self-update'], UPDATE_TIMEOUT_MS"),
            ("async function initFromCommand", "'init', ...flags]"),
        ):
            body = text[text.index(flow) :]
            body = body[: body.index("\n}\n")]
            self.assertLess(body.index("$.ui.ask("), body.index(write), flow)

    def test_it_never_writes_prompts_spawns_or_reaches_the_network(self):
        text = source()
        for call in NEVER:
            self.assertNotIn(call, text, call)
        # A command's `context` is read by the model; the pane writes none, and its `text` only on a failure.
        self.assertNotRegex(text, r"\bcontext:")

    def test_the_engines_generated_types_stay_out_of_git(self):
        self.assertIn("/.claude-plugin/types/", (MODS / ".gitignore").read_text(encoding="utf-8"))
        tracked = subprocess.run(["git", "ls-files", "plugins/aidd-mods"], cwd=ROOT, capture_output=True, text=True, check=False).stdout
        self.assertNotIn(".claude-plugin/types/", tracked)


if __name__ == "__main__":
    unittest.main()
