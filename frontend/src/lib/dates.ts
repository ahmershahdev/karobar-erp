// The local calendar date as YYYY-MM-DD. toISOString() would give the UTC date, which is
// yesterday in Pakistan and the Gulf until 5 in the morning.
export function today(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}
