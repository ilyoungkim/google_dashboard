"""API routes: /api/sites, /api/searchanalytics/query, /api/sitemaps, etc."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.schemas import (
    SearchAnalyticsRequest,
    SearchAnalyticsResponse,
    SearchAnalyticsRow,
    SitesResponse,
    SiteEntry,
    SitemapsResponse,
    SitemapEntry,
    URLInspectionRequest,
    URLInspectionResult,
    KPISummary,
)
from app.api.searchconsole import SearchConsoleClient
from app.config import settings
from app.deps import gsc_client

router = APIRouter(prefix="/api", tags=["api"])


# ── GET /api/sites ─────────────────────────────────────────────────────

@router.get("/sites", response_model=SitesResponse)
async def list_sites(client: SearchConsoleClient = Depends(gsc_client)):
    """List all verified sites in the user's Search Console account."""
    entries = await client.list_sites()
    return SitesResponse(
        siteEntry=[SiteEntry(**e) for e in entries]
    )


# ── POST /api/searchanalytics/query ────────────────────────────────────

@router.post("/searchanalytics/query", response_model=SearchAnalyticsResponse)
async def query_analytics(
    body: SearchAnalyticsRequest,
    client: SearchConsoleClient = Depends(gsc_client),
):
    """Query Search Analytics data for a given site and date range."""
    data = await client.query_analytics(
        site_url=body.siteUrl,
        start_date=body.startDate,
        end_date=body.endDate,
        dimensions=body.dimensions,
        row_limit=body.rowLimit,
        dimension_filter_groups=[
            f.model_dump() for f in body.dimensionFilterGroups
        ],
        aggregation_type=body.aggregationType,
        data_state=body.dataState,
    )
    rows = [SearchAnalyticsRow(**r) for r in data.get("rows", [])]
    return SearchAnalyticsResponse(
        rows=rows,
        responseAggregationType=data.get("responseAggregationType", ""),
    )


# ── GET /api/sitemaps ──────────────────────────────────────────────────

@router.get("/sitemaps", response_model=SitemapsResponse)
async def list_sitemaps(
    siteUrl: str = Query(..., description="Site URL (e.g. https://example.com/)"),
    client: SearchConsoleClient = Depends(gsc_client),
):
    """List submitted sitemaps for a site."""
    data = await client.list_sitemaps(siteUrl)
    entries = data.get("sitemap", []) if isinstance(data, dict) else []
    return SitemapsResponse(
        sitemap=[SitemapEntry(**e) for e in entries]
    )


# ── POST /api/urlinspection/index ──────────────────────────────────────

@router.post("/urlinspection/index", response_model=URLInspectionResult)
async def inspect_url(
    body: URLInspectionRequest,
    client: SearchConsoleClient = Depends(gsc_client),
):
    """Inspect a URL's index status."""
    data = await client.inspect_url(
        site_url=body.siteUrl,
        inspection_url=body.inspectionUrl,
        language_code=body.languageCode,
    )
    return URLInspectionResult(**data)


# ── GET /api/kpi ───────────────────────────────────────────────────────

@router.get("/kpi", response_model=KPISummary)
async def get_kpi_summary(
    siteUrl: str = Query(..., description="Site URL"),
    startDate: str = Query(..., description="Start date YYYY-MM-DD"),
    endDate: str = Query(..., description="End date YYYY-MM-DD"),
    client: SearchConsoleClient = Depends(gsc_client),
):
    """Return aggregated KPI summary (total clicks, impressions, avg CTR, avg position)."""
    data = await client.query_analytics(
        site_url=siteUrl,
        start_date=startDate,
        end_date=endDate,
        dimensions=[],
        row_limit=1,
    )
    rows = data.get("rows", [])
    if not rows:
        return KPISummary()

    # Aggregate all rows
    total_clicks = sum(r.get("clicks", 0) for r in rows)
    total_impressions = sum(r.get("impressions", 0) for r in rows)
    avg_ctr = total_clicks / total_impressions if total_impressions > 0 else 0.0
    avg_position = (
        sum(r.get("position", 0) * r.get("impressions", 1) for r in rows)
        / total_impressions
        if total_impressions > 0
        else 0.0
    )

    return KPISummary(
        totalClicks=total_clicks,
        totalImpressions=total_impressions,
        avgCtr=round(avg_ctr, 4),
        avgPosition=round(avg_position, 1),
    )


# ── GET /api/robots-txt ───────────────────────────────────────────────

class RobotsTxtIssue(BaseModel):
    severity: str  # "error" | "warning" | "info"
    message: str


class RobotsTxtAnalysis(BaseModel):
    found: bool
    statusCode: int
    content: str
    sitemaps: list[str]
    issues: list[RobotsTxtIssue]


