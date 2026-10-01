# Monl Brand

Monl compiles business rules into a precise backend. Its identity is **typographic**: charcoal, cream, and copper reserved for actionable elements. The reference world is printing, not the terminal — a specification is read before it is executed.

## Mark

The mark represents the compiler core: a stable nucleus surrounded by four open transformation steps. The horizontal lockup pairs this mark with the word **MONL** and the descriptor **COMPILER**. The entire brand is monochrome.

Source files: [`brand/monl-mark.svg`](brand/monl-mark.svg) (the mark), [`brand/monl-wordmark.svg`](brand/monl-wordmark.svg) (the wordmark). Both are **vectorized from the artwork** by `outils/vectoriser_logo.py`, from the alpha channel of the transparent PNG. Do not edit them by hand: `src/monl_platform/brand.py` is the source; everything else derives from it. The original artwork is kept alongside them ([`brand/monl-logo-source.png`](brand/monl-logo-source.png)): without it, we could neither re-vectorize nor verify. The previous orange logo is archived as `brand/monl-logo-precedent-orange.png`, and the first banner as `brand/monl-logo-precedent.png`. These archives are never generation sources.

**The lockup is drawn in `currentColor`, with no background.** This is the rule that matters, and it comes from a measured defect: served as an `<img>`, the logo keeps the dark background of its artwork regardless of theme — the old banner had a **1.29:1** ratio against the dark page, making it literally invisible in the header. As SVG in the page, the mark and letters take the text color, while the page background remains visible through the openings.

**One exception: the favicon.** It lives in a tab, outside any page, with no inherited color, so it has its own badge and fixed strokes. This is the only place where a background is justified — a tab expects one. And `/favicon.ico` exists alongside the SVG: browsers request it automatically, and a 404 leaves them showing an old cached icon.

- Do not change the proportions or stroke thickness.
- Keep all four openings in the circle and the central nucleus.
- Do not replace the strokes with typographic characters.
- Keep clear space around the mark at least one quarter of its width.
- Minimum size: 16 px for the mark, 96 px for the full lockup.

## Palette

| Role | Light | Dark |
|---|---|---|
| Ink | `#2E2B25` | `#F9F4ED` |
| Paper | `#F9F4ED` | `#171512` |
| Surface | `#FFFDF9` | `#211E1A` |
| Secondary text | `#665F55` | `#B9B0A5` |
| Divider | `#DDD4C8` | `#403B34` |
| Control border | `#8B8175` | `#786F64` |
| Primary action | `#2E2B25` | `#F9F4ED` |
| Copper accent | `#924821` | `#E5A45F` |
| Code background | `#2E2B25` | `#0F0E0C` |
| Alert | `#B3123C` | `#FF90A6` |

**The primary action stays monochrome.** Buttons, links, and active states use the logo's ink or cream. Copper is reserved for fine markers: eyebrows, progress, and syntax. It does not fill a card or large section.

**Two values for one copper.** `#924821` on paper (6.62:1), `#E5A45F` on a dark background (6.59:1). Daytime copper would be too dark at night, and the reverse would be unreadable by day: it is one color in two values, not two accents to maintain.

**Two borders, not one.** `Divider` outlines a card or table row; `Control border` surrounds what can be clicked or filled in, and reaches **3:1** because WCAG 1.4.11 requires this of an interface component. Confusing the two makes secondary buttons and fields hard to distinguish from the background.

**The alert is an ink red, not orange.** It should read as another ink, not as a variation of the action copper.

No state is communicated by color alone: a label or icon always carries it too.

## Where these values live

In `src/monl_platform/theme.py`, and **nowhere else**. Pages use only variables (`var(--brand)`, `var(--code-muted)`): this is how an identity change is made in one place. An earlier redesign had left five hard-coded greens in the console — they survived a complete palette change without anything flagging them. `tests/test_platform_marque.py` now forbids this, and does not itself name any color: it measures contrast from the actually declared variables, so it remains valid as the direction changes.

## Typography and tone

Text uses the system sans-serif font; technical data uses monospace. No remote fonts: the platform must open behind a firewall, and this is the same independence it requires of the frontends it generates.

The tone is direct and factual: an action verb, an observable result, no vague promises. Write “Compile the backend” rather than “Start the magic.”
