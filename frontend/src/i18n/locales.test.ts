import { expect, it } from 'vitest';

import ar from './locales/ar.json';
import en from './locales/en.json';
import ur from './locales/ur.json';

function shape(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(shape);
  if (value && typeof value === 'object')
    return Object.fromEntries(Object.entries(value).map(([key, inner]) => [key, shape(inner)]));
  return typeof value;
}

it.each([
  ['ur', ur],
  ['ar', ar],
])('%s has exactly the same keys as English', (_, locale) => {
  expect(shape(locale)).toEqual(shape(en));
});

it('home page lists stay lists, in every language', () => {
  for (const locale of [en, ur, ar]) {
    expect(Array.isArray(locale.home.steps.items)).toBe(true);
  }
});
