# The accessibility statement, and where the standard is heading

Load this to write an accessibility statement, and when someone names WCAG 3 or asks what to prepare for next.

## The statement

A service sold to consumers in the EU publishes an accessibility statement under the European Accessibility Act, Directive (EU) 2019/882, Annex V. It is a living text in the service's general terms or an equivalent page. It is never part of a frozen compliance record, because the published text changes with each release.

The compliance analyst writes it from the accessibility test results: the last run on the base branch, and the Acceptance ids that prove each change on its head. Delete it, with the reason, when the product or service is outside the Act.

- **Service.** A general description of the service, and how a person operates it (Annex V, points 1(a) and 1(b)).
- **Conformance.** How the service meets the requirements of Annex I (point 1(c)). Name the level the results show, such as EN 301 549 or WCAG 2.2 AA, and the test run and its commit.
- **Known exceptions.** Each failing criterion, why it fails, its workaround, and its fix date, or the disproportionate-burden assessment (Article 14) that covers it.
- **Contact.** Where a person reports a barrier or asks for the content in another format.
- **Date.** The date of the results the statement rests on, and its next review.

The compliance record links to this page for the statement and holds only the obligation and its evidence.

## Where the standard is heading (emerging)

WCAG 3.0 is a W3C Working Draft of 10 September 2026, not a standard. The W3C says that "WCAG 3 does not replace WCAG
2", and that it "is not expected to be a completed W3C standard for a few more years". So WCAG 2.2 AA stays the floor and
the only conformance you name. Never cite WCAG 3 in a test, a lint, a done line, or a claim. Its contrast method "is yet
to be determined", so the comfort checks keep APCA as an aid, never a rule.

The draft's new areas point to habits that already hold under WCAG 2.2 and good practice. Each is emerging: apply it
where it costs nothing extra, and never fail a change on it.

| Draft area | The habit now | Where it already lives |
| --- | --- | --- |
| Clear language | Write at the reader's level, in short sentences, with one word for one thing. | the `aidd-team:plain-language` skill |
| Prevent errors | Constrain the input, keep what a person typed after an error, and confirm a step they cannot undo. | WCAG 2.2 SC 3.3.4, 3.3.7 |
| Avoid deception | Show the total price first, and use no false urgency, hidden cost, or fake review. | the commerce, games, and children's packs |
| Adequate time | Let a person turn off, adjust, or extend a time limit. | WCAG 2.2 SC 2.2.1 |
| Unnecessary steps | Ask only for what the task needs, and never twice. | WCAG 2.2 SC 3.3.7 |
| Help available | Put help in the same place on every screen, and make each error say how to fix it. | WCAG 2.2 SC 3.2.6, 3.3.3 |
| User control | Follow the person's text size, motion, color scheme, and orientation. | this skill's Implement |
| Keyboard focus appearance | Draw a focus indicator a person finds at the size they see it. | "State indicators" in criteria.md; WCAG 2.2 SC 2.4.13 (AAA) |
| Physical or cognitive effort | Keep the Tab path short, and ask for no puzzle and no memory test. | WCAG 2.2 SC 2.4.1, 3.3.8 |

Sources, read on 2026-11-11 (UTC): the draft, <https://www.w3.org/TR/wcag-3.0/>, and the W3C's introduction, updated 25 September
2026, <https://www.w3.org/WAI/standards-guidelines/wcag/wcag3-intro/>.
