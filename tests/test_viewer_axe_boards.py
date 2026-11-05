"""axe-core on the prototype viewer's Board and comments views: the second part of `test_viewer_axe.py`, which says what it
checks and why the views split into files."""

from __future__ import annotations

import unittest

from browser_driver import needs_chrome
from test_viewer_axe import VIEW_GROUPS, AxeChecks, start

SESSION: dict = {}


def setUpModule():
    start(SESSION)


@needs_chrome
class BoardAxeTests(AxeChecks, unittest.TestCase):
    session = SESSION
    views = VIEW_GROUPS[1]


if __name__ == "__main__":
    unittest.main()
