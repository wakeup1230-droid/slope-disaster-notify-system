from __future__ import annotations

import re
import time
from pathlib import Path

import pytest

from app.models.case import Case, ReviewStatus
from app.services.case_store import CaseStore


@pytest.fixture
def case_store(tmp_path: Path) -> CaseStore:
    return CaseStore(cases_dir=tmp_path / "cases", locks_dir=tmp_path / "locks")


def _make_case(
    case_id: str,
    district_id: str = "jingmei",
    district_name: str = "景美工務段",
    review_status: ReviewStatus = ReviewStatus.PENDING_REVIEW,
) -> Case:
    return Case(
        case_id=case_id,
        district_id=district_id,
        district_name=district_name,
        review_status=review_status,
    )


def test_generate_case_id_format(case_store: CaseStore) -> None:
    case_id = case_store.generate_case_id()

    assert re.match(r"^case_\d{8}_\d{4}$", case_id)


def test_generate_case_id_sequential(case_store: CaseStore) -> None:
    first = case_store.generate_case_id()
    second = case_store.generate_case_id()
    third = case_store.generate_case_id()

    assert first.endswith("_0001")
    assert second.endswith("_0002")
    assert third.endswith("_0003")


def test_create_case(case_store: CaseStore) -> None:
    case = _make_case("case_20260228_0001")

    created = case_store.create(case)

    case_dir = case_store.get_case_dir(case.case_id)
    assert created is True
    assert case_dir.exists()
    assert (case_dir / "case.json").exists()
    assert (case_dir / "evidence").is_dir()
    assert (case_dir / "derived").is_dir()
    assert (case_dir / "thumbnails").is_dir()


def test_create_duplicate_case(case_store: CaseStore) -> None:
    case = _make_case("case_20260228_0001")

    first_created = case_store.create(case)
    second_created = case_store.create(case)

    assert first_created is True
    assert second_created is False


def test_get_case(case_store: CaseStore) -> None:
    case = _make_case(
        "case_20260228_0001",
        district_id="fuxing",
        district_name="復興工務段",
    )
    _ = case_store.create(case)

    loaded = case_store.get(case.case_id)

    assert loaded is not None
    assert loaded.case_id == case.case_id
    assert loaded.district_id == "fuxing"
    assert loaded.district_name == "復興工務段"
    assert loaded.review_status == ReviewStatus.PENDING_REVIEW


def test_get_nonexistent_case(case_store: CaseStore) -> None:
    loaded = case_store.get("case_20260228_9999")

    assert loaded is None


def test_save_case_atomic(case_store: CaseStore) -> None:
    case = _make_case("case_20260228_0001")
    _ = case_store.create(case)
    before = case_store.get(case.case_id)
    assert before is not None
    original_updated_at = before.updated_at

    time.sleep(0.01)
    before.district_name = "更新後工務段"
    saved = case_store.save(before)
    after = case_store.get(case.case_id)

    assert saved is True
    assert after is not None
    assert after.district_name == "更新後工務段"
    assert after.updated_at != original_updated_at


def test_delete_case(case_store: CaseStore) -> None:
    case = _make_case("case_20260228_0001")
    _ = case_store.create(case)
    case_dir = case_store.get_case_dir(case.case_id)
    _ = (case_dir / "derived" / "artifact.txt").write_text("data", encoding="utf-8")

    deleted = case_store.delete(case.case_id)

    assert deleted is True
    assert not case_dir.exists()


def test_delete_nonexistent(case_store: CaseStore) -> None:
    deleted = case_store.delete("case_20260228_9999")

    assert deleted is False


def test_list_all(case_store: CaseStore) -> None:
    ids = ["case_20260228_0001", "case_20260228_0003", "case_20260228_0002"]
    for case_id in ids:
        _ = case_store.create(_make_case(case_id))

    listed = case_store.list_all()

    assert listed == ["case_20260228_0003", "case_20260228_0002", "case_20260228_0001"]


def test_list_by_district(case_store: CaseStore) -> None:
    _ = case_store.create(_make_case("case_20260228_0001", district_id="jingmei"))
    _ = case_store.create(_make_case("case_20260228_0002", district_id="fuxing"))
    _ = case_store.create(_make_case("case_20260228_0003", district_id="jingmei"))

    listed = case_store.list_by_district("jingmei")

    assert [case.case_id for case in listed] == ["case_20260228_0003", "case_20260228_0001"]


def test_list_by_status(case_store: CaseStore) -> None:
    _ = case_store.create(_make_case("case_20260228_0001", review_status=ReviewStatus.PENDING_REVIEW))
    _ = case_store.create(_make_case("case_20260228_0002", review_status=ReviewStatus.IN_PROGRESS))
    _ = case_store.create(_make_case("case_20260228_0003", review_status=ReviewStatus.IN_PROGRESS))

    listed = case_store.list_by_status(ReviewStatus.IN_PROGRESS.value)

    assert [case.case_id for case in listed] == ["case_20260228_0003", "case_20260228_0002"]


def test_exists(case_store: CaseStore) -> None:
    case = _make_case("case_20260228_0001")
    _ = case_store.create(case)

    assert case_store.exists(case.case_id) is True
    assert case_store.exists("case_20260228_9999") is False
