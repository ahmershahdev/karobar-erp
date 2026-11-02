import { describe, expect, it } from 'vitest';

import { headFor } from '../../build/seo-plugin';
import { breadcrumbs, serializeJsonLd, structuredData } from './jsonld';
import en from '../i18n/locales/en.json';
import { HOME_FAQ, PUBLIC_ROUTES, absoluteUrl } from './site';

const SITE_URL = 'https://karobarerp.ahmershah.dev';

describe.each(PUBLIC_ROUTES)('public route $path', (route) => {
  it('has a title under 60 and a description under 160 characters', () => {
    expect(route.title.length).toBeLessThanOrEqual(60);
    expect(route.description.length).toBeLessThanOrEqual(160);
    expect(route.description.length).toBeGreaterThanOrEqual(70);
  });

  it('renders canonical, Open Graph, Twitter and JSON-LD tags', () => {
    const head = headFor(SITE_URL, route);
    const url = absoluteUrl(SITE_URL, route.path);
    expect(head).toContain(`<link rel="canonical" href="${url}" />`);
    expect(head).toContain(`<meta property="og:url" content="${url}" />`);
    expect(head).toContain('<meta name="twitter:card" content="summary_large_image" />');
    expect(head).toContain('"@type":"BreadcrumbList"');
  });

  it('builds a breadcrumb trail that starts at home', () => {
    const trail = breadcrumbs(SITE_URL, route).itemListElement as { item: string }[];
    expect(trail[0]?.item).toBe(`${SITE_URL}/`);
    expect(trail.at(-1)?.item).toBe(absoluteUrl(SITE_URL, route.path));
  });
});

it('titles are unique across public routes', () => {
  const titles = PUBLIC_ROUTES.map((route) => route.title);
  expect(new Set(titles).size).toBe(titles.length);
});

it('JSON-LD cannot close its script tag', () => {
  const json = serializeJsonLd({ name: '</script><script>alert(1)</script>' });
  expect(json).not.toContain('</script>');
  expect(JSON.parse(json)).toEqual({ name: '</script><script>alert(1)</script>' });
});

it('only the home page claims to be the software application', () => {
  const types = (route: (typeof PUBLIC_ROUTES)[number]) =>
    (structuredData(SITE_URL, route)['@graph'] as { '@type': string }[]).map((n) => n['@type']);
  expect(types(PUBLIC_ROUTES[0])).toContain('SoftwareApplication');
  expect(types(PUBLIC_ROUTES[1])).not.toContain('SoftwareApplication');
});

it('the FAQ markup matches the FAQ on the page', () => {
  expect(HOME_FAQ).toEqual(en.home.faq.items);
});
