"""Search Console API client abstraction.

Supports two backends:
1. ``google-api-python-client`` (default, production)
2. ``httpx`` direct REST calls (lighter, optional)

In dry-run mode (``DRY_RUN=true``) the client returns canned data without
touching the network.

Caching: results are stored in SQLite via ``app.db.repository`` so that
repeated queries for the same user/site/date-range don't hit the GSC API.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import httpx

from app.config import settings


# ═══════════════════════════════════════════════════════════════════════
# Dry-run canned data
# ═══════════════════════════════════════════════════════════════════════

_DRY_RUN_SITES = [
    {"siteUrl": "https://example.com/", "permissionLevel": "siteOwner"},
    {"siteUrl": "https://blog.example.com/", "permissionLevel": "siteFullUser"},
    {"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"},
]

_DRY_RUN_SITEMAPS = [
    {
        "path": "https://example.com/sitemap.xml",
        "lastSubmitted": "2026-07-20T10:00:00Z",
        "isPending": False,
        "isSitemapsIndex": True,
        "type": "sitemap",
        "lastDownloaded": "2026-07-21T02:00:00Z",
        "warnings": "0",
        "errors": "0",
        "contents": [
            {"type": "web", "submitted": "5000", "indexed": "4800"},
        ],
    }
]


def _random_analytics_rows(
    dimensions: list[str], row_limit: int
) -> list[dict[str, Any]]:
    """Generate plausible-looking canned analytics data."""
    dim_values: dict[str, list[str]] = {
        "query": ["홈페이지", "블로그", "API 문서", "튜토리얼", "가이드", "다운로드", "가격", "리뷰"],
        "page": ["/", "/blog", "/docs", "/tutorial", "/pricing", "/about"],
        "country": ["KOR", "USA", "JPN", "GBR", "DEU"],
        "device": ["DESKTOP", "MOBILE", "TABLET"],
        "date": [],
    }

    # Generate date range if needed
    if "date" in dimensions:
        today = date.today()
        dim_values["date"] = [
            (today - timedelta(days=i)).isoformat() for i in range(90)
        ]

    rows = []
    for i in range(min(row_limit, 50)):
        keys = []
        for dim in dimensions:
            pool = dim_values.get(dim, ["unknown"])
            keys.append(random.choice(pool))
        rows.append(
            {
                "keys": keys,
                "clicks": round(random.uniform(0, 500), 1),
                "impressions": round(random.uniform(100, 10000), 1),
                "ctr": round(random.uniform(0, 0.15), 4),
                "position": round(random.uniform(1, 50), 1),
            }
        )
    return rows


# ═══════════════════════════════════════════════════════════════════════
# Client interface
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class SearchConsoleClient:
    """Read-only client for the Google Search Console API.

    When *user_id* is provided, results are cached in SQLite so that
    repeated queries don't hit the GSC API.
    """

    access_token: str
    user_id: str = ""

    # ── Sites ──────────────────────────────────────────────────────

    async def list_sites(self) -> list[dict[str, Any]]:
        """Return all verified sites for the authenticated user.

        On first call the result is fetched from GSC and cached in the
        ``projects`` table.  Subsequent calls return the cached list.
        In dry-run mode, cached projects take precedence over canned data.

        Always returns a list of site-entry dicts with keys:
        ``siteUrl``, ``permissionLevel``.
        """
        # Try cache first (works in both dry-run and live mode)
        if self.user_id:
            from app.db.repository import list_projects_by_user

            cached = await list_projects_by_user(self.user_id)
            if cached:
                return cached

        if settings.dry_run:
            return _DRY_RUN_SITES

        # Fetch from GSC
        data = await self._get("https://www.googleapis.com/webmasters/v3/sites")
        entries: list[dict[str, Any]] = data.get("siteEntry", []) if isinstance(data, dict) else []

        # Persist to cache
        if self.user_id and entries:
            from app.db.repository import sync_projects_from_gsc

            await sync_projects_from_gsc(self.user_id, entries)

        return entries

    # ── Search Analytics ───────────────────────────────────────────

    async def query_analytics(
        self,
        site_url: str,
        start_date: str,
        end_date: str,
        dimensions: list[str] | None = None,
        row_limit: int = 1000,
        dimension_filter_groups: list[dict] | None = None,
        aggregation_type: str = "auto",
        data_state: str = "all",
    ) -> dict[str, Any]:
        """Run a Search Analytics query (with SQLite caching)."""
        dims = dimensions or []

        # Try cache first (works in both dry-run and live mode)
        if self.user_id:
            from app.db.repository import get_project_id, get_cached_analytics

            project_id = await get_project_id(self.user_id, site_url)
            if project_id is not None:
                cached = await get_cached_analytics(
                    project_id,
                    start_date,
                    end_date,
                    dims,
                    row_limit,
                    dimension_filter_groups,
                    aggregation_type,
                    data_state,
                )
                if cached is not None:
                    return cached

        if settings.dry_run:
            return {
                "rows": _random_analytics_rows(dims, row_limit),
                "responseAggregationType": aggregation_type,
            }

        # Fetch from GSC
        body: dict[str, Any] = {
            "startDate": start_date,
            "endDate": end_date,
            "rowLimit": row_limit,
            "aggregationType": aggregation_type,
            "dataState": data_state,
        }
        if dims:
            body["dimensions"] = dims
        if dimension_filter_groups:
            body["dimensionFilterGroups"] = dimension_filter_groups

        encoded = site_url.replace("/", "%2F")
        data = await self._post(
            f"https://www.googleapis.com/webmasters/v3/sites/{encoded}/searchAnalytics/query",
            json=body,
        )

        # Persist to cache
        if self.user_id:
            from app.db.repository import get_project_id, set_cached_analytics

            project_id = await get_project_id(self.user_id, site_url)
            if project_id is not None:
                await set_cached_analytics(
                    project_id,
                    start_date,
                    end_date,
                    dims,
                    row_limit,
                    data,
                    dimension_filter_groups,
                    aggregation_type,
                    data_state,
                )

        return data

    # ── Sitemaps ───────────────────────────────────────────────────

    async def list_sitemaps(self, site_url: str) -> dict[str, Any]:
        """List submitted sitemaps for a site (with SQLite caching)."""
        # Try cache first (works in both dry-run and live mode)
        if self.user_id:
            from app.db.repository import get_project_id, get_cached_sitemaps

            project_id = await get_project_id(self.user_id, site_url)
            if project_id is not None:
                cached = await get_cached_sitemaps(project_id)
                if cached is not None:
                    return cached

        if settings.dry_run:
            return {"sitemap": _DRY_RUN_SITEMAPS}

        # Fetch from GSC
        encoded = site_url.replace("/", "%2F")
        data = await self._get(
            f"https://www.googleapis.com/webmasters/v3/sites/{encoded}/sitemaps"
        )

        # Persist to cache
        if self.user_id:
            from app.db.repository import get_project_id, set_cached_sitemaps

            project_id = await get_project_id(self.user_id, site_url)
            if project_id is not None:
                await set_cached_sitemaps(project_id, data)

        return data

    # ── URL Inspection ─────────────────────────────────────────────

    async def inspect_url(self, site_url: str, inspection_url: str, language_code: str = "ko") -> dict[str, Any]:
        """Inspect a URL's index status."""
        if settings.dry_run:
            return {
                "inspectionResult": {
                    "inspectionResultLink": f"https://search.google.com/search-console/inspect?resource_id={site_url}",
                    "indexStatusResult": {
                        "verdict": "PASS",
                        "coverageState": "Indexed",
                        "robotsTxtState": "ALLOWED",
                        "indexingState": "INDEXING_ALLOWED",
                        "lastCrawlTime": "2026-07-25T00:00:00Z",
                        "pageFetchState": "SUCCESSFUL",
                        "googleCanonical": inspection_url,
                        "userCanonical": inspection_url,
                        "crawledAs": "MOBILE",
                    },
                }
            }

        body = {
            "inspectionUrl": inspection_url,
            "siteUrl": site_url,
            "languageCode": language_code,
        }
        return await self._post(
            "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
            json=body,
        )

    # ── HTTP helpers ───────────────────────────────────────────────

    async def _get(self, url: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                url,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            resp.raise_for_status()
            return resp.json()

    async def _post(self, url: str, json: dict) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                json=json,
            )
            resp.raise_for_status()
            return resp.json()
