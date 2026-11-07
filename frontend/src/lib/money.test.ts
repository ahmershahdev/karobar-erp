import { describe, expect, it } from 'vitest';

import {
  formatMoney,
  fromMinor,
  lineMinor,
  percentMinor,
  spreadMinor,
  taxMinor,
  toMinor,
} from './money';

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

it('rounds a line and its tax the way the invoice does, without float error', () => {
  // 1.005 * 100 is 100.49999... in floats, which would show one paisa less than the invoice.
  expect(lineMinor('1.0050', 1)).toBe(101);
  expect(taxMinor(lineMinor('1.0050', 1), '10.0000')).toBe(10);
  expect(lineMinor('100.0000', 2)).toBe(20000);
  expect(lineMinor('0.0049', 1)).toBe(0);
  expect(taxMinor(50, '1.0000')).toBe(1);
  expect(taxMinor(1999, '17.5000')).toBe(350);
});

describe('discounts', () => {
  it('takes a percentage off and rounds halves up, as the server does', () => {
    expect(percentMinor(9999, '12.5')).toBe(1250);
    expect(percentMinor(1, '50')).toBe(1);
    expect(percentMinor(20000, '0')).toBe(0);
  });

  it('spreads a bill discount so the parts add back exactly', () => {
    expect(spreadMinor(100, [1000, 1000, 1000])).toEqual([33, 34, 33]);
    expect(spreadMinor(3000, [10000, 20000])).toEqual([1000, 2000]);
    const parts = spreadMinor(1777, [333, 5000, 0, 1201]);
    expect(parts.reduce((sum, part) => sum + part, 0)).toBe(1777);
    expect(spreadMinor(0, [5, 0])).toEqual([0, 0]);
  });
});
