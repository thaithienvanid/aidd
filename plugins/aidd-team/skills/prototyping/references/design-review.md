# The design review report

Load this when you review the built UI against the approved prototype and write up what you found.

The product designer writes this report in Review, after comparing the built UI with the approved prototype state by state. It goes to the author, who answers each point, and to the Approver, who weighs it at Merge approval. The designer never approves the change.

## Shape

Each point is one of three kinds:

- **Keep.** Something the build got right that a later change could easily lose. Naming it protects it.
- **Fix.** A difference from the approved prototype, or a failure of a rule or a criterion. It must change before Merge approval, or go back through Spec approval if the difference is better than what was approved.
- **Quick win.** A small improvement the prototype did not ask for, cheap enough to do now. It is optional; if it changes what was approved, it is a new change, not part of this one.

Every point carries its proof: at least one thing a reader can open or rerun without asking you.

| Proof | Example |
| --- | --- |
| A screenshot path | `review/SPEC-220/error-state-built.png` beside `review/SPEC-220/error-state-prototype.png` |
| A token | `color.danger` expected, `#d32f2f` found in `checkout.css:41` |
| A lint rule or tool rule | `color-no-hex`, axe `button-name` |
| A criterion | WCAG 2.2 SC 1.4.11 Non-text Contrast; SC 2.4.7 Focus Visible |
| A heuristic | Nielsen heuristic 1, visibility of system status |
| A state and the steps to reach it | "Empty state: fixture `orders=0`, then Tab to Retry" |

A point without proof is an opinion; drop it or find the proof.

## No score

Do not give the design a number, a grade, or a percentage. A score hides which point matters, invites arguing about the number instead of the screen, and cannot be traced to a proof. The list of Fix points is the verdict: none means the build matches what was approved.

## Example

```markdown
## Design review: SPEC-220 checkout, built UI against the approved prototype

Compared 6 of 6 named states at 1280 and 320 CSS pixels, keyboard-only and with VoiceOver.

### Fix
1. Error state: the retry button has no visible focus ring.
   Proof: review/SPEC-220/error-focus.png; WCAG 2.2 SC 2.4.7; prototype uses token `color.focus`.
2. Card total uses a raw colour instead of the token.
   Proof: `color-no-hex` on src/checkout/total.css:12; expected `color.text`.

### Keep
1. The loading state keeps the layout still while totals load.
   Proof: review/SPEC-220/loading.png; Nielsen heuristic 1, visibility of system status.

### Quick win
1. The empty-state copy could name the next step ("Add your first address").
   Proof: review/SPEC-220/empty.png; Nielsen heuristic 6, recognition rather than recall.
```

Order points by how much they matter to the person using the screen, most first, inside each kind. Capture the screenshots with Playwright or Chrome DevTools MCP, at the same viewport and state as the prototype's, so the pair can be compared.
