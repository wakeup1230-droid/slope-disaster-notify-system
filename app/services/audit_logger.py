"""
Audit logger service.

Provides append-only audit trail for case operations.
Each case has an audit.jsonl file with one JSON object per line.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.core.logging_config import get_logger
from app.models.case import AuditEntry

logger = get_logger(__name__)


class AuditLogger:
    """
    Append-only audit logger for case operations.

    Writes to {case_dir}/audit.jsonl — one JSON line per action.
    Thread-safe via append mode (OS-level atomic for single lines < PIPE_BUF).
    """

    def __init__(self, cases_dir: Path) -> None:
        self._cases_dir = cases_dir

    def _audit_path(self, case_id: str) -> Path:
        return self._cases_dir / case_id / "audit.jsonl"

    def log(
        self,
        case_id: str,
        action: str,
        actor: str,
        actor_name: str = "",
        details: Optional[dict[str, Any]] = None,
    ) -> AuditEntry:
        """
        Append an audit entry to the case's audit log.

        Args:
            case_id: The case identifier.
            action: Action type (create, update, status_change, evidence_add, etc.).
            actor: user_id of the person performing the action.
            actor_name: Display name of the actor.
            details: Additional details about the action.

        Returns:
            The created AuditEntry.
        """
        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            action=action,
            actor=actor,
            actor_name=actor_name,
            details=details or {},
            case_id=case_id,
        )

        audit_path = self._audit_path(case_id)
        audit_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(audit_path, "a", encoding="utf-8") as f:
                f.write(entry.model_dump_json() + "\n")
            logger.debug("Audit: case=%s action=%s actor=%s", case_id, action, actor)
        except OSError as e:
            logger.error("Failed to write audit log for case %s: %s", case_id, e)

        return entry

    def get_history(self, case_id: str) -> list[AuditEntry]:
        """
        Read the complete audit history for a case.

        Returns:
            List of AuditEntry objects in chronological order.
        """
        audit_path = self._audit_path(case_id)
        if not audit_path.exists():
            return []

        entries = []
        try:
            with open(audit_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entries.append(AuditEntry(**data))
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.warning(
                            "Corrupt audit line %d in case %s: %s",
                            line_num, case_id, e,
                        )
        except OSError as e:
            logger.error("Failed to read audit log for case %s: %s", case_id, e)

        return entries

    def get_recent(self, case_id: str, limit: int = 10) -> list[AuditEntry]:
        """Get the most recent N audit entries for a case."""
        history = self.get_history(case_id)
        return history[-limit:] if len(history) > limit else history
