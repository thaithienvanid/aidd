"""Limits: the numbers that change what aidd decides or shows. The config schema owns each default, range, and direction; code and
text read them there. For every limit, a project can only move it the way its direction allows, a number outside its range fails
the config's load at its line with the range and the next step, and with nothing set every effective value is what it was before
the limits had a home (START below)."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
import work_page_fixtures as fx
from helpers import ROOT

from aidd import config, knowledge, views
from aidd.cli.commands import risk_answers
from aidd.config import limits, locks
from aidd.delegation import parts
from aidd.kernel import json_schema, resources
from aidd.knowledge import team_registry
from aidd.setup import team_install
from aidd.testing import runner, target_view
from aidd.workitems import status

HEAD = 'aidd_version: "1.0.0"\nprofile: solo\n'

# Every effective value with nothing set, as it was when each was a constant in code or a number in prose.
START = {
    "limits.max_task_retries": 3,
    "limits.min_fix_review_lines": 20,
    "limits.max_fix_lines": 50,
    "limits.retrospective_every.days": 14,
    "limits.retrospective_every.merges": 20,
    "limits.max_paths_shown": 50,
    "docs.max_review_age_days": 180,
    "docs.max_runbook_age_days": 180,
    "tests.timeout_seconds": 1800,
    "tests.reruns": 0,
}
START_PACKET = {
    "request": 8000,
    "person_request": 8000,
    "claimed_request": 8000,
    "acceptance": 12000,
    "design": 8000,
    "concerns": 4000,
    "rollback": 4000,
    "tasks": 6000,
    "risk": 3000,
    "commit_subjects": 6000,
}


def load(extra: str) -> config.Config:
    return config.load_text(HEAD + extra)


class EveryValueWithNothingSetIsWhatItWas(unittest.TestCase):
    def test_the_schema_defaults(self):
        for path, was in START.items():
            with self.subTest(path):
                self.assertEqual(config.setting_default(path), was)
                self.assertEqual(config.EMPTY.setting(path) if not path.startswith("tests.") else was, was)

    def test_the_fixed_limits_and_the_sizes_the_evidence_owns(self):
        self.assertEqual(parts.caps(), START_PACKET)
        self.assertEqual(parts.max_diffstat_files(), 300)
        self.assertEqual(json_schema.keyword_at(target_view.CHANGES, "maxItems"), 10)
        self.assertEqual(json_schema.keyword_at(runner.DIRTY_PATHS, "maxItems"), 50)

    def test_the_texts_the_registry_renders_say_the_defaults(self):
        rules = knowledge.roles()["graph"]["shared_rules"]
        self.assertTrue(any(r.startswith("At most 3 retries per Task") for r in rules), rules)
        fix = next(f for f in knowledge.roles()["graph"]["flows"] if f["command"] == "fix")
        self.assertIn("within 50 changed lines", fix["when"])
        self.assertIn("over 20 changed lines", fix["stops_when"])
        self.assertNotIn("{{", json.dumps(knowledge.roles()), "a limit's mark is always replaced")

    def test_a_mark_naming_no_limit_raises(self):
        with self.assertRaises(KeyError):
            team_registry.with_limits({"rule": "at most {{limit:no_such_limit}}"})

    def test_a_role_file_keeps_its_number_when_no_turn_limit_is_set(self):
        """Every generated role file is the same with `agents.max_turns` unset, empty, or the role's own number."""
        roles = knowledge.roles()["roles"]
        none, empty = team_install.team_files(["claude-code"], True), team_install.team_files(["claude-code"], True, None, {"max_turns": {}})
        self.assertEqual(none, empty)
        for key, role in roles.items():
            with self.subTest(key):
                path = f".claude/agents/aidd-{key}.md"
                self.assertIn(f"\nmaxTurns: {role['max_turns']}\n", none[path])
                same = team_install.team_files(["claude-code"], True, None, {"max_turns": {key: role["max_turns"]}})
                self.assertEqual(same[path], none[path])


