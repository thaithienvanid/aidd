# The criteria teams miss, state indicators, form feedback, and what the tools prove

Load this in Specify for a new screen or form, and in Verify when you set up the automated checks. Load it too before
you change a control's look or a state indicator, for the rule and its check, and before you write an error, a hint, or a focus move.

**Contents**

<!-- aidd:gen toc -->
- [WCAG 2.2 criteria that teams miss](#wcag-22-criteria-that-teams-miss)
- [What the automated checks prove](#what-the-automated-checks-prove)
- [State indicators](#state-indicators)
- [The state check](#the-state-check)
- [Form feedback and focus](#form-feedback-and-focus)
<!-- aidd:end -->

## WCAG 2.2 criteria that teams miss

WCAG 2.2 added these at levels A and AA. Older checklists leave them out.

- **Dragging movements (2.5.7).** Each drag has a single-pointer alternative, such as buttons that move an item up and down.
- **Consistent help (3.2.6).** Help, such as a contact link or a chat, sits in the same place on each page.
- **Redundant entry (3.3.7).** A form never asks again for what the person already gave in the same process. Fill it in, or let them pick it.
- **Accessible authentication (3.3.8).** Sign-in needs no puzzle and no memory test. Paste works in every field, so a password manager works.

Two older criteria are often missed too:

- **Orientation (1.3.4).** The screen works in both portrait and landscape, unless one orientation is essential.
- **Text spacing (1.4.12).** Content survives larger line, paragraph, letter, and word spacing with nothing cut off.

## What the automated checks prove

- axe checks only the rules it can test by machine, so it finds part of the failures. The keyboard and screen-reader passes still run.
- Scope axe to WCAG with the tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, and `wcag22aa`. Without tags it also runs best-practice rules, which are advice, not WCAG failures.
- Run it once per screen state, theme, and motion setting, after `page.emulateMedia({colorScheme, reducedMotion})`.
- On mobile, the platform audits check labels, contrast, and touch targets. A cross-platform toolkit has its own checks, such as Flutter's `meetsGuideline` matchers in widget tests.

## State indicators

- Design a state indicator, such as a focus ring, a selection mark, or a hover edge, from the object it decorates.
  Read the object's edge, shape, and colors first, on each of its variants. The indicator keeps 3:1 against the object's
  own edge and against the background (WCAG 2.2 SC 1.4.11, and SC 2.4.13, level AAA, for focus). It follows the
  object's shape and corners, and repeats none of its lines, so it never reads as a second border.
- A control's interaction states (rest, hover, focus, selected, disabled) are states. Two states never look alike, and
  they differ by more than color (WCAG 2.2 SC 1.4.1): a width, an offset, a fill, a weight, or a mark.
- Screenshot each state on each variant of the object, in each theme, and judge it first at the size a person sees it,
  then up close. The state check below fails on two states that look the same, two that differ only by color, and an
  indicator in its edge's color. Run it again at each pixel ratio and zoom that `aidd-team:prototyping` lists, because a width that rounds to the same pixel is the same state to the eye.

## The state check

A changed control gets a check that can fail. Capture its look in each interaction state, then compare the looks.
`look` runs in the page on the element that draws the indicator. `stateProblems` takes the looks by state name. It
returns what is wrong: two states that look the same, two that differ only by color, and an indicator drawn in the
color of the edge it sits beside. Run it on each variant of the control, in each theme, in the view that the screenshot
loop of `aidd-team:prototyping` opened (its `references/prototype-screenshots.md`).

```js
// The paint of one element and its ::before and ::after: everything a state indicator can change.
const look = (e) => Object.fromEntries(["", "::before", "::after"].flatMap((p) => {
  const s = getComputedStyle(e, p || null);
  return p && s.content === "none" ? [] : ["outline-style", "outline-width", "outline-offset", "outline-color", "box-shadow", "border-style", "border-width", "border-color", "background-color", "background-image", "color", "text-decoration-line", "font-weight", "opacity"].map((k) => [p + k, s.getPropertyValue(k)]);
}));
const COLOR = /(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\([^)]*\)|#[0-9a-f]{3,8}\b/gi;
// `looks` maps each state's name to its look; `rest` names the state that draws no indicator.
const stateProblems = (looks, rest = "rest") => {
  const out = [], names = Object.keys(looks), text = (l) => JSON.stringify(l), colors = (v) => (v || "").match(COLOR) || [];
  names.forEach((a, i) => names.slice(i + 1).forEach((b) => {
    if (text(looks[a]) === text(looks[b])) out.push(`${a} and ${b} look the same: give one a width, an offset, a fill, or a mark`);
    else if (text(looks[a]).replace(COLOR, "c") === text(looks[b]).replace(COLOR, "c")) out.push(`${a} and ${b} differ only by color: add a width, an offset, a fill, or a mark`);
  }));
  const r = looks[rest];
  if (!r) return out;
  const edge = [...(parseFloat(r["border-width"]) > 0 && r["border-style"] !== "none" ? colors(r["border-color"]) : []), ...colors(r["box-shadow"])];
  for (const name of names.filter((n) => n !== rest)) {
    const l = looks[name];
    const drawn = [...(l["outline-style"] !== "none" && parseFloat(l["outline-width"]) > 0 ? colors(l["outline-color"]) : []),
      ...colors(l["box-shadow"]).filter((c) => !colors(r["box-shadow"]).includes(c)), ...(l["border-color"] !== r["border-color"] ? colors(l["border-color"]) : [])];
    for (const c of new Set(drawn.filter((c) => edge.includes(c)))) out.push(`the ${name} indicator takes its edge's color, ${c}, so it reads as a second border: use a color 3:1 from the edge, or a halo between them`);
  }
  return out;
};
```

In that loop, for the control `part`, a selector such as `[data-component="tab"][data-variant="quiet"]`, take each
state from the keyboard and the pointer, as a person reaches it. `name` is the view's screenshot name without `.png`,
and each state's screenshot goes beside it, to read:

```ts
const marks = { selected: "[aria-selected=true],[aria-current]:not([aria-current=false]),[aria-pressed=true],[aria-checked=true]", disabled: "[disabled],[aria-disabled=true]" };
const control = screenFrame.locator(`${part}:not(:is(${Object.values(marks)})):not(:has(${Object.values(marks)}))`).first();
const looks = {};
const take = async (state, element) => {
  looks[state] = await element.evaluate(look);
  await page.locator("#frame").screenshot({ path: `${name}-${state}.png`, animations: "disabled" });
};
await page.mouse.move(0, 0);
await take("rest", control);
await control.hover();
await take("hover", control);
await page.mouse.move(0, 0);
await control.focus();
await page.keyboard.press("Shift+Tab");
await page.keyboard.press("Tab"); // focus that came from the keyboard, so :focus-visible holds
await take("focus", control);
for (const [state, mark] of Object.entries(marks)) {
  const shown = screenFrame.locator(`${part}:is(${mark}), ${part}:has(${mark})`).first();
  if (await shown.count()) await take(state, shown);
}
expect(stateProblems(looks)).toEqual([]);
```

What it cannot see, so a person still reads the screenshots:

- **Contrast between colors that differ.** It finds an indicator in its edge's very color, not one that is close. The
  tokens' contrast pairs and axe hold 3:1.
- **Geometry.** It reads paint, not position, so a ring that a scrolling parent clips, or that something covers, passes.
- **Size on screen.** It cannot say whether a person finds the indicator at the size they see it. Judge the overview
  first.
- **Another element's paint.** It reads the element it is given and its `::before` and `::after`. Give it the element
  that draws the indicator.
- **Motion and forced colors.** It reads the end of a transition, so the loop sets reduced motion. Forced colors need a
  run of their own, with `forced-colors: active` emulated.

## Form feedback and focus

On the web, each item is something a person or a test can observe.

- **An error is not shown by color alone (WCAG 2.2 SC 3.3.1, 1.4.1).** At page load no field has `aria-invalid`, even an empty required one. After a failed submit, or after a person leaves a field with a bad value, that field has `aria-invalid="true"` and its error text is on screen. With color removed, the error still reads from its text or a mark.
- **An error shown on submit is read when its field takes focus (SC 3.3.1, 1.3.1).** The error text is in the field's `aria-describedby`, so it is part of the field's accessible description and a screen reader reads it with the field. When a failed submit moves focus to a field (next item), that field's accessible description reads the error text.
- **An error that appears while focus is elsewhere is announced through a live region (SC 4.1.3).** After a person leaves a field with a bad value, focus is on the next control, so the field's description is not read. The error text is also in a live region (`role="alert"`, `role="status"`, or `aria-live`) that is in the page before the error appears. Leave the field and read the region's text: it is the error. Without a live region, the error is not announced.
- **A failed submit moves focus to the first invalid field, or to an error summary that links to each (practice).** SC 3.3.1 requires each error to be identified in text, and SC 2.4.3 requires an order that keeps meaning. Neither requires the move, so it is practice. The GOV.UK Design System's error summary does it: it takes focus and links each error to its field (design-system.service.gov.uk/components/error-summary, read 2026-11-12). Submit a form with two bad fields. Either `document.activeElement` is the first of them in reading order, or it is an error summary with one link for each bad field, in reading order, and following the first link focuses the first bad field. The submit control stays enabled, so a failed submit can happen and give this feedback.
- **A field's hint is tied to it (SC 1.3.1, 3.3.2).** The hint's id is in the field's `aria-describedby`, and the field's accessible description reads the hint. The hint sits above the input, so an autofill list does not cover it.
- **Focus lands somewhere sensible when its control is disabled or removed (SC 2.4.3).** Press a control until it disables or leaves the page, such as the last page of a pager or a deleted row. `document.activeElement` is then the next control in the flow or the container's heading, never `body`. A native `disabled` takes the control out of the focus order, so use `aria-disabled="true"` where a person should still land on it.
