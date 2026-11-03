/**
 * Rough strength from length and variety. The server's validators are the real gate; this only
 * nudges people toward a longer passphrase before they press submit.
 *
 * Length is counted after collapsing repeats ("aaaa" to "a", "abcabc" to "abc"), so padding a
 * short password with the same characters never earns a better score.
 */
export function passwordScore(password: string): 0 | 1 | 2 | 3 | 4 {
  if (password.length < 12) return 0;
  const length = password.replace(/(.+?)\1+/g, '$1').length;
  if (length < 12) return 1;
  const kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^\w\s]/, /\s/].filter((pattern) =>
    pattern.test(password),
  ).length;
  let score = 1;
  if (length >= 16) score += 1;
  if (kinds >= 2) score += 1;
  if (kinds >= 3 || length >= 24) score += 1;
  return Math.min(score, 4) as 0 | 1 | 2 | 3 | 4;
}
