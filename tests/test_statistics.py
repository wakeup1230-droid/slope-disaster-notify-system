from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.models.case import Case, EvidenceSummary, MilepostInfo, ReviewStatus
from app.services.audit_logger import AuditLogger
from app.services.case_manager import CaseManager
from app.services.case_store import CaseStore


@pytest.fixture
def store(tmp_path: Path) -> CaseStore:
    cases_dir = tmp_path / "cases"
    locks_dir = tmp_path / "locks"
    return CaseStore(cases_dir=cases_dir, locks_dir=locks_dir)


@pytest.fixture
def manager(store: CaseStore, tmp_path: Path) -> CaseManager:
    cases_dir = tmp_path / "cases"
    audit = AuditLogger(cases_dir=cases_dir)
    return CaseManager(case_store=store, audit_logger=audit)


def _make_case(
    case_id: str,
    district_id: str = "D01",
    district_name: str = "North",
    review_status: ReviewStatus = ReviewStatus.PENDING_REVIEW,
    created_at: str | None = None,
    updated_at: str | None = None,
    road_number: str = "台7線",
    milepost: MilepostInfo | None = None,
    damage_mode_category: str = "revetment_retaining",
    damage_mode_name: str = "擋土牆破損",
    estimated_cost: float | None = 10.0,
    evidence_summary: list[EvidenceSummary] | None = None,
) -> Case:
    now = datetime.now().replace(microsecond=0)
    if milepost is None:
        milepost = MilepostInfo(
            road="台7線",
            milepost_km=10.0,
            milepost_display="10K+000",
            confidence=1.0,
            source="manual",
        )
    return Case(
        case_id=case_id,
        district_id=district_id,
        district_name=district_name,
        review_status=review_status,
        created_at=created_at or now.isoformat(),
        updated_at=updated_at or now.isoformat(),
        road_number=road_number,
        milepost=milepost,
        damage_mode_category=damage_mode_category,
        damage_mode_name=damage_mode_name,
        estimated_cost=estimated_cost,
        evidence_summary=evidence_summary or [],
    )


def test_statistics_has_all_sections(manager: CaseManager, store: CaseStore) -> None:
    case = _make_case("case_20260301_0001")
    assert store.create(case) is True

    stats = manager.get_statistics()

    assert set(stats.keys()) == {
        "total_cases",
        "today_new",
        "by_status",
        "by_district",
        "budget",
        "photo_completeness",
        "route_frequency",
        "time_trend",
        "damage_types",
        "processing_time",
    }


def test_statistics_budget(manager: CaseManager, store: CaseStore) -> None:
    closed_case = _make_case(
        "case_20260301_0001",
        review_status=ReviewStatus.CLOSED,
        estimated_cost=10.2,
    )
    pending_case = _make_case(
        "case_20260301_0002",
        review_status=ReviewStatus.PENDING_REVIEW,
        estimated_cost=5.5,
    )
    no_cost_case = _make_case(
        "case_20260301_0003",
        estimated_cost=None,
    )
    assert store.create(closed_case) is True
    assert store.create(pending_case) is True
    assert store.create(no_cost_case) is True

    budget = manager.get_statistics()["budget"]

    assert budget["total_estimated"] == 15.7
    assert budget["closed_estimated"] == 10.2
    assert budget["pending_estimated"] == 5.5
    assert budget["unfilled_count"] == 1


def test_statistics_photo_completeness(manager: CaseManager, store: CaseStore) -> None:
    complete_case = _make_case(
        "case_20260301_0001",
        evidence_summary=[
            EvidenceSummary(evidence_id="e1", sha256="a", original_filename="1.jpg", content_type="image/jpeg", photo_type="P1"),
            EvidenceSummary(evidence_id="e2", sha256="b", original_filename="2.jpg", content_type="image/jpeg", photo_type="P2"),
            EvidenceSummary(evidence_id="e3", sha256="c", original_filename="3.jpg", content_type="image/jpeg", photo_type="P3"),
            EvidenceSummary(evidence_id="e4", sha256="d", original_filename="4.jpg", content_type="image/jpeg", photo_type="P4"),
        ],
    )
    partial_case = _make_case(
        "case_20260301_0002",
        evidence_summary=[
            EvidenceSummary(evidence_id="e5", sha256="e", original_filename="5.jpg", content_type="image/jpeg", photo_type="P1"),
        ],
    )
    no_photo_case = _make_case("case_20260301_0003", evidence_summary=[])
    assert store.create(complete_case) is True
    assert store.create(partial_case) is True
    assert store.create(no_photo_case) is True

    photo = manager.get_statistics()["photo_completeness"]

    assert photo["total_cases"] == 3
    assert photo["cases_complete"] == 1
    assert photo["overall_pct"] == 33.3
    assert photo["by_photo_type"] == {"P1": 2, "P2": 1, "P3": 1, "P4": 1}


