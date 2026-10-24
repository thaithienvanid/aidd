---
name: product-defaults
description: "Practice skill: build what `project.defaults` leaves on, each with its test. Use in an aidd repository on Day 0 or when a Task touches a default."
metadata:
  checked: "2026-10-22"
---

# Product defaults

**Use it when** the MVP's Day 0 lays the baseline, or a Task adds a page, an endpoint, a table, an email, or a service. It owns every default and its test; the packs point here.

**Do not use when** the change touches none of these areas, or `project.defaults.disabled` names the default (its value is the reason).

## Standards

<!-- aidd:gen practice:product-defaults -->
| Standard | Edition | Checked | Source |
| --- | --- | --- | --- |
| WCAG 2.2 AA (SC 2.5.8 target size) | 2.2 | 2026-10-16 | <https://www.w3.org/TR/WCAG22/> |
| Core Web Vitals (LCP, INP, CLS) | 2024 thresholds | 2026-10-16 | <https://web.dev/articles/vitals> |
| RFC 9457 problem details | 2023 | 2026-10-16 | <https://www.rfc-editor.org/rfc/rfc9457> |
| Idempotency keys and rate limits (emerging) | draft-ietf-httpapi-idempotency-key-header-07; draft-ietf-httpapi-ratelimit-headers-11 | 2026-10-16 | <https://datatracker.ietf.org/doc/draft-ietf-httpapi-idempotency-key-header/> |
| RFC 9562 UUIDs, with UUIDv7 for sortable ids | RFC 9562 | 2026-10-16 | <https://www.rfc-editor.org/rfc/rfc9562.html> |
| OWASP Cheat Sheet Series (HTTP headers, cookies, CSRF) | — | 2026-10-16 (reviewed) | <https://cheatsheetseries.owasp.org/> |
| The Twelve-Factor App | — | 2026-10-16 (reviewed) | <https://12factor.net/> |
| Conventional Commits | 1.0.0 | 2026-10-16 | <https://www.conventionalcommits.org/en/v1.0.0/> |
<!-- aidd:end -->

## Implement

Every default is on unless `project.defaults.disabled` in `.aidd/config.yaml` names it with its reason. `aidd init` writes the interface ones (`dark_mode`, `responsive`, `perf_budget`, `public_page_basics`) off in a command-line tool or a library, and `modular_monolith` off where code exists. Build only what is on, and name each on the handoff note.

Details and tests: the first seven in [references/web.md](references/web.md), the next five in [references/services.md](references/services.md).

| Default | Builds |
| --- | --- |
| `dark_mode` | light and dark token sets, `prefers-color-scheme` with a persisted toggle, contrast in both |
| `responsive` | layouts from 320 CSS px, targets of 24 by 24 CSS px (44 by 44 pt on iOS, 48 by 48 dp on Android), forms with `autocomplete` and paste |
| `i18n_ready` | strings in message files, `Intl` formatting, CSS logical properties |
| `perf_budget` | the Core Web Vitals budget (LCP, INP, CLS) as Lighthouse CI assertions |
| `public_page_basics` | title, description, Open Graph, icons, manifest, and designed 404, 500, and maintenance pages |
| `legal_placeholders` | privacy policy and terms pages a person writes |
| `transactional_email` | a plain-text part, SPF, DKIM, and DMARC, and one-click `List-Unsubscribe` on mail that is not strictly transactional |
| `api_conventions` | versioning, cursor pagination, `Idempotency-Key`, RFC 9457 errors, `RateLimit` fields |
| `data_conventions` | UTC times, integer minor units, UUIDv7 or ULID, `created_at`, `updated_at`, `created_by`, an undoable soft delete |
| `operability` | `/healthz`, `/readyz`, JSON logs with the trace ID, graceful SIGTERM |
| `security_headers` | CSP, HSTS, `nosniff`, Referrer-Policy, cookie flags, CSRF |
| `dev_basics` | formatter, linter, type check, pre-commit, `.editorconfig`, update bot, Conventional Commits |
| `modular_monolith` | `apps/`, `modules/`, `packages/` in one repository (`aidd-team:modular-monolith`) |

Twelve-Factor for `operability` and `dev_basics`: `aidd-team:observability`, `aidd-team:ci-pipeline`.

## Test commands

Each goes in the Spec's `tests.commands`, or in `tests` once it is the baseline.

| Command | Proves | How |
| --- | --- | --- |
| Performance budget | LCP 2.5 s or less, CLS 0.1 or less, and TBT 200 ms or less under a script-size cap in the lab; INP 200 ms from field data | `npx @lhci/cli@0.15.1 autorun` with assertions on the pages touched |
| Both themes | no WCAG 2.2 AA violation and no unreviewed visual change in either theme | Playwright `page.emulateMedia({colorScheme})`, then axe and `toHaveScreenshot` per state |
| Responsive and targets | no horizontal scroll at 320 CSS px, no target under 24 by 24 CSS px | Playwright per breakpoint (`scrollWidth <= clientWidth`) and axe's `target-size` |
| i18n readiness | no literal string in a component | a lint rule that bans a literal string, such as `eslint-plugin-i18next` |
| Public page basics | each public route has its title, description, and `og:image`; an unknown path gets the 404 | a test per route |
| Transactional email | a text/plain part, and `List-Unsubscribe` on the non-transactional ones | render each template and assert |
| Security headers | the four headers and the cookie attributes on every response; no CSRF token, no write | request each route and assert |
| API conventions | problem+json errors, one effect per `Idempotency-Key`, a next cursor, `Retry-After` on 429 | contract tests |
| Operability smoke | health and readiness answer; SIGTERM lets an in-flight request finish | SIGTERM mid-request |
| Dev basics | formatter, linter, and type check pass in CI and pre-commit | the pre-commit hooks over every file on a clean checkout, such as `pre-commit run --all-files` |

- From `aidd-team:internationalization`: Pseudo-localization build.

## Stop if

- A Task would turn a default on or off, or build one `project.defaults.disabled` names: a person edits the config.
- A Task would draft, edit, or paraphrase the privacy policy or terms.
- The repository already has a structure (adopted before this default, or source files and no `modules/`): never restructure it. `modular_monolith` shapes a new project only; a change of structure is an ADR a person decides.

## Hand off

- Done: the defaults that are on, built, each with its test green; the ones off, with the config's reason. Next: the reviewer. Needs: a person for the legal text, and to turn a default off. Stopped at: none, or the stop rule that fired.
