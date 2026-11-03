# Design

Two surfaces, two jobs. The public site sells the idea and can afford spectacle. The app is used
all day at a shop counter and has to be fast, dense and calm. Shared tokens keep them related.

The direction follows the logo (`KarobarERP Cloud Growth Logo.png`): a midnight navy canvas
taken from the wordmark, the royal blue of the cloud, and the orange of the growth arrow and
"ERP" as the single accent, with heavy geometric headlines like the wordmark's letters.

## Tokens

All colours, gradients, fonts, easings and radii live in `frontend/src/styles/tokens.css`. The
palette has 30 named colours (red, blue, green, yellow, orange, purple, black, white, grey, pink,
brown, navy, sky, maroon, violet, turquoise, cyan, magenta, cream, beige, silver, ember, olive,
teal, indigo, lavender, peach, coral, mint, charcoal) plus `azure`, tuned to sit on navy. `ember`
(#f7931e) is the logo's orange and `azure` (#2563eb) its blue. Each is a Tailwind utility
(`bg-ember`, `text-cream`, `border-azure`).

| Semantic token | Value | Use |
|---|---|---|
| `canvas` | black (midnight navy) | page background |
| `surface`, `raised` | deep navy and one step lighter | cards, panels, hover |
| `ink` | cream (cool white) | text |
| `muted` | blue grey | secondary text |
| `accent` | ember | focus, highlights, selection, indexes, primary buttons |
| `line`, `line-strong` | cream at 10% and 22% | hairlines and outlines |

Gradients: `molten` (amber, ember, coral: the arrow) is the signature, used for primary buttons,
accent words and "ERP" in the wordmark. `cloud` (blue, azure, sky) is the logo's cloud. `aurora`, `lagoon`, `orchard`, `dusk`, `sunrise`, `blossom` and
`earth` colour the modules.

No raw hex values in components. A new colour goes into `tokens.css` first.

## Type

| Role | Face | Where |
|---|---|---|
| Display | Montserrat at 800, tightly tracked, like the logo's wordmark | headlines, numerals, wordmark |
| Text | Geist | body copy, forms, tables |
| Labels | Geist Mono, uppercase, tracked | eyebrows, indexes like `[02]`, figures |
| Urdu | Noto Nastaliq Urdu | loaded only when Urdu is picked |
| Arabic | Noto Kufi Arabic | loaded only when Arabic is picked |

Scale: `.display-xl` (hero, up to 8rem), `.display-lg` (section titles), `.display-md`
(statements), `.label` (mono labels). Nastaliq and Kufi get larger line heights per language in
`global.css`. Headlines split by word, never by letter, because Arabic script letters join.
Headings and imagery can't be selected or dragged; body text, tables and forms stay selectable.

## Layout

- `.shell` is the page container: 90rem wide, with a fluid gutter (`--gutter`, 16px on phones).
- Sections carry an index and an eyebrow (`[03] One sale, posted`) above a heavy sans title.
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
- `Preloader`: tells the logo's story. The cloud outline draws itself, the three bars rise with
  a little overshoot, the growth arrow shoots out of the cloud and its head pops, then
  "KarobarERP" lifts in letter by letter over the orange swoosh while stock, sales, books and
  payroll cycle below, with a blue and orange halo turning behind the mark. A percentage and an
  orange bar fill along the bottom; the screen then lifts away in six panels from the centre out. About two and a half seconds, public pages only, with a 5 second
  failsafe so it can never trap the page. The mark's geometry lives in `components/mark.ts`, shared
  with `Logo` and the favicon.
- `Header`: a floating glass capsule. Links roll their text on hover and a soft pill glides to the
  hovered link; the header hides while scrolling down and returns on the first scroll up; an orange
  hairline along its edge shows reading progress.
- `Footer`: a closing call to action with a large magnetic round button, link columns that roll
  on hover, the live time in Lahore, and a back-to-top button ringed by scroll progress.
- `Magnetic`: primary buttons lean toward the pointer.
- `Cursor`: an orange dot exactly on the pointer and a thin ring that trails it and opens over
  anything clickable. It never paints over the element under it (no fills, blurs or blend
  modes), so buttons keep their colours; over text fields it steps aside for the system I-beam.
  Fine pointers only, never with reduced motion.
- `PageTransition`: an orange wave and then a navy panel, both with curved leading edges, sweep
  up; the mark and wordmark show while the route swaps, then both continue upward. App screens
  switch instantly.
- Scroll lock (`lib/scroll-lock.ts`): the preloader and the page transition each hold a named lock
  while they cover the page, so nothing scrolls and no scrollbar shows; `scrollbar-gutter: stable`
  keeps the page from shifting when it comes back.
- `Footer`: links underline in orange from the start edge, and a full-width "KarobarERP" sits at
  the foot in low-contrast ink that lights up orange around the pointer.
- `ScrollTopButton`: floats bottom-right once you are a screen down, ringed by reading progress.
- Module cards: each module has a line-drawn glyph (`features/modules/catalog.tsx`) that redraws
  on hover, a status chip (live since, or arriving in, a milestone), its feature points, a 3D tilt
  and a spotlight that follows the pointer.
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
