/**
 * Rough strength from length and variety. The server's validators are the real gate; this only
 * nudges people toward a longer passphrase before they press submit.
 */
export function passwordScore(password: string): 0 | 1 | 2 | 3 | 4 {
  if (password.length < 12) return 0;
  const kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^\w\s]/, /\s/].filter((pattern) =>
    pattern.test(password),
  ).length;
  let score = 1;
  if (password.length >= 16) score += 1;
  if (kinds >= 2) score += 1;
  if (kinds >= 3 || password.length >= 24) score += 1;
  return Math.min(score, 4) as 0 | 1 | 2 | 3 | 4;
}
