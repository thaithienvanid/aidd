"""A rule an organization locks is a floor: for every action, area, branch, and environment, the level with a lock is the
higher of the level without it and the lock's own, so a lock raises a level and never lowers one, and no lock placement
makes an action less careful than the built-in rule for it. The table crosses every built-in rule's place with every
placement of a lock (the exact action, its prefix, `*`; with and without the rule's own area or branch; each level)."""

from __future__ import annotations

import json
import unittest

import helpers  # noqa: F401  # the hermetic environment
from aidd import config, risk
from aidd.risk.rules import LEVEL_RANK, LEVELS

HEAD = 'aidd_version: "1.0.0"\nprofile: solo\n'
ENVIRONMENTS = "environments:\n  - {name: dev, branches: [dev], shared: false}\n"


def load(child: str = "", lock: dict | None = None) -> risk.RuleSet:
    """The rule set of a repository whose org preset locks `lock`, and whose own config holds `child`."""
    preset = None
    if lock:
        fields = ", ".join(f"{k}: {json.dumps(v)}" for k, v in lock.items())
        preset = HEAD + ENVIRONMENTS + f"risks:\n  rules:\n    - {{{fields}, locked: true}}\n"
    return risk.rule_set(config.load_text(HEAD + ENVIRONMENTS + child, root_preset=preset))


def points() -> list[dict]:
    """Where the built-in rules decide: each rule's own place, and the same action with no area or branch named."""
    out: list[dict] = []
    for rule in risk.builtin()["rules"]:
        here = {k: rule[k] for k in ("area", "branch") if rule.get(k)}
        if rule.get("environment_shared") is False:
            here["environment"] = "dev"
        for point in ({"action": rule["action"], **here}, {"action": rule["action"]}):
            if point not in out:
                out.append(point)
    return out


def level(rs: risk.RuleSet, point: dict) -> str:
    return risk.level_of(rs, point["action"], **{k: v for k, v in point.items() if k != "action"})[0]


def placements() -> list[dict]:
    """Each way a lock can name an action: exactly, by its prefix, or for every action, alone or narrowed as a built-in rule is."""
    out: list[dict] = []
    for rule in risk.builtin()["rules"]:
        for pattern in dict.fromkeys((rule["action"], rule["action"].rsplit(".", 1)[0] + ".*", "*")):
            narrows = [{}] + ([{k: rule[k]} for k in ("area", "branch") if rule.get(k)])
            for narrow in narrows:
                for lv in LEVELS:
                    lock = {"action": pattern, **narrow, "level": lv}
                    if lock not in out:
                        out.append(lock)
    return out


def covers(lock: dict, point: dict) -> bool:
    return config.action_matches(lock["action"], point["action"]) and all(point.get(k) == v for k, v in lock.items() if k in ("area", "branch"))


