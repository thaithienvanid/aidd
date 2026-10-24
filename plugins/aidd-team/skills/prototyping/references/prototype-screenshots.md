# The prototype's screenshots and lint

Load this when you take a round's screenshots of `prototype.html`, or turn the screenshot matrix and the prototype lint into Spec tests.

Every view has an address: `prototype.html#<screen>/<state>?theme=<light|dark>&frame=<320|768|1024|1440|ios|android>`, with `mode=wireframe` and `round=<N>`; each key is optional, and the frame defaults to 1024. A loop opens each view by its link and names the image `<screen>-<state>-<target>-<theme>.png`.

## The screenshot loop

The screens and states come from the prototype itself, so a screen added later is covered without editing the test (Playwright with `@axe-core/playwright`).

```ts
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const path = resolve("specs/SPEC-220/design/prototype.html");
const file = pathToFileURL(path).href;
// Each section[data-screen] and its [data-state] children, as the screen menu reads them.
const html = readFileSync(path, "utf8").replace(/<!--[\s\S]*?-->/g, "");
const screens = new Map(
  [...html.matchAll(/<section\b[^>]*\bdata-screen="([^"]+)"[^>]*>([\s\S]*?)<\/section>/g)].map(([, screen, body]) => [
    screen, [...body.matchAll(/\bdata-state="([^"]+)"/g)].map(([, state]) => state)]),
);
const frames = { "320": 320, "768": 768, "1024": 1024, "1440": 1440, ios: 390, android: 412 };

for (const screen of screens.keys()) {
  for (const state of screens.get(screen)!) {
    for (const theme of ["light", "dark"] as const) {
      for (const frame of Object.keys(frames)) {
        test(`${screen}-${state}-${frame}-${theme}`, async ({ page }) => {
          await page.setViewportSize({ width: frames[frame] + 480, height: 1000 });
          await page.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
          await page.goto(`${file}#${screen}/${state}?theme=${theme}&frame=${frame}`);
          await expect(page.locator(`section[data-screen="${screen}"] > [data-state="${state}"]`)).toBeVisible();
          await expect(page.locator("#frame")).toHaveScreenshot(`${screen}-${state}-${frame}-${theme}.png`);
          expect((await new AxeBuilder({ page }).include("#frame").analyze()).violations).toEqual([]);
        });
      }
    }
  }
}
```

The viewport is wider than the frame, so the frame sets the layout. `emulateMedia` sets the system scheme as well as `theme=`, and `reducedMotion` keeps captures still. Drop a frame the product does not ship to, and drop `dark` when `dark_mode` is in `project.defaults.disabled`. For a round's pictures, write the captures to `specs/SPEC-220/design/rounds/<N>/` with `page.locator("#frame").screenshot({path, animations: "disabled"})` instead of comparing. `aidd explore` pairs each with the round before and the feedback given on that screen and state.

## The prototype lint

Rules a machine can check, each exiting non-zero on a violation, so the verifier freezes them as Spec tests (`new_behavior: false`). The prototype is one self-contained file; below, `P=specs/SPEC-220/design/prototype.html`.

- **No raw color outside the tokens block**: `! sed '/<style id="tokens">/,/<\/style>/d' "$P" | grep -nE '(color|background|border|fill|stroke|outline|shadow)[a-z-]*: *[^;"}]*(#[0-9a-fA-F]{3,8}\b|(rgb|hsl|hwb|lab|lch|oklab|oklch|color)a?\()'`, in style blocks and `style` attributes alike; the tokens block holds the generated roles ([design-system-contract.md](design-system-contract.md)). Product code has the web pack's Design-token lint.
- **No hotlinked images or fonts**: `! grep -nE '(src|href)=["'"'"']https?://|url\(["'"'"']?https?://|@import +url\(' "$P"`; keep the template's Content-Security-Policy, and in Playwright fail on any request.
- **No placeholder text**: `! grep -niE 'lorem ipsum|dolor sit amet|\bTODO\b|\bFIXME\b|\bTBD\b|john doe|jane doe|placeholder text' "$P"`, plus the project's own stand-ins (such as "Your Name").
- **No emoji as icons**: `node -e 'process.exit(/(?![©®™])\p{Extended_Pictographic}/u.test(require("fs").readFileSync(process.argv[1], "utf8")) ? 1 : 0)' "$P"`; icons come from the system's set, with a name or `aria-hidden="true"`.
- **A name and a keyboard path for every interactive element**:
  - axe per state (`withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])`, rules such as `button-name`, `label`, `nested-interactive`, `target-size`);
  - a Playwright keyboard walk that tabs until focus returns, and asserts every visible `data-testid` was reached in the Spec's order (WCAG 2.2 SC 2.1.1, 2.4.3);
  - for JSX, `eslint-plugin-jsx-a11y`.

  The full practice is `aidd-team:accessible-ui`.

Put the checks in one script beside the file, `specs/SPEC-220/design/lint.sh <rule>`, list it in `tests.files`, and give each rule its own command, as a vector:

```yaml
tests:
  commands:
    - name: prototype-lint-placeholders
      command: [sh, specs/SPEC-220/design/lint.sh, placeholders]
      new_behavior: false
```

## Several flows

One prototype per flow or Spec, each in its own design folder (`--area <flow>` for a second flow). Run the loop once per file, and keep a short `docs/design/index.md` that lists each prototype, its path, and its screens.