class EveryLimitKeepsItsDirection(unittest.TestCase):
    def test_a_limit_a_project_may_only_lower_has_its_default_as_the_ceiling(self):
        for name in limits.names():
            node = limits.schema_node(f"limits.{name}")
            with self.subTest(name):
                self.assertIn(node["type"], ("integer",))
                self.assertTrue(node["minimum"] <= node["default"] <= node["maximum"])
                self.assertIn(node["x-project-may"], ("lower", "raise", "any"))
                if node["x-project-may"] == "lower":
                    self.assertEqual(node["maximum"], node["default"], "a project may not loosen it")
                if node["x-project-may"] == "raise":
                    self.assertEqual(node["minimum"], node["default"])

    def test_a_limit_that_guards_a_control_is_not_free(self):
        guarded = {"max_task_retries", "min_fix_review_lines", "max_fix_lines"}
        free = {name for name in limits.names() if limits.may(name) == "any"}
        self.assertEqual(guarded & free, set())
        self.assertEqual({n for n in limits.names() if limits.may(n) == "lower"}, guarded)

    def test_the_turn_limit_ceiling_is_the_most_aidd_ships(self):
        bound = json_schema.deref(limits.schema_node("agents.max_turns")["additionalProperties"], "config.schema.json")[0]
        shipped = [r["max_turns"] for r in knowledge.roles()["roles"].values()]
        self.assertEqual(bound["maximum"], max(shipped))
        self.assertTrue(all(bound["minimum"] <= n <= bound["maximum"] for n in shipped))


class AnOutOfRangeValueFailsTheLoadAtItsLine(unittest.TestCase):
    ROWS = (
        # (a config's lines after the header, whether it loads, a word its error holds)
        ("limits:\n  max_task_retries: 3\n", True, ""),
        ("limits:\n  max_task_retries: 1\n", True, ""),
        ("limits:\n  max_task_retries: 4\n", False, "1 to 3, and a project may only lower it"),
        ("limits:\n  max_task_retries: 0\n", False, "1 to 3"),
        ("limits:\n  max_task_retries: -1\n", False, "1 to 3"),
        ("limits:\n  max_task_retries: many\n", False, "1 to 3"),
        ("limits:\n  max_task_retries: 2.5\n", False, "1 to 3"),
        ("limits:\n  max_task_retries: true\n", False, "1 to 3"),
        ("limits:\n  min_fix_review_lines: 20\n", True, ""),
        ("limits:\n  min_fix_review_lines: 21\n", False, "1 to 20"),
        ("limits:\n  max_fix_lines: 50\n", True, ""),
        ("limits:\n  max_fix_lines: 51\n", False, "1 to 50"),
        ("limits:\n  max_paths_shown: 500\n", True, ""),
        ("limits:\n  max_paths_shown: 501\n", False, "1 to 500"),
        ("limits:\n  max_paths_shown: 0\n", False, "1 to 500"),
        ("limits:\n  retrospective_every:\n    days: 365\n    merges: 1000\n", True, ""),
        ("limits:\n  retrospective_every:\n    days: 366\n", False, "1 to 365"),
        ("limits:\n  retrospective_every:\n    merges: 0\n", False, "1 to 1000"),
        ("agents:\n  max_turns:\n    execution: 500\n    developer: 10\n", True, ""),
        ("agents:\n  max_turns:\n    execution: 501\n", False, "10 to 500 turns"),
        ("agents:\n  max_turns:\n    developer: 9\n", False, "10 to 500 turns"),
        ("agents:\n  max_turns:\n    developer: 0\n", False, "10 to 500 turns"),
        ("agents:\n  max_turns:\n    developer: -5\n", False, "10 to 500 turns"),
        ("agents:\n  max_turns:\n    developer: lots\n", False, "10 to 500 turns"),
    )

    def test_each_row(self):
        for extra, loads, word in self.ROWS:
            with self.subTest(extra=extra):
                if loads:
                    load(extra)
                    continue
                with self.assertRaises(config.ConfigError) as caught:
                    load(extra)
                message = str(caught.exception)
                self.assertRegex(message, r"line \d+: \$\.(limits|agents)\.", "it names the line and the key")
                self.assertIn(word, message)
                self.assertIn("Remove the line to use", message, "it says the next step")

    def test_a_name_that_is_no_limit_fails_with_the_close_one(self):
        with self.assertRaises(config.ConfigError) as caught:
            load("limits:\n  max_task_retrys: 2\n")
        self.assertIn("max_task_retries", str(caught.exception))