async def _get_robots_url(site_url: str, client: SearchConsoleClient) -> str:
    """Validate a robots.txt target and return its URL.

    Search Console properties are allowed for the authenticated user. Private
    and loopback IPs are supported only when explicitly configured for local
    development or trusted network diagnostics.
    """
    site_url = site_url.strip()
    registered_sites = {
        entry.get("siteUrl", "") for entry in await client.list_sites()
    }
    if site_url in registered_sites:
        if site_url.startswith("sc-domain:"):
            host = site_url.removeprefix("sc-domain:").strip("/")
            if not host or any(char in host for char in "/@?#"):
                raise HTTPException(status_code=422, detail="Invalid domain property.")
            return f"https://{host}/robots.txt"

        parsed = urlparse(site_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise HTTPException(status_code=422, detail="Invalid site URL.")
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    parsed = urlparse(site_url)
    hostname = parsed.hostname
    allowed_hosts = {
        host.strip() for host in settings.robots_allowed_local_hosts.split(",") if host.strip()
    }
    try:
        is_private_ip = hostname is not None and (
            ipaddress.ip_address(hostname).is_private
            or ipaddress.ip_address(hostname).is_loopback
        )
    except ValueError:
        is_private_ip = False

    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username
        or parsed.password
        or not is_private_ip
        or hostname not in allowed_hosts
    ):
        raise HTTPException(
            status_code=403,
            detail="Site is not authorized for robots.txt analysis.",
        )
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


@router.get("/robots-txt", response_model=RobotsTxtAnalysis)
async def analyze_robots_txt(
    siteUrl: str = Query(..., description="Site URL (e.g. https://example.com/)"),
    client: SearchConsoleClient = Depends(gsc_client),
):
    """Fetch and analyze the site's robots.txt file."""
    robots_url = await _get_robots_url(siteUrl, client)
    site_host = urlparse(robots_url).hostname or ""

    issues: list[RobotsTxtIssue] = []
    sitemaps: list[str] = []
    content = ""

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as http_client:
            resp = await http_client.get(robots_url)

        if resp.status_code != 200:
            issues.append(RobotsTxtIssue(
                severity="error",
                message=f"robots.txt를 불러올 수 없음 (HTTP {resp.status_code})",
            ))
            return RobotsTxtAnalysis(
                found=False,
                statusCode=resp.status_code,
                content="",
                sitemaps=[],
                issues=issues,
            )

        content = resp.text
        # Parse robots.txt
        lines = content.splitlines()
        for line in lines:
            line = line.strip()
            if line.lower().startswith("sitemap:"):
                sitemap_url = line.split(":", 1)[1].strip()
                sitemaps.append(sitemap_url)
                # Check if sitemap URL matches the site host
                sitemap_host = urlparse(sitemap_url).hostname or ""
                if sitemap_host and sitemap_host != site_host and not sitemap_host.endswith(site_host):
                    issues.append(RobotsTxtIssue(
                        severity="error",
                        message=f"사이트맵 URL이 다른 도메인을 가리킴: {sitemap_url} (사이트: {site_host}) — 오타 또는 잘못된 도메인 설정 의심",
                    ))

        # Check for common issues
        has_user_agent = any(line.lower().startswith("user-agent:") for line in lines)
        if not has_user_agent:
            issues.append(RobotsTxtIssue(
                severity="warning",
                message="User-Agent 지시어가 없음 — 모든 크롤러에 대한 규칙이 정의되지 않음",
            ))

        has_disallow = any(line.lower().startswith("disallow:") for line in lines)
        if not has_disallow:
            issues.append(RobotsTxtIssue(
                severity="info",
                message="Disallow 규칙이 없음 — 모든 페이지가 크롤링 허용됨",
            ))

        if not sitemaps:
            issues.append(RobotsTxtIssue(
                severity="warning",
                message="Sitemap 선언이 없음 — 크롤러가 사이트맵을 자동 발견하기 어려움",
            ))

        # Check for overly broad Disallow
        for line in lines:
            if line.lower().startswith("disallow:") and line.split(":", 1)[1].strip() == "/":
                issues.append(RobotsTxtIssue(
                    severity="error",
                    message="Disallow: / (전체 사이트 크롤링 차단) — 모든 검색엔진 색인이 차단됨",
                ))

        if not issues:
            issues.append(RobotsTxtIssue(
                severity="info",
                message="robots.txt에 명백한 문제가 발견되지 않음",
            ))

    except httpx.ConnectError:
        issues.append(RobotsTxtIssue(
            severity="error",
            message=f"사이트에 연결할 수 없음: {robots_url}",
        ))
        return RobotsTxtAnalysis(found=False, statusCode=0, content="", sitemaps=[], issues=issues)
    except Exception as exc:
        issues.append(RobotsTxtIssue(
            severity="error",
            message=f"robots.txt 분석 중 오류: {exc}",
        ))
        return RobotsTxtAnalysis(found=False, statusCode=0, content="", sitemaps=[], issues=issues)

    return RobotsTxtAnalysis(
        found=True,
        statusCode=resp.status_code,
        content=content,
        sitemaps=sitemaps,
        issues=issues,
    )
