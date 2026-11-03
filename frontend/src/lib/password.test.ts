import { expect, it } from 'vitest';

import { passwordScore } from './password';

it('scores passwords by length and variety', () => {
  expect(passwordScore('short')).toBe(0);
  expect(passwordScore('aaaaaaaaaaaa')).toBe(1);
  expect(passwordScore('ledger lantern cardamom')).toBe(3);
  expect(passwordScore('Ledger lantern 42 cardamom!')).toBe(4);
});

it('does not reward repeated characters or patterns', () => {
  expect(passwordScore('aaaaaaaaaaaaaaaaaaaaaaa1')).toBe(1);
  expect(passwordScore('abc1abc1abc1abc1abc1abc1')).toBe(1);
});
