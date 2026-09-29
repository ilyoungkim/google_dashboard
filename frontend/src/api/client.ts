const BASE = import.meta.env.VITE_API_BASE_URL || '';

class ApiError extends Error {
  status: number;
  code: string;
  detail: Record<string, unknown>;

  constructor(status: number, body: { error?: { code?: string; message?: string; detail?: Record<string, unknown> } }) {
    super(body?.error?.message || `HTTP ${status}`);
    this.status = status;
    this.code = body?.error?.code || 'UNKNOWN';
    this.detail = body?.error?.detail || {};
  }
}

async function fetchJson<T>(input: RequestInfo, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${input}`, {
    credentials: 'include',
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
  });

  if (res.status === 401) {
    // Session expired — redirect to login (unless already on login page)
    if (window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
    throw new ApiError(401, { error: { code: 'UNAUTHENTICATED', message: 'Session expired' } });
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body);
  }

  return res.json();
}

export { fetchJson, ApiError };
