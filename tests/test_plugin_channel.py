"""The Claude Code plugins' release channel: aidd adds its marketplace at the `stable` branch once a release has made it,
follows main until then and says so, and only the release job moves that branch, forward."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import ROOT

from aidd.setup import claude_plugins, pins

AIDD = {"source": "github", "repo": claude_plugins.MARKETPLACE_REPO}
STABLE = {**AIDD, "ref": pins.STABLE_BRANCH}


class ChannelCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.settings = self.root / ".claude" / "settings.json"

    def write(self, source: dict) -> None:
        """Settings as `aidd init` leaves them: aidd's marketplace at `source`, and the aidd plugin on."""
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        data = {"extraKnownMarketplaces": {"aidd": {"source": source}}, "enabledPlugins": {"aidd@aidd": True}}
        self.settings.write_text(json.dumps(data), encoding="utf-8")

    def source(self) -> dict:
        return json.loads(self.settings.read_text(encoding="utf-8"))["extraKnownMarketplaces"]["aidd"]["source"]


class SourceTests(ChannelCase):
    def test_the_source_names_stable_only_once_a_release_has_made_it(self):
        for exists, want in ((True, STABLE), (False, AIDD), (None, AIDD)):
            with self.subTest(exists=exists), mock.patch("aidd.setup.pins.stable_exists", return_value=exists):
                self.assertEqual(claude_plugins.marketplace_source(), want)

    def test_init_writes_stable_moves_its_own_entry_there_and_keeps_a_chosen_ref(self):
        cases = (
            ("no entry", None, STABLE, "enables aidd@aidd"),
            ("init's entry, from before the release", AIDD, STABLE, claude_plugins.STABLE_NOTE),
            ("a branch a person chose", {**AIDD, "ref": "main"}, {**AIDD, "ref": "main"}, "kept     .claude/settings.json"),
        )
        for name, before, after, says in cases:
            with self.subTest(name), mock.patch("aidd.setup.pins.stable_exists", return_value=True):
                self.settings.unlink(missing_ok=True)
                if before:
                    self.write(before)
                actions: list[str] = []
                self.assertTrue(claude_plugins.share_with_project(self.root, actions, aidd_team=False))
                self.assertEqual(self.source(), after)
                self.assertIn(says, actions[-1])
                self.assertNotIn("follows main", actions[-1])

    def test_before_a_release_init_follows_main_and_says_so(self):
        actions: list[str] = []
        with mock.patch("aidd.setup.pins.stable_exists", return_value=False):
            self.assertTrue(claude_plugins.share_with_project(self.root, actions, aidd_team=False))
        self.assertEqual(self.source(), AIDD)
        self.assertIn(claude_plugins.UNTIL_RELEASE, actions[-1])

    def test_another_repository_or_a_ref_not_of_aidds_is_another_source(self):
        """Only aidd's own refs count: the channel, main, or a release tag. Any other branch may be anyone's push."""
        others = (
            {"source": "github", "repo": "someone/aidd", "ref": pins.STABLE_BRANCH},
            {**AIDD, "ref": "pr-123"},
            {**AIDD, "ref": 7},
            {**AIDD, "ref": "v1.0"},
        )
        for source in others:
            self.write(source)
            actions: list[str] = []
            with self.subTest(source=source), mock.patch("aidd.setup.pins.stable_exists", return_value=True):
                self.assertFalse(claude_plugins.share_with_project(self.root, actions, aidd_team=False))
                self.assertIn("names another source", actions[-1])
        for ref in (pins.STABLE_BRANCH, "main", "v1.2.3", "v1.1.0-rc.1"):
            with self.subTest(ref=ref):
                self.assertTrue(claude_plugins.is_aidd_marketplace({"source": {**AIDD, "ref": ref}}))

    def test_no_write_goes_through_a_linked_settings_file(self):
        """A `.claude/settings.json` that links elsewhere, perhaps outside the repository, is never written through."""
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        target = Path(outside.name) / "settings.json"
        target.write_text(json.dumps({"extraKnownMarketplaces": {"aidd": {"source": AIDD}}, "enabledPlugins": {"aidd@aidd": True}}), encoding="utf-8")
        before = target.read_text(encoding="utf-8")
        self.settings.parent.mkdir(parents=True)
        self.settings.symlink_to(target)
        with mock.patch("aidd.setup.pins.stable_exists", return_value=True):
            actions: list[str] = []
            self.assertFalse(claude_plugins.share_with_project(self.root, actions, aidd_team=True))
            self.assertIn("is a link, and aidd writes nothing through a link", actions[-1])
            claude_plugins.follow_stable(self.root, actions, yes=True)
            self.assertIn("is a link", actions[-1])
        self.assertEqual(target.read_text(encoding="utf-8"), before)

    def test_the_cli_adds_the_marketplace_at_stable_once_it_exists(self):
        done = subprocess.CompletedProcess([], 0, stdout="ok", stderr="")
        for exists, want in ((True, f"{claude_plugins.MARKETPLACE_REPO}#{pins.STABLE_BRANCH}"), (False, claude_plugins.MARKETPLACE_REPO)):
            run = mock.Mock(return_value=done)
            with (
                self.subTest(exists=exists),
                mock.patch.dict(os.environ, {"AIDD_OFFLINE": "0"}),  # offline, init installs no plugin at all
                mock.patch("aidd.setup.pins.stable_exists", return_value=exists),
                mock.patch("shutil.which", return_value="/usr/bin/claude"),
                mock.patch.object(claude_plugins, "PLUGIN_RUNNER", run),
            ):
                self.assertEqual(claude_plugins.install_claude_plugins(self.root, [], aidd_team=False), ("", ["aidd@aidd"]))
                self.assertEqual(run.call_args_list[0].args[0][1:], ["plugin", "marketplace", "add", want])

    def test_upgrade_moves_inits_entry_to_stable_and_asks_github_only_for_one(self):
        self.write(AIDD)
        with mock.patch("aidd.setup.pins.stable_exists", return_value=True):
            dry: list[str] = []
            claude_plugins.follow_stable(self.root, dry, yes=False)
            self.assertEqual((dry, self.source()), ([f"would update .claude/settings.json ({claude_plugins.STABLE_NOTE})"], AIDD))
            claude_plugins.follow_stable(self.root, [], yes=True)
            self.assertEqual(self.source(), STABLE)
        for source in (STABLE, {**AIDD, "ref": "main"}):
            self.write(source)
            with self.subTest(source=source), mock.patch("aidd.setup.pins.stable_exists") as asked:
                actions: list[str] = []
                claude_plugins.follow_stable(self.root, actions, yes=True)
                self.assertEqual((actions, self.source()), ([], source))
                asked.assert_not_called()

    def test_doctor_names_the_branch_and_the_next_step(self):
        cases = (
            (STABLE, None, "ok", "at `stable`, which moves only when aidd releases"),
            (AIDD, True, "warn", "while aidd has a release: `aidd upgrade --yes` moves it to `stable`"),
            (AIDD, False, "info", "because aidd has no release yet"),
            (AIDD, None, "info", "could not ask GitHub"),
        )
        for source, exists, level, says in cases:
            self.write(source)
            with self.subTest(source=source, exists=exists), mock.patch("aidd.setup.pins.stable_exists", return_value=exists):
                (found,) = claude_plugins.channel_checks(self.root)
                self.assertEqual(found[0], level)
                self.assertIn(says, found[1])
        self.write({**AIDD, "ref": "main"})
        self.assertEqual(claude_plugins.channel_checks(self.root), [], "a branch a person chose is theirs")


