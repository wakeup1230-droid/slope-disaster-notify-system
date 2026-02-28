"""
Case manager service.

Orchestrates case lifecycle: creation, status transitions, completeness checks.
Enforces the dual-track status system (technical + business).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.core.logging_config import get_logger
from app.models.case import (
    Case,
    CreatedBy,
    ProcessingStage,
    ReviewStatus,
    ReviewHistoryEntry,
)
from app.services.audit_logger import AuditLogger
from app.services.case_store import CaseStore

logger = get_logger(__name__)

# Valid business status transitions
VALID_TRANSITIONS: dict[ReviewStatus, set[ReviewStatus]] = {
    ReviewStatus.PENDING_REVIEW: {ReviewStatus.IN_PROGRESS, ReviewStatus.RETURNED},
    ReviewStatus.IN_PROGRESS: {ReviewStatus.CLOSED, ReviewStatus.RETURNED},
    ReviewStatus.RETURNED: {ReviewStatus.PENDING_REVIEW},
    ReviewStatus.CLOSED: set(),  # Terminal state
}


class CaseManager:
    """
    Orchestrates case lifecycle operations.

    Responsibilities:
    - Case creation with ID generation
    - Business status transitions with validation
    - Technical stage advancement (auto)
    - Completeness calculation
    - Integration with audit logger
    """

    def __init__(self, case_store: CaseStore, audit_logger: AuditLogger) -> None:
        self._store = case_store
        self._audit = audit_logger

    def create_case(
        self,
        user_id: str,
        display_name: str = "",
        real_name: str = "",
        district_id: str = "",
        district_name: str = "",
    ) -> Optional[Case]:
        """
        Create a new disaster case.

        Returns:
            The created Case or None on failure.
        """
        case_id = self._store.generate_case_id()

        case = Case(
            case_id=case_id,
            district_id=district_id,
            district_name=district_name,
            created_by=CreatedBy(
                user_id=user_id,
                display_name=display_name,
                real_name=real_name,
                district_id=district_id,
                district_name=district_name,
            ),
        )

        if not self._store.create(case):
            logger.error("Failed to create case: %s", case_id)
            return None

        self._audit.log(
            case_id=case_id,
            action="create",
            actor=user_id,
            actor_name=real_name or display_name,
            details={"district_id": district_id},
        )

        logger.info("Case created: %s by %s", case_id, user_id)
        return case

    def update_case(self, case: Case, actor: str, actor_name: str = "", changes: Optional[dict[str, Any]] = None) -> bool:
        """
        Save case updates with audit logging.

        Args:
            case: The modified case object.
            actor: user_id making the change.
            actor_name: Display name of actor.
            changes: Description of what changed (for audit).

        Returns:
            True if successful.
        """
        case.calculate_completeness()
        success = self._store.save(case)

        if success:
            self._audit.log(
                case_id=case.case_id,
                action="update",
                actor=actor,
                actor_name=actor_name,
                details=changes or {},
            )

        return success

    def transition_review_status(
        self,
        case_id: str,
        new_status: ReviewStatus,
        actor: str,
        actor_name: str = "",
        note: str = "",
    ) -> Optional[Case]:
        """
        Transition the business review status of a case.

        Validates the transition against VALID_TRANSITIONS.

        Args:
            case_id: The case to transition.
            new_status: Target review status.
            actor: user_id performing the transition.
            actor_name: Display name.
            note: Optional note (e.g., return reason).

        Returns:
            Updated Case or None if transition is invalid.
        """
        case = self._store.get(case_id)
        if case is None:
            logger.warning("Case not found for transition: %s", case_id)
            return None

        current = case.review_status
        valid_targets = VALID_TRANSITIONS.get(current, set())

        if new_status not in valid_targets:
            logger.warning(
                "Invalid transition: %s → %s for case %s",
                current.value, new_status.value, case_id,
            )
            return None

        # Record history
        entry = ReviewHistoryEntry(
            from_status=current.value,
            to_status=new_status.value,
            actor=actor,
            actor_name=actor_name,
            note=note,
        )
        case.review_history.append(entry)
        case.review_status = new_status

        # Special handling
        if new_status == ReviewStatus.RETURNED:
            case.return_reason = note

        # Save
        if not self._store.save(case):
            return None

        self._audit.log(
            case_id=case_id,
            action="status_change",
            actor=actor,
            actor_name=actor_name,
            details={
                "from": current.value,
                "to": new_status.value,
                "note": note,
            },
        )

        logger.info(
            "Status transition: case=%s %s→%s by %s",
            case_id, current.value, new_status.value, actor,
        )
        return case

    def advance_processing_stage(self, case_id: str, new_stage: ProcessingStage) -> Optional[Case]:
        """
        Advance the technical processing stage.

        This is called automatically by the system, not by users.
        Stages must advance in order: ingested → photos_processed → milepost_resolved → complete.

        Returns:
            Updated Case or None if advancement is invalid.
        """
        stage_order = [
            ProcessingStage.INGESTED,
            ProcessingStage.PHOTOS_PROCESSED,
            ProcessingStage.MILEPOST_RESOLVED,
            ProcessingStage.COMPLETE,
        ]

        case = self._store.get(case_id)
        if case is None:
            return None

        current_idx = stage_order.index(case.processing_stage)
        new_idx = stage_order.index(new_stage)

        if new_idx <= current_idx:
            logger.warning(
                "Cannot go backward: %s → %s for case %s",
                case.processing_stage.value, new_stage.value, case_id,
            )
            return None

        case.processing_stage = new_stage
        if not self._store.save(case):
            return None

        self._audit.log(
            case_id=case_id,
            action="stage_advance",
            actor="system",
            details={
                "from": stage_order[current_idx].value,
                "to": new_stage.value,
            },
        )

        logger.info("Stage advanced: case=%s → %s", case_id, new_stage.value)
        return case

    def add_manager_note(
        self,
        case_id: str,
        note: str,
        actor: str,
        actor_name: str = "",
    ) -> Optional[Case]:
        """Add a manager note to a case."""
        case = self._store.get(case_id)
        if case is None:
            return None

        case.manager_notes.append(f"[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {actor_name}: {note}")

        if not self._store.save(case):
            return None

        self._audit.log(
            case_id=case_id,
            action="manager_note",
            actor=actor,
            actor_name=actor_name,
            details={"note": note},
        )

        return case

    def get_case(self, case_id: str) -> Optional[Case]:
        """Get a case by ID."""
        return self._store.get(case_id)

    def get_pending_cases(self) -> list[Case]:
        """Get all cases pending review."""
        return self._store.list_by_status(ReviewStatus.PENDING_REVIEW.value)

    def get_cases_by_district(self, district_id: str) -> list[Case]:
        """Get all cases for a district."""
        return self._store.list_by_district(district_id)

    def get_cases_by_user(self, user_id: str) -> list[Case]:
        """Get all cases created by a user."""
        return self._store.list_by_user(user_id)

    def get_statistics(self) -> dict[str, Any]:
        """Get system-wide case statistics."""
        by_status = self._store.count_by_status()
        by_district = self._store.count_by_district()
        total = sum(by_status.values())

        return {
            "total_cases": total,
            "by_status": by_status,
            "by_district": by_district,
        }
