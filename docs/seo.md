# SEO

Public pages are the marketing site at `https://karobarerp.ahmershah.dev`. Everything under `/app`
is the product and is `noindex`.

## One source of truth

`frontend/src/seo/site.ts` holds the site facts and the list of public routes: path, name, title,
description and a longer summary. Everything else is generated from it:

| Output | Made by |
|---|---|
| `<head>` of each public page | `build/seo-plugin.ts` at build time, one `index.html` per route |
| Head updates during client-side navigation | `usePublicSeo()` in `src/lib/seo.ts` |
| `robots.txt`, `sitemap.xml` | `build/seo-plugin.ts` |
| `llms.txt`, `llms-full.txt` | `build/seo-plugin.ts`, following [llmstxt.org](https://llmstxt.org) |
| JSON-LD | `src/seo/jsonld.ts` |

The site URL comes from `VITE_SITE_URL` at build time; nothing hardcodes the domain.

## Every public route has

- a `<title>` under 60 characters and a meta description between 70 and 160 characters
  (`src/seo/seo.test.ts` fails otherwise, and checks that titles are unique),
- a canonical URL,
- Open Graph tags (`og:title`, `og:description`, `og:url`, `og:image` 1200x630, `og:type`,
  `og:site_name`, `og:locale`) and Twitter `summary_large_image` tags,
- JSON-LD with `Organization`, `WebSite`, `WebPage` and a `BreadcrumbList`; the home page also has
  `SoftwareApplication`,
- a visible breadcrumb trail on every page below home.

## Adding a public page

1. Add the route to `PUBLIC_ROUTES` in `src/seo/site.ts`.
2. Add the page component, call `usePublicSeo(PUBLIC_ROUTES[n])`, render `<Breadcrumbs>`.
3. Add the route to `App.tsx` and a link in the header or footer.
4. Run `npm test`; the SEO tests cover the new route automatically.

Private screens call `usePrivateSeo(title)`, which sets `noindex, nofollow`. nginx also sends
`X-Robots-Tag: noindex` for `/app`, and `robots.txt` disallows `/app` and `/api/`.

## Performance that affects ranking

- The hero paints a CSS gradient first; three.js loads lazily after it, so it never blocks LCP.
- Fonts are self-hosted; Urdu and Arabic fonts load only when those languages are picked.
- Hashed assets are cached for a year; HTML is `no-cache`.
