import { fetchJson } from './client';

export interface AuthStatus {
  authenticated: boolean;
  email?: string;
  scopes?: string[];
}

export async function getAuthStatus(): Promise<AuthStatus> {
  return fetchJson<AuthStatus>('/auth/status');
}

export async function logout(): Promise<void> {
  await fetchJson('/auth/logout', { method: 'POST' });
}
