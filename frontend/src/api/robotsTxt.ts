import { fetchJson } from './client';

export interface RobotsTxtIssue {
  severity: 'error' | 'warning' | 'info';
  message: string;
}

export interface RobotsTxtAnalysis {
  found: boolean;
  statusCode: number;
  content: string;
  sitemaps: string[];
  issues: RobotsTxtIssue[];
}

export async function analyzeRobotsTxt(siteUrl: string): Promise<RobotsTxtAnalysis> {
  const params = new URLSearchParams({ siteUrl });
  return fetchJson<RobotsTxtAnalysis>(`/api/robots-txt?${params}`);
}