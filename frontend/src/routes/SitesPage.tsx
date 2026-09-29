import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { getSites, type SiteEntry } from '../api/sites';
import { useAuth } from '../auth/AuthContext';
import { qk } from '../lib/queryKeys';

const PERMISSION_LABELS: Record<string, { label: string; color: string }> = {
  siteOwner: { label: '소유자', color: 'bg-blue-100 text-blue-700' },
  siteFullUser: { label: '전체 사용자', color: 'bg-green-100 text-green-700' },
  siteRestrictedUser: { label: '제한된 사용자', color: 'bg-gray-100 text-gray-600' },
  siteUnverifiedUser: { label: '미확인 사용자', color: 'bg-yellow-100 text-yellow-700' },
};

export function SitesPage() {
  const { email, logout } = useAuth();
  const navigate = useNavigate();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: qk.sites(),
    queryFn: getSites,
    staleTime: 5 * 60 * 1000,
  });

  const sites = data?.siteEntry ?? [];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b bg-white shadow-sm">
        <div className="flex items-center justify-between px-6 py-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">
              G
            </div>
            <span className="text-lg font-semibold text-gray-800">GSC Dashboard</span>
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

      {/* Main */}
      <main className="px-6 py-8">
        <h1 className="mb-6 text-2xl font-bold text-gray-900">내 Search Console 사이트</h1>

        {/* Loading */}
        {isLoading && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-28 animate-pulse rounded-xl bg-gray-200" />
            ))}
          </div>
        )}

        {/* Error */}
        {isError && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
            <p className="mb-3 text-red-700">사이트 목록을 불러올 수 없습니다.</p>
            <button
              onClick={() => refetch()}
              className="rounded-lg bg-red-600 px-4 py-2 text-sm text-white transition hover:bg-red-700"
            >
              다시 시도
            </button>
          </div>
        )}

        {/* Empty */}
        {!isLoading && !isError && sites.length === 0 && (
          <div className="rounded-xl border border-dashed border-gray-300 p-12 text-center">
            <p className="mb-2 text-lg text-gray-500">Search Console에 등록된 사이트가 없습니다.</p>
            <a
              href="https://search.google.com/search-console"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-blue-600 underline"
            >
              Search Console 열기 →
            </a>
          </div>
        )}

        {/* Site cards */}
        {!isLoading && !isError && sites.length > 0 && (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5">
            {sites.map((site: SiteEntry) => {
              const perm = PERMISSION_LABELS[site.permissionLevel] ?? {
                label: site.permissionLevel,
                color: 'bg-gray-100 text-gray-600',
              };
              return (
                <button
                  key={site.siteUrl}
                  onClick={() => navigate(`/dashboard/${encodeURIComponent(site.siteUrl)}`)}
                  className="rounded-xl border bg-white p-5 text-left shadow-sm transition hover:shadow-md hover:border-blue-300"
                >
                  <p className="mb-2 truncate text-sm font-medium text-gray-900">{site.siteUrl}</p>
                  <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${perm.color}`}>
                    {perm.label}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
