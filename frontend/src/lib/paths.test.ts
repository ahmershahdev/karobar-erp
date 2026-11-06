import { expect, it } from 'vitest';

import { isAppPath, safeNext } from './paths';

it('knows which pages are for getting work done', () => {
  expect(isAppPath('/login')).toBe(true);
  expect(isAppPath('/app/al-madina-traders')).toBe(true);
  expect(isAppPath('/')).toBe(false);
  expect(isAppPath('/modules')).toBe(false);
});

it('only follows next inside the app', () => {
  expect(safeNext('/app/al-madina-traders/members')).toBe('/app/al-madina-traders/members');
  expect(safeNext('/accept-invite?token=abc')).toBe('/accept-invite?token=abc');
  expect(safeNext('https://evil.test')).toBeNull();
  expect(safeNext('//evil.test')).toBeNull();
  expect(safeNext('/app//evil.test')).toBeNull();
  expect(safeNext('/app\\evil')).toBeNull();
  expect(safeNext(null)).toBeNull();
});
