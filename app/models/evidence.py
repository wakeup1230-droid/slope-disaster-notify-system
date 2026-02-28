"""
Evidence data models.

Defines the structure for evidence files (photos, documents)
with content-addressed storage and annotation support.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AnnotationTag(BaseModel):
    """A single annotation tag on a photo."""
    category: str = Field(description="Tag category, e.g., 'structure', 'severity'")
    tag_id: str = Field(description="Tag identifier, e.g., 'foundation_scour'")
    label: str = Field(description="Display label in Chinese")
    source: str = Field(default="user_select", description="'user_select' or 'user_input' or 'auto'")


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
