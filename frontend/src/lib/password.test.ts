import { expect, it } from 'vitest';

import { passwordChecks, passwordScore } from './password';

it('scores passwords by length and variety', () => {
  expect(passwordScore('short')).toBe(0);
  expect(passwordScore('aaaaaaaaaaaa')).toBe(1);
  expect(passwordScore('karobar12345')).toBe(2);
  expect(passwordScore('Karobar12345')).toBe(3);
  expect(passwordScore('ledger lantern cardamom')).toBe(4);
  expect(passwordScore('Ledger lantern 42 cardamom!')).toBe(4);
});

it('lets a strong 12 character password fill the bar', () => {
  expect(passwordScore('Karobar2026!')).toBe(4);
});

it('does not reward repeated characters or patterns', () => {
  expect(passwordScore('aaaaaaaaaaaaaaaaaaaaaaa1')).toBe(1);
  expect(passwordScore('abc1abc1abc1abc1abc1abc1')).toBe(1);
});

it('lists what a password still needs', () => {
  expect(passwordChecks('')).toEqual({
    length: 0,
    longEnough: false,
    varied: false,
    noRepeats: false,
  });
  expect(passwordChecks('lantern river cardamom')).toMatchObject({
    longEnough: true,
    varied: true,
    noRepeats: true,
  });
  expect(passwordChecks('aaaaaaaaaaaaaaaa').noRepeats).toBe(false);
  expect(passwordChecks('short').longEnough).toBe(false);
});
