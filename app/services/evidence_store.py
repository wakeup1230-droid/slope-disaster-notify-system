"""
Evidence store service.

Manages evidence file storage using content-addressed (SHA-256) artifacts.
Works with case_store for directory management and image_processor for processing.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.core.logging_config import get_logger
from app.core.security import compute_sha256
from app.models.evidence import EvidenceManifest, EvidenceMetadata

logger = get_logger(__name__)


class EvidenceStore:
    """
    Content-addressed evidence storage.

    Evidence files are stored by SHA-256 hash to enable deduplication.
    Each case has an evidence_manifest.json tracking all evidence metadata.
    """

    def __init__(self, cases_dir: Path) -> None:
        self._cases_dir = cases_dir

    def _case_dir(self, case_id: str) -> Path:
        return self._cases_dir / case_id

    def _evidence_dir(self, case_id: str) -> Path:
        return self._case_dir(case_id) / "evidence"

    def _thumbnail_dir(self, case_id: str) -> Path:
        return self._case_dir(case_id) / "thumbnails"

    def _manifest_path(self, case_id: str) -> Path:
        return self._case_dir(case_id) / "evidence_manifest.json"

    # --- Manifest ---

    def get_manifest(self, case_id: str) -> EvidenceManifest:
        """Load or create the evidence manifest for a case."""
        path = self._manifest_path(case_id)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return EvidenceManifest(**data)
            except (json.JSONDecodeError, ValueError, OSError) as e:
                logger.error("Failed to load manifest for case %s: %s", case_id, e)

        return EvidenceManifest(case_id=case_id)

    def save_manifest(self, manifest: EvidenceManifest) -> bool:
        """Save the evidence manifest atomically."""
        manifest.last_updated = datetime.now().isoformat()
        manifest.check_required_types()

        path = self._manifest_path(manifest.case_id)
        tmp_path = path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(manifest.model_dump_json(indent=2))
            tmp_path.replace(path)
            return True
        except OSError as e:
            logger.error("Failed to save manifest for case %s: %s", manifest.case_id, e)
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return False

    # --- Evidence Storage ---

    def store_evidence(
        self,
        case_id: str,
        file_data: bytes,
        original_filename: str,
        content_type: str,
        photo_type: Optional[str] = None,
        photo_type_name: Optional[str] = None,
    ) -> Optional[EvidenceMetadata]:
        """
        Store an evidence file using content-addressed naming.

        Args:
            case_id: The case to attach evidence to.
            file_data: Raw file bytes.
            original_filename: Original upload filename.
            content_type: MIME type.
            photo_type: Optional photo type code (P1-P10).
            photo_type_name: Optional Chinese name of photo type.

        Returns:
            EvidenceMetadata for the stored file, or None on failure.
        """
        # Compute content hash
        sha256 = compute_sha256(file_data)

        # Determine file extension
        ext_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/heic": ".heic",
            "application/pdf": ".pdf",
        }
        ext = ext_map.get(content_type, Path(original_filename).suffix or ".bin")

        # Ensure directories exist
        evidence_dir = self._evidence_dir(case_id)
        evidence_dir.mkdir(parents=True, exist_ok=True)

        # Write evidence file (content-addressed)
        evidence_filename = f"{sha256}{ext}"
        evidence_path = evidence_dir / evidence_filename
        rel_evidence_path = f"evidence/{evidence_filename}"

        if not evidence_path.exists():
            try:
                with open(evidence_path, "wb") as f:
                    f.write(file_data)
            except OSError as e:
                logger.error("Failed to write evidence %s: %s", evidence_filename, e)
                return None
        else:
            logger.debug("Evidence already exists (dedup): %s", sha256[:16])

        # Generate evidence ID
        manifest = self.get_manifest(case_id)
        evidence_id = f"ev_{len(manifest.evidence) + 1:03d}"

        # Check for duplicate SHA in manifest
        for existing in manifest.evidence:
            if existing.sha256 == sha256:
                logger.info("Duplicate evidence skipped: %s", sha256[:16])
                return existing

        # Determine if this is a required photo type
        required_types = {"P1", "P2", "P3", "P4"}
        is_required = photo_type in required_types if photo_type else False

        # Create metadata
        metadata = EvidenceMetadata(
            evidence_id=evidence_id,
            sha256=sha256,
            original_filename=original_filename,
            content_type=content_type,
            file_size_bytes=len(file_data),
            photo_type=photo_type,
            photo_type_name=photo_type_name,
            is_required_type=is_required,
            evidence_path=rel_evidence_path,
        )

        # Add to manifest and save
        manifest.evidence.append(metadata)
        self.save_manifest(manifest)

        logger.info(
            "Stored evidence: case=%s id=%s sha=%s type=%s",
            case_id, evidence_id, sha256[:16], photo_type,
        )
        return metadata

    def store_thumbnail(
        self,
        case_id: str,
        sha256: str,
        thumbnail_data: bytes,
    ) -> Optional[str]:
        """
        Store a thumbnail image.

        Args:
            case_id: The case ID.
            sha256: SHA-256 of the original evidence.
            thumbnail_data: Thumbnail JPEG bytes.

        Returns:
            Relative path to the thumbnail, or None on failure.
        """
        thumb_dir = self._thumbnail_dir(case_id)
        thumb_dir.mkdir(parents=True, exist_ok=True)

        thumb_filename = f"{sha256}_thumb.jpg"
        thumb_path = thumb_dir / thumb_filename
        rel_path = f"thumbnails/{thumb_filename}"

        try:
            with open(thumb_path, "wb") as f:
                f.write(thumbnail_data)
            return rel_path
        except OSError as e:
            logger.error("Failed to write thumbnail: %s", e)
            return None

    def update_thumbnail_path(
        self, case_id: str, evidence_id: str, thumbnail_path: str
    ) -> bool:
        """Update the thumbnail path for an evidence item in the manifest."""
        manifest = self.get_manifest(case_id)
        for ev in manifest.evidence:
            if ev.evidence_id == evidence_id:
                ev.thumbnail_path = thumbnail_path
                return self.save_manifest(manifest)
        return False

    def update_exif(
        self,
        case_id: str,
        evidence_id: str,
        gps_lat: Optional[float] = None,
        gps_lon: Optional[float] = None,
        datetime_original: Optional[str] = None,
        camera: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> bool:
        """Update EXIF metadata for an evidence item."""
        manifest = self.get_manifest(case_id)
        for ev in manifest.evidence:
            if ev.evidence_id == evidence_id:
                if gps_lat is not None:
                    ev.exif_gps_lat = gps_lat
                if gps_lon is not None:
                    ev.exif_gps_lon = gps_lon
                if datetime_original:
                    ev.exif_datetime = datetime_original
                if camera:
                    ev.exif_camera = camera
                if width:
                    ev.width = width
                if height:
                    ev.height = height
                return self.save_manifest(manifest)
        return False

    def update_annotations(
        self,
        case_id: str,
        evidence_id: str,
        annotations_data: dict[str, Any],
    ) -> bool:
        """Update annotations for an evidence item."""
        from app.models.evidence import PhotoAnnotations

        manifest = self.get_manifest(case_id)
        for ev in manifest.evidence:
            if ev.evidence_id == evidence_id:
                ev.annotations = PhotoAnnotations(**annotations_data)
                ev.annotated_at = datetime.now().isoformat()
                return self.save_manifest(manifest)
        return False

    def get_evidence(self, case_id: str, evidence_id: str) -> Optional[EvidenceMetadata]:
        """Get metadata for a specific evidence item."""
        manifest = self.get_manifest(case_id)
        for ev in manifest.evidence:
            if ev.evidence_id == evidence_id:
                return ev
        return None

    def get_evidence_file(self, case_id: str, evidence_id: str) -> Optional[tuple[bytes, str]]:
        """
        Read evidence file bytes.

        Returns:
            Tuple of (file_data, content_type) or None.
        """
        ev = self.get_evidence(case_id, evidence_id)
        if ev is None:
            return None

        file_path = self._case_dir(case_id) / ev.evidence_path
        if not file_path.exists():
            logger.error("Evidence file missing: %s", file_path)
            return None

        try:
            with open(file_path, "rb") as f:
                data = f.read()
            return (data, ev.content_type)
        except OSError as e:
            logger.error("Failed to read evidence file: %s", e)
            return None

    def get_thumbnail_file(self, case_id: str, evidence_id: str) -> Optional[bytes]:
        """Read thumbnail bytes for an evidence item."""
        ev = self.get_evidence(case_id, evidence_id)
        if ev is None or not ev.thumbnail_path:
            return None

        thumb_path = self._case_dir(case_id) / ev.thumbnail_path
        if not thumb_path.exists():
            return None

        try:
            with open(thumb_path, "rb") as f:
                return f.read()
        except OSError as e:
            logger.error("Failed to read thumbnail: %s", e)
            return None

    def count_evidence(self, case_id: str) -> int:
        """Count total evidence items for a case."""
        manifest = self.get_manifest(case_id)
        return manifest.total_evidence
