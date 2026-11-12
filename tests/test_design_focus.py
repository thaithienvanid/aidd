"""Focus in the design system, in a real browser: a focused field turns its border to the ring and draws no outline,
and a focused button draws its outline in the ring, in both themes. The ring is a blue of its own, so focus never reads as
a pressed button's ink fill. The page is built here from `system_css()`, so a change to `components.css` reaches it before
gen-docs runs. Opt in with `AIDD_BROWSER_TESTS=1` (see `browser_driver.py`).
"""

from __future__ import annotations

import atexit
import json
import tempfile
import unittest
from pathlib import Path

import work_page_browser as wb
from browser_driver import CHROME, ENABLED, finish, needs_chrome, start_browser

from aidd.views import system_css

SESSION: dict = {}
# One column per theme, each with the controls the probe focuses: a field, a button, a pressed button, and a segment group.
COLUMN = (
    '<section data-theme="{theme}"><input class="field" aria-label="Field"> <button class="btn" type="button">Button</button>'
    ' <button class="btn" type="button" aria-pressed="true">Pressed</button>'
    ' <div class="seg"><button type="button" aria-pressed="true">On</button><button type="button" aria-pressed="false">Off</button></div></section>'
)
# For a theme's column: the ring token as the browser computes a color, then a focused field's and button's styles.
FOCUS = r"""((theme) => {
  const col = document.querySelector(`[data-theme=${theme}]`);
  const probe = document.createElement('span'); col.append(probe); probe.style.color = 'var(--ring)';
  const ring = getComputedStyle(probe).color; probe.remove();
  const field = col.querySelector('input.field:not(.is-focus)'); field.focus();
  const f = getComputedStyle(field);
  const out = {ring, fieldBorder: f.borderTopColor, fieldOutline: f.outlineStyle, fieldShadow: f.boxShadow};
  const button = col.querySelector('button.btn:not(.is-focus):not(.btn-primary):not([aria-pressed=true])'); button.focus();
  const b = getComputedStyle(button);
  const result = {...out, buttonOutline: b.outlineColor, buttonStyle: b.outlineStyle, pressedFill: getComputedStyle(col.querySelector('.btn[aria-pressed=true]')).backgroundColor};
  const segment = col.querySelector('.seg > button:not([aria-pressed=true])'); segment.focus();
  const s = getComputedStyle(segment);
  return JSON.stringify({...result, segmentOutline: s.outlineColor, segmentOffset: parseFloat(s.outlineOffset), segmentWidth: parseFloat(s.outlineWidth)});
})"""


def setUpModule():
    if ENABLED:
        if not CHROME:
            raise AssertionError("AIDD_BROWSER_TESTS=1 asks for the focus test, but no Chrome or Chromium was found: install one, or set CHROME_BIN to it")
        atexit.register(finish, SESSION)
        SESSION["browser"] = start_browser(SESSION)
        SESSION["page"] = SESSION["browser"].page()


@needs_chrome
class FocusTests(unittest.TestCase):
    def test_a_focused_field_turns_its_border_to_the_ring_and_a_button_draws_the_ring_as_its_outline(self):
        page = SESSION["page"]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "focus.html"
            columns = "".join(COLUMN.format(theme=theme) for theme in wb.THEMES)
            path.write_text(f'<!doctype html><html lang="en"><title>Focus</title><style>{system_css()}</style><body>{columns}</body></html>', encoding="utf-8")
            page.open(path.as_uri(), wb.DESKTOP)
        for theme in wb.THEMES:
            with self.subTest(theme=theme):
                got = json.loads(page.js(f"{FOCUS}({theme!r})"))
                self.assertEqual(got["fieldBorder"], got["ring"], "a focused field's border is the ring")
                self.assertEqual(got["fieldOutline"], "none", "a focused field draws no outline, so no double border")
                self.assertIn("inset", got["fieldShadow"], "the ring doubles inside the field")
                self.assertEqual(got["buttonOutline"], got["ring"], "a focused button's outline is the ring")
                self.assertEqual(got["buttonStyle"], "solid")
                self.assertNotEqual(got["ring"], got["pressedFill"], "focus never looks like a pressed button's fill")
                # A segmented control scrolls on a narrow screen, so a ring outside it would be clipped: it sits inside.
                self.assertEqual(got["segmentOutline"], got["ring"], "a focused segment's outline is the ring")
                self.assertLessEqual(got["segmentOffset"], -got["segmentWidth"], "a segment's ring sits inside it")


if __name__ == "__main__":
    unittest.main()