class ALimitInTheConfigIsRead(unittest.TestCase):
    def test_the_values_a_project_sets(self):
        cfg = load("limits:\n  max_task_retries: 2\n  max_paths_shown: 7\n  retrospective_every:\n    days: 7\n")
        self.assertEqual((cfg.max_task_retries, cfg.max_paths_shown), (2, 7))
        self.assertEqual((cfg.setting("limits.retrospective_every.days"), cfg.setting("limits.retrospective_every.merges")), (7, 20))

    def test_a_child_never_loosens_what_a_parent_set(self):
        """Table: the parent's value, the child's, and the merged one, by direction."""
        for name, parent, child, merged in (
            ("max_task_retries", 2, 3, 2),  # lower only: the lower stays
            ("max_task_retries", 2, 1, 1),
            ("max_fix_lines", 30, 50, 30),
            ("max_paths_shown", 10, 40, 40),  # any: the child's
            ("max_paths_shown", 40, 10, 10),
        ):
            with self.subTest(name=name, parent=parent, child=child):
                self.assertEqual(limits.merged({name: parent}, {name: child}), {name: merged})
        self.assertEqual(
            limits.merged({"retrospective_every": {"days": 7}}, {"retrospective_every": {"merges": 5}}), {"retrospective_every": {"days": 7, "merges": 5}}
        )

    def test_a_child_file_never_loosens_its_parent_file(self):
        parent = HEAD + "limits:\n  max_task_retries: 2\n  max_paths_shown: 10\n"
        for child_value, want in ((3, 2), (1, 1)):
            with self.subTest(child=child_value):
                child = HEAD + f"extends: [{{path: parent.yaml}}]\nlimits:\n  max_task_retries: {child_value}\n  max_paths_shown: 40\n"
                cfg = config.load_text(child, read=lambda rel: parent if rel == "parent.yaml" else None)
                self.assertEqual((cfg.max_task_retries, cfg.max_paths_shown), (want, 40))

    def test_a_parent_lock_drops_the_childs_value(self):
        parent = HEAD + "limits:\n  max_task_retries: 2\nlocks: [limits.max_task_retries]\n"
        child = HEAD + "extends: [{path: parent.yaml}]\nlimits:\n  max_task_retries: 1\n  max_paths_shown: 9\n"
        cfg = config.load_text(child, read=lambda rel: parent if rel == "parent.yaml" else None)
        self.assertEqual((cfg.max_task_retries, cfg.max_paths_shown), (2, 9))
        self.assertTrue(any("max_task_retries" in w for w in cfg.warnings), cfg.warnings)

    def test_limits_is_a_key_a_parent_can_lock(self):
        self.assertIn("limits", locks.lockable())


class TheTaskRetryLimitDecidesWhenATaskStops(unittest.TestCase):
    """Table: the limit, the retries a Task used, and whether it is stopped. The boundary, one below, and one past."""

    def test_each_row(self):
        for limit, used, stopped in ((3, 2, False), (3, 3, True), (2, 1, False), (2, 2, True), (2, 3, True), (1, 0, False), (1, 1, True)):
            with self.subTest(limit=limit, used=used):
                data = {"tasks": [{"id": "T1", "title": "t", "scope": ["a/**"], "retry_count": used}]}
                (task,) = status.task_states(data, "in_progress", limit)
                self.assertEqual(task["status"] == "stopped", stopped)
                self.assertEqual(bool(status.retries_used(data, limit)), stopped)
                self.assertEqual(any("retries" in r for r in status.blocked_reasons(data, "in_progress", limit)), stopped)
                if stopped:
                    self.assertIn(f"used its {limit} retries", task["why"])


class ThePageSaysTheLimitTheConfigSets(unittest.TestCase):
    def test_a_stopped_task_reads_its_retries_of_the_limit(self):
        item = fx.blocked_spec()
        for limit, want in ((None, "3 of 3 retries"), (2, "3 of 2 retries"), (1, "3 of 1 retries")):
            with self.subTest(limit=limit):
                html = views.status_page({"schema_version": "1", "items": [item], "due": []}, written=fx.WRITTEN, retry_limit=limit)
                self.assertIn(f"Blocked, {want}", html)


