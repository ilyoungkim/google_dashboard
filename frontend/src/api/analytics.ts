import { fetchJson } from './client';

export interface SearchAnalyticsRow {
  keys: string[];
  clicks: number;
  impressions: number;
  ctr: number;
  position: number;
}

export interface SearchAnalyticsResponse {
  rows: SearchAnalyticsRow[];
  responseAggregationType: string;
}

export interface SearchAnalyticsRequest {
  siteUrl: string;
  startDate: string;
  endDate: string;
  dimensions?: string[];
  rowLimit?: number;
  dimensionFilterGroups?: Array<{ filters: Array<Record<string, unknown>>; groupType: string }>;
  aggregationType?: string;
  dataState?: string;
}

export async function queryAnalytics(body: SearchAnalyticsRequest): Promise<SearchAnalyticsResponse> {
  return fetchJson<SearchAnalyticsResponse>('/api/searchanalytics/query', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export interface KPISummary {
  totalClicks: number;
  totalImpressions: number;
  avgCtr: number;
  avgPosition: number;
}

export async function getKPI(siteUrl: string, startDate: string, endDate: string): Promise<KPISummary> {
  const params = new URLSearchParams({ siteUrl, startDate, endDate });
  return fetchJson<KPISummary>(`/api/kpi?${params}`);
}
