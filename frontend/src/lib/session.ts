// Session management for frontend. Generates and persists a per-tab session ID.
// The backend expects header `X-Session-Id` with a UUID v4 (36 chars).

const STORAGE_KEY = 'invoice_session_id';

function isBrowser() {
  return typeof window !== 'undefined' && typeof localStorage !== 'undefined';
}

export function getSessionId(): string | null {
  if (!isBrowser()) return null;
  const val = localStorage.getItem(STORAGE_KEY);
  return val && val.length === 36 ? val : null;
}

export function getOrCreateSessionId(): string {
  if (!isBrowser()) {
    // SSR fallback; caller should re-check on client.
    return '00000000-0000-0000-0000-000000000000';
  }
  let sid = getSessionId();
  if (!sid) {
    sid = crypto.randomUUID();
    localStorage.setItem(STORAGE_KEY, sid);
  }
  return sid;
}

export function resetSessionId(): string {
  if (!isBrowser()) {
    return '00000000-0000-0000-0000-000000000000';
  }
  const sid = crypto.randomUUID();
  localStorage.setItem(STORAGE_KEY, sid);
  return sid;
}
