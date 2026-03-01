from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.models.case import Case, ProcessingStage, ReviewStatus
from app.services.audit_logger import AuditLogger
from app.services.case_manager import CaseManager, VALID_TRANSITIONS
from app.services.case_store import CaseStore


@pytest.fixture
def cases_dir(tmp_path: Path) -> Path:
    return tmp_path / "cases"


@pytest.fixture
def manager(tmp_path: Path, cases_dir: Path) -> CaseManager:
    locks_dir = tmp_path / "locks"
    store = CaseStore(cases_dir=cases_dir, locks_dir=locks_dir)
    audit = AuditLogger(cases_dir=cases_dir)
    return CaseManager(case_store=store, audit_logger=audit)


def _create_case(manager: CaseManager, user_id: str = "u1", name: str = "Manager") -> Case:
    case = manager.create_case(user_id=user_id, display_name=name, real_name=name)
    assert case is not None
    return case


def test_create_case(manager: CaseManager, cases_dir: Path) -> None:
    case = manager.create_case(user_id="u1", display_name="Amy", real_name="Amy Chen")

    assert case is not None
    assert isinstance(case, Case)
    assert re.fullmatch(r"case_\d{8}_\d{4}", case.case_id)

    history = AuditLogger(cases_dir=cases_dir).get_history(case.case_id)
    assert len(history) == 1
    assert history[0].action == "create"
    assert history[0].actor == "u1"


def test_create_case_with_district(manager: CaseManager) -> None:
    case = manager.create_case(
        user_id="u2",
        display_name="Bob",
        real_name="Bob Lin",
        district_id="D01",
        district_name="North District",
    )

    assert case is not None
    assert case.district_id == "D01"
    assert case.district_name == "North District"
    assert case.created_by is not None
    assert case.created_by.district_id == "D01"
    assert case.created_by.district_name == "North District"


def test_update_case(manager: CaseManager, cases_dir: Path) -> None:
    case = _create_case(manager)
    case.description = "Updated incident details"
    case.road_number = "台7線"

    result = manager.update_case(case, actor="u1", actor_name="Manager", changes={"description": "updated"})

    assert result is True
    saved = manager.get_case(case.case_id)
    assert saved is not None
    assert saved.description == "Updated incident details"

    history = AuditLogger(cases_dir=cases_dir).get_history(case.case_id)
    assert [entry.action for entry in history] == ["create", "update"]


def test_transition_pending_to_in_progress(manager: CaseManager) -> None:
    case = _create_case(manager)

    updated = manager.transition_review_status(
        case_id=case.case_id,
        new_status=ReviewStatus.IN_PROGRESS,
        actor="u1",
        actor_name="Manager",
    )

    assert updated is not None
    assert updated.review_status == ReviewStatus.IN_PROGRESS


def test_transition_pending_to_returned(manager: CaseManager) -> None:
    case = _create_case(manager)

    updated = manager.transition_review_status(
        case_id=case.case_id,
        new_status=ReviewStatus.RETURNED,
        actor="u1",
        actor_name="Manager",
        note="Missing photos",
    )

    assert updated is not None
    assert updated.review_status == ReviewStatus.RETURNED


def test_transition_in_progress_to_closed(manager: CaseManager) -> None:
    case = _create_case(manager)
    to_progress = manager.transition_review_status(case.case_id, ReviewStatus.IN_PROGRESS, actor="u1")
    assert to_progress is not None

    closed = manager.transition_review_status(case.case_id, ReviewStatus.CLOSED, actor="u1")

    assert closed is not None
    assert closed.review_status == ReviewStatus.CLOSED


def test_transition_closed_is_terminal(manager: CaseManager) -> None:
    case = _create_case(manager)
    assert manager.transition_review_status(case.case_id, ReviewStatus.IN_PROGRESS, actor="u1") is not None
    assert manager.transition_review_status(case.case_id, ReviewStatus.CLOSED, actor="u1") is not None

    blocked = manager.transition_review_status(case.case_id, ReviewStatus.RETURNED, actor="u1")

    assert blocked is None
    assert VALID_TRANSITIONS[ReviewStatus.CLOSED] == set()


