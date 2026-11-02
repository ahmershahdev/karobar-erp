# Design

Two surfaces, two jobs. The public site sells the idea and can afford spectacle. The app is used
all day at a shop counter and has to be fast, dense and calm. Shared tokens keep them related.

The direction is called Ledger Noir: warm ink, bone-white type, molten gold light, and an
editorial layout that reads like a well-kept account book.

## Tokens

All colours, gradients, fonts, easings and radii live in `frontend/src/styles/tokens.css`. The
palette has 30 named colours (red, blue, green, yellow, orange, purple, black, white, grey, pink,
brown, navy, sky, maroon, violet, turquoise, cyan, magenta, cream, beige, silver, gold, olive,
teal, indigo, lavender, peach, coral, mint, charcoal), tuned to sit on warm ink: slightly
desaturated so the gold accents and the WebGL light stay the brightest things on the page. Each is
a Tailwind utility (`bg-gold`, `text-cream`, `border-teal`).

| Semantic token | Value | Use |
|---|---|---|
| `canvas` | black (warm ink) | page background |
| `surface`, `raised` | charcoal and one step lighter | cards, panels, hover |
| `ink` | cream | text |
| `muted` | warm grey | secondary text |
| `accent` | gold | focus, highlights, selection, indexes |
| `line`, `line-strong` | cream at 10% and 22% | hairlines and outlines |

Gradients: `molten` (gold, peach, coral) is the signature, used for primary buttons, italic
accents and the wordmark. `aurora`, `lagoon`, `orchard`, `dusk`, `sunrise`, `blossom` and
`earth` colour the modules.

No raw hex values in components. A new colour goes into `tokens.css` first.

## Type

| Role | Face | Where |
|---|---|---|
| Display | Instrument Serif, with its italic for accent words | headlines, numerals, wordmark |
| Text | Geist | body copy, forms, tables |
| Labels | Geist Mono, uppercase, tracked | eyebrows, indexes like `[02]`, figures |
| Urdu | Noto Nastaliq Urdu | loaded only when Urdu is picked |
| Arabic | Noto Kufi Arabic | loaded only when Arabic is picked |

Scale: `.display-xl` (hero, up to 11.5rem), `.display-lg` (section titles), `.display-md`
(statements), `.label` (mono labels). Nastaliq and Kufi get larger line heights per language in
`global.css`. Headlines split by word, never by letter, because Arabic script letters join.

## Layout

- `.shell` is the page container: 90rem wide, with a fluid gutter (`--gutter`, 16px on phones).
- Sections carry an index and an eyebrow (`[03] One sale, posted`) above a serif title.
- Lists are editorial rows divided by hairlines rather than grids of cards; cards (`.card`) are
  reserved for things that are objects, like the journal entry or a module.
- Phone first. Every page is checked at 390px for horizontal overflow; the header collapses into
  a full-screen menu below 768px, and the module gallery becomes a grid below 1024px.

## Motion and WebGL

- `features/scene/ParticleField.tsx`: one `THREE.Points` draw call with 22,000 particles (9,000
  on phones). Each particle has three positions, a globe, a 3D bar chart and a ring, and the
  vertex shader blends between them. Sections mark the shape they want with `data-morph="0|1|2"`;
  the scroll position between markers sets the blend. Particles drift, react to the pointer and
  fade to 40% past the hero so text stays readable. The canvas pauses when the tab is hidden.
- `Preloader`: the logo draws itself above a gold seam, the four things Karobar keeps (stock,
  sales, books, payroll) cycle below it, a mono counter runs to 100, then the screen opens like a
  ledger, top half up and bottom half down. About two seconds, public pages only, with a 4 second
  failsafe so it can never trap the page.
- `Header`: a floating glass capsule. Links roll their text on hover and a soft pill glides to the
  hovered link; the header hides while scrolling down and returns on the first scroll up; a gold
  hairline along its edge shows reading progress.
- `Footer`: a closing call to action with a large magnetic round button, link columns that roll
  on hover, the live time in Lahore, and a back-to-top button ringed by scroll progress.
- `Cursor`: a dot and a trailing ring that grows over anything clickable and shows its
  `data-cursor` label. Fine pointers only.
- `Magnetic`: primary buttons lean toward the pointer.
- `SplitHeadline`, `Reveal`, `ScrollWords`: word reveals, staggered entrances, and a paragraph
  that lights up word by word as it crosses the screen.
- `PageTransition`: an ink curtain with the wordmark between public pages; app screens switch
  instantly.
- Lenis smooths scrolling; anime.js runs every timeline.

`prefers-reduced-motion: reduce` turns all of this off: no preloader, cursor, Lenis, reveals or
curtain, and the particle field renders still frames that follow the scroll. When WebGL is
missing, the soft gradient backdrop stays and nothing else changes.

## App screens

The app reuses the tokens and type with less motion: no WebGL and no smooth scrolling inside
tables. Sign-in and sign-up use a split screen on wide displays. The workspace sidebar becomes a
top bar on phones, with sign-out and the language switcher always reachable.
