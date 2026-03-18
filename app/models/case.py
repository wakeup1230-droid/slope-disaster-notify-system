"""
Case data models.

Defines the structure for disaster cases including dual-track status,
evidence references, damage classification, and audit trail.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# --- Enums ---

class ProcessingStage(str, Enum):
    """Technical processing stages (auto-advanced)."""
    INGESTED = "ingested"
    PHOTOS_PROCESSED = "photos_processed"
    MILEPOST_RESOLVED = "milepost_resolved"
    COMPLETE = "complete"


class ReviewStatus(str, Enum):
    """Business review status (manager-controlled)."""
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    IN_PROGRESS = "in_progress"
    RETURNED = "returned"
    CLOSED = "closed"

class Urgency(str, Enum):
    """Case urgency level."""
    NORMAL = "normal"
    URGENT = "urgent"
    EMERGENCY = "emergency"


class DamageModeCategory(str, Enum):
    """Top-level damage mode categories."""
    REVETMENT_RETAINING = "revetment_retaining"
    ROAD_SLOPE = "road_slope"
    BRIDGE = "bridge"


# --- Sub-models ---

class CoordinateCandidate(BaseModel):
    """A GPS coordinate candidate with confidence scoring."""
    lat: float
    lon: float
    source: str = Field(description="Origin: 'exif', 'manual', 'lrs_reverse'")
    confidence: float = Field(ge=0.0, le=1.0)
    label: Optional[str] = None


class MilepostInfo(BaseModel):
    """Resolved milepost information."""
    road: str = Field(description="Road name, e.g., '台7線'")
    milepost_km: float = Field(description="Milepost in km, e.g., 32.4")
    milepost_display: str = Field(description="Display format, e.g., '32K+400'")
    confidence: float = Field(ge=0.0, le=1.0)
    is_interpolated: bool = False
    source: str = Field(default="auto", description="'auto' or 'manual'")


class EvidenceSummary(BaseModel):
    """Summary of an evidence file attached to a case."""
    evidence_id: str
    sha256: str
    original_filename: str
    content_type: str
    photo_type: Optional[str] = None
    file_size_bytes: int = 0
    uploaded_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class ReviewHistoryEntry(BaseModel):
    """A single status transition record."""
    from_status: str
    to_status: str
    actor: str = Field(description="user_id of the person who made the change")
    actor_name: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    note: str = ""


class CreatedBy(BaseModel):
    """Information about the case creator."""
    user_id: str
    display_name: str = ""
    real_name: str = ""
    district_id: str = ""
    district_name: str = ""


class SiteSurveyItem(BaseModel):
    """A single site survey checklist item."""
    category_id: str
    item_id: str
    item_name: str = ""
    checked: bool = False
    note: str = ""

class CostBreakdownItem(BaseModel):
    """A single line item in the cost breakdown."""
    item_id: str = ""
    item_name: str = ""
    unit: str = ""
    unit_price: Optional[float] = None
    quantity: Optional[float] = None
    amount: Optional[float] = Field(default=None, description="Amount in NTD (元); quantity * unit_price for items 1-4, or direct input for items 5-6")

# --- Main Case Model ---

class Case(BaseModel):
    """
    Complete disaster case record.

    Dual-track status:
    - processing_stage: technical stages (auto-advanced by system)
    - review_status: business review (manager-controlled)
    """

    # --- Identity ---
    case_id: str = Field(description="Format: case_YYYYMMDD_NNNN")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # --- Dual-track Status ---
    processing_stage: ProcessingStage = ProcessingStage.INGESTED
    review_status: ReviewStatus = ReviewStatus.DRAFT
    review_history: list[ReviewHistoryEntry] = Field(default_factory=list)

    # --- Location ---
    district_id: str = ""
    district_name: str = ""
    road_number: str = ""
    milepost: Optional[MilepostInfo] = None
    coordinate_candidates: list[CoordinateCandidate] = Field(default_factory=list)
    primary_coordinate: Optional[CoordinateCandidate] = None
    geology_info: dict[str, Any] = Field(default_factory=dict, description="Auto-queried geology data: 地層, 岩性, 斷層, 褶皺")
    county_name: str = Field(default="", description="縣市 from admin boundary query")
    town_name: str = Field(default="", description="鄉鎮市區 from admin boundary query")
    village_name: str = Field(default="", description="村里 from admin boundary query")
    national_park: str = Field(default="", description="國家公園名稱, empty if not in national park")

    # --- Damage Classification ---
    damage_mode_category: str = ""
    damage_mode_id: str = ""
    damage_mode_name: str = ""
    damage_cause_ids: list[str] = Field(default_factory=list)
    damage_cause_names: list[str] = Field(default_factory=list)

    # --- Description ---
    description: str = ""
    urgency: Urgency = Urgency.NORMAL
    related_event: str = Field(default="", description="Related event, e.g., typhoon name")
    estimated_cost: Optional[float] = Field(default=None, description="Optional estimated cost in NTD (萬元)")
    cost_breakdown: list[CostBreakdownItem] = Field(default_factory=list, description="Structured cost breakdown items")

    # --- P1: Auto-fill ---
    reporting_agency: str = Field(default="交通部公路局北區養護工程分局", description="提報機關")
    reporting_year: str = Field(default="", description="年度 (民國年)")

    # --- P1+: Word document fields ---
    project_name: str = Field(default="", description="工程名稱")
    disaster_date: str = Field(default="", description="災害發生日期 (YYYY-MM-DD or 民國年月日)")
    nearby_landmark: str = Field(default="", description="所在或鄰近之河溪、道路或顯著目標")
    # --- P2: User selections ---
    disaster_type: str = Field(default="", description="災害類型: 一般 | 專案")
    processing_type: str = Field(default="", description="處理類型: 搶修 | 復建")
    repeat_disaster: str = Field(default="", description="是否重複致災: 是 | 否")
    repeat_disaster_year: str = Field(default="", description="重複致災興建年份")

    # --- P3: Analysis ---
    original_protection: str = Field(default="", description="原設計保護型式")
    analysis_review: str = Field(default="", description="分析與檢討")
    design_doc_evidence_id: str = Field(default="", description="設計圖說 PDF evidence ID")

    # --- P4: Regulatory ---
    soil_conservation: str = Field(default="", description="水土保持計畫: 需要已核定 | 需要未核定 | 不需要")
    safety_assessment: str = Field(default="", description="整體安全評估")

    # --- P5: Hazard ---
    hazard_summary: list[str] = Field(default_factory=list, description="自動彙整工址環境危害項目")
    hazard_supplement: str = Field(default="", description="工址環境危害補充說明")
    other_supplement: str = Field(default="", description="其他補充事項")
    # --- Evidence ---
    evidence_summary: list[EvidenceSummary] = Field(default_factory=list)
    photo_count: int = 0

    # --- Site Survey ---
    site_survey: list[SiteSurveyItem] = Field(default_factory=list)

    # --- Creator ---
    created_by: Optional[CreatedBy] = None

    # --- Completeness ---
    completeness_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    missing_fields: list[str] = Field(default_factory=list)

    # --- Manager Notes ---
    manager_notes: list[str] = Field(default_factory=list)
    return_reason: str = ""

    def update_timestamp(self) -> None:
        """Update the updated_at field to now."""
        self.updated_at = datetime.now().isoformat()

    def calculate_completeness(self) -> None:
        """Calculate completeness percentage based on filled fields."""
        required_fields = {
            "district_id": bool(self.district_id),
            "road_number": bool(self.road_number),
            "milepost": self.milepost is not None,
            "coordinate": len(self.coordinate_candidates) > 0,
            "damage_mode": bool(self.damage_mode_id),
            "damage_cause": len(self.damage_cause_ids) > 0,
            "description": bool(self.description),
            "photos_min": self.photo_count >= 4,
            "site_survey": any(item.checked for item in self.site_survey),
        }
        filled = sum(1 for v in required_fields.values() if v)
        total = len(required_fields)
        self.completeness_pct = round((filled / total) * 100, 1) if total > 0 else 0.0
        self.missing_fields = [k for k, v in required_fields.items() if not v]


# --- Audit Log Entry ---

class AuditEntry(BaseModel):
    """A single entry in the case audit trail (audit.jsonl)."""
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    action: str = Field(description="create, update, status_change, evidence_add, evidence_remove, review, return, close")
    actor: str = Field(description="user_id")
    actor_name: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
    case_id: str = ""
