/**
 * In-memory API call recorder for the developer inspector.
 *
 * The typed client (`request()` in client.ts) pushes an entry per call so a
 * (super-admin, env-gated) panel can show the exact endpoint + request/response
 * body. Kept out of client.ts so the store + React subscription are isolated.
 */

export interface ApiLogEntry {
  id: number;
  method: string;
  path: string;
  requestBody: unknown;
  status: number;
  ok: boolean;
  responseBody?: unknown;
  error?: string;
  durationMs: number;
  timestamp: number;
}

const MAX_ENTRIES = 100;
let entries: ApiLogEntry[] = [];
let seq = 0;
const listeners = new Set<() => void>();

function emit(): void {
  for (const l of listeners) l();
}

export function recordApiCall(entry: Omit<ApiLogEntry, 'id'>): void {
  seq += 1;
  // Newest first; keep a bounded ring so long sessions don't leak memory.
  entries = [{ ...entry, id: seq }, ...entries].slice(0, MAX_ENTRIES);
  emit();
}

export function clearApiLog(): void {
  entries = [];
  emit();
}

/** Subscribe/getSnapshot pair for React's useSyncExternalStore. */
export function subscribeApiLog(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getApiLog(): ApiLogEntry[] {
  return entries;
}
