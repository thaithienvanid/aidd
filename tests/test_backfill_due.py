"""An emergency change has one deadline for its backfill Spec and its review: the stored `emergency.backfill_due`, a calendar
day compared with the local date of the machine that runs aidd. One function reads it (`due_dates.backfill_overdue`): the day
itself is in time, the day after is overdue until `outcome.learn_ref` records the review, and a date that is absent or none is
never overdue. `aidd validate`, `aidd status`, and the work-item page give the same answer on every row."""

import datetime as dt
import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import ROOT

from aidd import config, views, workitems
from aidd.setup import adoption
from aidd.workitems import due_dates, validation

DUE = dt.date(2026, 9, 24)
INC = (ROOT / "tests" / "fixtures" / "specs" / "INC-481.md").read_text(encoding="utf-8")
LEARNED = "\noutcome:\n  learn_ref: docs/postmortems/inc-481.md\n---\n"

# (the case, what the block's date says, whether a review is recorded, today, whether the backfill is overdue)
CASES = [
    ("the day before", '"2026-09-24"', False, DUE - dt.timedelta(days=1), False),
    ("the day itself", '"2026-09-24"', False, DUE, False),
    ("the day after", '"2026-09-24"', False, DUE + dt.timedelta(days=1), True),
    ("a month after", '"2026-09-24"', False, DUE + dt.timedelta(days=31), True),
    ("the day after, reviewed", '"2026-09-24"', True, DUE + dt.timedelta(days=1), False),
    ("a date in the future", '"2099-01-01"', False, DUE, False),
    ("a timestamp, which is no date", '"2026-09-24T00:00:00Z"', False, DUE + dt.timedelta(days=1), False),
    ("no date", "next tuesday", False, DUE + dt.timedelta(days=1), False),
    ("absent", None, False, DUE + dt.timedelta(days=1), False),
]


def spec_text(due: str | None, learned: bool) -> str:
    text = INC.replace('  backfill_due: "2026-09-24"\n', f"  backfill_due: {due}\n" if due is not None else "")
    return text.replace("\n---\n", LEARNED, 1) if learned else text


class TheOneReading(unittest.TestCase):
    def test_the_boundary_rows(self):
        for name, due, learned, today, overdue in CASES:
            with self.subTest(name):
                data = {"route": "emergency", "emergency": {} if due is None else {"backfill_due": due.strip('"')}}
                if learned:
                    data["outcome"] = {"learn_ref": "x"}
                self.assertEqual(due_dates.backfill_overdue(data, today), overdue)

    def test_only_an_emergency_has_one(self):
        data = {"route": "normal", "emergency": {"backfill_due": "2020-01-01"}}
        self.assertFalse(due_dates.backfill_overdue(data, DUE))
        self.assertIsNone(due_dates.backfill_due({"emergency": {"backfill_due": 20260924}}))


class ADateFarAhead(unittest.TestCase):
    """Nothing makes an author write the backfill's date near, so a date past the horizon warns, as a delegation's `review_due` far
    ahead does, and blocks nothing: the day of the horizon is in time, the day after warns, and a past date is the overdue error's."""

    def test_the_horizon_rows(self):
        horizon = due_dates.BACKFILL_HORIZON_DAYS
        for name, days, route, warns in (
            ("the day itself", 0, "emergency", False),
            ("the horizon", horizon, "emergency", False),
            ("the day after the horizon", horizon + 1, "emergency", True),
            ("ten years", 3650, "emergency", True),
            ("a past date", -5, "emergency", False),
            ("another route", 3650, "normal", False),
        ):
            with self.subTest(name):
                data = {"route": route, "emergency": {"backfill_due": (DUE + dt.timedelta(days=days)).isoformat()}}
                warning = due_dates.backfill_horizon_warning("specs/INC-481.md", data, DUE)
                self.assertEqual(warning is not None, warns, warning)
                if warning:
                    self.assertIn(f"{horizon} days", warning, "the warning says the horizon")


class EveryReaderAgrees(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.template = Path(cls.tmp.name) / "repo"
        cls.template.mkdir()
        adoption.init(cls.template, adoption.InitOptions(profile="team", ci="none", links=[], skill=False, approvers=["@lead"], harnesses=[]))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def readers(self, text: str, today: dt.date) -> tuple[bool, bool, bool, bool]:
        """(`aidd validate` fails on the review, `aidd status` says overdue, the page's heading and its banner say overdue) for one Spec."""
        root = Path(self.tmp.name) / f"r{len(list(Path(self.tmp.name).iterdir()))}"
        shutil.copytree(self.template, root, symlinks=True)
        (root / "specs" / "INC-481.md").write_text(text, encoding="utf-8")
        errors, _ = validation.check_repo(root, today=today)
        cfg = config.load_file(config.CONFIG_PATH, str(root))
        answer = workitems.open_work(root, cfg, today=today)
        [item] = [i for i in answer["items"] if i["id"] == "INC-481"]
        page = views.status_page({"schema_version": "1", **answer}, written=dt.datetime.combine(today, dt.time(12)))
        banner = 'data-overdue="true"' in page
        return any("post-incident review was due" in e for e in errors), item.get("backfill_overdue") is True, "The review is overdue" in page, banner

    def test_validate_status_and_the_page_say_the_same(self):
        for name, due, learned, today, overdue in CASES:
            with self.subTest(name):
                self.assertEqual(self.readers(spec_text(due, learned), today), (overdue,) * 4)

    def test_validate_warns_on_a_date_far_ahead_and_fails_nothing_for_it(self):
        root = Path(self.tmp.name) / "far"
        shutil.copytree(self.template, root, symlinks=True)
        (root / "specs" / "INC-481.md").write_text(spec_text('"2099-01-01"', False), encoding="utf-8")
        errors, warnings = validation.check_repo(root, today=DUE)
        self.assertTrue(any("emergency.backfill_due 2099-01-01" in w for w in warnings), warnings)
        self.assertFalse([e for e in errors if "backfill" in e], errors)


if __name__ == "__main__":
    unittest.main()
