from __future__ import annotations

from app.models.case import Case, CoordinateCandidate, ReviewStatus
from app.routers.vendor_api import _is_webgis_visible_status, case_to_vendor_summary


def test_case_to_vendor_summary_returned_uses_district_fallback_coordinate() -> None:
    case = Case(
        case_id="case_20260303_0001",
        district_id="keelung",
        district_name="基隆工務段",
        review_status=ReviewStatus.RETURNED,
    )

    summary = case_to_vendor_summary(case, "https://example.com")

    assert summary.coordinate is not None
    assert round(summary.coordinate.lat, 4) == 25.1306
    assert round(summary.coordinate.lon, 4) == 121.7392
    assert summary.coordinate.confidence == 0.2


def test_case_to_vendor_summary_prefers_real_coordinate_over_fallback() -> None:
    case = Case(
        case_id="case_20260303_0002",
        district_id="keelung",
        district_name="基隆工務段",
        review_status=ReviewStatus.RETURNED,
        coordinate_candidates=[
            CoordinateCandidate(lat=24.1234, lon=121.5678, source="manual", confidence=1.0)
        ],
    )

    summary = case_to_vendor_summary(case, "https://example.com")

    assert summary.coordinate is not None
    assert round(summary.coordinate.lat, 4) == 24.1234
    assert round(summary.coordinate.lon, 4) == 121.5678
    assert summary.coordinate.confidence == 1.0


def test_is_webgis_visible_status_excludes_draft() -> None:
    assert _is_webgis_visible_status("pending_review") is True
    assert _is_webgis_visible_status("in_progress") is True
    assert _is_webgis_visible_status("closed") is True
    assert _is_webgis_visible_status("returned") is True
    assert _is_webgis_visible_status("draft") is False
