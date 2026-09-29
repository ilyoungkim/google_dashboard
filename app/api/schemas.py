"""Pydantic schemas for API request/response models."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


# ── Sites ──────────────────────────────────────────────────────────────

class SiteEntry(BaseModel):
    siteUrl: str
    permissionLevel: str


class SitesResponse(BaseModel):
    siteEntry: list[SiteEntry] = []


# ── Search Analytics ───────────────────────────────────────────────────

class DimensionFilterGroup(BaseModel):
    filters: list[dict[str, Any]] = []
    groupType: str = "and"


class SearchAnalyticsRequest(BaseModel):
    siteUrl: str
    startDate: str  # YYYY-MM-DD
    endDate: str  # YYYY-MM-DD
    dimensions: list[str] = Field(default_factory=list)
    rowLimit: int = Field(default=1000, ge=1, le=25000)
    dimensionFilterGroups: list[DimensionFilterGroup] = Field(default_factory=list)
    aggregationType: str = "auto"
    dataState: str = "all"


class SearchAnalyticsRow(BaseModel):
    keys: list[str] = Field(default_factory=list)
    clicks: float = 0.0
    impressions: float = 0.0
    ctr: float = 0.0
    position: float = 0.0


class SearchAnalyticsResponse(BaseModel):
    rows: list[SearchAnalyticsRow] = Field(default_factory=list)
    responseAggregationType: str = ""


# ── Sitemaps ───────────────────────────────────────────────────────────

class SitemapEntry(BaseModel):
    path: str = ""
    lastSubmitted: str = ""
    isPending: bool = False
    isSitemapsIndex: bool = False
    type: str = ""
    lastDownloaded: str = ""
    warnings: str = ""
    errors: str = ""
    contents: list[dict[str, Any]] = Field(default_factory=list)


class SitemapsResponse(BaseModel):
    sitemap: list[SitemapEntry] = Field(default_factory=list)


# ── URL Inspection ─────────────────────────────────────────────────────

class URLInspectionRequest(BaseModel):
    siteUrl: str
    inspectionUrl: str
    languageCode: str = "ko"


class URLInspectionResult(BaseModel):
    inspectionResult: dict[str, Any] = Field(default_factory=dict)


# ── KPI Summary (computed) ─────────────────────────────────────────────

class KPISummary(BaseModel):
    totalClicks: float = 0.0
    totalImpressions: float = 0.0
    avgCtr: float = 0.0
    avgPosition: float = 0.0
