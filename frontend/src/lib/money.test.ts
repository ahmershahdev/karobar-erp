import { expect, it } from 'vitest';

import { formatMoney, fromMinor, toMinor } from './money';

it('converts decimal strings to minor units without float drift', () => {
  expect(toMinor('0.1') + toMinor('0.2')).toBe(30);
  expect(toMinor('1250.5')).toBe(125050);
  expect(toMinor('-3.07')).toBe(-307);
  expect(toMinor('')).toBe(0);
  expect(toMinor(null)).toBe(0);
  expect(toMinor('12.345')).toBeNaN();
  expect(toMinor('abc')).toBeNaN();
});

it('formats minor units back to decimal strings', () => {
  expect(fromMinor(125050)).toBe('1250.50');
  expect(fromMinor(-307)).toBe('-3.07');
  expect(fromMinor(5)).toBe('0.05');
});

it('reads strings as rupees and numbers as paisa, which callers must not mix up', () => {
  expect(formatMoney('590', 'en')).toBe('590.00');
  expect(formatMoney(59000, 'en')).toBe('590.00');
  expect(formatMoney(toMinor('1180') - toMinor('590.50'), 'en')).toBe('589.50');
});
