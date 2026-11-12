# Comfort: the target above the AA floor

WCAG 2.2 AA is the floor, and every pair keeps it. Comfort is the target above it, for a person who reads a screen for
hours. Check each rule from the tokens by script, in both themes, and never work a ratio out by hand. APCA-W3
0.0.98G-4g is a candidate contrast method outside any W3C standard (emerging), so it measures a target and never
replaces the WCAG check. |Lc| is APCA's lightness contrast, without its sign. The Lc bands, floors, and caps below are
aidd's own convention, calibrated on Material 3's levels and measured with APCA as an aid. They are not APCA's
thresholds, and APCA's size table does not apply.

## The rules

| Rule | What holds | Source |
| --- | --- | --- |
| C1 Floor and target | Every pair keeps 4.5:1 for text and 3:1 for UI. Small text aims for 7:1. | WCAG 2.2 SC 1.4.3 and 1.4.11; Apple HIG, Dark Mode |
| C2 Body text | Body text on its page reaches 7:1, at \|Lc\| 90 to 102 in light and 82 to 90 in dark. So it is never pure black on pure white, or near-white on near-black. Never drop below Lc 90 in light to soften it. | Material 3's on-surface roles, measured with APCA |
| C3 Secondary text | A solid token at 4.5:1 or more on every surface it sits on, \|Lc\| 60 or more on the page, and 15 Lc or more below body text. | aidd's convention, measured with APCA |
| C4 Emphasis | A view has at most three text levels, each a solid token: body, secondary, and disabled or placeholder. Size and weight carry hierarchy before color, and a row gets one bold run at most. | Apple HIG and Material 3 typography |
| C5 Surfaces | The light page is not pure white; white is a raised card or a dialog. The dark page is a grey at OKLCH L 0.18 or more, and a raised dark surface is lighter. | Material 3 surface roles; Material dark theme; Apple HIG base and elevated |
| C6 Large fills | A fill bigger than an icon, such as a filled button, a chosen row, a toast, or a banner, keeps \|Lc\| 90 or less on the page, a card, and a dialog. In dark mode a filled primary is a softened tone, never the text's full brightness. | Material 3's dark primary at tone 80, measured with APCA |
| C7 Saturation | A fill wider than a control, such as a page, panel, row, notice, or banner, keeps OKLCH chroma at 0.06 or less. A saturated hue goes into text, an icon, an edge, or a fill the size of a control. A system may name one alarm exception. | Material dark theme: desaturated colors |
| C8 Opacity | Alpha is for decoration: a divider, a halo, a scrim, a shadow, an underline, a dimmed image, and a disabled control whose blended text keeps Lc 30. Text takes a solid token, because alpha text changes its contrast with what lies behind it. A divider is the text color at 10 to 14%. | WCAG 2.2 SC 1.4.3 |
| C9 Reading | Body text is 14px or more in a tool and 16px on a reading page, with a line height of 1.5 or more. A block of prose runs 80 characters a line or fewer, and a one-line row may run wider. | WCAG 2.2 SC 1.4.8; Butterick, line length |
| C10 Motion | Motion explains a change, then stops. Nothing loops or pulses in a reading area, and nothing plays by itself. Under reduced motion, a move becomes a cut or a short fade. | WCAG 2.2 SC 2.2.2 and 2.3.3 |

## Check the tokens

APCA-W3 0.0.98G-4g, in the standard library. `rgb` is three sRGB channels from 0 to 1, and a role with alpha is first
blended over the surface it sits on.

```python
def apca(text, bg):
    def y(rgb):
        v = sum(k * c**2.4 for k, c in zip((0.2126729, 0.7151522, 0.0721750), rgb))
        return v + (0.022 - v) ** 1.414 if v < 0.022 else v
    yt, yb = y(text), y(bg)
    if abs(yb - yt) < 0.0005:
        return 0.0
    if yb > yt:
        s = (yb**0.56 - yt**0.57) * 1.14
        return 0.0 if s < 0.1 else (s - 0.027) * 100
    s = (yb**0.65 - yt**0.62) * 1.14
    return 0.0 if s > -0.1 else (s + 0.027) * 100
```

For C5 and C7, convert each surface to OKLCH, as CSS Color 4 does, and read L and chroma.

## Probe each state

Run this in the page for each state and theme, such as with Playwright's `page.evaluate`. It lists text drawn with
opacity and prose past about 80 characters a line, at about 0.46em a character.

```js
const found = [];
for (const e of document.querySelectorAll("p, li, dd, td, span, a, button, label, h1, h2, h3")) {
  if (!e.textContent.trim() || !e.checkVisibility()) continue;
  const s = getComputedStyle(e);
  let o = 1;
  for (let n = e; n; n = n.parentElement) o *= +getComputedStyle(n).opacity;
  if (o < 1 || /rgba\(.*,\s*0?\.\d+\)|\/\s*0?\.\d+/.test(s.color)) found.push(["text with opacity", e]);
  const lh = s.lineHeight === "normal" ? parseFloat(s.fontSize) * 1.2 : parseFloat(s.lineHeight);
  const lines = e.offsetHeight / lh;
  if (e.matches("p") && lines >= 2 && e.clientWidth / parseFloat(s.fontSize) > 37) found.push(["prose over 80 characters", e]);
}
```

## Sources

- APCA in a Nutshell: <https://git.apcacontrast.com/documentation/APCA_in_a_Nutshell.html>
- Apple HIG, Dark Mode: <https://developer.apple.com/design/human-interface-guidelines/dark-mode>
- Material 3 color roles: <https://github.com/material-components/material-components-android/blob/master/docs/theming/Color.md>
- Material dark theme: <https://github.com/material-components/material-components-android/blob/master/docs/theming/Dark.md>
- WCAG 2.2 SC 1.4.8: <https://www.w3.org/WAI/WCAG22/Understanding/visual-presentation.html>
- Butterick, line length: <https://practicaltypography.com/line-length.html>
