"""A command renders the team files once per set of arguments, and every answer is the one a fresh render gives.

Invariant: inside `team_install.rendered_once`, `team_files(...)` returns exactly what the render returns for those arguments,
for every argument, however often it is asked and whatever a caller does to an answer; and the scope ends with the command.
"""

from __future__ import annotations

import itertools
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers

from aidd.setup import adoption, doctor_checks, team_install, uninstalling, upgrading

HARNESSES = list(team_install.NATIVE_AGENT_HARNESSES)
# Every shape of argument a caller passes: no harness, one, all, with and without Claude Code's files, the config's models and settings, and the packs.
HARNESS_SETS = [[], HARNESSES[:1], HARNESSES]
CHOICES = list(
    itertools.product(
        HARNESS_SETS,
        (True, False),
        (None, {"developer": "inherit"}),
        (None, {"effort": {"developer": "high"}, "max_turns": {}}),
        (None, ["ai-features"]),
    )
)


class TheRenderIsOncePerArgumentsAndTheSameAnswer(unittest.TestCase):
    def test_every_answer_in_a_scope_equals_the_fresh_render(self):
        fresh = [team_install.team_files(*choice) for choice in CHOICES]
        with team_install.rendered_once():
            first = [team_install.team_files(*choice) for choice in CHOICES]
            again = [team_install.team_files(*choice) for choice in reversed(CHOICES)][::-1]
        self.assertEqual(first, fresh)
        self.assertEqual(again, fresh)

    def test_a_scope_renders_each_set_of_arguments_once_and_no_scope_renders_each_time(self):
        asked = list(CHOICES[:6])
        with mock.patch.object(team_install, "_render_team_files", wraps=team_install._render_team_files) as render:
            for choice in asked * 3:
                team_install.team_files(*choice)
            self.assertEqual(render.call_count, 18, "the control: with no scope, every call renders")
            render.reset_mock()
            with team_install.rendered_once():
                for choice in asked * 3:
                    team_install.team_files(*choice)
            self.assertEqual(render.call_count, 6)

    def test_a_skill_is_read_once_whatever_arguments_ask_for_it(self):
        """Most of a render is reading the skills, and fewer packs ask for a subset of the skills the first call read."""
        every, fewer = ([], True), ([], True, None, None, [])
        with mock.patch.object(Path, "rglob", autospec=True, side_effect=Path.rglob) as scans:
            with team_install.rendered_once():
                team_install.team_files(*every)
                first = scans.call_count
                team_install.team_files(*fewer)
                self.assertEqual(scans.call_count, first, "a skill read for the first call was read again")
            scans.reset_mock()
            team_install.team_files(*every)
            first = scans.call_count
            team_install.team_files(*fewer)
            self.assertGreater(scans.call_count, first, "the control: with no scope, the second call reads the skills again")

    def test_a_caller_that_changes_an_answer_changes_no_later_one(self):
        choice = ([], True, None, None, None)
        with team_install.rendered_once():
            first = team_install.team_files(*choice)
            expected = dict(first)
            first.clear()
            first["junk"] = "x"
            self.assertEqual(team_install.team_files(*choice), expected)

    def test_a_scope_inside_another_shares_it_and_none_is_left_open(self):
        with team_install.rendered_once():
            outer = team_install._RENDERED.get()
            with team_install.rendered_once():
                self.assertIs(team_install._RENDERED.get(), outer)
        self.assertIsNone(team_install._RENDERED.get())


class AWholeCommandRendersOnce(unittest.TestCase):
    def test_init_upgrade_uninstall_and_the_doctor_each_render_in_one_scope(self):
        seen: dict[str, list[bool]] = {name: [] for name in ("init", "upgrade", "uninstall", "doctor")}

        def watch(name: str):
            real = team_install._render_team_files

            def spy(*args, **kwargs):
                seen[name].append(team_install._RENDERED.get() is not None)
                return real(*args, **kwargs)

            return spy

        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp).resolve() / "fresh"
            fresh.mkdir()
            helpers.git(fresh, "init", "-q", "-b", "main")
            adopted = helpers.make_repo(Path(tmp).resolve() / "adopted", aidd_team=True, harnesses=["codex"])
            with mock.patch.object(team_install, "_render_team_files", watch("init")):
                adoption.init(
                    fresh, adoption.InitOptions(profile="solo", ci="none", links=[], harnesses=["codex"], approvers=["@x"], skill=False, aidd_team=True)
                )
            with mock.patch.object(team_install, "_render_team_files", watch("upgrade")):
                upgrading.upgrade(adopted)
            with mock.patch.object(team_install, "_render_team_files", watch("uninstall")):
                uninstalling.uninstall(adopted)
            with mock.patch.object(team_install, "_render_team_files", watch("doctor")):
                doctor_checks.doctor(adopted)
        for name, answers in seen.items():
            with self.subTest(command=name):
                self.assertTrue(answers and all(answers), "the command rendered with no scope open")
        self.assertIsNone(team_install._RENDERED.get(), "a scope outlived its command")


if __name__ == "__main__":
    unittest.main()
