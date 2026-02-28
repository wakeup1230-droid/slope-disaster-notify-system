"""
Vendor API data models.

Defines request/response schemas for the vendor WebGIS integration API.
Uses a pull model: vendors poll for updated cases.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class VendorCaseListParams(BaseModel):
    """Query parameters for vendor case listing."""
    since: Optional[str] = Field(default=None, description="ISO datetime — return cases updated after this time")
    district_id: Optional[str] = Field(default=None, description="Filter by district ID")
    review_status: Optional[str] = Field(default=None, description="Filter by review status")
    road: Optional[str] = Field(default=None, description="Filter by road name")
    limit: int = Field(default=50, ge=1, le=200, description="Maximum results per page")
    offset: int = Field(default=0, ge=0, description="Pagination offset")


class VendorCoordinate(BaseModel):
    """Simplified coordinate for vendor consumption."""
    lat: float
    lon: float
    confidence: float = 0.0


class VendorMilepost(BaseModel):
    """Simplified milepost for vendor consumption."""
    road: str
    milepost_display: str
    milepost_km: float


class VendorCaseSummary(BaseModel):
    """
    Summarized case data for vendor API responses.
    Strips internal fields, exposes only what vendors need for WebGIS.
    """
    case_id: str
    district_id: str
    district_name: str
    road_number: str
    coordinate: Optional[VendorCoordinate] = None
    milepost: Optional[VendorMilepost] = None
    damage_mode_category: str = ""
    damage_mode_name: str = ""
    description: str = ""
    urgency: str = "normal"
    review_status: str = ""
    photo_count: int = 0
    thumbnail_url: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""


class VendorCaseListResponse(BaseModel):
    """Response wrapper for vendor case listing."""
    total: int = 0
    limit: int = 50
    offset: int = 0
    cases: list[VendorCaseSummary] = Field(default_factory=list)


class VendorCaseDetail(BaseModel):
    """
    Detailed case data for vendor single-case endpoint.
    Includes evidence URLs for map popups.
    """
    case_id: str
    district_id: str
    district_name: str
    road_number: str
    coordinate: Optional[VendorCoordinate] = None
    milepost: Optional[VendorMilepost] = None
    damage_mode_category: str = ""
    damage_mode_name: str = ""
    damage_cause_names: list[str] = Field(default_factory=list)
    description: str = ""
    urgency: str = "normal"
    review_status: str = ""
    processing_stage: str = ""
    completeness_pct: float = 0.0
    site_survey_summary: list[str] = Field(default_factory=list)
    evidence_urls: list[VendorEvidenceItem] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class VendorEvidenceItem(BaseModel):
    """Evidence item for vendor case detail."""
    evidence_id: str
    photo_type: Optional[str] = None
    photo_type_name: Optional[str] = None
    thumbnail_url: str = ""
    full_url: str = ""
    annotations_summary: str = ""
