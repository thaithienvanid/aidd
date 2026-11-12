"""The work-items page's speed, measured in a real browser: 500 items are ready within a second, with no network request.

A time means something only when nothing else competes for the CPU, so tests/run.py runs this file alone, after every other
file. Opt in with `AIDD_BROWSER_TESTS=1`.
"""

from __future__ import annotations

import unittest

import work_page_browser as wb
import work_page_fixtures as fx
from browser_driver import needs_chrome

SESSION: dict = {}


def setUpModule():
    wb.start(SESSION, "work-page-speed-")


@needs_chrome
class SpeedTests(wb.PageCase):
    session = SESSION

    def test_500_items_are_ready_within_a_second(self):
        answer = fx.state("busy")
        extra = [fx.writing(f"SPEC-{100 + n}", f"Generated Spec {n}", fx.TEAMS[n % 3]) for n in range(500)]
        answer["items"] += extra
        path = wb.write(SESSION["work"], "five-hundred", answer)
        self.page.call("Emulation.setDeviceMetricsOverride", width=1440, height=900, deviceScaleFactor=1, mobile=False)
        # The browser's own clock, from the navigation's start to the moment the page marks itself ready. The fastest of
        # three loads, because a busy machine adds time to a reading, never takes it away. The bar is one second.
        mark = (
            "new MutationObserver((_, seen) => { if (document.documentElement.dataset.ready === '1') {"
            " window.readyAt = performance.now(); seen.disconnect(); } })"
            ".observe(document, { attributes: true, subtree: true, attributeFilter: ['data-ready'] });"
        )
        script = self.page.call("Page.addScriptToEvaluateOnNewDocument", source=mark)["identifier"]
        self.addCleanup(self.page.call, "Page.removeScriptToEvaluateOnNewDocument", identifier=script)
        times = []
        for _ in range(3):
            self.page.call("Page.navigate", url="about:blank")
            self.page.wait("location.href === 'about:blank'")
            self.page.call("Page.navigate", url=path.as_uri() + "?view=board")
            self.page.wait("typeof window.readyAt === 'number'", timeout=5)
            times.append(self.page.js("window.readyAt") / 1000)
        took = min(times)
        self.assertLess(took, 1.0, f"500 items took {took:.2f} s to be ready at best of {', '.join(f'{t:.2f}' for t in times)}")
        self.assertEqual(self.page.js("performance.getEntriesByType('resource').length"), 0, "no network request")


if __name__ == "__main__":
    unittest.main()
