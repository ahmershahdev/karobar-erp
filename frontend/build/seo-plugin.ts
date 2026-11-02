import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

import type { Plugin } from 'vite';

import { structuredData, serializeJsonLd } from '../src/seo/jsonld';
import { NOINDEX_PREFIXES, PUBLIC_ROUTES, SITE, absoluteUrl } from '../src/seo/site';
import type { PublicRoute } from '../src/seo/site';

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

export function headFor(siteUrl: string, route: PublicRoute): string {
  const url = absoluteUrl(siteUrl, route.path);
  const image = absoluteUrl(siteUrl, SITE.ogImage);
  const title = escapeHtml(route.title);
  const description = escapeHtml(route.description);
  return [
    `<title>${title}</title>`,
    `<meta name="description" content="${description}" />`,
    `<link rel="canonical" href="${url}" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:site_name" content="${SITE.name}" />`,
    `<meta property="og:locale" content="${SITE.locale}" />`,
    `<meta property="og:title" content="${title}" />`,
    `<meta property="og:description" content="${description}" />`,
    `<meta property="og:url" content="${url}" />`,
    `<meta property="og:image" content="${image}" />`,
    `<meta property="og:image:width" content="1200" />`,
    `<meta property="og:image:height" content="630" />`,
    `<meta property="og:image:alt" content="${SITE.name}" />`,
    `<meta name="twitter:card" content="summary_large_image" />`,
    `<meta name="twitter:title" content="${title}" />`,
    `<meta name="twitter:description" content="${description}" />`,
    `<meta name="twitter:image" content="${image}" />`,
    `<script type="application/ld+json" id="structured-data">${serializeJsonLd(structuredData(siteUrl, route))}</script>`,
  ].join('\n    ');
}

function robots(siteUrl: string): string {
  const disallow = NOINDEX_PREFIXES.map((prefix) => `Disallow: ${prefix}`).join('\n');
  return `User-agent: *\nAllow: /\n${disallow}\nDisallow: /api/\n\nSitemap: ${absoluteUrl(siteUrl, '/sitemap.xml')}\n`;
}

function sitemap(siteUrl: string, lastmod: string): string {
  const urls = PUBLIC_ROUTES.map(
    (route) =>
      `  <url>\n    <loc>${absoluteUrl(siteUrl, route.path)}</loc>\n    <lastmod>${lastmod}</lastmod>\n    <changefreq>${route.changefreq}</changefreq>\n    <priority>${route.priority.toFixed(1)}</priority>\n  </url>`,
  ).join('\n');
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls}\n</urlset>\n`;
}

function llms(siteUrl: string): string {
  const links = PUBLIC_ROUTES.map(
    (route) => `- [${route.name}](${absoluteUrl(siteUrl, route.path)}): ${route.description}`,
  ).join('\n');
  return `# ${SITE.name}\n\n> ${PUBLIC_ROUTES[0].description}\n\nOpen source under the MIT license. Source code: ${SITE.repo}\n\n## Pages\n\n${links}\n\n## Optional\n\n- [Full text for language models](${absoluteUrl(siteUrl, '/llms-full.txt')})\n`;
}

function llmsFull(siteUrl: string): string {
  const sections = PUBLIC_ROUTES.map(
    (route) =>
      `## ${route.name}\n\nURL: ${absoluteUrl(siteUrl, route.path)}\n\n${route.description}\n\n${route.summary}\n`,
  ).join('\n');
  return `# ${SITE.name}\n\n${PUBLIC_ROUTES[0].summary}\n\nAuthor: ${SITE.author} (${SITE.authorUrl}). Contact: ${SITE.email}. License: MIT. Source: ${SITE.repo}\n\nLanguages: English, Urdu and Arabic, with right-to-left layouts for Urdu and Arabic.\n\n${sections}`;
}

const HEAD_MARKER = '<!--seo-head-->';
const HEAD_BLOCK = /<!--seo:start-->[\s\S]*?<!--seo:end-->/;
const LD_NONCE = /id="structured-data"( nonce="[^"]*")/;

function wrapHead(head: string): string {
  return `<!--seo:start-->
    ${head}
    <!--seo:end-->`;
}

/**
 * Writes one HTML file per public route with its own head, so crawlers and link previews get
 * the right title, canonical and JSON-LD without running JavaScript, and emits robots.txt,
 * sitemap.xml, llms.txt and llms-full.txt from the same route list.
 *
 * The route pages are copied from the final index.html after Vite has written it, because
 * Vite rewrites emitted .html assets and would drop them.
 */
export function seoPlugin(siteUrl: string): Plugin {
  if (!siteUrl) throw new Error('VITE_SITE_URL must be set');
  let outDir = 'dist';
  return {
    name: 'karobar-seo',
    configResolved(config) {
      outDir = config.build.outDir;
    },
    transformIndexHtml: {
      order: 'post',
      handler: (html) => html.replace(HEAD_MARKER, wrapHead(headFor(siteUrl, PUBLIC_ROUTES[0]))),
    },
    generateBundle() {
      const lastmod = new Date().toISOString().slice(0, 10);
      const files: Record<string, string> = {
        'robots.txt': robots(siteUrl),
        'sitemap.xml': sitemap(siteUrl, lastmod),
        'llms.txt': llms(siteUrl),
        'llms-full.txt': llmsFull(siteUrl),
      };
      for (const [fileName, source] of Object.entries(files)) {
        this.emitFile({ type: 'asset', fileName, source });
      }
    },
    async writeBundle() {
      const index = await readFile(join(outDir, 'index.html'), 'utf8');
      if (!HEAD_BLOCK.test(index)) throw new Error('index.html lost its SEO head block');
      const nonce = LD_NONCE.exec(index)?.[1] ?? '';
      for (const route of PUBLIC_ROUTES.slice(1)) {
        const head = headFor(siteUrl, route).replace(
          'id="structured-data">',
          `id="structured-data"${nonce}>`,
        );
        const dir = join(outDir, route.path.slice(1));
        await mkdir(dir, { recursive: true });
        await writeFile(
          join(dir, 'index.html'),
          index.replace(HEAD_BLOCK, () => wrapHead(head)),
        );
      }
    },
  };
}
