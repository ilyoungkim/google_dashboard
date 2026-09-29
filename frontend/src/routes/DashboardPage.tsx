import { useMutation, useQuery } from '@tanstack/react-query';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useState, useMemo } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from 'recharts';
import { getKPI, queryAnalytics } from '../api/analytics';
import { getSites } from '../api/sites';
import { getSitemaps, type SitemapEntry } from '../api/sitemaps';
import { analyzeRobotsTxt } from '../api/robotsTxt';
import { inspectUrl, type IndexStatusResult } from '../api/urlInspection';
import { useAuth } from '../auth/AuthContext';
import { qk } from '../lib/queryKeys';
import { formatNumber, formatPercent, formatPosition, daysAgo, todayStr } from '../lib/format';

const DATE_PRESETS = [
  { label: '1일', days: 1 },
  { label: '7일', days: 7 },
  { label: '28일', days: 28 },
  { label: '90일', days: 90 },
  { label: '6개월', days: 180 },
];

const AVERAGE_WINDOWS = [
  { label: '7일 평균', days: 7 },
  { label: '28일 평균', days: 28 },
  { label: '3개월 평균', days: 90 },
];

function daysBefore(dateString: string, days: number): string {
  const date = new Date(`${dateString}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() - days);
  return date.toISOString().slice(0, 10);
}

export function DashboardPage() {
  const { siteUrl: encodedSiteUrl } = useParams<{ siteUrl: string }>();
  const siteUrl = decodeURIComponent(encodedSiteUrl ?? '');
  const { email, logout } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const defaultDays = 7;
  const startDate = searchParams.get('start') || daysAgo(defaultDays);
  const endDate = searchParams.get('end') || todayStr();
  const [activePreset, setActivePreset] = useState<number>(defaultDays);
  const [averageWindow, setAverageWindow] = useState<number>(28);

  // ── KPI ──────────────────────────────────────────────────────────
  const kpiQuery = useQuery({
    queryKey: qk.kpi(siteUrl, startDate, endDate),
    queryFn: () => getKPI(siteUrl, startDate, endDate),
    staleTime: 10 * 60 * 1000,
  });

  // ── Trend (daily clicks/impressions) ────────────────────────────
  const trendQuery = useQuery({
    queryKey: qk.analytics(siteUrl, startDate, endDate, ['date']),
    queryFn: () =>
      queryAnalytics({
        siteUrl,
        startDate,
        endDate,
        dimensions: ['date'],
        rowLimit: 500,
      }),
    staleTime: 10 * 60 * 1000,
  });

  // ── Configurable average window for chart reference lines ───────
  const avgStart = daysBefore(endDate, averageWindow - 1);
  const avgEnd = endDate;
  const avgQuery = useQuery({
    queryKey: qk.analytics(siteUrl, avgStart, avgEnd, ['date']),
    queryFn: () =>
      queryAnalytics({
        siteUrl,
        startDate: avgStart,
        endDate: avgEnd,
        dimensions: ['date'],
        rowLimit: 500,
      }),
    staleTime: 10 * 60 * 1000,
  });

  // ── Top queries ──────────────────────────────────────────────────
  const queriesQuery = useQuery({
    queryKey: qk.analytics(siteUrl, startDate, endDate, ['query']),
    queryFn: () =>
      queryAnalytics({
        siteUrl,
        startDate,
        endDate,
        dimensions: ['query'],
        rowLimit: 50,
      }),
    staleTime: 10 * 60 * 1000,
  });

  // ── Top pages ───────────────────────────────────────────────────
  const pagesQuery = useQuery({
    queryKey: qk.analytics(siteUrl, startDate, endDate, ['page']),
    queryFn: () =>
      queryAnalytics({
        siteUrl,
        startDate,
        endDate,
        dimensions: ['page'],
        rowLimit: 50,
      }),
    staleTime: 10 * 60 * 1000,
  });

  // ── Country and device breakdowns ───────────────────────────────
  const countriesQuery = useQuery({
    queryKey: qk.analytics(siteUrl, startDate, endDate, ['country']),
    queryFn: () =>
      queryAnalytics({
        siteUrl,
        startDate,
        endDate,
        dimensions: ['country'],
        rowLimit: 20,
      }),
    staleTime: 10 * 60 * 1000,
  });

  const devicesQuery = useQuery({
    queryKey: qk.analytics(siteUrl, startDate, endDate, ['device']),
    queryFn: () =>
      queryAnalytics({
        siteUrl,
        startDate,
        endDate,
        dimensions: ['device'],
        rowLimit: 10,
      }),
    staleTime: 10 * 60 * 1000,
  });

  const searchAppearanceQuery = useQuery({
    queryKey: qk.analytics(siteUrl, startDate, endDate, ['searchAppearance']),
    queryFn: () =>
      queryAnalytics({
        siteUrl,
        startDate,
        endDate,
        dimensions: ['searchAppearance'],
        rowLimit: 20,
      }),
    staleTime: 10 * 60 * 1000,
  });

  // ── Sites (for selector) ────────────────────────────────────────
  const sitesQuery = useQuery({
    queryKey: qk.sites(),
    queryFn: getSites,
    staleTime: 5 * 60 * 1000,
  });

  // ── Sitemaps ────────────────────────────────────────────────────
  const sitemapsQuery = useQuery({
    queryKey: qk.sitemaps(siteUrl),
    queryFn: () => getSitemaps(siteUrl),
    staleTime: 30 * 60 * 1000,
  });

  // ── robots.txt ─────────────────────────────────────────────────
  const robotsQuery = useQuery({
    queryKey: ['robots-txt', siteUrl],
    queryFn: () => analyzeRobotsTxt(siteUrl),
    staleTime: 30 * 60 * 1000,
  });

  const kpi = kpiQuery.data;
  const trendData = (trendQuery.data?.rows ?? [])
    .map((r) => ({
      date: r.keys[0] ?? '',
      clicks: r.clicks,
      impressions: r.impressions,
    }))
    .sort((a, b) => a.date.localeCompare(b.date));

  // ── Compute selected-period average for reference lines ─────────
  const avgRows = avgQuery.data?.rows ?? trendData;  // fallback to current trend
  const avgClicks = avgRows.length > 0
    ? avgRows.reduce((sum, r) => sum + r.clicks, 0) / avgRows.length
    : 0;
  const avgImpressions = avgRows.length > 0
    ? avgRows.reduce((sum, r) => sum + r.impressions, 0) / avgRows.length
    : 0;

  const topQueries = queriesQuery.data?.rows ?? [];

  const topPages = pagesQuery.data?.rows ?? [];
  const topCountries = countriesQuery.data?.rows ?? [];
  const topDevices = devicesQuery.data?.rows ?? [];
  const searchAppearances = searchAppearanceQuery.data?.rows ?? [];

  const sites = sitesQuery.data?.siteEntry ?? [];
  const sitemaps = sitemapsQuery.data?.sitemap ?? [];

  function setDatePreset(days: number) {
    setActivePreset(days);
    const end = todayStr();
    const start = daysAgo(days);
    setSearchParams({ start, end });
  }

  // ── Report download ──────────────────────────────────────────────
  const [reportLoading, setReportLoading] = useState(false);

  function generateTrendSVG(
    data: { date: string; clicks: number; impressions: number }[],
    avgClicks: number,
    avgImpressions: number,
  ): string {
    if (data.length === 0) return '';

    const W = 800;
    const H = 320;
    const PAD = { top: 20, right: 60, bottom: 40, left: 60 };
    const chartW = W - PAD.left - PAD.right;
    const chartH = H - PAD.top - PAD.bottom;

    const maxClicks = Math.max(...data.map((d) => d.clicks), avgClicks, 1);
    const maxImpressions = Math.max(...data.map((d) => d.impressions), avgImpressions, 1);

    const xScale = (i: number) => PAD.left + (data.length === 1 ? chartW / 2 : (i / (data.length - 1)) * chartW);
    const yClicks = (v: number) => PAD.top + chartH - (v / maxClicks) * chartH;
    const yImpressions = (v: number) => PAD.top + chartH - (v / maxImpressions) * chartH;

    const clicksPath = data.map((d, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)} ${yClicks(d.clicks)}`).join(' ');
    const impressionsPath = data.map((d, i) => `${i === 0 ? 'M' : 'L'} ${xScale(i)} ${yImpressions(d.impressions)}`).join(' ');

    // X labels (show ~8 ticks)
    const labelStep = Math.max(1, Math.floor(data.length / 7));
    const xLabels = data
      .filter((_, i) => i % labelStep === 0 || i === data.length - 1)
      .map((d, i) => {
        const actualIdx = data.findIndex((dd) => dd.date === d.date);
        return `<text x="${xScale(actualIdx)}" y="${H - 10}" font-size="10" fill="#666" text-anchor="middle">${d.date.slice(5)}</text>`;
      }).join('\n');

    // Y labels (clicks - left)
    const yClickLabels = [0, 0.25, 0.5, 0.75, 1].map((p) => {
      const v = Math.round(maxClicks * p);
      return `<text x="${PAD.left - 8}" y="${yClicks(v) + 3}" font-size="10" fill="#2563eb" text-anchor="end">${v}</text>`;
    }).join('\n');

    // Y labels (impressions - right)
    const yImpLabels = [0, 0.25, 0.5, 0.75, 1].map((p) => {
      const v = Math.round(maxImpressions * p);
      return `<text x="${W - PAD.right + 8}" y="${yImpressions(v) + 3}" font-size="10" fill="#16a34a">${v}</text>`;
    }).join('\n');

    // Grid lines
    const gridLines = [0, 0.25, 0.5, 0.75, 1].map((p) => {
      const y = PAD.top + chartH - p * chartH;
      return `<line x1="${PAD.left}" y1="${y}" x2="${W - PAD.right}" y2="${y}" stroke="#e5e7eb" stroke-dasharray="3 3"/>`;
    }).join('\n');

    // Avg lines
    const avgClickLine = avgClicks > 0
      ? `<line x1="${PAD.left}" y1="${yClicks(avgClicks)}" x2="${W - PAD.right}" y2="${yClicks(avgClicks)}" stroke="#2563eb" stroke-dasharray="5 5" stroke-opacity="0.5"/><text x="${PAD.left + 4}" y="${yClicks(avgClicks) - 4}" font-size="9" fill="#2563eb">28일 평균 ${avgClicks.toFixed(0)}</text>`
      : '';
    const avgImpLine = avgImpressions > 0
      ? `<line x1="${PAD.left}" y1="${yImpressions(avgImpressions)}" x2="${W - PAD.right}" y2="${yImpressions(avgImpressions)}" stroke="#16a34a" stroke-dasharray="5 5" stroke-opacity="0.5"/><text x="${W - PAD.right - 4}" y="${yImpressions(avgImpressions) - 4}" font-size="9" fill="#16a34a" text-anchor="end">28일 평균 ${avgImpressions.toFixed(0)}</text>`
      : '';

    // Dots
    const dots = data.map((d, i) =>
      `<circle cx="${xScale(i)}" cy="${yClicks(d.clicks)}" r="3" fill="#2563eb"/><circle cx="${xScale(i)}" cy="${yImpressions(d.impressions)}" r="3" fill="#16a34a"/>`
    ).join('\n');

    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="background:#fff">
<rect width="${W}" height="${H}" fill="white"/>
${gridLines}
${avgClickLine}
${avgImpLine}
<path d="${clicksPath}" fill="none" stroke="#2563eb" stroke-width="2"/>
<path d="${impressionsPath}" fill="none" stroke="#16a34a" stroke-width="2"/>
${dots}
${xLabels}
${yClickLabels}
${yImpLabels}
<text x="${PAD.left}" y="${PAD.top - 6}" font-size="11" fill="#2563eb" font-weight="bold">클릭</text>
<text x="${W - PAD.right}" y="${PAD.top - 6}" font-size="11" fill="#16a34a" font-weight="bold" text-anchor="end">노출</text>
</svg>`;

    return `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(svg)))}`;
  }

  async function downloadReport() {
    setReportLoading(true);
    try {
      const periods = DATE_PRESETS.map((p) => ({
        label: p.label,
        days: p.days,
        start: daysAgo(p.days),
        end: todayStr(),
      }));

      // Fetch KPI + top queries + top pages + trend for each period in parallel
      const results = await Promise.all(
        periods.map(async (per) => {
          const [kpi, queries, pages, trend] = await Promise.all([
            getKPI(siteUrl, per.start, per.end),
            queryAnalytics({ siteUrl, startDate: per.start, endDate: per.end, dimensions: ['query'], rowLimit: 50 }),
            queryAnalytics({ siteUrl, startDate: per.start, endDate: per.end, dimensions: ['page'], rowLimit: 50 }),
            queryAnalytics({ siteUrl, startDate: per.start, endDate: per.end, dimensions: ['date'], rowLimit: 500 }),
          ]);
          const trendRows = (trend.rows ?? [])
            .map((r) => ({ date: r.keys[0] ?? '', clicks: r.clicks, impressions: r.impressions }))
            .sort((a, b) => a.date.localeCompare(b.date));
          return { ...per, kpi, queries: queries.rows, pages: pages.rows, trend: trendRows };
        }),
      );

      // Fetch 28-day average for reference lines
      const avg28Start = daysAgo(28);
      const avg28End = todayStr();
      let avgClicks = 0;
      let avgImpressions = 0;
      try {
        const avg28Data = await queryAnalytics({ siteUrl, startDate: avg28Start, endDate: avg28End, dimensions: ['date'], rowLimit: 500 });
        const avgRows = avg28Data.rows ?? [];
        if (avgRows.length > 0) {
          avgClicks = avgRows.reduce((s, r) => s + r.clicks, 0) / avgRows.length;
          avgImpressions = avgRows.reduce((s, r) => s + r.impressions, 0) / avgRows.length;
        }
      } catch {
        // fallback: use first period's average
      }

      // Fetch sitemaps & robots.txt for issue analysis
      let sitemaps: SitemapEntry[] = [];
      let robotsIssues: Array<{ severity: string; message: string }> = [];
      try {
        const [sitemapsResp, robotsResp] = await Promise.all([
          getSitemaps(siteUrl),
          analyzeRobotsTxt(siteUrl),
        ]);
        sitemaps = sitemapsResp.sitemap ?? [];
        robotsIssues = robotsResp.issues ?? [];
      } catch {
        // non-critical; continue without sitemap/robots data
      }

      const now = new Date().toISOString().slice(0, 19).replace('T', ' ');
      const siteDisplay = siteUrl.replace(/^sc-domain:/, '');

      const md: string[] = [];
      md.push(`# Google Search Console 리포트`);
      md.push(``);
      md.push(`- **사이트**: ${siteUrl}`);
      md.push(`- **생성일시**: ${now}`);
      md.push(`- **보고 기간**: 1일 / 7일 / 28일 / 90일 / 6개월`);
      md.push(``);
      md.push(`---`);
      md.push(``);

      // ── Global issues section (sitemaps + robots.txt) ───────────
      const globalIssues: string[] = [];
      for (const sm of sitemaps) {
        const errCount = parseInt(sm.errors || '0', 10);
        const warnCount = parseInt(sm.warnings || '0', 10);
        const contentSummary = (sm.contents ?? [])
          .map((c) => {
            const submitted = parseInt(c.submitted || '0', 10);
            const indexed = parseInt(c.indexed || '0', 10);
            return `${c.type}: 제출 ${submitted}, 색인 ${indexed}`;
          }).join(', ');
        if (errCount > 0) {
          globalIssues.push(`- 🔴 **사이트맵 오류**: ${sm.path} — ${errCount}개 오류${contentSummary ? ` (${contentSummary})` : ''}`);
        }
        if (warnCount > 0) {
          const allSubmitted = (sm.contents ?? []).reduce((s, c) => s + parseInt(c.submitted || '0', 10), 0);
          const allIndexed = (sm.contents ?? []).reduce((s, c) => s + parseInt(c.indexed || '0', 10), 0);
          let detail = `${warnCount}개 경고`;
          if (contentSummary) detail += ` | ${contentSummary}`;
          if (sm.lastDownloaded) detail += ` | 최종 다운로드: ${sm.lastDownloaded.slice(0, 10)}`;
          if (allSubmitted > 0 && allIndexed === 0) {
            detail += ` | ⚠️ 제출된 URL이 색인되지 않음 — URL 접근성 및 robots.txt 확인 필요`;
          } else if (allSubmitted > 0 && allIndexed < allSubmitted * 0.5) {
            detail += ` | ⚠️ 색인률 낮음 (${Math.round((allIndexed / allSubmitted) * 100)}%)`;
          } else {
            detail += ` | 사이트맵 형식 또는 URL 관련 경고`;
          }
          globalIssues.push(`- 🟡 **사이트맵 경고**: ${sm.path} — ${detail}`);
        }
      }
      for (const ri of robotsIssues) {
        const icon = ri.severity === 'error' ? '🔴' : ri.severity === 'warning' ? '🟡' : '🔵';
        const label = ri.severity === 'error' ? '오류' : ri.severity === 'warning' ? '경고' : '정보';
        globalIssues.push(`- ${icon} **robots.txt ${label}**: ${ri.message}`);
      }
      if (globalIssues.length > 0) {
        md.push(`## ⚠️ 사이트 이슈`);
        md.push(``);
        md.push(...globalIssues);
        md.push(``);
        md.push(`---`);
        md.push(``);
      }

      for (const r of results) {
        md.push(`## 📊 ${r.label} 통계 (${r.start} ~ ${r.end})`);
        md.push(``);
        md.push(`| 지표 | 값 |`);
        md.push(`|------|-----|`);
        md.push(`| 총 클릭수 | ${formatNumber(r.kpi.totalClicks)} |`);
        md.push(`| 총 노출수 | ${formatNumber(r.kpi.totalImpressions)} |`);
        md.push(`| 평균 CTR | ${formatPercent(r.kpi.avgCtr)} |`);
        md.push(`| 평균 순위 | ${formatPosition(r.kpi.avgPosition)} |`);
        md.push(``);

        // Top queries
        md.push(`### 상위 검색어`);
        md.push(``);
        md.push(`| 순위 | 검색어 | 클릭 | 노출 | CTR | 순위 |`);
        md.push(`|------|--------|-------|-------|-----|------|`);
        r.queries
          .slice()
          .sort((a, b) => b.clicks - a.clicks)
          .forEach((row, i) => {
            md.push(`| ${i + 1} | ${row.keys[0] ?? '-'} | ${formatNumber(row.clicks)} | ${formatNumber(row.impressions)} | ${formatPercent(row.ctr)} | ${formatPosition(row.position)} |`);
          });
        md.push(``);

        // Top pages
        md.push(`### 상위 페이지`);
        md.push(``);
        md.push(`| 순위 | 페이지 | 클릭 | 노출 | CTR | 순위 |`);
        md.push(`|------|--------|-------|-------|-----|------|`);
        r.pages
          .slice()
          .sort((a, b) => b.clicks - a.clicks)
          .forEach((row, i) => {
            md.push(`| ${i + 1} | ${row.keys[0] ?? '-'} | ${formatNumber(row.clicks)} | ${formatNumber(row.impressions)} | ${formatPercent(row.ctr)} | ${formatPosition(row.position)} |`);
          });
        md.push(``);

        // Trend chart for this period
        if (r.trend.length > 0) {
          const svgDataUrl = generateTrendSVG(r.trend, avgClicks, avgImpressions);
          md.push(`### 일별 클릭 / 노출 트렌드`);
          md.push(``);
          md.push(`![트렌드 ${r.label}](${svgDataUrl})`);
          md.push(``);
        }

        // Issues for this period
        const periodIssues: string[] = [];
        // Low CTR pages
        const lowCtr = r.pages.filter((p) => p.impressions >= 100 && p.ctr < 0.01).sort((a, b) => b.impressions - a.impressions).slice(0, 3);
        for (const p of lowCtr) {
          periodIssues.push(`- 🔵 **낮은 CTR**: ${p.keys[0] ?? '-'} (노출 ${formatNumber(p.impressions)}, CTR ${formatPercent(p.ctr)}) — 제목/메타 설명 개선 필요`);
        }
        // Low ranking pages
        const lowRank = r.pages.filter((p) => p.position > 20 && p.impressions >= 50).sort((a, b) => b.impressions - a.impressions).slice(0, 3);
        for (const p of lowRank) {
          periodIssues.push(`- 🔵 **낮은 순위**: ${p.keys[0] ?? '-'} (순위 ${formatPosition(p.position)}, 노출 ${formatNumber(p.impressions)}) — 콘텐츠 품질 개선 필요`);
        }
        if (periodIssues.length > 0) {
          md.push(`### 이슈 및 개선 제안`);
          md.push(``);
          md.push(...periodIssues);
          md.push(``);
        }

        md.push(`---`);
        md.push(``);
      }

      md.push(`> 이 리포트는 Google Search Console API에서 자동 생성되었습니다.`);

      const fullReport = md.join('\n');

      const blob = new Blob([fullReport], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `GSC_Report_${siteDisplay}_${todayStr()}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Report generation failed:', err);
      alert('리포트 생성에 실패했습니다.');
    } finally {
      setReportLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b bg-white shadow-sm">
        <div className="flex items-center justify-between px-6 py-3">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/')}
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white"
            >
              G
            </button>

            {/* Site selector */}
            <select
              value={siteUrl}
              onChange={(e) => navigate(`/dashboard/${encodeURIComponent(e.target.value)}`)}
              className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700"
            >
              {sites.map((s) => (
                <option key={s.siteUrl} value={s.siteUrl}>
                  {s.siteUrl}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-3">
            {email && <span className="text-sm text-gray-500">{email}</span>}
            <button
              onClick={logout}
              className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm text-gray-600 transition hover:bg-gray-100"
            >
              로그아웃
            </button>
          </div>
        </div>
      </header>

      <main className="px-6 py-6">
        {/* Date presets */}
        <div className="mb-6 flex flex-wrap items-center gap-2">
          {DATE_PRESETS.map((p) => (
            <button
              key={p.days}
              onClick={() => setDatePreset(p.days)}
              className={`rounded-lg px-4 py-1.5 text-sm font-medium transition ${
                activePreset === p.days
                  ? 'bg-blue-600 text-white'
                  : 'bg-white text-gray-600 border border-gray-300 hover:bg-gray-100'
              }`}
            >
              {p.label}
            </button>
          ))}
          <span className="ml-2 text-sm text-gray-400">
            {startDate} ~ {endDate}
          </span>
          <button
            onClick={downloadReport}
            disabled={reportLoading}
            className="ml-auto rounded-lg bg-blue-600 px-4 py-1.5 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {reportLoading ? '리포트 생성 중...' : '📄 리포트 다운로드'}
          </button>
        </div>

        {/* KPI Cards */}
        <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard title="총 클릭수" value={kpi ? formatNumber(kpi.totalClicks) : '-'} loading={kpiQuery.isLoading} />
          <KpiCard title="총 노출수" value={kpi ? formatNumber(kpi.totalImpressions) : '-'} loading={kpiQuery.isLoading} />
          <KpiCard title="평균 CTR" value={kpi ? formatPercent(kpi.avgCtr) : '-'} loading={kpiQuery.isLoading} />
          <KpiCard title="평균 순위" value={kpi ? formatPosition(kpi.avgPosition) : '-'} loading={kpiQuery.isLoading} />
        </div>

        {/* Trend Chart */}
        <section className="mb-8 rounded-xl border bg-white p-5 shadow-sm">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-gray-800">일별 클릭 / 노출 트렌드</h2>
            <div className="flex rounded-lg border border-gray-200 p-1" aria-label="평균 비교 기간">
              {AVERAGE_WINDOWS.map((window) => (
                <button
                  key={window.days}
                  onClick={() => setAverageWindow(window.days)}
                  className={`rounded-md px-3 py-1 text-xs font-medium transition ${
                    averageWindow === window.days
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-600 hover:bg-gray-100'
                  }`}
                >
                  {window.label}
                </button>
              ))}
            </div>
          </div>
          {trendQuery.isLoading ? (
            <div className="h-64 animate-pulse rounded-lg bg-gray-200" />
          ) : trendData.length === 0 ? (
            <p className="py-12 text-center text-gray-400">선택한 기간에 검색 트래픽이 없습니다.</p>
          ) : (
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Line yAxisId="left" type="monotone" dataKey="clicks" stroke="#2563eb" name="클릭" strokeWidth={2} dot={{ r: 3 }} />
                <Line yAxisId="right" type="monotone" dataKey="impressions" stroke="#16a34a" name="노출" strokeWidth={2} dot={{ r: 3 }} />
                {avgClicks > 0 && (
                  <ReferenceLine yAxisId="left" y={avgClicks} stroke="#2563eb" strokeDasharray="5 5" strokeOpacity={0.5} label={{ value: `${averageWindow}일 평균 클릭 ${avgClicks.toFixed(0)}`, position: 'insideTopLeft', fill: '#2563eb', fontSize: 10 }} />
                )}
                {avgImpressions > 0 && (
                  <ReferenceLine yAxisId="right" y={avgImpressions} stroke="#16a34a" strokeDasharray="5 5" strokeOpacity={0.5} label={{ value: `${averageWindow}일 평균 노출 ${avgImpressions.toFixed(0)}`, position: 'insideTopRight', fill: '#16a34a', fontSize: 10 }} />
                )}
              </LineChart>
            </ResponsiveContainer>
          )}
        </section>

        {/* Tables: Queries + Pages side by side */}
        <div className="mb-8 grid gap-6 xl:grid-cols-3">
          {/* Top Queries */}
          <section className="rounded-xl border bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-gray-800">상위 검색어</h2>
            <DataTable
              loading={queriesQuery.isLoading}
              rows={topQueries}
              keyLabel="검색어"
              keyIdx={0}
            />
          </section>

          {/* Top Pages */}
          <section className="rounded-xl border bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-gray-800">상위 페이지</h2>
            <DataTable
              loading={pagesQuery.isLoading}
              rows={topPages}
              keyLabel="페이지"
              keyIdx={0}
            />
          </section>

          <section className="rounded-xl border bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-gray-800">검색 표시 유형별 성과</h2>
            <DataTable
              loading={searchAppearanceQuery.isLoading}
              rows={searchAppearances}
              keyLabel="표시 유형"
              keyIdx={0}
            />
          </section>
        </div>

        {/* Search Analytics breakdowns */}
        <div className="mb-8 grid gap-6 lg:grid-cols-2">
          <section className="rounded-xl border bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-gray-800">국가별 검색 성과</h2>
            <DataTable
              loading={countriesQuery.isLoading}
              rows={topCountries}
              keyLabel="국가"
              keyIdx={0}
            />
          </section>

          <section className="rounded-xl border bg-white p-5 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-gray-800">기기별 검색 성과</h2>
            <DataTable
              loading={devicesQuery.isLoading}
              rows={topDevices}
              keyLabel="기기"
              keyIdx={0}
            />
          </section>
        </div>

        {/* Sitemaps */}
        <section className="rounded-xl border bg-white p-5 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-gray-800">사이트맵</h2>
          {sitemapsQuery.isLoading ? (
            <div className="h-20 animate-pulse rounded-lg bg-gray-200" />
          ) : sitemaps.length === 0 ? (
            <p className="py-4 text-center text-gray-400">등록된 사이트맵이 없습니다.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-gray-500">
                    <th className="pb-2 pr-4 font-medium">경로</th>
                    <th className="pb-2 pr-4 font-medium">유형</th>
                    <th className="pb-2 pr-4 font-medium">제출일</th>
                    <th className="pb-2 pr-4 font-medium">경고</th>
                    <th className="pb-2 pr-4 font-medium">오류</th>
                  </tr>
                </thead>
                <tbody>
                  {sitemaps.map((s, i) => (
                    <tr key={i} className="border-b last:border-0">
                      <td className="py-2 pr-4 max-w-xs truncate">{s.path}</td>
                      <td className="py-2 pr-4">{s.type}</td>
                      <td className="py-2 pr-4">{s.lastSubmitted?.slice(0, 10)}</td>
                      <td className="py-2 pr-4">{s.warnings}</td>
                      <td className="py-2 pr-4">{s.errors}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Issues */}
        <IssuesSection
          sitemaps={sitemaps}
          topPages={topPages}
          robotsIssues={robotsQuery.data?.issues ?? []}
          loading={sitemapsQuery.isLoading || pagesQuery.isLoading || robotsQuery.isLoading}
        />

        <UrlInspectionPanel key={siteUrl} siteUrl={siteUrl} />
      </main>
    </div>
  );
}

/* ── Sub-components ───────────────────────────────────────────────── */

function UrlInspectionPanel({ siteUrl }: { siteUrl: string }) {
  const [inspectionUrl, setInspectionUrl] = useState('');
  const inspection = useMutation({
    mutationFn: (url: string) => inspectUrl(siteUrl, url),
  });
  const status: IndexStatusResult | undefined = inspection.data?.inspectionResult.indexStatusResult;

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const url = inspectionUrl.trim();
    if (url) {
      inspection.mutate(url);
    }
  }

  return (
    <section className="mt-6 rounded-xl border bg-white p-5 shadow-sm">
      <div className="mb-4">
        <h2 className="text-lg font-semibold text-gray-800">URL 색인 검사</h2>
        <p className="mt-1 text-sm text-gray-500">
          Google Search Console의 현재 색인, 크롤링, robots.txt, canonical 상태를 조회합니다.
        </p>
      </div>

      <form className="flex flex-col gap-2 sm:flex-row" onSubmit={submit}>
        <input
          type="url"
          required
          value={inspectionUrl}
          onChange={(event) => setInspectionUrl(event.target.value)}
          placeholder={siteUrl.startsWith('sc-domain:') ? 'https://example.com/page' : `${siteUrl}page`}
          className="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-800 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
        />
        <button
          type="submit"
          disabled={inspection.isPending || !inspectionUrl.trim()}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {inspection.isPending ? '검사 중...' : '검사'}
        </button>
      </form>

      {inspection.isError && (
        <p className="mt-3 text-sm text-red-700">
          URL 검사에 실패했습니다. 선택한 Search Console 속성에 속한 전체 URL인지 확인하세요.
        </p>
      )}

      {status && (
        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <InspectionField label="색인 판정" value={status.verdict} />
          <InspectionField label="색인 상태" value={status.coverageState} />
          <InspectionField label="크롤링 허용" value={status.indexingState} />
          <InspectionField label="robots.txt" value={status.robotsTxtState} />
          <InspectionField label="페이지 가져오기" value={status.pageFetchState} />
          <InspectionField label="크롤러" value={status.crawledAs} />
          <InspectionField label="마지막 크롤링" value={status.lastCrawlTime?.slice(0, 10)} />
          <InspectionField label="Google Canonical" value={status.googleCanonical} />
          <InspectionField label="사용자 Canonical" value={status.userCanonical} />
        </div>
      )}
    </section>
  );
}

function InspectionField({ label, value }: { label: string; value?: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
      <p className="text-xs font-medium text-gray-500">{label}</p>
      <p className="mt-1 break-all text-sm font-medium text-gray-800">{value || '정보 없음'}</p>
    </div>
  );
}

function KpiCard({ title, value, loading }: { title: string; value: string; loading: boolean }) {
  return (
    <div className="rounded-xl border bg-white p-5 shadow-sm">
      <p className="mb-1 text-sm text-gray-500">{title}</p>
      {loading ? (
        <div className="h-8 w-20 animate-pulse rounded bg-gray-200" />
      ) : (
        <p className="text-2xl font-bold text-gray-900">{value}</p>
      )}
    </div>
  );
}

type SortKey = 'clicks' | 'impressions' | 'ctr' | 'position';

function DataTable({
  loading,
  rows,
  keyLabel,
  keyIdx,
}: {
  loading: boolean;
  rows: Array<{ keys: string[]; clicks: number; impressions: number; ctr: number; position: number }>;
  keyLabel: string;
  keyIdx: number;
}) {
  const [sortKey, setSortKey] = useState<SortKey>('clicks');
  const [sortDesc, setSortDesc] = useState(true);

  const sortedRows = useMemo(() => {
    const sorted = [...rows].sort((a, b) => {
      const diff = (a[sortKey] as number) - (b[sortKey] as number);
      return sortDesc ? -diff : diff;
    });
    return sorted.slice(0, 50);
  }, [rows, sortKey, sortDesc]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDesc(!sortDesc);
    } else {
      setSortKey(key);
      setSortDesc(true);
    }
  }

  function sortIndicator(key: SortKey) {
    if (sortKey !== key) return ' ↕';
    return sortDesc ? ' ↓' : ' ↑';
  }

  if (loading) {
    return <div className="h-48 animate-pulse rounded-lg bg-gray-200" />;
  }
  if (rows.length === 0) {
    return <p className="py-12 text-center text-gray-400">데이터가 없습니다.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-gray-500">
            <th className="pb-2 pr-4 font-medium">{keyLabel}</th>
            <SortHeader label="클릭" sortKey="clicks" current={sortKey} desc={sortDesc} onToggle={toggleSort} indicator={sortIndicator('clicks')} />
            <SortHeader label="노출" sortKey="impressions" current={sortKey} desc={sortDesc} onToggle={toggleSort} indicator={sortIndicator('impressions')} />
            <SortHeader label="CTR" sortKey="ctr" current={sortKey} desc={sortDesc} onToggle={toggleSort} indicator={sortIndicator('ctr')} />
            <SortHeader label="순위" sortKey="position" current={sortKey} desc={sortDesc} onToggle={toggleSort} indicator={sortIndicator('position')} />
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((r, i) => (
            <tr key={i} className="border-b last:border-0">
              <td className="py-2 pr-4 max-w-[200px] truncate">{r.keys[keyIdx] ?? '-'}</td>
              <td className="py-2 pr-4 text-right">{formatNumber(r.clicks)}</td>
              <td className="py-2 pr-4 text-right">{formatNumber(r.impressions)}</td>
              <td className="py-2 pr-4 text-right">{formatPercent(r.ctr)}</td>
              <td className="py-2 pr-4 text-right">{formatPosition(r.position)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SortHeader({
  label,
  sortKey,
  current,
  desc,
  onToggle,
  indicator,
}: {
  label: string;
  sortKey: SortKey;
  current: SortKey;
  desc: boolean;
  onToggle: (key: SortKey) => void;
  indicator: string;
}) {
  const isActive = current === sortKey;
  return (
    <th
      className="pb-2 pr-4 cursor-pointer select-none font-medium text-right whitespace-nowrap"
      onClick={() => onToggle(sortKey)}
    >
      <span className={isActive ? 'text-blue-600' : ''}>
        {label}{indicator}
      </span>
    </th>
  );
}

/* ── Issues Section ──────────────────────────────────────────────── */

function IssuesSection({
  sitemaps,
  topPages,
  robotsIssues,
  loading,
}: {
  sitemaps: SitemapEntry[];
  topPages: Array<{ keys: string[]; clicks: number; impressions: number; ctr: number; position: number }>;
  robotsIssues: Array<{ severity: 'error' | 'warning' | 'info'; message: string }>;
  loading: boolean;
}) {
  if (loading) {
    return (
      <section className="mt-6 rounded-xl border bg-white p-5 shadow-sm">
        <h2 className="mb-4 text-lg font-semibold text-gray-800">이슈</h2>
        <div className="h-32 animate-pulse rounded-lg bg-gray-200" />
      </section>
    );
  }

  const issues: { severity: 'error' | 'warning' | 'info'; title: string; detail: string }[] = [];

  // Sitemap errors & warnings
  for (const sm of sitemaps) {
    const errCount = parseInt(sm.errors || '0', 10);
    const warnCount = parseInt(sm.warnings || '0', 10);
    // Build content summary from contents array
    const contentSummary = (sm.contents ?? [])
      .map((c) => {
        const submitted = parseInt(c.submitted || '0', 10);
        const indexed = parseInt(c.indexed || '0', 10);
        const indexedPct = submitted > 0 ? Math.round((indexed / submitted) * 100) : 0;
        return `${c.type === 'web' ? '웹' : c.type === 'image' ? '이미지' : c.type === 'video' ? '동영상' : c.type}: 제출 ${submitted}개, 색인 ${indexed}개 (${indexedPct}%)`;
      })
      .join(' / ');
    const lastDownloaded = sm.lastDownloaded ? sm.lastDownloaded.slice(0, 10) : '';
    if (errCount > 0) {
      issues.push({
        severity: 'error',
        title: `사이트맵 오류: ${sm.path}`,
        detail: [`${errCount}개 오류 발생`, contentSummary, lastDownloaded ? `최종 다운로드: ${lastDownloaded}` : ''].filter(Boolean).join(' | '),
      });
    }
    if (warnCount > 0) {
      const detailParts: string[] = [`${warnCount}개 경고 발생`];
      if (contentSummary) detailParts.push(contentSummary);
      if (lastDownloaded) detailParts.push(`최종 다운로드: ${lastDownloaded}`);
      // Check for low index rate
      const allSubmitted = (sm.contents ?? []).reduce((s, c) => s + parseInt(c.submitted || '0', 10), 0);
      const allIndexed = (sm.contents ?? []).reduce((s, c) => s + parseInt(c.indexed || '0', 10), 0);
      if (allSubmitted > 0 && allIndexed === 0) {
        detailParts.push('⚠️ 제출된 URL이 색인되지 않음 — URL 접근성 및 robots.txt 확인 필요');
      } else if (allSubmitted > 0 && allIndexed < allSubmitted * 0.5) {
        detailParts.push(`⚠️ 색인률 낮음 (${Math.round((allIndexed / allSubmitted) * 100)}%) — 콘텐츠 품질 및 크롤링 오류 확인 필요`);
      } else {
        detailParts.push('사이트맵 형식 또는 URL 관련 경고 — Search Console에서 상세 확인 필요');
      }
      issues.push({
        severity: 'warning',
        title: `사이트맵 경고: ${sm.path}`,
        detail: detailParts.join(' | '),
      });
    }
  }

  // Low CTR pages (high impressions, low clicks — improvement opportunity)
  const lowCtrPages = topPages
    .filter((p) => p.impressions >= 100 && p.ctr < 0.01)
    .sort((a, b) => b.impressions - a.impressions)
    .slice(0, 5);
  for (const p of lowCtrPages) {
    issues.push({
      severity: 'info',
      title: `낮은 CTR 페이지: ${p.keys[0] ?? '-'}`,
      detail: `노출 ${formatNumber(p.impressions)}회, CTR ${formatPercent(p.ctr)} — 제목/메타 설명 개선 필요`,
    });
  }

  // Low ranking pages (position > 20 — not on first 2 pages)
  const lowRankPages = topPages
    .filter((p) => p.position > 20 && p.impressions >= 50)
    .sort((a, b) => b.impressions - a.impressions)
    .slice(0, 5);
  for (const p of lowRankPages) {
    issues.push({
      severity: 'info',
      title: `낮은 순위 페이지: ${p.keys[0] ?? '-'}`,
      detail: `평균 순위 ${formatPosition(p.position)}위 — 콘텐츠 품질 및 내부 링크 개선 필요`,
    });
  }

  // robots.txt issues
  for (const ri of robotsIssues) {
    issues.push({
      severity: ri.severity,
      title: `robots.txt: ${ri.severity === 'error' ? '오류' : ri.severity === 'warning' ? '경고' : '정보'}`,
      detail: ri.message,
    });
  }

  const errorCount = issues.filter((i) => i.severity === 'error').length;
  const warnCount = issues.filter((i) => i.severity === 'warning').length;
  const infoCount = issues.filter((i) => i.severity === 'info').length;

  return (
    <section className="mt-6 rounded-xl border bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-3">
        <h2 className="text-lg font-semibold text-gray-800">이슈</h2>
        {errorCount > 0 && <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-700">오류 {errorCount}</span>}
        {warnCount > 0 && <span className="rounded-full bg-yellow-100 px-2.5 py-0.5 text-xs font-medium text-yellow-700">경고 {warnCount}</span>}
        {infoCount > 0 && <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-700">개선 제안 {infoCount}</span>}
        {issues.length === 0 && <span className="text-sm text-green-600">✓ 발견된 이슈 없음</span>}
      </div>

      {issues.length === 0 ? (
        <p className="py-8 text-center text-gray-400">모든 항목이 정상입니다.</p>
      ) : (
        <div className="space-y-3">
          {issues.map((issue, i) => {
            const styles = {
              error: { bg: 'bg-red-50', border: 'border-red-200', icon: '🔴', label: '오류' },
              warning: { bg: 'bg-yellow-50', border: 'border-yellow-200', icon: '🟡', label: '경고' },
              info: { bg: 'bg-blue-50', border: 'border-blue-200', icon: '🔵', label: '제안' },
            }[issue.severity];
            return (
              <div key={i} className={`rounded-lg border ${styles.border} ${styles.bg} p-3`}>
                <div className="flex items-start gap-2">
                  <span className="text-sm">{styles.icon}</span>
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-800">{issue.title}</p>
                    <p className="text-xs text-gray-500">{issue.detail}</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
