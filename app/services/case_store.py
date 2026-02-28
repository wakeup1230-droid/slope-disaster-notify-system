"""
Case store service.

Manages case persistence using filesystem-based JSON storage.
Each case is a folder: storage/cases/case_YYYYMMDD_NNNN/
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.core.logging_config import get_logger
from app.models.case import Case

logger = get_logger(__name__)


class CaseStore:
    """
    File-based case storage.

    Directory structure per case:
        case_YYYYMMDD_NNNN/
        ├── case.json           # Main case data
        ├── audit.jsonl         # Audit trail (managed by AuditLogger)
        ├── evidence/           # Original evidence files (SHA-256 named)
        ├── derived/            # Derived data (LRS results, parsed PDFs)
        ├── thumbnails/         # Image thumbnails
        └── evidence_manifest.json  # Evidence metadata

    Concurrency: per-case directory lock via os.mkdir (atomic on all OS).
    Atomic writes: write to .tmp then os.replace.
    """

    def __init__(self, cases_dir: Path, locks_dir: Path) -> None:
        self._cases_dir = cases_dir
        self._locks_dir = locks_dir
        self._cases_dir.mkdir(parents=True, exist_ok=True)
        self._locks_dir.mkdir(parents=True, exist_ok=True)

    # --- ID Generation ---

    def _daily_counter_path(self) -> Path:
        """Path to today's case counter file."""
        today = datetime.now().strftime("%Y%m%d")
        return self._locks_dir / f"counter_{today}.txt"

    def generate_case_id(self) -> str:
        """
        Generate a unique case ID: case_YYYYMMDD_NNNN.

        Uses a daily counter file with OS-level file locking.
        """
        today = datetime.now().strftime("%Y%m%d")
        counter_path = self._daily_counter_path()

        # Atomic increment via lock directory
        lock_path = self._locks_dir / f"id_lock_{today}"
        try:
            os.mkdir(lock_path)  # Atomic on all OS
        except FileExistsError:
            # Another process holds the lock — spin briefly
            import time
            for _ in range(50):
                time.sleep(0.01)
                try:
                    os.mkdir(lock_path)
                    break
                except FileExistsError:
                    continue
            else:
                # Force break stale lock (> 5s old)
                try:
                    lock_stat = lock_path.stat()
                    if (datetime.now().timestamp() - lock_stat.st_mtime) > 5:
                        os.rmdir(lock_path)
                        os.mkdir(lock_path)
                except OSError:
                    pass

        try:
            if counter_path.exists():
                count = int(counter_path.read_text(encoding="utf-8").strip()) + 1
            else:
                count = 1
            counter_path.write_text(str(count), encoding="utf-8")
        finally:
            try:
                os.rmdir(lock_path)
            except OSError:
                pass

        case_id = f"case_{today}_{count:04d}"
        return case_id

    # --- Case Directory ---

    def _case_dir(self, case_id: str) -> Path:
        return self._cases_dir / case_id

    def _case_json_path(self, case_id: str) -> Path:
        return self._case_dir(case_id) / "case.json"

    def _ensure_case_dirs(self, case_id: str) -> Path:
        """Create case directory structure. Returns the case directory."""
        case_dir = self._case_dir(case_id)
        for sub in ["evidence", "derived", "thumbnails"]:
            (case_dir / sub).mkdir(parents=True, exist_ok=True)
        return case_dir

    # --- CRUD ---

    def create(self, case: Case) -> bool:
        """
        Create a new case.

        Returns:
            True if successful, False if case already exists.
        """
        case_dir = self._case_dir(case.case_id)
        if case_dir.exists():
            logger.warning("Case already exists: %s", case.case_id)
            return False

        self._ensure_case_dirs(case.case_id)
        return self._write_case(case)

    def get(self, case_id: str) -> Optional[Case]:
        """
        Load a case by ID.

        Returns:
            Case object or None if not found.
        """
        path = self._case_json_path(case_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return Case(**data)
        except (json.JSONDecodeError, ValueError, OSError) as e:
            logger.error("Failed to load case %s: %s", case_id, e)
            return None

    def save(self, case: Case) -> bool:
        """
        Save/update a case.

        Uses atomic write (tmp → replace) to prevent corruption.
        """
        case.update_timestamp()
        return self._write_case(case)

    def exists(self, case_id: str) -> bool:
        """Check if a case exists."""
        return self._case_json_path(case_id).exists()

    def delete(self, case_id: str) -> bool:
        """
        Delete a case and all its files.

        WARNING: This is destructive and irreversible.
        """
        import shutil
        case_dir = self._case_dir(case_id)
        if not case_dir.exists():
            return False
        try:
            shutil.rmtree(case_dir)
            logger.info("Deleted case: %s", case_id)
            return True
        except OSError as e:
            logger.error("Failed to delete case %s: %s", case_id, e)
            return False

    # --- Queries ---

    def list_all(self) -> list[str]:
        """List all case IDs, sorted by creation date (newest first)."""
        case_ids = []
        for p in self._cases_dir.iterdir():
            if p.is_dir() and p.name.startswith("case_"):
                case_ids.append(p.name)
        return sorted(case_ids, reverse=True)

    def list_by_district(self, district_id: str) -> list[Case]:
        """List all cases for a given district."""
        cases = []
        for case_id in self.list_all():
            case = self.get(case_id)
            if case and case.district_id == district_id:
                cases.append(case)
        return cases

    def list_by_status(self, review_status: str) -> list[Case]:
        """List all cases with a given review status."""
        cases = []
        for case_id in self.list_all():
            case = self.get(case_id)
            if case and case.review_status.value == review_status:
                cases.append(case)
        return cases

    def list_by_user(self, user_id: str) -> list[Case]:
        """List all cases created by a specific user."""
        cases = []
        for case_id in self.list_all():
            case = self.get(case_id)
            if case and case.created_by and case.created_by.user_id == user_id:
                cases.append(case)
        return cases

    def list_updated_since(self, since_iso: str) -> list[Case]:
        """List all cases updated after the given ISO datetime."""
        cases = []
        for case_id in self.list_all():
            case = self.get(case_id)
            if case and case.updated_at > since_iso:
                cases.append(case)
        return cases

    def count_by_district(self) -> dict[str, int]:
        """Count cases per district."""
        counts: dict[str, int] = {}
        for case_id in self.list_all():
            case = self.get(case_id)
            if case:
                counts[case.district_id] = counts.get(case.district_id, 0) + 1
        return counts

    def count_by_status(self) -> dict[str, int]:
        """Count cases per review status."""
        counts: dict[str, int] = {}
        for case_id in self.list_all():
            case = self.get(case_id)
            if case:
                status = case.review_status.value
                counts[status] = counts.get(status, 0) + 1
        return counts

    # --- Internal ---

    def _write_case(self, case: Case) -> bool:
        """Atomic write: tmp file → os.replace."""
        path = self._case_json_path(case.case_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(case.model_dump_json(indent=2))
            tmp_path.replace(path)
            logger.debug("Saved case: %s", case.case_id)
            return True
        except OSError as e:
            logger.error("Failed to write case %s: %s", case.case_id, e)
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return False

    def get_case_dir(self, case_id: str) -> Path:
        """Get the directory path for a case (for evidence storage)."""
        return self._case_dir(case_id)