class WhichPluginsTheProjectEnablesTests(ChannelCase):
    """The aidd-packs plugin's descriptions share Claude Code's skill listing budget, so a project enables it only when the repository
    calls for a domain pack, and only with the team, which its packs extend."""

    def test_the_project_enables_the_packs_plugin_only_with_the_team_and_a_pack_the_repository_calls_for(self):
        cases = (
            (False, False, ["aidd@aidd"]),
            (False, True, ["aidd@aidd"]),
            (True, False, ["aidd@aidd", "aidd-team@aidd"]),
            (True, True, ["aidd@aidd", "aidd-team@aidd", "aidd-packs@aidd"]),
        )
        for team, packs, enabled in cases:
            with self.subTest(team=team, packs=packs), mock.patch("aidd.setup.pins.stable_exists", return_value=True):
                self.settings.unlink(missing_ok=True)
                self.assertTrue(claude_plugins.share_with_project(self.root, [], aidd_team=team, packs=packs))
                self.assertEqual(sorted(json.loads(self.settings.read_text(encoding="utf-8"))["enabledPlugins"]), sorted(enabled))

    def test_a_marketplace_entry_for_the_packs_plugin_names_the_team_it_extends(self):
        market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        names = [p["name"] for p in market["plugins"]]
        self.assertIn("aidd-packs", names)
        self.assertEqual(next(p for p in market["plugins"] if p["name"] == "aidd-packs")["dependencies"], ["aidd-team"])


class StableBranchTests(unittest.TestCase):
    def test_github_says_whether_the_branch_exists_and_offline_asks_nothing(self):
        branch = f"refs/heads/{pins.STABLE_BRANCH}"
        for refs, want in (({branch: "a" * 40}, True), ({}, False), (None, None)):
            pins._stable_lookup.cache_clear()
            with (
                self.subTest(refs=refs),
                mock.patch.dict(os.environ, {"AIDD_OFFLINE": "0"}),
                mock.patch("aidd.setup.pins.remote_refs", return_value=refs) as asked,
            ):
                self.assertIs(pins.stable_exists(), want)
                self.assertIs(pins.stable_exists(), want)
                self.assertEqual((asked.call_count, asked.call_args.args[2:]), (1, (branch,)), "GitHub is asked once a process")
        pins._stable_lookup.cache_clear()
        with mock.patch("aidd.setup.pins.remote_refs") as asked:
            self.assertIsNone(pins.stable_exists())  # the tests run with AIDD_OFFLINE=1
            asked.assert_not_called()

    def test_only_a_tag_release_moves_the_branch_and_only_forward(self):
        text = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        job = text.split("\n  stable:\n", 1)[1]
        self.assertIn("    if: github.event_name == 'push' && !contains(github.ref_name, '-')", job)  # no dry run, no prerelease
        self.assertIn("    needs: release\n", job)
        self.assertIn(":refs/heads/stable", (ROOT / "RELEASING.md").read_text(encoding="utf-8"), "the push a maintainer runs when the token's move fails")
        self.assertIn(f"git/refs/heads/{pins.STABLE_BRANCH}", job)
        self.assertIn("-F force=false", job)
        self.assertNotIn("force=true", job)
        ruleset = json.loads((ROOT / ".github" / "rulesets" / "stable.json").read_text(encoding="utf-8"))
        self.assertEqual(ruleset["conditions"]["ref_name"]["include"], [f"refs/heads/{pins.STABLE_BRANCH}"])
        self.assertEqual({r["type"] for r in ruleset["rules"]}, {"deletion", "non_fast_forward", "update"})


if __name__ == "__main__":
    unittest.main()
