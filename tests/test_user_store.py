from __future__ import annotations

from pathlib import Path

import pytest

from app.models.user import User, UserRole, UserStatus
from app.services.user_store import UserStore


@pytest.fixture
def user_store(tmp_path: Path) -> UserStore:
    return UserStore(users_dir=tmp_path / "users")


def test_create_user(user_store: UserStore, tmp_path: Path) -> None:
    created = user_store.create(
        user_id="U001",
        display_name="alice",
        real_name="Alice",
        district_id="jingmei",
        district_name="景美工務段",
    )

    assert created is not None
    assert isinstance(created, User)
    assert created.user_id == "U001"
    assert (tmp_path / "users" / "U001.json").exists()


def test_create_duplicate_user(user_store: UserStore) -> None:
    first = user_store.create(user_id="U001", display_name="first")
    duplicate = user_store.create(user_id="U001", display_name="second")

    assert first is not None
    assert duplicate is not None
    assert duplicate.user_id == "U001"
    assert duplicate.display_name == "first"


def test_get_user(user_store: UserStore) -> None:
    _ = user_store.create(user_id="U001", display_name="alice", real_name="Alice")

    loaded = user_store.get("U001")

    assert loaded is not None
    assert loaded.user_id == "U001"
    assert loaded.display_name == "alice"
    assert loaded.real_name == "Alice"


def test_get_nonexistent(user_store: UserStore) -> None:
    loaded = user_store.get("U404")

    assert loaded is None


def test_save_user(user_store: UserStore) -> None:
    created = user_store.create(user_id="U001", display_name="alice")
    assert created is not None

    created.real_name = "Alice Chen"
    created.district_id = "fuxing"
    saved = user_store.save(created)
    loaded = user_store.get("U001")

    assert saved is True
    assert loaded is not None
    assert loaded.real_name == "Alice Chen"
    assert loaded.district_id == "fuxing"


def test_approve_user(user_store: UserStore) -> None:
    _ = user_store.create(user_id="U001", status=UserStatus.PENDING)

    approved = user_store.approve("U001", approved_by="manager_1")
    loaded = user_store.get("U001")

    assert approved is not None
    assert approved.status == UserStatus.ACTIVE
    assert approved.approved_at is not None
    assert approved.approved_by == "manager_1"
    assert loaded is not None
    assert loaded.status == UserStatus.ACTIVE


def test_reject_user(user_store: UserStore) -> None:
    _ = user_store.create(user_id="U001", status=UserStatus.PENDING)

    rejected = user_store.reject("U001")
    loaded = user_store.get("U001")

    assert rejected is not None
    assert rejected.status == UserStatus.REJECTED
    assert loaded is not None
    assert loaded.status == UserStatus.REJECTED


def test_approve_nonexistent(user_store: UserStore) -> None:
    approved = user_store.approve("U404", approved_by="manager_1")

    assert approved is None


def test_list_pending(user_store: UserStore) -> None:
    _ = user_store.create(user_id="U001", status=UserStatus.PENDING)
    _ = user_store.create(user_id="U002", status=UserStatus.ACTIVE)
    _ = user_store.create(user_id="U003", status=UserStatus.PENDING)

    pending_users = user_store.list_pending()

    assert sorted([user.user_id for user in pending_users]) == ["U001", "U003"]


def test_list_by_district(user_store: UserStore) -> None:
    _ = user_store.create(user_id="U001", district_id="jingmei", status=UserStatus.ACTIVE)
    _ = user_store.create(user_id="U002", district_id="jingmei", status=UserStatus.PENDING)
    _ = user_store.create(user_id="U003", district_id="fuxing", status=UserStatus.ACTIVE)
    _ = user_store.create(user_id="U004", district_id="jingmei", status=UserStatus.ACTIVE)

    district_users = user_store.list_by_district("jingmei")

    assert sorted([user.user_id for user in district_users]) == ["U001", "U004"]


def test_list_managers(user_store: UserStore) -> None:
    _ = user_store.create(user_id="U001", role=UserRole.MANAGER, status=UserStatus.ACTIVE)
    _ = user_store.create(user_id="U002", role=UserRole.MANAGER, status=UserStatus.PENDING)
    _ = user_store.create(user_id="U003", role=UserRole.USER, status=UserStatus.ACTIVE)

    managers = user_store.list_managers()

    assert [user.user_id for user in managers] == ["U001"]


def test_ensure_bootstrap_admin(user_store: UserStore) -> None:
    created_admin = user_store.ensure_bootstrap_admin(line_id="ADMIN1", name="Root Admin")

    assert created_admin.user_id == "ADMIN1"
    assert created_admin.role == UserRole.MANAGER
    assert created_admin.status == UserStatus.ACTIVE

    _ = user_store.create(user_id="ADMIN2", role=UserRole.USER, status=UserStatus.PENDING)
    upgraded_admin = user_store.ensure_bootstrap_admin(line_id="ADMIN2", name="Bootstrap")
    reloaded = user_store.get("ADMIN2")

    assert upgraded_admin.user_id == "ADMIN2"
    assert upgraded_admin.role == UserRole.MANAGER
    assert upgraded_admin.status == UserStatus.ACTIVE
    assert reloaded is not None
    assert reloaded.role == UserRole.MANAGER
    assert reloaded.status == UserStatus.ACTIVE


def test_exists(user_store: UserStore) -> None:
    _ = user_store.create(user_id="U001")

    assert user_store.exists("U001") is True
    assert user_store.exists("U404") is False
