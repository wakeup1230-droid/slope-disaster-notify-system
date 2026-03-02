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
    ReviewStatus.DRAFT: {ReviewStatus.PENDING_REVIEW},
    ReviewStatus.PENDING_REVIEW: {ReviewStatus.IN_PROGRESS, ReviewStatus.RETURNED},
    ReviewStatus.IN_PROGRESS: {ReviewStatus.CLOSED, ReviewStatus.RETURNED},
    ReviewStatus.RETURNED: {ReviewStatus.PENDING_REVIEW},
    ReviewStatus.CLOSED: set(),  # Terminal state
}

VISIBLE_DASHBOARD_STATUSES: set[ReviewStatus] = {
    ReviewStatus.PENDING_REVIEW,
    ReviewStatus.IN_PROGRESS,
    ReviewStatus.CLOSED,
    ReviewStatus.RETURNED,
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

        case.calculate_completeness()

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

    def delete_case(
        self,
        case_id: str,
        actor: str,
        actor_name: str = "",
    ) -> bool:
        """
        Delete a case permanently.

        Logs an audit entry before deletion so we keep a record.

        Returns:
            True if deleted successfully, False otherwise.
        """
        case = self._store.get(case_id)
        if case is None:
            logger.warning("Case not found for deletion: %s", case_id)
            return False

        # Audit BEFORE deletion (directory will be removed)
        self._audit.log(
            case_id=case_id,
            action="delete",
            actor=actor,
            actor_name=actor_name,
            details={
                "district_id": case.district_id,
                "district_name": case.district_name,
                "road_number": case.road_number or "",
                "review_status": case.review_status.value,
            },
        )

        if not self._store.delete(case_id):
            logger.error("Failed to delete case: %s", case_id)
            return False

        logger.info("Case deleted: %s by %s", case_id, actor)
        return True

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
        """Get system-wide case statistics for dashboard aggregation."""
        all_cases = self._store.load_all_cases()
        # Dashboard/WebGIS unified counting scope.
        # Draft cases are form drafts and should not be included.
        cases = [case for case in all_cases if case.review_status in VISIBLE_DASHBOARD_STATUSES]
        today_str = datetime.now().strftime("%Y-%m-%d")

        by_status: dict[str, int] = {}
        by_district: dict[str, int] = {}

        budget_total = 0.0
        budget_closed = 0.0
        budget_pending = 0.0
        budget_unfilled = 0

        photo_type_counts: dict[str, int] = {"P1": 0, "P2": 0, "P3": 0, "P4": 0}
        cases_complete = 0

        route_data: dict[str, dict[str, Any]] = {}
        time_trend_counts: dict[str, int] = {}
        damage_by_category: dict[str, int] = {}
        damage_by_name: dict[str, int] = {}

        closed_hours: list[float] = []
        closed_hours_by_district: dict[str, list[float]] = {}
        today_new = 0

        for case in cases:
            status = case.review_status.value
            by_status[status] = by_status.get(status, 0) + 1

            district = case.district_id
            by_district[district] = by_district.get(district, 0) + 1

            if case.created_at.startswith(today_str):
                today_new += 1

            created_date = case.created_at[:10]
            time_trend_counts[created_date] = time_trend_counts.get(created_date, 0) + 1

            if case.estimated_cost is None:
                budget_unfilled += 1
            else:
                budget_total += case.estimated_cost
                if case.review_status == ReviewStatus.CLOSED:
                    budget_closed += case.estimated_cost
                else:
                    budget_pending += case.estimated_cost

            present_photo_types: set[str] = set()
            for evidence in case.evidence_summary:
                photo_type = evidence.photo_type
                if photo_type in photo_type_counts:
                    photo_type_counts[photo_type] += 1
                    present_photo_types.add(photo_type)
            if len(present_photo_types) == 4:
                cases_complete += 1

            if case.road_number:
                if case.road_number not in route_data:
                    route_data[case.road_number] = {
                        "road": case.road_number,
                        "count": 0,
                        "mileposts": [],
                    }
                route_data[case.road_number]["count"] += 1
                if case.milepost is not None:
                    route_data[case.road_number]["mileposts"].append(case.milepost.milepost_km)

            if case.damage_mode_category:
                category = case.damage_mode_category
                damage_by_category[category] = damage_by_category.get(category, 0) + 1
            if case.damage_mode_name:
                name = case.damage_mode_name
                damage_by_name[name] = damage_by_name.get(name, 0) + 1

            if case.review_status == ReviewStatus.CLOSED:
                try:
                    created_at = datetime.fromisoformat(case.created_at)
                    updated_at = datetime.fromisoformat(case.updated_at)
                    hours = (updated_at - created_at).total_seconds() / 3600
                except ValueError:
                    continue

                closed_hours.append(hours)
                if district not in closed_hours_by_district:
                    closed_hours_by_district[district] = []
                closed_hours_by_district[district].append(hours)

        total_cases = len(cases)
        photo_overall_pct = round((cases_complete / total_cases) * 100, 1) if total_cases > 0 else 0.0

        route_frequency: list[dict[str, Any]] = []
        for route in route_data.values():
            route["mileposts"] = sorted(route["mileposts"])
            route_frequency.append(route)
        route_frequency.sort(key=lambda item: (-item["count"], item["road"]))

        time_trend = [
            {"date": date_str, "count": count}
            for date_str, count in sorted(time_trend_counts.items())
        ]

        district_avg_hours = {
            district_id: round(sum(hours_list) / len(hours_list), 1)
            for district_id, hours_list in closed_hours_by_district.items()
            if hours_list
        }
        avg_hours = round(sum(closed_hours) / len(closed_hours), 1) if closed_hours else 0.0

        return {
            "total_cases": total_cases,
            "today_new": today_new,
            "by_status": by_status,
            "by_district": by_district,
            "budget": {
                "total_estimated": round(budget_total, 1),
                "closed_estimated": round(budget_closed, 1),
                "pending_estimated": round(budget_pending, 1),
                "unfilled_count": budget_unfilled,
            },
            "photo_completeness": {
                "total_cases": total_cases,
                "cases_complete": cases_complete,
                "overall_pct": photo_overall_pct,
                "by_photo_type": photo_type_counts,
            },
            "route_frequency": route_frequency,
            "time_trend": time_trend,
            "damage_types": {
                "by_category": damage_by_category,
                "by_name": damage_by_name,
            },
            "processing_time": {
                "avg_hours": avg_hours,
                "total_closed": len(closed_hours),
                "by_district": district_avg_hours,
            },
        }
