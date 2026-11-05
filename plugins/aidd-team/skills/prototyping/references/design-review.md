# The plan, the quick pick, the fidelity pass, and the design review

Load this before you draw a direction or place an item, when taste decides an open question, for a design artifact,
before done, or to review the built UI.

**Contents**

<!-- aidd:gen toc -->
- [Before code: the plan and the anti-default review](#before-code-the-plan-and-the-anti-default-review)
- [A quick pick where taste decides](#a-quick-pick-where-taste-decides)
- [Where it goes](#where-it-goes)
- [Design artifacts](#design-artifacts)
- [Before done: the fidelity pass](#before-done-the-fidelity-pass)
- [The design review: a pass/fail critique with proof](#the-design-review-a-passfail-critique-with-proof)
- [Stop if](#stop-if)
<!-- aidd:end -->

## Before code: the plan and the anti-default review

From Anthropic's frontend-design skill (Apache-2.0). For each direction, before any markup, a short plan:

- **Color**: 4–6 named colors, each on a role (`accent`, `surface`); with a design system, its roles, and a new color is a design-system change.
- **Type**: the families and their roles, and the scale by token.
- **Layout**: a concept in one sentence and an ASCII wireframe, each item placed as [Where it goes](#where-it-goes) says.
- **Principles**: what makes this screen this product's, in a line or two.

Review the plan against the request. Change a choice any similar request would get, or keep it with the request's reason. Such defaults include a centred hero with a stat row, italic accent words, identical rounded cards with one soft shadow, and a gradient wash. So are a cream background, all-caps labels over headings, the default typeface, monospace labels, step numbers on items with no order, pill buttons, and an entrance animation per section.

Note each change under the plan. The request's words and `DESIGN.md` win over novelty.

## A quick pick where taste decides

Settle the open question first, before any pass or test: the one the lead's brief or the Task names, or the one you find.
When it is how something should look, and two or three answers are sound, it is a taste pick, so a person picks:

1. Render the options side by side in one screenshot, in context, at the size a person sees them. The options may differ
   only in color, size, or spacing.
2. Ask one question: the options, your recommendation and why, and the words to reply, such as "Reply A, B, or C".
3. Without the person, or in a headless run, put the options in a decision card instead: `aidd new exploration` with
   `taste_pick: true`, one direction per option, each with its own screenshot. `aidd explore` shows them side by side on
   one page. Name it on the handoff note's Needs line.
4. Record who picked, when, and why: in the Spec's `## Design`, in `DESIGN.md`'s Decisions for a design-system look, or,
   with no Spec, on the handoff note's `decided`. Then build the picked option, and only that one.

Ask only what a person can weigh by eye. A rule is never a pick: text at 200%, a contrast floor, or a keyboard path is
built in, and a layout that cannot hold one gets a fallback you propose.

## Where it goes

Place each item before you draw, and check it in review. A rule broken on purpose is a line in the Spec.

| Item | Rule | Standard |
| --- | --- | --- |
| Width classes | Plan compact (under 600 dp or CSS px), medium (600 to 839), and 840 up. Medium shows one side pane at a time. A toolbar keeps one row, the rest in a More menu. | Material 3 window size classes; Apple HIG toolbars |
| Navigation, primary action | The platform's home: an iPhone's bottom tab bar, Android's navigation bar or rail, the web's header or sidebar. One primary action, trailing, in view at every width. | Apple HIG, Material 3, web convention |
| Phone reach | Content in the middle; frequent actions along the top or bottom edge; rare ones in a corner menu. An edge or corner target gets more room, about 12 mm against 7 mm. | Hoober, UXmatters (2017) |
| Groups | Related items sit closer than the next group, with gaps from the spacing scale, on shared edges. | Gestalt proximity; the spacing tokens |
| Order | Visual order is DOM order, so reading and Tab follow what the eye sees. | WCAG 2.2 SC 1.3.2, 2.4.3 |
| Repeated items | Navigation, help, and shared controls keep the same order and place on every screen. | WCAG 2.2 SC 3.2.3, 3.2.6 |
| Sticky bars | A fixed or sticky bar paints above what scrolls under it and reserves its space: content ends clear of it, `scroll-padding` matches it, and focus never hides under it. | WCAG 2.2 SC 2.4.11, technique C43; Apple HIG safe areas |
| Overlays | An overlay, annotation, or toast never covers what it marks, the content beside it, the action it reports on, or the area a person works in while it is open. | Material snackbar placement |
| Targets | Frequent actions are big and near the hand: at least 24 by 24 CSS px, 44 pt on iOS, 48 dp on Android. | Fitts's law (1954); WCAG 2.2 SC 2.5.8 |

## Design artifacts

User flows go in the design spec's `## Flows` when a feat adds screens or journeys. A new or changed component goes in `DESIGN.md`'s Components, its own design-system change. A journey goes in the Intent's `## Map`. A usability test goes in the design spec's `## Usability test` when a risky flow needs evidence from real users. Flows and the usability test freeze with the Spec. A restyle still lists the parts to keep. The Spec's `## Design` records who picked a direction, when, and why.

## Before done: the fidelity pass

Only screenshots check the finish. Size the pass to what changed, and judge each view first at the size a person sees it,
then up close. A close-up that looks right can still be too weak to find on the screen. The product designer runs the
pass on a new or reshaped screen or flow, or a change to a component's look or states. Its author runs the quick pass on
any other UI change. `aidd prototype --shots` lists the views, in the order to take them:

| What changed | The views |
| --- | --- |
| A new or reshaped screen or flow, or a prototype before a round or done | The full matrix of those screens (`--changed-screen <id>`, or none for the whole design): every state at 320, a phone, and 1024, in both themes. Then 200% text and right to left, on each screen's fullest state. |
| A component's look or states, or a token it draws | `--changed-component <name>`: first each screen it appears on, at the default frame and theme. Then its interaction states, once on each variant, in both themes, with the state check. Then the narrowest frame and 200% text, on it alone. |
| Any other UI change, such as copy or the layout inside one screen | The quick pass: the changed screens and states, in both themes. |

A product that ships other frames names them with `--frames`, such as `desktop,desktop-1440` for a desktop app.

1. Take the views in order, and read each screenshot. When the view a person sees first fails, fix it or ask before any
   close-up. Check each frame against the device table.
2. List each defect with its view, file, and line: clipped text, edges out of line, spacing off the scale, a lost focus ring, a browser default, or a stuck state.
3. Run the screenshot loop for axe, sideways scroll, placement, and the state check ([prototype-screenshots.md](prototype-screenshots.md)).
   Run axe's contrast rule and `aidd-team:accessible-ui`'s comfort checks on a sketch too, never by hand.
4. Sort the points as the review does. Done means no Fix is open.

Some things never scale down: axe and the comfort checks on every view taken, real copy, both themes for what changed,
and each screenshot read. Text at 200% and a 320 CSS px width hold on every screen (WCAG 2.2 SC 1.4.4 and 1.4.10). Build
them in: type and spacing in relative units, and the loop's sideways-scroll check at the narrowest frame. Where a layout
cannot hold at either, say so and propose the fallback, such as a stacked layout or a More menu. The fallback is the one
thing a person decides there.

## The design review: a pass/fail critique with proof

The product designer writes it in Review, after the fidelity pass compares the built UI with the approved prototype state by state. The author answers each point, and the person weighs it at Merge approval. The designer never approves the change. Name its screenshots as the loop does, for Compare.

Each criterion passes or fails, with proof a reader can open or rerun. The criteria are the approved prototype's states, the tokens, where each item goes, WCAG 2.2, comfort, and Nielsen's heuristics.

Proof is a screenshot path beside the prototype's, a token found against the one expected, a rule (axe `button-name`, WCAG 2.2 SC 2.4.7, Nielsen heuristic 1), or a state and the steps to reach it.

Sort the results into three kinds, most important first:

- **Keep.** A pass a later change could lose; naming it protects it.
- **Fix.** A fail: a difference from the approved prototype, or a failed rule. It changes before Merge approval, or goes back through Spec approval if the difference is better.
- **Quick win.** A small improvement nobody asked for, cheap to do now; optional, and a new change if it changes what was approved.

A point without proof is an opinion: drop it or find the proof. Give no numeric score, grade, or percentage. The Fix list is the verdict: none means the build matches what was approved.

```markdown
## Design review: SPEC-220 checkout against the approved prototype

6 of 6 states at 1280 and 320 CSS px, by keyboard and screen reader.

### Fix
1. Error state at 320: the toast covers the Pay button.
   Proof: review/SPEC-220/error-320.png; Where it goes, Overlays.
```

## Stop if

- The design spec's flows or usability test need a change after Spec approval: note the drift in the verification report.
- A finding or an opportunity has no evidence: mark it assumed, or leave it out.
