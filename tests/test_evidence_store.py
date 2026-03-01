from __future__ import annotations

from pathlib import Path

import pytest

from app.core.security import compute_sha256
from app.models.evidence import EvidenceMetadata
from app.services.evidence_store import EvidenceStore


@pytest.fixture
def case_dir(tmp_path: Path) -> Path:
    cases_dir = tmp_path / "cases"
    case_dir = cases_dir / "case_20260228_0001"
    for sub in ["evidence", "derived", "thumbnails"]:
        (case_dir / sub).mkdir(parents=True)
    return case_dir


@pytest.fixture
def evidence_store(case_dir: Path) -> EvidenceStore:
    return EvidenceStore(cases_dir=case_dir.parent)


def _store_sample(evidence_store: EvidenceStore, photo_type: str = "P1") -> EvidenceMetadata | None:
    file_data = b"fake jpeg data for testing"
    return evidence_store.store_evidence(
        case_id="case_20260228_0001",
        file_data=file_data,
        original_filename="test.jpg",
        content_type="image/jpeg",
        photo_type=photo_type,
        photo_type_name="全景照",
    )


def test_store_evidence(evidence_store: EvidenceStore, case_dir: Path) -> None:
    file_data = b"fake jpeg data for testing"
    metadata = evidence_store.store_evidence(
        case_id="case_20260228_0001",
        file_data=file_data,
        original_filename="test.jpg",
        content_type="image/jpeg",
        photo_type="P1",
        photo_type_name="全景照",
    )

    assert metadata is not None
    expected_name = f"{compute_sha256(file_data)}.jpg"
    expected_path = case_dir / "evidence" / expected_name
    assert expected_path.exists()


def test_store_evidence_returns_metadata(evidence_store: EvidenceStore) -> None:
    metadata = _store_sample(evidence_store, photo_type="P2")

    assert metadata is not None
    assert metadata.evidence_id == "ev_001"
    assert metadata.content_type == "image/jpeg"
    assert metadata.photo_type == "P2"
    assert metadata.photo_type_name == "全景照"
    assert metadata.file_size_bytes == len(b"fake jpeg data for testing")
    assert metadata.is_required_type is True


def test_store_duplicate_evidence(evidence_store: EvidenceStore) -> None:
    first = _store_sample(evidence_store)
    second = _store_sample(evidence_store)

    assert first is not None
    assert second is not None
    assert first.evidence_id == second.evidence_id
    assert first.sha256 == second.sha256
    assert evidence_store.count_evidence("case_20260228_0001") == 1


def test_manifest_created(evidence_store: EvidenceStore, case_dir: Path) -> None:
    _ = _store_sample(evidence_store)
    manifest_path = case_dir / "evidence_manifest.json"

    assert manifest_path.exists()


def test_manifest_tracks_required_types(evidence_store: EvidenceStore) -> None:
    for photo_type in ["P1", "P2", "P3", "P4"]:
        _ = evidence_store.store_evidence(
            case_id="case_20260228_0001",
            file_data=f"{photo_type} data".encode("utf-8"),
            original_filename=f"{photo_type}.jpg",
            content_type="image/jpeg",
            photo_type=photo_type,
            photo_type_name="測試",
        )

    manifest = evidence_store.get_manifest("case_20260228_0001")
    assert manifest.required_types_present == ["P1", "P2", "P3", "P4"]
    assert manifest.required_types_missing == []


def test_store_thumbnail(evidence_store: EvidenceStore, case_dir: Path) -> None:
    metadata = _store_sample(evidence_store)
    assert metadata is not None

    thumbnail_data = b"thumbnail-bytes"
    rel_path = evidence_store.store_thumbnail(
        case_id="case_20260228_0001",
        sha256=metadata.sha256,
        thumbnail_data=thumbnail_data,
    )

    assert rel_path is not None
    thumb_path = case_dir / rel_path
    assert thumb_path.exists()
    assert thumb_path.read_bytes() == thumbnail_data


def test_update_exif(evidence_store: EvidenceStore) -> None:
    metadata = _store_sample(evidence_store)
    assert metadata is not None

    updated = evidence_store.update_exif(
        case_id="case_20260228_0001",
        evidence_id=metadata.evidence_id,
        gps_lat=24.83,
        gps_lon=121.47,
        datetime_original="2026-02-28T12:00:00",
        camera="TestCam",
        width=800,
        height=600,
    )

    assert updated is True
    loaded = evidence_store.get_evidence("case_20260228_0001", metadata.evidence_id)
    assert loaded is not None
    assert loaded.exif_gps_lat == 24.83
    assert loaded.exif_gps_lon == 121.47
    assert loaded.exif_datetime == "2026-02-28T12:00:00"
    assert loaded.exif_camera == "TestCam"
    assert loaded.width == 800
    assert loaded.height == 600


def test_get_evidence(evidence_store: EvidenceStore) -> None:
    metadata = _store_sample(evidence_store)
    assert metadata is not None

    loaded = evidence_store.get_evidence("case_20260228_0001", metadata.evidence_id)
    assert loaded is not None
    assert loaded.evidence_id == metadata.evidence_id


def test_get_evidence_file(evidence_store: EvidenceStore) -> None:
    file_data = b"fake jpeg data for testing"
    metadata = evidence_store.store_evidence(
        case_id="case_20260228_0001",
        file_data=file_data,
        original_filename="test.jpg",
        content_type="image/jpeg",
        photo_type="P1",
        photo_type_name="全景照",
    )
    assert metadata is not None

    file_result = evidence_store.get_evidence_file("case_20260228_0001", metadata.evidence_id)
    assert file_result is not None
    data, content_type = file_result
    assert data == file_data
    assert content_type == "image/jpeg"


def test_count_evidence(evidence_store: EvidenceStore) -> None:
    _ = evidence_store.store_evidence(
        case_id="case_20260228_0001",
        file_data=b"one",
        original_filename="one.jpg",
        content_type="image/jpeg",
        photo_type="P1",
        photo_type_name="全景照",
    )
    _ = evidence_store.store_evidence(
        case_id="case_20260228_0001",
        file_data=b"two",
        original_filename="two.jpg",
        content_type="image/jpeg",
        photo_type="P2",
        photo_type_name="近景照",
    )

    assert evidence_store.count_evidence("case_20260228_0001") == 2


def test_get_nonexistent_evidence(evidence_store: EvidenceStore) -> None:
    loaded = evidence_store.get_evidence("case_20260228_0001", "ev_999")
    assert loaded is None
