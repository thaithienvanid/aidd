# The criteria teams miss, and what the tools prove

Load this in Specify for a new screen or form, and in Verify when you set up the automated checks.

## WCAG 2.2 criteria that teams miss

WCAG 2.2 added these at levels A and AA. Older checklists leave them out.

- **Dragging movements (2.5.7).** Each drag has a single-pointer alternative, such as buttons that move an item up and down.
- **Consistent help (3.2.6).** Help, such as a contact link or a chat, sits in the same place on each page.
- **Redundant entry (3.3.7).** A form never asks again for what the person already gave in the same process. Fill it in, or let them pick it.
- **Accessible authentication (3.3.8).** Sign-in needs no puzzle and no memory test. Paste works in every field, so a password manager works.

Two older criteria are often missed too:

- **Text spacing (1.4.12).** Content survives larger line, paragraph, letter, and word spacing with nothing cut off.
- **Orientation (1.3.4).** The screen works in both portrait and landscape, unless one orientation is essential.

## What the automated checks prove

- axe checks only the rules it can test by machine, so it finds part of the failures. The keyboard and screen-reader passes still run.
- Scope axe to WCAG with the tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, and `wcag22aa`. Without tags it also runs best-practice rules, which are advice, not WCAG failures.
- Run it once per screen state, theme, and motion setting, after `page.emulateMedia({colorScheme, reducedMotion})`.
- On mobile, the platform audits check labels, contrast, and touch targets. A cross-platform toolkit has its own checks, such as Flutter's `meetsGuideline` matchers in widget tests.
