from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from app.services.audit_logger import AuditLogger


@pytest.fixture
def audit(tmp_path: Path) -> AuditLogger:
    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    return AuditLogger(cases_dir=cases_dir)


def test_log_creates_file(audit: AuditLogger, tmp_path: Path) -> None:
    case_id = "case_20260228_0001"

    _ = audit.log(case_id=case_id, action="create", actor="u1", actor_name="Alice")

    audit_path = tmp_path / "cases" / case_id / "audit.jsonl"
    assert audit_path.exists()
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_log_appends(audit: AuditLogger, tmp_path: Path) -> None:
    case_id = "case_20260228_0002"

    _ = audit.log(case_id=case_id, action="create", actor="u1")
    _ = audit.log(case_id=case_id, action="update", actor="u2")

    audit_path = tmp_path / "cases" / case_id / "audit.jsonl"
    lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = cast(dict[str, str], json.loads(lines[0]))
    second = cast(dict[str, str], json.loads(lines[1]))
    assert first["action"] == "create"
    assert second["action"] == "update"


def test_log_returns_entry(audit: AuditLogger) -> None:
    entry = audit.log(
        case_id="case_20260228_0003",
        action="status_change",
        actor="manager01",
        actor_name="Manager",
        details={"from": "pending_review", "to": "in_progress"},
    )

    assert entry.case_id == "case_20260228_0003"
    assert entry.action == "status_change"
    assert entry.actor == "manager01"
    assert entry.actor_name == "Manager"
    assert entry.details == {"from": "pending_review", "to": "in_progress"}
    assert entry.timestamp


def test_get_history(audit: AuditLogger) -> None:
    case_id = "case_20260228_0004"
    _ = audit.log(case_id=case_id, action="create", actor="u1")
    _ = audit.log(case_id=case_id, action="update", actor="u2")
    _ = audit.log(case_id=case_id, action="status_change", actor="u3")

    history = audit.get_history(case_id)

    assert len(history) == 3
    assert [entry.action for entry in history] == ["create", "update", "status_change"]


def test_get_history_empty(audit: AuditLogger) -> None:
    history = audit.get_history("case_20990101_9999")

    assert history == []


def test_get_recent(audit: AuditLogger) -> None:
    case_id = "case_20260228_0005"
    for idx in range(5):
        _ = audit.log(case_id=case_id, action=f"action_{idx}", actor=f"u{idx}")

    recent = audit.get_recent(case_id, limit=2)

    assert len(recent) == 2
    assert [entry.action for entry in recent] == ["action_3", "action_4"]


def test_corrupt_line_skipped(audit: AuditLogger, tmp_path: Path) -> None:
    case_id = "case_20260228_0006"
    _ = audit.log(case_id=case_id, action="create", actor="u1")
    audit_path = tmp_path / "cases" / case_id / "audit.jsonl"
    with open(audit_path, "a", encoding="utf-8") as f:
        _ = f.write("not-json\n")
    _ = audit.log(case_id=case_id, action="update", actor="u2")

    history = audit.get_history(case_id)

    assert len(history) == 2
    assert [entry.action for entry in history] == ["create", "update"]
