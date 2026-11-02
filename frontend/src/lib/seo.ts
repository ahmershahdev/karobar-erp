import { useEffect } from 'react';

import { env } from './env';
import { serializeJsonLd, structuredData } from '../seo/jsonld';
import { SITE, absoluteUrl, type PublicRoute } from '../seo/site';

function setMeta(attribute: 'name' | 'property', key: string, content: string): void {
  let tag = document.head.querySelector<HTMLMetaElement>(`meta[${attribute}="${key}"]`);
  if (!tag) {
    tag = document.createElement('meta');
    tag.setAttribute(attribute, key);
    document.head.append(tag);
  }
  tag.content = content;
}

function setCanonical(href: string): void {
  let link = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (!link) {
    link = document.createElement('link');
    link.rel = 'canonical';
    document.head.append(link);
  }
  link.href = href;
}

/**
 * Keeps the head in step with client-side navigation. The first load already has the right
 * head from the build (build/seo-plugin.ts); this only rewrites the same tags in place.
 */
export function usePublicSeo(route: PublicRoute): void {
  useEffect(() => {
    const url = absoluteUrl(env.siteUrl, route.path);
    document.title = route.title;
    setMeta('name', 'description', route.description);
    setMeta('name', 'robots', 'index, follow');
    setMeta('property', 'og:title', route.title);
    setMeta('property', 'og:description', route.description);
    setMeta('property', 'og:url', url);
    setMeta('property', 'og:image', absoluteUrl(env.siteUrl, SITE.ogImage));
    setMeta('name', 'twitter:title', route.title);
    setMeta('name', 'twitter:description', route.description);
    setCanonical(url);
    const script = document.getElementById('structured-data');
    if (script) script.textContent = serializeJsonLd(structuredData(env.siteUrl, route));
  }, [route]);
}

export function usePrivateSeo(title: string): void {
  useEffect(() => {
    document.title = `${title} | ${SITE.name}`;
    setMeta('name', 'robots', 'noindex, nofollow');
  }, [title]);
}
