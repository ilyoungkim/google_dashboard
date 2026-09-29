import { fetchJson } from './client';

export interface SitemapContent {
  type: string;
  submitted: string;
  indexed: string;
}

export interface SitemapEntry {
  path: string;
  lastSubmitted: string;
  isPending: boolean;
  isSitemapsIndex: boolean;
  type: string;
  lastDownloaded: string;
  warnings: string;
  errors: string;
  contents: SitemapContent[];
}

export interface SitemapsResponse {
  sitemap: SitemapEntry[];
}

export async function getSitemaps(siteUrl: string): Promise<SitemapsResponse> {
  const params = new URLSearchParams({ siteUrl });
  return fetchJson<SitemapsResponse>(`/api/sitemaps?${params}`);
}
