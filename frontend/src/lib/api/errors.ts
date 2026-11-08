export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
  ) {
    super(firstMessage(body) ?? `Request failed with status ${status}`);
  }
}

// DRF answers {"detail": "..."} or {"field": ["message", ...]}; show the first human message.
function firstMessage(body: unknown): string | null {
  if (!body || typeof body !== 'object') return null;
  for (const [key, value] of Object.entries(body)) {
    // A string `code` is our machine-readable error code; a field named code holds a list.
    if (key === 'request_id' || (key === 'code' && typeof value === 'string')) continue;
    if (typeof value === 'string') return value;
    if (Array.isArray(value) && typeof value[0] === 'string') return value[0];
  }
  return null;
}

/** Unwrap an openapi-fetch result: return data or throw an ApiError the UI can show. */
export async function unwrap<T>(
  promise: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await promise;
  if (!response.ok) throw new ApiError(response.status, error);
  return data as T;
}

// The JSON body of a failed fetch, for files fetched outside the typed client (PDFs, CSVs).
export async function errorBody(response: Response): Promise<unknown> {
  try {
    return JSON.parse(await response.text());
  } catch {
    return undefined;
  }
}
