"""Probes that measure alignment in a page, in the browser, as docs/design/DESIGN.md's Layout > Alignment asks: rule 3 (a centred
thing is centred), rule 4 (an icon beside text shares the text's middle), and rule 5 (opposite paddings are equal).

A page's test runs a probe, then reads its rows with `centre_problems` or `padding_problems`. Each exception is in the test that
calls them, with its reason. The viewer, the design reference page, and the work-items page share these probes, so one rule is
measured the same way on each."""

from __future__ import annotations

# For each visible control that holds an icon, the icon's own box against the control's and its text's. The set is
# probed in the page: a control is a button, a link-button, or a summary; its text is a visible text node that a screen
# reader's own copy (`.sr-only`) is not.
ICON_PROBE = """(() => {
  const shown = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  // Text for a screen reader alone is drawn in a box of one pixel or less, which is how `.sr-only` and `.pv-tab-label` hide it.
  const hidden = (el, control) => { for (; el && el !== control; el = el.parentElement) { const r = el.getBoundingClientRect(); if (r.width <= 1 || r.height <= 1) return true; } return false; };
  const rows = [];
  for (const control of document.querySelectorAll('button, a.btn, [role=button], summary, .btn')) {
    const icon = control.querySelector('svg');
    if (!shown(control) || !icon || !shown(icon)) continue;
    const walker = document.createTreeWalker(control, NodeFilter.SHOW_TEXT);
    const lines = [];
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const range = document.createRange();
      range.selectNodeContents(n);
      if (!n.textContent.trim() || hidden(n.parentElement, control)) continue;
      for (const r of range.getClientRects()) if (r.width > 0) lines.push({ top: r.top, bottom: r.bottom, size: parseFloat(getComputedStyle(n.parentElement).fontSize) });
    }
    // Text that wraps is read by its first line: an icon beside it sits on that line, and the later lines are below it on purpose.
    // Where the first line sets two sizes, such as an id and a title, the larger one is the text.
    const first = lines.length ? lines.filter((r) => r.top < Math.min(...lines.map((l) => l.top)) + (r.bottom - r.top) / 2) : [];
    const b = control.getBoundingClientRect(), i = icon.getBoundingClientRect();
    const mid = (r, axis) => axis === 'x' ? r.left + r.width / 2 : r.top + r.height / 2;
    const main = first.length ? first.reduce((a, r) => (r.size > a.size ? r : a)) : null;
    const words = main ? { middle: (main.top + main.bottom) / 2, below: first.every((r) => r.top >= i.bottom - 1) } : null;
    rows.push({
      id: control.dataset.testid || control.id || control.className, classes: [...control.classList],
      dx: mid(i, 'x') - mid(b, 'x'), dy: mid(i, 'y') - mid(b, 'y'),
      words: Boolean(words),
      stacked: Boolean(words) && words.below,  // a line of text starts below the icon
      beside: words ? words.middle - mid(i, 'y') : 0,
    });
  }
  return rows;
})()"""

# Each visible button, field, and segment with the four paddings it draws, in px.
PADDING_PROBE = """(() => {
  const shown = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
  const kinds = 'button, a.btn, [role=button], summary, input:not([type=hidden]), select, textarea, .field, .select, .seg';
  const rows = [];
  for (const el of document.querySelectorAll(kinds)) {
    if (!shown(el)) continue;
    const s = getComputedStyle(el);
    rows.push({ id: el.dataset.testid || el.id || el.className || el.tagName.toLowerCase(), tag: el.tagName.toLowerCase(), classes: [...el.classList],
      left: parseFloat(s.paddingLeft), right: parseFloat(s.paddingRight), top: parseFloat(s.paddingTop), bottom: parseFloat(s.paddingBottom) });
  }
  return rows;
})()"""

CENTRE_TOLERANCE = 0.5  # px: rule 3
BESIDE_TOLERANCE = 1  # px: rule 4, an icon beside text against the middle of the text's letters
PADDING_TOLERANCE = 0.01  # px: rule 5, opposite paddings are equal; a computed padding is exact, so only rounding is allowed


def centre_problems(rows: list[dict], *, width: int, stacked_on_purpose: frozenset[str] = frozenset(), exceptions: dict[str, str] | None = None) -> list[str]:
    """Each control whose icon is off the middle: an icon alone sits at its control's middle, and an icon beside text shares the
    middle of the text. An icon stacked over its text is allowed only for a control in `stacked_on_purpose`, on a window of 400 px.
    `exceptions` names a control by one of its CSS classes and says why its icon is off the middle."""
    found: list[str] = []
    for row in rows:
        if any(name in row["classes"] for name in exceptions or {}):
            continue
        if row["stacked"]:
            if not (width == 400 and row["id"] in stacked_on_purpose):
                found.append(f"{row['id']} stacks its icon over its text")
        elif row["words"]:
            if abs(row["beside"]) > BESIDE_TOLERANCE:
                found.append(f"{row['id']} (icon and text, {row['beside']:.1f} px apart)")
        elif abs(row["dx"]) > CENTRE_TOLERANCE or abs(row["dy"]) > CENTRE_TOLERANCE:
            found.append(f"{row['id']} (icon alone, {row['dx']:.1f} and {row['dy']:.1f} px off)")
    return found


def padding_problems(rows: list[dict], exceptions: dict[str, tuple[tuple[float, float, float, float], str]]) -> list[str]:
    """Each control whose left and right paddings, or top and bottom paddings, differ, unless it is an exception. `exceptions`
    names a kind of control, by its tag or one of its CSS classes, with the four paddings it keeps on purpose (left, right, top,
    bottom, in px) and why. A control of that kind is allowed those paddings and no others, so another amount on it is found."""
    found: list[str] = []
    for row in rows:
        paddings = (row["left"], row["right"], row["top"], row["bottom"])
        if abs(paddings[0] - paddings[1]) <= PADDING_TOLERANCE and abs(paddings[2] - paddings[3]) <= PADDING_TOLERANCE:
            continue
        kept = [want for name, (want, _) in exceptions.items() if name == row["tag"] or name in row["classes"]]
        if any(all(abs(a - b) <= PADDING_TOLERANCE for a, b in zip(paddings, want, strict=True)) for want in kept):
            continue
        found.append(f"{row['id']} ({row['left']:g} left, {row['right']:g} right, {row['top']:g} top, {row['bottom']:g} bottom)")
    return found
