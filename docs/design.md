# Design

Two surfaces, two jobs. The public site sells the idea and can afford spectacle. The app is used
all day at a shop counter and has to be fast, dense and calm. Shared tokens keep them related.

## Tokens

All colours, gradients, fonts, easings and radii live in `frontend/src/styles/tokens.css`. The
palette has 30 named colours (red, blue, green, yellow, orange, purple, black, white, grey, pink,
brown, navy, sky, maroon, violet, turquoise, cyan, magenta, cream, beige, silver, gold, olive,
teal, indigo, lavender, peach, coral, mint, charcoal), each available as a Tailwind utility
(`bg-gold`, `text-cream`, `border-teal`).

Semantic names sit on top and are what components should reach for first:

| Token | Value | Use |
|---|---|---|
| `canvas` | black | page background |
| `surface` | charcoal | cards, panels |
| `ink` | cream | body text |
| `muted` | silver | secondary text |
| `accent` | gold | focus rings, highlights, selection |
| `line` | cream at 10% | borders and dividers |

Gradients, each named for what it evokes:

| Name | Colours | Used for |
|---|---|---|
| `aurora` | navy, indigo, violet, magenta | page transition curtain, CTA panel |
| `ledger` | gold, peach, coral | primary buttons, totals, headings |
| `lagoon` | teal, cyan, sky | modules, inventory |
| `orchard` | olive, green, mint | languages, success states |
| `dusk` | maroon, purple, lavender | security |
| `sunrise` | orange, yellow | tax |
| `blossom` | pink, peach | point of sale |
| `earth` | brown, beige | HR and payroll |

No raw hex values in components. A new colour goes into `tokens.css` first.

## Type

Fraunces (display serif) for headings, Inter for text, Noto Kufi Arabic for Arabic and Noto
Nastaliq Urdu for Urdu. Nastaliq needs much taller lines; `global.css` sets them per language.
Animations split headlines by word, never by letter, because Arabic script letters join.

## Motion

- Lenis for smooth scrolling, anime.js for reveals, counters and the page transition curtain,
  three.js for the hero shader (`features/hero/silk-shader.ts`).
- `prefers-reduced-motion: reduce` turns off Lenis, reveals and the curtain, and renders the
  shader as a single still frame. Check both modes for every new effect.
- The hero shader pauses when it is off screen or the tab is hidden, caps the pixel ratio at
  1.75, and falls back to the CSS gradient when WebGL is missing.
- Durations: 180 ms for hover, 420 ms for small transitions, about 1 s for reveals. Ease out with
  `--ease-out-expo` for entrances.

## Details

- Custom scrollbar (gold to coral to violet thumb) and gold text selection in `global.css`.
- A fixed film-grain overlay (`.grain`) at 6% opacity.
- Cards use `.gradient-border` with a `--gradient` custom property.
- Every interactive element has a visible `:focus-visible` ring in gold.
- Layouts use logical properties (`ps-`, `pe-`, `start-`, `end-`, `text-start`) so right-to-left
  works without separate styles.

## App screens

The app will reuse the tokens with less motion: no WebGL, no smooth scrolling inside tables, and
transitions only where they explain a change (a row being posted, a total updating).
