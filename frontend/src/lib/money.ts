// Money arrives from the API as decimal strings ("1250.50"). The UI adds lines up while someone
// types, so it works in integer paisa/fils to avoid float drift; the server re-checks everything.

export function toMinor(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === '') return 0;
  const text = String(value).trim();
  if (!/^-?\d+(\.\d{0,2})?$/.test(text)) return Number.NaN;
  const negative = text.startsWith('-');
  const [whole = '0', fraction = ''] = text.replace('-', '').split('.');
  const minor = Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
  return negative ? -minor : minor;
}

export function fromMinor(minor: number): string {
  const sign = minor < 0 ? '-' : '';
  const absolute = Math.abs(minor);
  return `${sign}${Math.floor(absolute / 100)}.${String(absolute % 100).padStart(2, '0')}`;
}

/** A string is an API amount in rupees. A number is a UI sum in paisa, as from toMinor. */
export function formatMoney(value: string | number, locale: string | undefined): string {
  const minor = typeof value === 'number' ? value : toMinor(value);
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(minor / 100);
}

// Exact decimal text as a whole number, for example ("1.005", 4) is 10050n.
function scaled(value: string, places: number): bigint {
  const [whole = '0', fraction = ''] = value.split('.');
  return BigInt(whole + fraction.padEnd(places, '0').slice(0, places));
}

/** Quantity times a price of up to four decimals, in paisa, rounded as the invoice rounds it. */
export function lineMinor(price: string, quantity: number): number {
  return Number((scaled(price, 4) * BigInt(quantity) + 50n) / 100n);
}

/** Tax in paisa on a line already rounded by lineMinor, rounded as the invoice rounds it. */
export function taxMinor(amount: number, ratePercent: string): number {
  return Number((BigInt(amount) * scaled(ratePercent, 4) + 500_000n) / 1_000_000n);
}

// Halves round up, as ROUND_HALF_UP does on the server. Both numbers are whole and not negative.
function roundDiv(top: bigint, bottom: bigint): bigint {
  return (2n * top + bottom) / (2n * bottom);
}

/** A percentage of an amount in paisa, rounded once, as the invoice rounds it. */
export function percentMinor(amount: number, percent: string): number {
  return Number(roundDiv(BigInt(amount) * scaled(percent, 2), 10_000n));
}

/** A bill discount split over line amounts, all in paisa, the way the server splits it: from
 * rounded running totals, so the parts always add back to the whole discount. */
export function spreadMinor(amount: number, weights: number[]): number[] {
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  if (amount <= 0 || total <= 0) return weights.map(() => 0);
  let done = 0;
  return weights.map((weight) => {
    const before = roundDiv(BigInt(amount) * BigInt(done), BigInt(total));
    done += weight;
    return Number(roundDiv(BigInt(amount) * BigInt(done), BigInt(total)) - before);
  });
}
