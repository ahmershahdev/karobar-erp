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