def test_transition_invalid(manager: CaseManager) -> None:
    case = _create_case(manager)

    blocked = manager.transition_review_status(case.case_id, ReviewStatus.CLOSED, actor="u1")

    assert blocked is None


def test_transition_nonexistent_case(manager: CaseManager) -> None:
    result = manager.transition_review_status("case_20990101_9999", ReviewStatus.IN_PROGRESS, actor="u1")

    assert result is None


def test_transition_records_history(manager: CaseManager) -> None:
    case = _create_case(manager)

    step1 = manager.transition_review_status(case.case_id, ReviewStatus.IN_PROGRESS, actor="u1", note="Start")
    assert step1 is not None
    step2 = manager.transition_review_status(case.case_id, ReviewStatus.RETURNED, actor="u1", note="Need correction")

    assert step2 is not None
    assert len(step2.review_history) == 2
    assert step2.review_history[0].from_status == ReviewStatus.PENDING_REVIEW.value
    assert step2.review_history[0].to_status == ReviewStatus.IN_PROGRESS.value
    assert step2.review_history[1].from_status == ReviewStatus.IN_PROGRESS.value
    assert step2.review_history[1].to_status == ReviewStatus.RETURNED.value


def test_transition_returned_sets_reason(manager: CaseManager) -> None:
    case = _create_case(manager)

    updated = manager.transition_review_status(
        case.case_id,
        ReviewStatus.RETURNED,
        actor="u1",
        note="Need clearer description",
    )

    assert updated is not None
    assert updated.return_reason == "Need clearer description"


def test_advance_processing_stage_forward(manager: CaseManager) -> None:
    case = _create_case(manager)

    updated = manager.advance_processing_stage(case.case_id, ProcessingStage.PHOTOS_PROCESSED)

    assert updated is not None
    assert updated.processing_stage == ProcessingStage.PHOTOS_PROCESSED


def test_advance_processing_stage_backward(manager: CaseManager) -> None:
    case = _create_case(manager)
    assert manager.advance_processing_stage(case.case_id, ProcessingStage.PHOTOS_PROCESSED) is not None

    blocked = manager.advance_processing_stage(case.case_id, ProcessingStage.INGESTED)

    assert blocked is None


def test_advance_processing_stage_skip(manager: CaseManager) -> None:
    case = _create_case(manager)

    updated = manager.advance_processing_stage(case.case_id, ProcessingStage.COMPLETE)

    assert updated is not None
    assert updated.processing_stage == ProcessingStage.COMPLETE


def test_add_manager_note(manager: CaseManager) -> None:
    case = _create_case(manager)

    updated = manager.add_manager_note(
        case_id=case.case_id,
        note="Please verify road number",
        actor="u9",
        actor_name="Chief",
    )

    assert updated is not None
    assert len(updated.manager_notes) == 1
    assert re.match(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}\] Chief: Please verify road number$", updated.manager_notes[0])


def test_get_statistics(manager: CaseManager) -> None:
    case1 = manager.create_case(user_id="u1", district_id="D01", district_name="North")
    case2 = manager.create_case(user_id="u2", district_id="D02", district_name="South")
    case3 = manager.create_case(user_id="u3", district_id="D01", district_name="North")
    assert case1 is not None and case2 is not None and case3 is not None

    assert manager.transition_review_status(case2.case_id, ReviewStatus.IN_PROGRESS, actor="u2") is not None
    assert manager.transition_review_status(case3.case_id, ReviewStatus.RETURNED, actor="u3", note="Fix fields") is not None

    stats = manager.get_statistics()

    assert stats["total_cases"] == 3
    assert stats["by_status"][ReviewStatus.PENDING_REVIEW.value] == 1
    assert stats["by_status"][ReviewStatus.IN_PROGRESS.value] == 1
    assert stats["by_status"][ReviewStatus.RETURNED.value] == 1
    assert stats["by_district"]["D01"] == 2
    assert stats["by_district"]["D02"] == 1