class TheRunnerReadsTheSchemasDefaultsForACommandThatSetsNone(unittest.TestCase):
    """Table: a command with no `timeout_seconds` or `reruns` runs with the schema's; one that sets its own keeps it."""

    def run_one(self, command: dict, phase: str = "green") -> tuple[list[int], int]:
        seen: list[int] = []

        def fake(argv, **kwargs):
            seen.append(kwargs["timeout_seconds"])
            return {"status": "failed", "exit_code": 1}

        with tempfile.TemporaryDirectory() as tmp, mock.patch("aidd.testing.runner.run_test_command", fake):
            result = runner._run({"name": "unit", "command": ["x"], **command}, phase, "config", tmp, Path(tmp), [])
        return seen, len(result.get("attempts", [result]))

    def test_each_row(self):
        for command, phase, timeouts in (
            ({}, "green", [1800]),
            ({"timeout_seconds": 60}, "green", [60]),
            ({"reruns": 2}, "green", [1800, 1800, 1800]),
            ({"reruns": 2}, "red", [1800]),
        ):
            with self.subTest(command=command, phase=phase):
                self.assertEqual(self.run_one(command, phase)[0], timeouts)


class ThePathListShowsWhatTheLimitSays(unittest.TestCase):
    def test_the_area_list_is_cut_at_the_limit_and_says_so(self):
        for shown, count in ((2, 1), (2, 2), (2, 3), (1, 5)):
            with self.subTest(shown=shown, count=count):
                answer = {"areas": [{"area": "auth", "paths": [f"p{i}" for i in range(count)]}], "hints": [], "route": "major", "edit": {"level": "ask"}}
                out = risk_answers.cap_area_paths(answer, shown)
                (hit,) = out["areas"]
                self.assertEqual((len(hit["paths"]), hit["path_count"]), (min(shown, count), count))
                self.assertEqual(bool(out["hints"]), count > shown, "a cap that cuts says so")
                self.assertEqual((out["route"], out["edit"]), ("major", {"level": "ask"}), "the cap decides nothing")

    def test_aidd_risk_as_a_person_runs_it_with_the_limit_set(self):
        files = [f"src/auth/f{i}.py" for i in range(5)]
        with helpers.adopted_repo("solo", branch=None) as root:
            cfg = root / config.CONFIG_PATH
            cfg.write_text(cfg.read_text(encoding="utf-8") + "\nlimits:\n  max_paths_shown: 3\n", encoding="utf-8")
            (root / "src" / "auth").mkdir(parents=True)
            for rel in files:
                (root / rel).write_text("x = 1\n", encoding="utf-8")
            helpers.git(root, "add", "-A")
            helpers.git(root, "commit", "-q", "-m", "files")
            run = helpers.aidd_here("risk", "--paths", *files, "--json", cwd=root)
            self.assertEqual(run.returncode, 0, run.stderr)
            data = json.loads(run.stdout)
            hit = next(a for a in data["areas"] if a["area"] == "auth")
            self.assertEqual((len(hit["paths"]), hit["path_count"]), (3, 5))
            self.assertEqual(data["route"], "major", "the route reads every path, whatever is shown")


class ATurnLimitReachesOnlyClaudeCodesRoleFiles(unittest.TestCase):
    SETTINGS = {"max_turns": {"execution": 150, "reviewer": 120}}

    def test_the_role_its_tier_and_the_rest(self):
        roles = knowledge.roles()["roles"]
        files = team_install.team_files(["claude-code", "codex", "opencode"], True, None, self.SETTINGS)
        for key, role in roles.items():
            want = 120 if key == "reviewer" else 150 if role["tier"] == "execution" else role["max_turns"]
            with self.subTest(key):
                self.assertIn(f"\nmaxTurns: {want}\n", files[f".claude/agents/aidd-{key}.md"])
        other = {rel: text for rel, text in files.items() if not rel.startswith(".claude/agents/")}
        self.assertFalse([rel for rel, text in other.items() if "maxTurns" in text and "agents/" in rel], "no other harness's agent file has a turn limit")

    def test_a_key_that_names_no_tier_and_no_role_is_warned_about(self):
        self.assertTrue(knowledge.unknown_key_warnings({"developr": 100}, "max_turns"))
        self.assertEqual(knowledge.unknown_key_warnings({"developer": 100, "execution": 100}, "max_turns"), [])

    def test_the_resolution_prefers_the_role_then_the_tier(self):
        self.assertEqual(knowledge.resolve_agent_turns({"developer": 120, "execution": 150}, "developer"), 120)
        self.assertEqual(knowledge.resolve_agent_turns({"execution": 150}, "developer"), 150)
        self.assertIsNone(knowledge.resolve_agent_turns({"reasoning": 150}, "developer"))
        self.assertIsNone(knowledge.resolve_agent_turns({}, "developer"))


