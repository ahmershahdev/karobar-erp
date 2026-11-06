interface Page<T> {
  results: T[];
  next?: string | null;
}

/**
 * Every row of a cursor-paginated list, for pickers that must offer all the choices. A distributor
 * can have hundreds of suppliers, and one missing from a dropdown simply can't be used.
 */
export async function allPages<T>(load: (cursor?: string) => Promise<Page<T>>): Promise<T[]> {
  const rows: T[] = [];
  let cursor: string | undefined;
  do {
    const page = await load(cursor);
    rows.push(...page.results);
    cursor = page.next
      ? (new URL(page.next, window.location.origin).searchParams.get('cursor') ?? undefined)
      : undefined;
  } while (cursor);
  return rows;
}
