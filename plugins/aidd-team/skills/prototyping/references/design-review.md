# The plan, the design artifacts, and the design review

Load this before you draw a direction, when a design artifact's trigger fires, or when you review the built UI against the approved prototype.

## Before code: the plan and the anti-default review

From Anthropic's frontend-design skill (Apache-2.0). For each direction, before any markup, a short plan:

- **Color**: 4–6 named colors, each on a role (`accent`, `surface`); with a design system, its roles, and a new color is a design-system change.
- **Type**: the families and their roles, and the scale by token.
- **Layout**: a layout concept in one sentence and an ASCII wireframe, with its alignment.
- **Principles**: what makes this screen this product's, in a line or two.

Then review the plan against the brief. Change a choice any similar brief would get, or keep it with the brief's reason. Such defaults include:

- a centred hero with a stat row;
- italic accent words in headlines;
- identical rounded cards with one soft shadow;
- a gradient wash;
- a cream background;
- an all-caps label over every heading;
- the default typeface;
- monospace labels;
- numbered markers on what is no sequence;
- pill-shaped buttons;
- an entrance animation on every section.

Note each change under the plan. The brief's own words and `DESIGN.md` win over novelty.

## Design artifacts, and when each is worth writing

Besides the prototype and the design spec, four artifacts help when their trigger fires. None is required or a file of its own: each is a section of the document that holds its context.

| Artifact | Where it lives | Write it when | Frozen or living |
| --- | --- | --- | --- |
| User flows | the design spec's `## Flows` | a feat adds screens or more than one journey: the sitemap, and each journey's entry, exit, and error paths | frozen with the Spec |
| Component | a row, or a subsection, in `DESIGN.md`'s Components | a component is new or changes: anatomy, props, states, accessibility, tokens, test ids | living, its own design-system change |
| Journey | the Initiative's `## Brief`, `### Journey` | discovery, before the solution: stages, pain points, and a service blueprint | living |
| Usability test | the design spec's `## Usability test` | before launch, a risky flow needs evidence from real users on the prototype; after launch, the feedback log | frozen with the Spec |

- **User flows** name only screens the Screen inventory lists, by the same names, with the Acceptance ids each covers.
- **Component**: tokens by name, never raw values; a new component or token is its own design-system change, merged before Spec approval.
- **Journey**: the product manager keeps it with the Initiative; each cell rests on evidence, a guess is marked "(assumed)", and it never holds the solution.
- **Usability test**: goals, participants, tasks, and script before the sessions; findings with severity and evidence after. Early rounds can run on `?mode=wireframe`. A person decides each finding; one that changes the Spec goes back through Spec approval.

## The design review: a pass/fail critique with proof

The product designer writes it in Review, after comparing the built UI with the approved prototype state by state. It goes to the author, who answers each point, and to the Approver, who weighs it at Merge approval. The designer never approves the change.

Each criterion passes or fails, and every result carries its proof: something a reader can open or rerun without asking you. The criteria are the approved prototype's states, the tokens, the WCAG 2.2 success criteria, and Nielsen's heuristics.

| Proof | Example |
| --- | --- |
| A screenshot path | `review/SPEC-220/error-state-built.png` beside `review/SPEC-220/error-state-prototype.png` |
| A token | `color.danger` expected, `#d32f2f` found in `checkout.css:41` |
| A lint or tool rule | `color-no-hex`, axe `button-name`, design.md `contrast-ratio` |
| A criterion | WCAG 2.2 SC 1.4.11 Non-text Contrast; SC 2.4.7 Focus Visible |
| A heuristic | Nielsen heuristic 1, visibility of system status |
| A state and the steps to reach it | "Empty state: fixture `orders=0`, then Tab to Retry" |

Sort the results into three kinds:

- **Keep.** A pass a later change could easily lose; naming it protects it.
- **Fix.** A fail: a difference from the approved prototype, or a failed rule or criterion. It changes before Merge approval, or goes back through Spec approval if the difference is better than what was approved.
- **Quick win.** A small improvement the prototype did not ask for, cheap enough to do now; optional, and a new change if it changes what was approved.

A point without proof is an opinion: drop it or find the proof. Give no numeric score, grade, or percentage: a score hides which point matters and traces to no proof. The list of Fix points is the verdict: none means the build matches what was approved.

```markdown
## Design review: SPEC-220 checkout, built UI against the approved prototype

Compared 6 of 6 named states at 1280 and 320 CSS pixels, keyboard-only and with VoiceOver.

### Fix
1. Error state: the retry button has no visible focus ring.
   Proof: review/SPEC-220/error-focus.png; WCAG 2.2 SC 2.4.7; prototype uses token `color.focus`.

### Keep
1. The loading state keeps the layout still while totals load.
   Proof: review/SPEC-220/loading.png; Nielsen heuristic 1, visibility of system status.

### Quick win
1. The empty-state copy could name the next step ("Add your first address").
   Proof: review/SPEC-220/empty.png; Nielsen heuristic 6, recognition rather than recall.
```

Order points by how much they matter to the person using the screen, inside each kind. Capture each screenshot at the prototype's viewport and state.

## Stop if

- The design spec's flows or usability test need a change after Spec approval. Note the drift in the verification report, and change it in a later change.
- A finding or an opportunity has no evidence: mark it assumed, or leave it out.
