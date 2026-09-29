export const qk = {
  authStatus: () => ['auth', 'status'] as const,
  sites: () => ['sites'] as const,
  analytics: (siteUrl: string, start: string, end: string, dim: string[]) =>
    ['analytics', siteUrl, start, end, ...dim] as const,
  kpi: (siteUrl: string, start: string, end: string) =>
    ['kpi', siteUrl, start, end] as const,
  sitemaps: (siteUrl: string) => ['sitemaps', siteUrl] as const,
};