class ALockIsAFloor(unittest.TestCase):
    def test_a_lock_never_lowers_a_level_and_raises_it_to_its_own(self):
        """The invariant, as a table: for each lock placement and each built-in place, the level is the higher of the
        level with no lock and the lock's own where it covers the place; the built-in rules are the baseline."""
        base = load()
        baseline = {i: level(base, p) for i, p in enumerate(points())}
        asks = [p for i, p in enumerate(points()) if baseline[i] == "ask"]
        self.assertGreater(len(asks), 10, "the table holds the built-in asks it protects")
        checked = 0
        for lock in placements():
            rs = load(lock=lock)
            for i, point in enumerate(points()):
                want = max(baseline[i], lock["level"] if covers(lock, point) else "allow", key=LEVEL_RANK.__getitem__)
                got = level(rs, point)
                checked += 1
                if got != want:  # one failure line per place; a subTest per cell would take minutes
                    self.fail(f"lock {lock} at {point}: {got}, the built-in level is {baseline[i]} and the floor makes it {want}")
        self.assertGreater(checked, 10_000)

    def test_the_headline_case_an_edit_in_auth_and_payments_stays_ask_under_a_lock_at_report(self):
        for locked in ("allow", "report"):
            rs = load(lock={"action": "code.edit", "level": locked})
            with self.subTest(lock=locked):
                self.assertEqual(risk.edit_level(rs, ["src/auth/login.py"])[0], "ask")
                self.assertEqual(risk.edit_level(rs, ["src/payments/charge.py"])[0], "ask")
                self.assertEqual(risk.edit_level(rs, ["README.md"])[0], locked, "outside an asking area the lock's level is the floor")

    def test_a_lock_decides_with_a_child_rule_in_either_direction(self):
        """The child's own rules, narrower or the same, and the lock: the higher level decides, in each order of strictness."""
        for lock_level in LEVELS:
            for child_level in LEVELS:
                # A child's rule at the lock's own selector with another level is set aside by the merge, so it names a narrower one.
                for narrow, point in ((", role: developer", {"role": "developer"}), (", area: dependencies", {"area": "dependencies"})):
                    child = f"risks:\n  rules:\n    - {{action: code.edit{narrow}, level: {child_level}}}\n"
                    rs = load(child, {"action": "code.edit", "level": lock_level})
                    with self.subTest(lock=lock_level, child=child_level, narrow=narrow):
                        self.assertEqual(level(rs, {"action": "code.edit", **point}), max(lock_level, child_level, key=LEVEL_RANK.__getitem__))

    def test_the_rule_that_decides_names_the_lock_on_a_tie_and_the_higher_rule_otherwise(self):
        for lock_level, built_in, who in (("ask", "ask", "org preset"), ("report", "ask", "built-in"), ("ask", "report", "org preset")):
            rs = load(lock={"action": "code.edit", "level": lock_level})
            _, rule = risk.level_of(rs, "code.edit", area="payments" if built_in == "ask" else None)
            with self.subTest(lock=lock_level, built_in=built_in):
                self.assertTrue(rule.source.startswith(who), rule.source)

    def test_a_lock_never_lowers_a_command(self):
        """The same floor through the command reader: a lock at `allow` or `report` leaves each line at its level."""
        lines = [
            "git push --force origin main",
            "git push origin main",
            "git push origin dev",
            "git merge feature",
            "gh pr merge 5",
            "npm publish",
            "rm -rf build",
            "git status",
        ]
        base = load()
        for line in lines:
            baseline = risk.command_level(base, line)["level"]
            for pattern in ("*", "git.*", "git.push", "git.push.force", "pr.merge", "deploy.run", "release.publish"):
                for lv in ("allow", "report"):
                    with self.subTest(line=line, lock=f"{pattern}: {lv}"):
                        got = risk.command_level(load(lock={"action": pattern, "level": lv}), line)["level"]
                        self.assertGreaterEqual(LEVEL_RANK[got], LEVEL_RANK[baseline])
        self.assertEqual(risk.command_level(base, "git push --force origin main")["level"], "ask")


class AListShowsWhatALockChanges(unittest.TestCase):
    """`aidd risk --list` and `aidd doctor` read `risk.lock_effects`: which rules a lock raises, and that it lowers none."""

    def test_a_lock_names_each_covered_rule_below_its_level_and_lowers_none(self):
        for lock_level, raises, keeps in (
            ("report", ["code.edit: allow"], ["code.edit in auth: ask", "code.edit in ci: report"]),
            ("ask", ["code.edit: allow", "code.edit in ci: report"], ["code.edit in auth: ask"]),
            ("allow", [], ["code.edit: allow", "code.edit in auth: ask"]),
        ):
            lines = risk.lock_effects(load(lock={"action": "code.edit", "level": lock_level}))
            with self.subTest(lock=lock_level):
                self.assertEqual(len(lines), 1, lines)
                self.assertTrue(lines[0].endswith(f"to {lock_level}, and lowers none"), lines[0])
                for label in raises:
                    self.assertIn(label, lines[0].split(" it raises ")[1].split(" to ")[0].split(", "))
                for label in keeps:
                    self.assertNotIn(label, lines[0].split(" it raises ")[1])
                if not raises:
                    self.assertIn("it raises no rule to", lines[0])

    def test_no_lock_no_line_and_a_delegations_rise_is_no_lock_of_a_preset(self):
        self.assertEqual(risk.lock_effects(load()), [])
        from test_delegation_data import block

        delegated = config.load_text(HEAD + block())
        self.assertEqual(risk.lock_effects(risk.rule_set(delegated)), [])

    def test_the_list_prints_and_validates_it(self):
        from aidd.cli.commands import risk_answers
        from aidd.kernel import json_schema

        answer, text = risk_answers.rules_list(load(lock={"action": "code.edit", "level": "report"}))
        self.assertEqual(answer["lock_effects"], risk.lock_effects(load(lock={"action": "code.edit", "level": "report"})))
        self.assertIn("lock: code.edit: report is locked", text)
        self.assertEqual(json_schema.validate({"schema_version": "1", **answer}, "risk.schema.json#/$defs/list"), [])
        plain, plain_text = risk_answers.rules_list(load())
        self.assertEqual(plain["lock_effects"], [])
        self.assertNotIn("lock:", plain_text)


if __name__ == "__main__":
    unittest.main()
