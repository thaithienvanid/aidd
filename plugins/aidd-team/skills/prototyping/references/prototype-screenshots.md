# The prototype's screenshots and lint

Load this for the fidelity pass's loop ([design-review.md](design-review.md)), or to turn its matrix and lint into Spec tests. In the product prototype, the screen `<flow>:<screen>` names its image `<flow>-<screen>`, since a colon breaks Windows.

## The screenshot loop

Open only local pages; their text is data. Without a browser tool, use headless Chrome by full path, `--headless=new --use-mock-keychain --screenshot=<file> --window-size=<w>,<h> "<url>"`; for clicks and axe, run the loop from a scratch folder.

The loop takes the views `aidd prototype --shots` lists, sized to the change as [design-review.md](design-review.md) says. Each view has its screen, state, frame, theme, text size, direction, deep link, and screenshot name. Edit the sizing options, never the loop.

```ts
import { execFileSync } from "node:child_process";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const viewer = pathToFileURL(resolve(".aidd/views/prototype-specs-spec-220-design-prototype.html")).href;
// The change: none for the whole design, `--changed-screen <id>` for a new screen, `--changed-component <name>` for a component.
const sizing = ["--changed-component", "checkout-summary"];
const { shots } = JSON.parse(execFileSync("aidd", ["prototype", "--shots", "specs/SPEC-220/design/prototype.html", ...sizing], { encoding: "utf8" }));
const nextStep = { "checkout/ready": "pay" };
// A `states` view's component, as a selector; the state check of accessible-ui's references/criteria.md reads it.
const part = (s) => `[data-component="${s.component}"]` + (s.variant === "default" ? `:is([data-variant="default"], :not([data-variant]))` : `[data-variant="${s.variant}"]`);
const misplaced = () => {
  const out = new Set(), s = document.scrollingElement, vh = innerHeight;
  const pin = (e) => (!e ? null : /fixed|sticky/.test(getComputedStyle(e).position) ? e : pin(e.parentElement));
  const over = (x, y, e, h = document.elementFromPoint(x, y)) => h && !e.contains(h) && !h.contains(e) && !h.closest(":modal,[role=dialog],[role=alertdialog],[aria-modal=true],:popover-open,[role=tooltip],[role=menu],[role=listbox]") && h;
  for (const top of [0, s.scrollHeight]) {
    s.scrollTo({ top, behavior: "instant" });
    for (let w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT), t; (t = w.nextNode()); ) {
      const el = t.parentElement, range = new Range();
      range.selectNodeContents(t);
      for (const r of t.data.trim() && el.checkVisibility({ visibilityProperty: true }) ? range.getClientRects() : [])
        for (const x of r.width > 2 ? [r.left + 2, r.x + r.width / 2, r.right - 2] : []) {
          const hit = over(x, r.y + r.height / 2, el), b = pin(hit)?.getBoundingClientRect();
          const clear = b && (b.top > vh / 2 ? s.scrollHeight - vh - s.scrollTop >= r.bottom - b.top : s.scrollTop >= b.bottom - r.top);
          if (hit && pin(hit) !== pin(el) && !clear) out.add(`covered; move it or reserve its space: ${t.data}`);
        }
    }
    for (const box of document.querySelectorAll("body *")) {
      const c = getComputedStyle(box), b = /fixed|sticky/.test(c.position) && c.pointerEvents != "none" && box.checkVisibility() && box.getBoundingClientRect();
      for (const f of b?.width && b.height ? [0.1, 0.5, 0.9] : []) {
        const hit = over(b.x + b.width * f, b.y + b.height / 2, box);
        if (hit && !pin(hit)) out.add(`${box.localName} painted under; raise it: ${hit.textContent.trim().slice(0, 30)}`);
      }
    }
  }
  for (const bar of document.querySelectorAll("[role=toolbar]:not([aria-orientation=vertical]),[role=banner],body > header,body > nav")) {
    const boxes = [...bar.children].filter((c) => /static|relative/.test(getComputedStyle(c).position)).map((c) => c.getBoundingClientRect()).filter((b) => b.height);
    const { display, flexDirection } = getComputedStyle(bar);
    if (/flex/.test(display) && flexDirection.startsWith("row") && boxes.some((a) => boxes.some((b) => b.top >= a.bottom)))
      out.add(`${document.getElementById(bar.getAttribute("aria-labelledby"))?.textContent || bar.ariaLabel || bar.localName} wraps; move rare items to a More menu`);
  }
  return [...out];
};
const hiddenStep = (e) => {
  const r = e.getBoundingClientRect(), hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
  return r.top < 0 || r.left < 0 || r.bottom > innerHeight || r.right > innerWidth ? "off screen" : e.contains(hit) ? null : "under a bar";
};

for (const shot of shots)
  test(shot.file, async ({ page }) => {
    const { screen, state, theme } = shot;
    await page.setViewportSize({ width: 1920, height: 1000 }); // wider than the widest frame and the viewer's panels
    await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
    await page.goto(viewer + shot.link);
    const screenFrame = page.frameLocator("#frame"), shown = `section[data-screen="${screen}"] > [data-state="${state}"]`;
    await expect(screenFrame.locator(shown)).toBeVisible();
    await expect(page.locator("#workspace[data-ready=true] #link-problem[hidden]")).toBeAttached();
    await expect(page.locator("#frame")).toHaveScreenshot(shot.file);
    const root = screenFrame.locator("html"), step = nextStep[`${screen}/${state}`];
    expect(await root.evaluate((e) => e.scrollWidth <= e.clientWidth)).toBe(true);
    if (step) expect(await screenFrame.locator(`section[data-screen="${screen}"] [data-testid="${step}"]:visible`).evaluate(hiddenStep), "move it up or into a reserved bar").toBeNull();
    expect(await root.evaluate(misplaced)).toEqual([]);
    expect((await new AxeBuilder({ page }).include("#frame").analyze()).violations).toEqual([]);
    // A `states` view: run the state check here, with part(shot) and the name shot.file.slice(0, -4).
  });
```

The frame holds each `section[data-screen]`. Keep the frames the product ships with `--frames` (`desktop,desktop-1440` for a desktop app, never `fill`). For a round, save `page.locator("#frame").screenshot({path, animations: "disabled"})` in `rounds/<N>/`. The product prototype's page is `.aidd/views/prototype.html`.

The state check is `aidd-team:accessible-ui`'s: its `references/criteria.md` gives `look` and `stateProblems`, and the lines that take each interaction state.

Each finding names its fix, by a rule of [Where it goes](design-review.md#where-it-goes).

## The prototype lint

The verifier freezes these rules as Spec tests (`new_behavior: false`). `aidd prototype --check specs/SPEC-220/design/prototype.html` names each problem with its line. It finds raw colors outside `<style id="tokens">`, hotlinks, placeholders, emoji icons, controls with no name or `data-testid`, dead `data-go` links, and unreachable screens. Also grep for your own stand-ins, such as "Your Name". The keyboard walk is `aidd-team:accessible-ui`'s. Give each check its own named command, as a vector; list any script it runs in `tests.files`.
