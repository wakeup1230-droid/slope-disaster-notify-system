"""
Evidence data models.

Defines the structure for evidence files (photos, documents)
with content-addressed storage and annotation support.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AnnotationTag(BaseModel):
    """A single annotation tag on a photo."""
    category: str = Field(description="Tag category, e.g., 'structure', 'severity'")
    tag_id: str = Field(description="Tag identifier, e.g., 'foundation_scour'")
    label: str = Field(description="Display label in Chinese")
    source: str = Field(default="user_select", description="'user_select' or 'user_input' or 'auto'")


class PhotoSetPhoto(BaseModel):
    """A single photo within a photo set (P1-P4 support 1-3 photos each)."""
    photo_id: str = Field(description="Unique ID within set, e.g., 'P2_001'")
    order: int = Field(default=1, description="Photo order within set (1-3)")
    evidence_id: str = Field(default="", description="Reference to EvidenceMetadata.evidence_id")
    file_path: str = Field(default="", description="Relative path to stored photo")
    visible_tags: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-photo visible tags from 📷 source. Keys are category_id, values are selected tag_ids."
    )


class PhotoSetAnnotation(BaseModel):
    """
    Complete annotation data for a photo set (e.g., P2 set with 1-3 photos).

    Separates photo-visible tags (per-photo) from judgment tags (per-set).
    Supports differential tagging for supplement photos.
    """
    photo_set_type: str = Field(description="Photo type code, e.g., 'P2'")
    photo_set_name: str = Field(default="", description="Chinese name, e.g., '災損近照'")
    disaster_type: str = Field(default="", description="'revetment_retaining', 'road_slope', or 'bridge'")
    max_photos: int = Field(default=3, description="Maximum photos allowed in this set")
    is_required: bool = Field(default=True, description="Whether this photo set is required")

    # Per-photo data (each photo has its own visible_tags)
    photos: list[PhotoSetPhoto] = Field(default_factory=list)

    # Judgment tags (filled once per set, after all photos)
    judgment_tags: dict[str, Any] = Field(
        default_factory=dict,
        description="Per-set judgment tags from 🧠 source. Keys are category_id, values are selected tag_ids."
    )

    # Merged visible tags across all photos in this set
    merged_visible_tags: dict[str, Any] = Field(
        default_factory=dict,
        description="Union of all per-photo visible_tags for reporting/AI training."
    )

    # Status tracking
    photo_tags_complete: bool = False
    judgment_tags_complete: bool = False
    is_complete: bool = False

    def merge_visible_tags(self) -> None:
        """Merge visible_tags from all photos into merged_visible_tags."""
        merged: dict[str, list[str]] = {}
        for photo in self.photos:
            for cat_id, tag_ids in photo.visible_tags.items():
                if cat_id not in merged:
                    merged[cat_id] = []
                if isinstance(tag_ids, list):
                    for tid in tag_ids:
                        if tid not in merged[cat_id]:
                            merged[cat_id].append(tid)
                elif isinstance(tag_ids, str):
                    if tag_ids not in merged[cat_id]:
                        merged[cat_id].append(tag_ids)
        self.merged_visible_tags = merged

    def mark_complete(self) -> None:
        """Mark the photo set as complete and perform final merge."""
        self.merge_visible_tags()
        self.is_complete = True

class CustomNote(BaseModel):
    """A user-entered custom note for a photo."""
    text: str
    source: str = Field(default="user_input")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class SeverityAnnotation(BaseModel):
    """Severity rating for a damage photo."""
    value: str = Field(description="'minor', 'moderate', 'severe', 'critical'")
    label: str = Field(description="Display label: '輕微', '中等', '嚴重', '極嚴重'")


class PhotoAnnotations(BaseModel):
    """Structured annotations for a single photo."""
    severity: Optional[SeverityAnnotation] = None
    tags: list[AnnotationTag] = Field(default_factory=list)
    custom_notes: list[CustomNote] = Field(default_factory=list)


class AiReadyData(BaseModel):
    """
    Fields reserved for Phase 2 AI processing.
    Phase 1: All fields are None/empty. Structure preserved for future use.
    """
    auto_tags: list[AnnotationTag] = Field(default_factory=list)
    auto_severity: Optional[SeverityAnnotation] = None
    auto_damage_score: Optional[float] = None
    human_verified: bool = True
    model_version: Optional[str] = None
    inference_timestamp: Optional[str] = None


class EvidenceMetadata(BaseModel):
    """
    Complete metadata for a single evidence file (photo/document).
    Stored in evidence_manifest.json within the case folder.
    """
    # --- Identity ---
    evidence_id: str = Field(description="Unique ID, e.g., 'ev_001'")
    sha256: str = Field(description="Content hash for deduplication")
    original_filename: str
    content_type: str = Field(description="MIME type, e.g., 'image/jpeg'")
    file_size_bytes: int = 0

    # --- Photo Type ---
    photo_type: Optional[str] = Field(default=None, description="P1-P10 type code")
    photo_type_name: Optional[str] = Field(default=None, description="Chinese name of photo type")
    is_required_type: bool = False

    # --- Annotations ---
    annotations: PhotoAnnotations = Field(default_factory=PhotoAnnotations)

    # --- AI Ready ---
    ai_ready: AiReadyData = Field(default_factory=AiReadyData)

    # --- EXIF Data ---
    exif_gps_lat: Optional[float] = None
    exif_gps_lon: Optional[float] = None
    exif_datetime: Optional[str] = None
    exif_camera: Optional[str] = None

    # --- Image Dimensions ---
    width: Optional[int] = None
    height: Optional[int] = None

    # --- Timestamps ---
    uploaded_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    annotated_at: Optional[str] = None

    # --- Storage Paths (relative to case folder) ---
    evidence_path: str = Field(default="", description="Relative path: evidence/{sha256}.{ext}")
    thumbnail_path: str = Field(default="", description="Relative path: thumbnails/{sha256}_thumb.jpg")


class EvidenceManifest(BaseModel):
    """
    Manifest of all evidence files for a case.
    Stored as evidence_manifest.json in the case folder.
    """
    case_id: str
    total_evidence: int = 0
    required_types_present: list[str] = Field(default_factory=list)
    required_types_missing: list[str] = Field(default_factory=list)
    evidence: list[EvidenceMetadata] = Field(default_factory=list)
    last_updated: str = Field(default_factory=lambda: datetime.now().isoformat())

    def check_required_types(self) -> None:
        """Check which required photo types (P1-P4) are present."""
        required = {"P1", "P2", "P3", "P4"}
        present = {e.photo_type for e in self.evidence if e.photo_type}
        self.required_types_present = sorted(required & present)
        self.required_types_missing = sorted(required - present)
        self.total_evidence = len(self.evidence)
