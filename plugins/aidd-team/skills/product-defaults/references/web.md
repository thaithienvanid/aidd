# The web product defaults: what each builds, and its test

Each is on unless `project.defaults.disabled` names it with its reason. Build only what is on, and name each one you built on the handoff note. The legal text itself is never an agent's: a person writes it.

- `dark_mode`:
  - light and dark token sets with the same role names (`design/tokens.json`);
  - the page follows `prefers-color-scheme` until a person picks a theme with a toggle (system, light, dark) that persists (a cookie, or the account);
  - the theme is set before first paint;
  - contrast checked, and a screenshot taken, in both themes;
  - logos and illustrations that read on both.
- `responsive`:
  - layouts from 320 CSS px with no horizontal scroll;
  - targets at least 24 by 24 CSS px (WCAG 2.2 SC 2.5.8), and 44 by 44 pt on iOS;
  - forms with a `<label>`, the right `type` and `inputmode`, and `autocomplete` tokens (`email`, `current-password`, `one-time-code`);
  - paste allowed, never blocked on a password or a code;
  - inline validation beside the field on blur, never only on submit.
- `i18n_ready`:
  - every user-facing string in a message file (ICU MessageFormat for plurals);
  - dates, numbers, and money through `Intl.DateTimeFormat` and `Intl.NumberFormat` (or the platform's formatter) for the person's locale;
  - CSS logical properties (`margin-inline-start`, `padding-block`, `inset-inline-end`) and `dir="auto"` on user text, so right-to-left needs no rewrite.
- `perf_budget`:
  - the Core Web Vitals budget as Lighthouse CI assertions on the pages the change touches;
  - the budget: LCP 2.5 s or less, INP 200 ms or less, CLS 0.1 or less, at the 75th percentile;
  - INP from field data (a RUM script or CrUX);
  - images sized, lazy below the fold, and in a modern format.
- `public_page_basics`:
  - a unique `<title>` and meta description;
  - Open Graph (`og:title`, `og:description`, `og:image`) and Twitter card tags;
  - a favicon, an Apple touch icon, and a web app manifest;
  - a `robots.txt` and a sitemap for public pages;
  - designed 404, 500, and maintenance pages, in the product's voice, each with a way back; the maintenance page answers 503 with `Retry-After`.
- `legal_placeholders`: a privacy policy page and a terms page from Day 0, linked from the footer and the sign-up form. Each is a placeholder that says a person writes it. An agent never drafts, edits, or paraphrases legal text; the person who answers for it does, with counsel.
- `transactional_email`:
  - every email has a plain-text part beside the HTML (multipart/alternative);
  - a message that is not strictly transactional (a digest, a nudge, marketing) carries an unsubscribe link and the `List-Unsubscribe` and `List-Unsubscribe-Post` headers (one-click);
  - sent from a domain with SPF, DKIM, and DMARC;
  - templates previewed in both themes and in plain text.

## How each test runs

The test names are the SKILL.md table's.

- Both themes: Playwright with `page.emulateMedia({colorScheme: "dark"})` and `"light"`, then `@axe-core/playwright` and `toHaveScreenshot` per state in each. A unit test checks that the toggle's choice survives a reload.
- Responsive and targets: Playwright at 320, 768, 1024, and 1440 asserting `scrollWidth <= clientWidth`, and axe's `target-size` rule. A test checks that each field has its `autocomplete` token and that paste fills it.
- i18n readiness: the `aidd-team:internationalization` pack's Pseudo-localization build (accented, 30 percent longer, right-to-left) renders without clipping. A lint rule bans a literal string in a component (`eslint-plugin-i18next` or `i18n-tasks`).
- Performance budget: `npx @lhci/cli@0.15.1 autorun` with assertions on `largest-contentful-paint` (2500 ms) and `cumulative-layout-shift` (0.1).
- Public page basics: a test fetches each public route and asserts the title, the description, and `og:image`. It also asserts that an unknown path answers 404 with the designed page.
- Transactional email: render each template and assert a text/plain part. Assert the `List-Unsubscribe` header on the non-transactional ones.
