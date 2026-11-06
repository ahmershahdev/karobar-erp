# Design

White paper, navy ink, one orange accent. The site should feel like a well-kept ledger: calm,
exact, and obvious to use. Premium comes from type, spacing and restraint, not effects. The public
site and the app share the same tokens; the app is simply denser.

## Logo

The artwork is in `frontend/src/assets/brand/`, as WebP cut from the master logo. Always use
`components/Logo.tsx`; never redraw the mark.

| Variant | File | Use |
|---|---|---|
| `horizontal` | `logo-horizontal.webp` | headers, sidebar, footer. The default |
| `full` | `logo.webp` | the stacked logo: the loading screen |
| `mark` | `logo-mark.webp` | the cloud alone, where space is tight |

`horizontal` exists because the stacked logo's wordmark can't be read at bar height; it is the same
art with the cloud moved beside the name. Files in `public/` stay PNG on purpose: `favicon.png`,
`apple-touch-icon.png`, `icon-192.png`, `icon-512.png` and `og-image.png`, because iOS, older
browsers and social crawlers don't reliably take WebP there.

## Tokens

All colours, fonts, easings and radii live in `frontend/src/styles/tokens.css`. No raw hex values
in components. A new colour goes into `tokens.css` first, and needs a reason.

| Token | Value | Use |
|---|---|---|
| `canvas` | white | page background |
| `surface`, `raised` | two faint cool greys | tinted panels, hover, selected rows |
| `ink` | navy `#0b1a3c`, the logo's wordmark | text, primary buttons |
| `muted` | slate | secondary text |
| `ember` | deep orange | small accents as text: indexes, links |
| `flame` | bright orange | headline accent words only |
| `orange` | the logo's orange | decoration only, never text |
| `azure` | the logo's blue | focus rings, primary button hover |
| `red`, `green`, `yellow` | status | errors, success, warnings |
| `line`, `line-strong` | ink at 9% and 20% | hairlines and outlines |

The logo's orange is 2.3:1 on white, which fails as text, hence the three oranges. `ember` and the
status colours are at least 4.5:1 on `canvas` and `surface`; `flame` is 3.3:1, which is only enough
for large text, so it stays at headline size. There are no gradients, glows or glass panels, apart
from the blur under the sticky header.

## Type

| Role | Face | Where |
|---|---|---|
| Display and text | Geist; headings at 500, tightly tracked | everything |
| Figures | Geist Mono, tabular | ledger and table numbers only |
| Urdu | Noto Nastaliq Urdu | loaded only when Urdu is picked |
| Arabic | Noto Kufi Arabic | loaded only when Arabic is picked |

Scale: `.display-xl` (hero, up to 7rem), `.display-lg` (section titles), `.display-md` (statements),
`.label` (small muted captions, sentence case). Nastaliq and Kufi rise and fall far beyond Latin,
so the end of `global.css` gives them their own line heights outside the layers, where they beat
the type scale; without that, masks like `RollText` clip the script. Headlines split by word, never
by letter, because Arabic script letters join.

## Layout

- `.shell` is the page container: 84rem wide, with a fluid gutter (`--gutter`, 16px on phones).
- Space does the work. Sections are 6 to 9rem apart and carry a small index and eyebrow above the
  title.
- Lists are rows divided by hairlines. Ruled grids (`gap-px` over `bg-line`) hold sets of equal
  things like the modules. `.card` is for objects, like the journal entry.
- Buttons are `.btn` with `.btn-primary` (navy, blue on hover) or `.btn-ghost` (outline). One
  primary per view.
- Phone first. Every page is checked at 390px for horizontal overflow in all three languages; the
  header collapses into a full-screen menu below 768px.
- Never hide things with large negative offsets. In RTL, content off to the left is scrollable and
  widens the page; use `sr-only`.

## Motion

Motion explains or settles; it never performs. Nothing replaces the system cursor or hijacks the
scroll direction.

- `Preloader`: the logo rises out of a mask, a hairline draws under it, and the white screen fades
  into the page. About a second, public pages only, with a 3 second failsafe.
- `PageTransition`: a white veil fades in, the route swaps, it fades out. App screens switch
  instantly.
- `ProductWindow`: the app's sidebar and a live journal entry under the hero; it settles from 94%
  to full size as it scrolls into place.
- `SplitHeadline`, `Reveal`, `ScrollWords`: word reveals, staggered entrances, and a paragraph that
  darkens word by word as it crosses the screen.
- `Magnetic`: main calls to action lean slightly toward the pointer.
- `RollText`: nav and footer labels roll on hover.
- `Footer`: a full-width "KarobarERP" sits barely visible and lights up orange around the pointer.
- Module glyphs redraw themselves on hover.
- `ScrollTopButton`: floats bottom-right once you are a screen down, ringed by reading progress.
- Scroll lock (`lib/scroll-lock.ts`): the preloader and transition each hold a named lock while they
  cover the page; `scrollbar-gutter: stable` keeps the page from shifting when it comes back.
- Lenis smooths scrolling; anime.js runs every timeline.

`prefers-reduced-motion: reduce` turns all of this off: no preloader, Lenis, reveals or veil.

## App screens

The app reuses the tokens with less motion and no smooth scrolling inside tables. The sidebar sits
on `surface`, content on white, and the selected item is solid navy. Sign-in and sign-up are a split
screen on wide displays, the promise on a tinted panel and the form on white. The workspace sidebar
becomes a top bar on phones, with sign-out and the language switcher always reachable.
