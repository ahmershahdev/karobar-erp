import { HOME_FAQ, PUBLIC_ROUTES, SITE, absoluteUrl, type PublicRoute } from './site';

type JsonLd = Record<string, unknown>;

export function breadcrumbs(siteUrl: string, route: PublicRoute): JsonLd {
  const trail = route.path === '/' ? [PUBLIC_ROUTES[0]] : [PUBLIC_ROUTES[0], route];
  return {
    '@type': 'BreadcrumbList',
    itemListElement: trail.map((step, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: step.name,
      item: absoluteUrl(siteUrl, step.path),
    })),
  };
}

export function structuredData(siteUrl: string, route: PublicRoute): JsonLd {
  const org = { '@id': absoluteUrl(siteUrl, '/#organization') };
  const graph: JsonLd[] = [
    {
      '@type': 'Organization',
      '@id': org['@id'],
      name: SITE.name,
      url: absoluteUrl(siteUrl, '/'),
      logo: absoluteUrl(siteUrl, '/favicon.svg'),
      email: SITE.email,
      founder: { '@type': 'Person', name: SITE.author, url: SITE.authorUrl },
      sameAs: [SITE.repo],
    },
    {
      '@type': 'WebSite',
      '@id': absoluteUrl(siteUrl, '/#website'),
      url: absoluteUrl(siteUrl, '/'),
      name: SITE.name,
      inLanguage: ['en', 'ur', 'ar'],
      publisher: org,
    },
    {
      '@type': 'WebPage',
      '@id': absoluteUrl(siteUrl, route.path),
      url: absoluteUrl(siteUrl, route.path),
      name: route.title,
      description: route.description,
      isPartOf: { '@id': absoluteUrl(siteUrl, '/#website') },
      breadcrumb: breadcrumbs(siteUrl, route),
    },
  ];
  if (route.path === '/') {
    graph.push({
      '@type': 'SoftwareApplication',
      name: SITE.name,
      applicationCategory: 'BusinessApplication',
      operatingSystem: 'Web',
      license: 'https://opensource.org/license/mit',
      offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' },
      author: { '@type': 'Person', name: SITE.author, url: SITE.authorUrl },
      codeRepository: SITE.repo,
    });
    graph.push({
      '@type': 'FAQPage',
      mainEntity: HOME_FAQ.map((item) => ({
        '@type': 'Question',
        name: item.q,
        acceptedAnswer: { '@type': 'Answer', text: item.a },
      })),
    });
  }
  return { '@context': 'https://schema.org', '@graph': graph };
}

// JSON-LD sits inside a <script> element, so "</script>" in any string would end it early.
export function serializeJsonLd(data: JsonLd): string {
  return JSON.stringify(data).replace(/</g, '\\u003c');
}