def test_statistics_route_frequency(manager: CaseManager, store: CaseStore) -> None:
    case_a = _make_case("case_20260301_0001", road_number="台7線", milepost=MilepostInfo(road="台7線", milepost_km=12.5, milepost_display="12K+500", confidence=1.0, source="manual"))
    case_b = _make_case("case_20260301_0002", road_number="台7線", milepost=MilepostInfo(road="台7線", milepost_km=10.0, milepost_display="10K+000", confidence=1.0, source="manual"))
    case_c = _make_case("case_20260301_0003", road_number="台9線", milepost=MilepostInfo(road="台9線", milepost_km=1.0, milepost_display="1K+000", confidence=1.0, source="manual"))
    case_d = _make_case("case_20260301_0004", road_number="台7線", milepost=MilepostInfo(road="台7線", milepost_km=0.0, milepost_display="0K+000", confidence=1.0, source="manual"))
    case_d.milepost = None
    assert store.create(case_a) is True
    assert store.create(case_b) is True
    assert store.create(case_c) is True
    assert store.create(case_d) is True

    route = manager.get_statistics()["route_frequency"]

    assert route[0] == {"road": "台7線", "count": 3, "mileposts": [10.0, 12.5]}
    assert route[1] == {"road": "台9線", "count": 1, "mileposts": [1.0]}


def test_statistics_damage_types(manager: CaseManager, store: CaseStore) -> None:
    case_a = _make_case(
        "case_20260301_0001",
        damage_mode_category="revetment_retaining",
        damage_mode_name="擋土牆破損",
    )
    case_b = _make_case(
        "case_20260301_0002",
        damage_mode_category="road_slope",
        damage_mode_name="路基流失",
    )
    case_c = _make_case(
        "case_20260301_0003",
        damage_mode_category="revetment_retaining",
        damage_mode_name="擋土牆破損",
    )
    assert store.create(case_a) is True
    assert store.create(case_b) is True
    assert store.create(case_c) is True

    damage = manager.get_statistics()["damage_types"]

    assert damage["by_category"] == {"revetment_retaining": 2, "road_slope": 1}
    assert damage["by_name"] == {"擋土牆破損": 2, "路基流失": 1}


def test_statistics_today_new(manager: CaseManager, store: CaseStore) -> None:
    now = datetime.now().replace(microsecond=0)
    yesterday = now - timedelta(days=1)
    today_case = _make_case("case_20260301_0001", created_at=now.isoformat())
    old_case = _make_case("case_20260301_0002", created_at=yesterday.isoformat())
    assert store.create(today_case) is True
    assert store.create(old_case) is True

    stats = manager.get_statistics()

    assert stats["today_new"] == 1


def test_statistics_time_trend(manager: CaseManager, store: CaseStore) -> None:
    case_a = _make_case("case_20260301_0001", created_at="2026-02-27T10:00:00")
    case_b = _make_case("case_20260301_0002", created_at="2026-02-27T11:00:00")
    case_c = _make_case("case_20260301_0003", created_at="2026-02-28T09:00:00")
    assert store.create(case_a) is True
    assert store.create(case_b) is True
    assert store.create(case_c) is True

    trend = manager.get_statistics()["time_trend"]

    assert trend == [
        {"date": "2026-02-27", "count": 2},
        {"date": "2026-02-28", "count": 1},
    ]


def test_statistics_processing_time(manager: CaseManager, store: CaseStore) -> None:
    closed_a = _make_case(
        "case_20260301_0001",
        review_status=ReviewStatus.CLOSED,
        district_id="D01",
        created_at="2026-02-28T00:00:00",
        updated_at="2026-02-28T10:00:00",
    )
    closed_b = _make_case(
        "case_20260301_0002",
        review_status=ReviewStatus.CLOSED,
        district_id="D02",
        created_at="2026-02-28T00:00:00",
        updated_at="2026-02-28T22:00:00",
    )
    pending = _make_case(
        "case_20260301_0003",
        review_status=ReviewStatus.PENDING_REVIEW,
        district_id="D01",
        created_at="2026-02-28T00:00:00",
        updated_at="2026-02-28T05:00:00",
    )
    assert store.create(closed_a) is True
    assert store.create(closed_b) is True
    assert store.create(pending) is True

    processing = manager.get_statistics()["processing_time"]

    assert processing["avg_hours"] == 16.0
    assert processing["total_closed"] == 2
    assert processing["by_district"] == {"D01": 10.0, "D02": 22.0}


def test_load_all_cases(store: CaseStore) -> None:
    case_a = _make_case("case_20260301_0001")
    case_b = _make_case("case_20260301_0002")
    assert store.create(case_a) is True
    assert store.create(case_b) is True

    cases = store.load_all_cases()

    assert [case.case_id for case in cases] == ["case_20260301_0002", "case_20260301_0001"]