def restated_defaults(node, where: str) -> list[str]:
    """Where a schema's description states the integer default its own node gives: `Default 3`, `default is 180`."""
    found: list[str] = []
    if isinstance(node, dict):
        if isinstance(node.get("default"), int) and not isinstance(node["default"], bool):
            if restated := re.search(rf"efault[^.]*\b{node['default']}\b", node.get("description", "")):
                found.append(f"{where}: {restated.group(0)}")
        for key, sub in node.items():
            found += restated_defaults(sub, f"{where}/{key}")
    elif isinstance(node, list):
        for i, sub in enumerate(node):
            found += restated_defaults(sub, f"{where}/{i}")
    return found


class NoNumberHasTwoOwners(unittest.TestCase):
    """A number a schema default owns is never stated again in the schema's own words, and the prose that states one agrees."""

    def test_no_description_restates_its_default(self):
        for name in ("config.schema.json", "common.schema.json"):
            self.assertEqual(restated_defaults(resources.load_json(name), name), [], "the generated table adds the default; the description must not state it")

    # (file, a pattern whose groups are the numbers it states, the limits they must equal, in order)
    PROSE = (
        (".agents/skills/aidd/SKILL.md", r"at most (\d+) per Task \(`limits\.max_task_retries`", ("limits.max_task_retries",)),
        ("docs/METHOD.md", r"retry a Task at most (\d+) times, or fewer when `limits\.max_task_retries`", ("limits.max_task_retries",)),
        (
            "docs/METHOD.md",
            r"every (\d+) days or (\d+) merged changes unless `limits\.retrospective_every`",
            ("limits.retrospective_every.days", "limits.retrospective_every.merges"),
        ),
        (
            ".agents/skills/aidd/references/observe-learn.md",
            r"Every (\d+) days or (\d+) merged changes, or as `limits\.retrospective_every`",
            ("limits.retrospective_every.days", "limits.retrospective_every.merges"),
        ),
        ("plugins/aidd-team/commands/fix.md", r"retrying at most (\d+) times \(`limits\.max_task_retries`", ("limits.max_task_retries",)),
        ("plugins/aidd-team/commands/fix.md", r"at most (\d+) changed lines \(`limits\.max_fix_lines`", ("limits.max_fix_lines",)),
        ("plugins/aidd-team/commands/fix.md", r"more than (\d+) changed lines \(`limits\.min_fix_review_lines`", ("limits.min_fix_review_lines",)),
        ("docs/CLI.md", r"at most (\d+) paths of each area, unless `limits\.max_paths_shown`", ("limits.max_paths_shown",)),
    )

    def test_each_sentence_agrees_with_the_default_it_names(self):
        for rel, pattern, names in self.PROSE:
            with self.subTest(rel=rel, names=names):
                found = re.search(pattern, (ROOT / rel).read_text(encoding="utf-8"))
                self.assertIsNotNone(found, f"{rel} no longer states {names}: update this row with the sentence")
                self.assertEqual([int(n) for n in found.groups()], [config.setting_default(n) for n in names])


class NoDecidingCodeReadsALimitFromTheHead(unittest.TestCase):
    """The run, the delegate, and the risk rules decide controls. A limit in the config comes from the head under review, so none of
    these reads one; the packet's limits are aidd's own data (schemas/risks.json), and the run's bounds come from the base view."""

    def test_no_file_there_reads_the_limits_group_or_the_setting_reader(self):
        found = []
        for folder in ("delegation", "testing", "risk"):
            for path in sorted((ROOT / "src" / "aidd" / folder).glob("*.py")):
                text = path.read_text(encoding="utf-8")
                found += [
                    f"{path.name}: {m}"
                    for m in re.findall(r"limits\.[a-z_]+|\.setting\(|max_task_retries|max_paths_shown|\.max_(?:review|runbook)_age_days", text)
                ]
        # the run reads a test command's own default (`config.setting_default`), which is the schema's, never a project's value
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
