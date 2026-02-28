# pyright: basic
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from app.core.logging_config import get_logger
from app.models.line_state import LineSession


logger = get_logger(__name__)


class LineSessionStore:
    """File-based LINE session persistence with atomic writes."""

    def __init__(self, sessions_dir: Path) -> None:
        self._sessions_dir = sessions_dir
        self._sessions_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, source_key: str) -> Path:
        return self._sessions_dir / f"{source_key}.json"

    def get(self, source_key: str) -> LineSession:
        path = self._session_path(source_key)
        if not path.exists():
            return LineSession(source_key=source_key, user_id=source_key)

        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return LineSession(**data)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Session decode failed, reset session: %s (%s)", source_key, exc)
            return LineSession(source_key=source_key, user_id=source_key)
        except OSError as exc:
            logger.error("Session read failed: %s (%s)", source_key, exc)
            return LineSession(source_key=source_key, user_id=source_key)

    def save(self, session: LineSession) -> bool:
        path = self._session_path(session.source_key)
        tmp_path = path.with_suffix(".tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as file:
                file.write(session.model_dump_json(indent=2))
            os.replace(tmp_path, path)
            return True
        except OSError as exc:
            logger.error("Session save failed: %s (%s)", session.source_key, exc)
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return False

    def delete(self, source_key: str) -> bool:
        path = self._session_path(source_key)
        if not path.exists():
            return False
        try:
            path.unlink()
            return True
        except OSError as exc:
            logger.error("Session delete failed: %s (%s)", source_key, exc)
            return False

    def cleanup_expired(self, timeout_minutes: int = 60) -> int:
        now = datetime.now()
        cutoff = now - timedelta(minutes=timeout_minutes)
        deleted = 0

        for session_file in self._sessions_dir.glob("*.json"):
            source_key = session_file.stem
            try:
                with open(session_file, "r", encoding="utf-8") as file:
                    payload = json.load(file)
                updated_at = payload.get("updated_at") or payload.get("last_message_at")
                if not updated_at:
                    continue

                timestamp = datetime.fromisoformat(updated_at)
                if timestamp < cutoff:
                    session_file.unlink(missing_ok=True)
                    deleted += 1
            except json.JSONDecodeError:
                logger.warning("Invalid session JSON removed: %s", source_key)
                try:
                    session_file.unlink(missing_ok=True)
                    deleted += 1
                except OSError as exc:
                    logger.error("Failed removing invalid session %s: %s", source_key, exc)
            except (OSError, ValueError) as exc:
                logger.error("Session cleanup failed: %s (%s)", source_key, exc)

        if deleted > 0:
            logger.info("Expired sessions cleaned: %d", deleted)
        return deleted
