# The prototype lint

Load this when you write the checks a prototype must pass before Spec approval, or turn them into Spec tests.

Five rules a machine can check, so the tester can put them in the Spec's `tests.commands` and Spec approval freezes them. Each one exits non-zero on a violation and gives the same answer every run. The commands below assume the prototype is in `docs/design/SPEC-220/prototype/` and its generated tokens in `docs/design/SPEC-220/tokens.css`; adjust the paths, not the rules.

Tool rule names were checked against each tool's documentation on 2026-09-28.

## 1. No raw colour outside the tokens file

Every colour comes from a token, so a reviewer who approves the tokens has approved every colour on the screen.

Stylelint, with the generated tokens file ignored (`ignoreFiles`):

```json
{
  "ignoreFiles": ["docs/design/SPEC-220/tokens.css"],
  "plugins": ["stylelint-declaration-strict-value"],
  "rules": {
    "color-no-hex": true,
    "color-named": "never",
    "function-disallowed-list": ["/^(rgb|rgba|hsl|hsla|hwb|lab|lch|oklab|oklch|color)$/"],
    "scale-unlimited/declaration-strict-value": ["/color$/", { "ignoreValues": ["transparent", "currentColor", "inherit"] }]
  }
}
```

`color-no-hex`, `color-named`, and `function-disallowed-list` are built-in rules; `scale-unlimited/declaration-strict-value` comes from the `stylelint-declaration-strict-value` plugin and requires a `var(--…)` for every colour property. Stylelint does not read inline `style` attributes, so add a grep for them:

```sh
! grep -rnE 'style="[^"]*(#[0-9a-fA-F]{3,8}|rgba?\(|hsla?\()' docs/design/SPEC-220/prototype
```

## 2. No hotlinked images or fonts

Everything the prototype shows is in its folder, so it runs offline and nothing changes after approval.

```sh
! grep -rnE '(src|href)=["'"'"']https?://|url\(["'"'"']?https?://|@import +url\(' docs/design/SPEC-220/prototype
```

The stronger check is at run time: in the Playwright tests, route every request and fail the test on any host other than the local server (`page.route('**/*', …)`).

## 3. No placeholder text

Placeholder copy hides the states where the real words do not fit.

```sh
! grep -rniE 'lorem ipsum|dolor sit amet|\bTODO\b|\bFIXME\b|\bTBD\b|your name|john doe|jane doe|example@example\.com|placeholder text' \
    --exclude=README.md docs/design/SPEC-220/prototype
```

Add the project's own stand-ins to the list. A person's name in a fixture is fine when it is realistic, varied in length, and fictional.

## 4. No emoji used as icons

An emoji renders differently on every platform, has a name a screen reader reads aloud, and is not part of the design system. Icons come from the system's icon set, with an accessible name or `aria-hidden="true"`.

```sh
node -e '
const fs=require("fs"),path=require("path");let bad=0;
const walk=d=>fs.readdirSync(d,{withFileTypes:true}).forEach(e=>{const p=path.join(d,e.name);
  if(e.isDirectory())return walk(p);if(!/\.(html|css|js|jsx|ts|tsx|vue|svelte|json)$/.test(p))return;
  fs.readFileSync(p,"utf8").split("\n").forEach((l,i)=>{if(/(?![©®™])\p{Extended_Pictographic}/u.test(l)){bad=1;console.log(`${p}:${i+1}: ${l.trim()}`)}})});
walk("docs/design/SPEC-220/prototype");process.exit(bad)'
```

Copy that really needs an emoji (a chat message in a fixture, say) goes on an allow-list in the command, not around it.

## 5. Every interactive element has a name and is reachable by keyboard

This is the accessibility floor, not the whole of it; the full practice is in `aidd-team:accessible-ui`.

- **axe-core per state**, with `@axe-core/playwright`: `new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze()`, and assert no violations. The rules that catch a missing name or a trap include `button-name`, `link-name`, `label`, `aria-command-name`, `nested-interactive`, `scrollable-region-focusable`, and `target-size` (WCAG 2.2 SC 2.5.8).
- **A keyboard walk** in Playwright, because axe does not prove reachability: press Tab until focus returns to the start, record each focused element's `data-testid`, and assert that every visible interactive element with a `data-testid` was reached, in the order the Spec names (WCAG 2.2 SC 2.1.1 and 2.4.3).
- **For a React or JSX prototype**, `eslint-plugin-jsx-a11y` catches a click handler on a `div` before anything runs: `jsx-a11y/click-events-have-key-events`, `jsx-a11y/no-static-element-interactions`, `jsx-a11y/interactive-supports-focus`, and `jsx-a11y/control-has-associated-label`.

## In the Spec

Put the shell checks in one script inside the design folder, list it in `tests.files` so Spec approval freezes it, and give each rule its own command. A command is a vector, never a shell string:

```toml
[[tests.commands]]
name = "prototype-lint-colours"
command = ["npx", "stylelint", "docs/design/SPEC-220/prototype/**/*.css"]
new_behavior = false

[[tests.commands]]
name = "prototype-lint-placeholders"
command = ["sh", "docs/design/SPEC-220/lint.sh", "placeholders"]
new_behavior = false
```

One entry per rule, so a red run says which rule broke.
