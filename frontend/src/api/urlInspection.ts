import { fetchJson } from './client';

export interface IndexStatusResult {
  verdict?: string;
  coverageState?: string;
  robotsTxtState?: string;
  indexingState?: string;
  lastCrawlTime?: string;
  pageFetchState?: string;
  googleCanonical?: string;
  userCanonical?: string;
  crawledAs?: string;
  sitemap?: string[];
  referringUrls?: string[];
}

export interface URLInspectionResult {
  inspectionResult: {
    inspectionResultLink?: string;
    indexStatusResult?: IndexStatusResult;
  };
}

export async function inspectUrl(
  siteUrl: string,
  inspectionUrl: string,
): Promise<URLInspectionResult> {
  return fetchJson<URLInspectionResult>('/api/urlinspection/index', {
    method: 'POST',
    body: JSON.stringify({ siteUrl, inspectionUrl, languageCode: 'ko' }),
  });
}
