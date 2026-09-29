import { fetchJson } from './client';

export interface SiteEntry {
  siteUrl: string;
  permissionLevel: string;
}

export interface SitesResponse {
  siteEntry: SiteEntry[];
}

export async function getSites(): Promise<SitesResponse> {
  return fetchJson<SitesResponse>('/api/sites');
}
