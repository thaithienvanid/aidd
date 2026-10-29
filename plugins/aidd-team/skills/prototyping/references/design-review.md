# The plan, the fidelity pass, and the design review

Load this before you draw a direction or place an item, for a design artifact, before done, or to review the built UI.

## Before code: the plan and the anti-default review

From Anthropic's frontend-design skill (Apache-2.0). For each direction, before any markup, a short plan:

- **Color**: 4–6 named colors, each on a role (`accent`, `surface`); with a design system, its roles, and a new color is a design-system change.
- **Type**: the families and their roles, and the scale by token.
- **Layout**: a layout concept in one sentence and an ASCII wireframe, with its alignment, each item placed as [Where it goes](#where-it-goes) says.
- **Principles**: what makes this screen this product's, in a line or two.

Then review the plan against the brief. Change a choice any similar brief would get, or keep it with the brief's reason. Such defaults include a centred hero with a stat row, italic accent words, identical rounded cards with one soft shadow, and a gradient wash. So are a cream background, all-caps labels over headings, the default typeface, monospace labels, step numbers on items with no order, pill buttons, and an entrance animation per section.

Note each change under the plan. The brief's own words and `DESIGN.md` win over novelty.

## Where it goes

Place each item before you draw, and check it in review. A rule broken on purpose is a line in the Spec.

| Item | Rule | Standard |
| --- | --- | --- |
| Width classes | Plan compact (under 600 dp or CSS px), medium (600 to 839), and 840 up. Medium shows one side pane at a time. A toolbar keeps one row, the rest in a More menu. | Material 3 window size classes; Apple HIG toolbars |
| Navigation, primary action | The platform's home: an iPhone's bottom tab bar, Android's navigation bar or rail, the web's header or sidebar. One primary action, trailing, in view at every width. | Apple HIG, Material 3, web convention |
| Phone reach | Content in the middle; frequent actions along the top or bottom edge, such as the top-trailing primary action; rare ones in a corner menu. An edge or corner target gets more room, about 12 mm against 7 mm. | Hoober, UXmatters (2017) |
| Groups | Related items sit closer than the next group, with gaps from the spacing scale, on shared edges. | Gestalt proximity; the spacing tokens |
| Order | Visual order is DOM order, so reading and Tab follow what the eye sees. | WCAG 2.2 SC 1.3.2, 2.4.3 |
| Repeated items | Navigation, help, and shared controls keep the same relative order on every screen, and by convention the same place. | WCAG 2.2 SC 3.2.3, 3.2.6 |
| Sticky bars | A fixed or sticky bar paints above what scrolls under it and reserves its space: content ends clear of it, `scroll-padding` matches it, and focus never hides under it. | WCAG 2.2 SC 2.4.11, technique C43; Apple HIG safe areas |
| Overlays | An overlay, annotation, or toast never covers what it marks, the content beside it, the action it reports on, or the area a person works in while it is open. | Material snackbar placement |
| Targets | Frequent actions are big and near the hand: at least 24 by 24 CSS px, 44 pt on iOS, 48 dp on Android. | Fitts's law (1954); WCAG 2.2 SC 2.5.8 |

## Design artifacts

User flows go in the design spec's `## Flows` when a feat adds screens or journeys. A new or changed component goes in `DESIGN.md`'s Components, its own design-system change. A journey goes in the Initiative's `### Journey`. A usability test goes in the design spec's `## Usability test` when a risky flow needs evidence from real users. Flows and the usability test freeze with the Spec.

## Before done: the fidelity pass

Only reading screenshots checks the finish. A small UI fix gets a **quick pass** by its author, on what changed. A prototype before a round or done, and a new or reshaped screen, flow, or component, get the designer's **full pass**:

1. Take every screen and state at 320, a phone, and 1024, in both themes, then at 200% text and right to left.
2. List each defect with its view, file, and line: clipped text, edges out of line, spacing off the scale, a lost focus ring, a browser default, or a stuck state.
3. Run the screenshot loop for axe, sideways scroll, and placement ([prototype-screenshots.md](prototype-screenshots.md)).
4. Sort the points as the review below does. Done means no Fix is open.

## The design review: a pass/fail critique with proof

The product designer writes it in Review, after the fidelity pass compares the built UI with the approved prototype state by state. The author answers each point, and the Approver weighs it at Merge approval. The designer never approves the change.

Each criterion passes or fails, with proof a reader can open or rerun. The criteria are the approved prototype's states, the tokens, where each item goes, WCAG 2.2, and Nielsen's heuristics.

Proof is a screenshot path beside the prototype's, a token found against the one expected, a rule (axe `button-name`, WCAG 2.2 SC 2.4.7, Nielsen heuristic 1), or a state and the steps to reach it.

Sort the results into three kinds:

- **Keep.** A pass a later change could lose; naming it protects it.
- **Fix.** A fail: a difference from the approved prototype, or a failed rule. It changes before Merge approval, or goes back through Spec approval if the difference is better.
- **Quick win.** A small improvement nobody asked for, cheap to do now; optional, and a new change if it changes what was approved.

A point without proof is an opinion: drop it or find the proof. Give no numeric score, grade, or percentage, because a score hides which point matters. The Fix list is the verdict: none means the build matches what was approved.

```markdown
## Design review: SPEC-220 checkout against the approved prototype

6 of 6 states at 1280 and 320 CSS px, by keyboard and screen reader.

### Fix
1. Error state at 320: the toast covers the Pay button.
   Proof: review/SPEC-220/error-320.png; Where it goes, Overlays.

### Keep
1. Loading keeps the layout still while totals load.
   Proof: review/SPEC-220/loading.png; Nielsen heuristic 1.
```

Order points in each kind by what matters most.

## Stop if

- The design spec's flows or usability test need a change after Spec approval: note the drift in the verification report.
- A finding or an opportunity has no evidence: mark it assumed, or leave it out.
