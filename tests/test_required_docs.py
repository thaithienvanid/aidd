"""The required-docs matrix is a list of condition rows per document type: the highest level any matching row gives wins.

The test plan is the case that needs it: it warns on every major and on a normal change with compliance on, it is only
a suggestion on any other normal change, and a minor change asks for none. A living component plan warns separately.
"""

import unittest
from unittest import mock

import helpers  # noqa: F401  (puts src/ on the path)
from aidd import config, workitems
from aidd.workitems import authoring

OFF = 'aidd_version: "1.0.0"\nprofile: team\n\nowners:\n  approvers: ["@x"]\n'
ON = OFF + "\nproject:\n  compliance:\n    targets: [soc2]\n"
DISABLED = OFF + "\ndocs:\n  disabled:\n    test-plan: not for this library\n"

FROZEN, LIVING = False, True  # a row's `living`: the Spec's own plan, or the component's


def asks(*, route: str, cfg: str = OFF, scope: str = "src/cart/", **spec) -> list[tuple[str, bool | None]]:
    """The test-plan asks for a Spec on `route`, as (level, living), read as every check reads a Spec: in today's shape."""
    data = workitems.todays_shape({"type": "spec", "route": route, "change_type": "feat", "tasks": [{"scope": [scope]}], "risk": {"dimensions": []}, **spec})
    return [(a.level, a.living) for a in authoring.required_docs(data, config.load_text(cfg)) if a.doc_type == "test-plan"]


WARN_FROZEN, SUGGEST_FROZEN, WARN_LIVING = ("warn", FROZEN), ("suggest", FROZEN), ("warn", LIVING)


class TestPlanByRoute(unittest.TestCase):
    CASES = [
        # (name, route, config, the Spec's own fields, the asks)
        ("minor asks nothing", "minor", OFF, {}, []),
        ("minor with compliance on asks nothing", "minor", ON, {}, []),
        ("minor with a device path asks nothing", "minor", OFF, {"scope": "ios/App.swift"}, []),
        ("normal only suggests", "normal", OFF, {}, [SUGGEST_FROZEN]),
        ("normal with manual acceptance only suggests", "normal", OFF, {"manual_acceptance": True}, [SUGGEST_FROZEN]),
        ("normal on a device path only suggests", "normal", OFF, {"scope": "ios/App.swift"}, [SUGGEST_FROZEN]),
        ("normal with a compliance dimension warns", "normal", OFF, {"risk": {"dimensions": ["compliance"]}}, [WARN_FROZEN]),
        ("normal of change type compliance, a Spec before 1.0.0 read as its dimension, warns", "normal", OFF, {"change_type": "compliance"}, [WARN_FROZEN]),
        ("normal with compliance on warns, and asks for the living plan", "normal", ON, {}, [WARN_FROZEN, WARN_LIVING]),
        ("major warns", "major", OFF, {}, [WARN_FROZEN]),
        ("major with manual acceptance warns", "major", OFF, {"manual_acceptance": True}, [WARN_FROZEN]),
        ("major on a device path warns", "major", OFF, {"scope": "android/app/"}, [WARN_FROZEN]),
        ("major with compliance on also asks for the living plan", "major", ON, {}, [WARN_FROZEN, WARN_LIVING]),
        ("docs.disabled turns every row off", "major", DISABLED, {}, []),
        ("docs.disabled turns every row off, compliance on", "normal", DISABLED + "\nproject:\n  compliance:\n    targets: [soc2]\n", {}, []),
    ]

    def test_each_route_and_trigger(self):
        for name, route, cfg, fields, want in self.CASES:
            with self.subTest(name):
                self.assertEqual(asks(route=route, cfg=cfg, **fields), want)

    def test_the_highest_level_wins_whatever_the_row_order(self):
        for rows in ([{"suggest": ["normal"]}, {"routes": ["normal"]}], [{"routes": ["normal"]}, {"suggest": ["normal"]}]):
            with mock.patch("aidd.config.model.default_docs_required", return_value={"x": rows}):
                (ask,) = authoring.required_docs({"route": "normal"}, config.load_text(OFF))
            self.assertEqual((ask.level, ask.living), ("warn", None), rows)

    def test_every_type_holds_a_list_of_rows(self):
        for doc_type, rows in config.default_docs_required().items():
            with self.subTest(doc_type):
                self.assertIsInstance(rows, list)
                self.assertTrue(rows and all(isinstance(r, dict) for r in rows))

    def test_the_highest_level_wins_and_its_row_gives_the_reason(self):
        data = {"route": "normal", "change_type": "feat", "tasks": [], "risk": {"dimensions": ["compliance"]}}
        (ask,) = [a for a in authoring.required_docs(data, config.load_text(OFF)) if a.doc_type == "test-plan"]
        self.assertEqual(ask.level, "warn")
        self.assertIn("risk compliance", ask.why)


if __name__ == "__main__":
    unittest.main()
