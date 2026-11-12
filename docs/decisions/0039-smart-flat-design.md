# 39. aidd's pages and a new project's design start from smart flat

Accepted on 2026-11-16. It is in force. `docs/design/DESIGN.md` states the model and its eight rules, the starting `DESIGN.md` gives it as the start, and `aidd prototype --check` refuses a raw shadow or blur.
The project owner decided it. Every contributor is informed through this record.

## Context and problem statement

aidd's pages, the design a project starts from, and the designer's rules each drew depth in their own way. Nothing said when a shadow is right. A shadow vanishes where a person sets forced colors, and a design with no depth at all gives a clickable thing no cue. Which depth model should they all follow, and how much of it should the check refuse?

## Considered options

- **Strictly flat, with no shadow anywhere.** It costs the cue a clickable part needs. In 2017 the Nielsen Norman Group studied 71 people. Pages with weak signifiers, where clickable parts looked flat, cost 22% more time and 25% more fixations. A layer over content also reads as part of the page.
- **A shadow on every raised surface.** It costs the edge in forced colors. There `box-shadow` and `text-shadow` compute to none (CSS Color Adjustment Module Level 1), so a separation told by a shadow alone vanishes.
- **Smart flat, with flat surfaces told apart by tone and a border, one shadow for a layer that floats, and a real border on every floating layer.** It costs a few more rules and one more border on the toast. It also needs a review of the rules that no check can measure.

## Decision outcome

The chosen option is "smart flat", because it keeps the cue a floating layer needs and the edge that forced colors keep, with one shadow token.

> Smart flat is the start for aidd's pages and for a new project's design. It has three levels at most. Tone and a border come first. One shadow is for a layer that floats over content, and that layer keeps a real border too. A product may state another depth model in its own `DESIGN.md`, in tokens. `aidd prototype --check` holds one rule in any design. A shadow or blur outside the tokens block is a ring, zero, or a token.

### The case that decided it

The owner asked on 2026-11-16 for smart flat design by default, beside accessibility and comfort. The shadow is for floating layers only, and every floating layer carries a real border. Strictly flat is not the goal. Two facts were read again at their sources that day. In forced colors a shadow computes to none, and `border-color` is forced to a system color, so a border stays. A transparent border is painted too, as a test shows in Chrome. The study above measured the cost of a flat clickable part.

### Consequences

- Good, because a floating layer keeps its edge in forced colors, a clickable part keeps its cue, and a project states depth once, as tokens.
- Good, because the check refuses a stray shadow or blur with its file and line. A project with five levels or a glass style passes with its values as tokens.
- Bad, because the check reads rule 1 only. The other seven rules need a judgment or a browser, so aidd's own tests and the designer's review hold them.
- Bad, because the check does not read an SVG filter, a paint server, a bevel drawn with borders, or an image of a shadow. It also leaves a custom property outside the tokens block that holds a shadow.
- Bad, because `prefers-reduced-transparency` is a Working Draft that some browsers lack. A design that reads it keeps its look where it is missing.

### Reopen when

A product needs the check to count levels or judge a clickable cue. A gradient may become a token type. A measured study may show that flat clickable parts no longer cost attention.

## More information

[docs/design/DESIGN.md](../design/DESIGN.md) holds the eight rules under "Elevation & Depth". The sources are [CSS Color Adjustment Module Level 1](https://www.w3.org/TR/css-color-adjust-1/), the Nielsen Norman Group's [Flat UI Elements Attract Less Attention and Cause Uncertainty](https://www.nngroup.com/articles/flat-ui-less-attention-cause-uncertainty/), and [Media Queries Level 5](https://www.w3.org/TR/mediaqueries-5/). The [prototype tool's README](../../plugins/aidd-team/tools/prototype/README.md) says what the check reads.
