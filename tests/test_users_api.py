"""Tests for admin token and user management API."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.security import generate_admin_token, verify_admin_token
from app.models.user import User, UserRole, UserStatus
from app.services.user_store import UserStore


# ══════════════════════════════════════════════════
# Token Generation / Verification
# ══════════════════════════════════════════════════

SECRET = "test_channel_secret_key_for_hmac"


class TestAdminToken:
    def test_generate_returns_string(self) -> None:
        token = generate_admin_token("U001", SECRET)
        assert isinstance(token, str)
        assert "." in token

    def test_verify_valid_token(self) -> None:
        token = generate_admin_token("U001", SECRET)
        uid = verify_admin_token(token, SECRET)
        assert uid == "U001"

    def test_verify_expired_token(self) -> None:
        token = generate_admin_token("U001", SECRET, expires_in=-1)
        uid = verify_admin_token(token, SECRET)
        assert uid is None

    def test_verify_wrong_secret(self) -> None:
        token = generate_admin_token("U001", SECRET)
        uid = verify_admin_token(token, "wrong_secret")
        assert uid is None

    def test_verify_tampered_token(self) -> None:
        token = generate_admin_token("U001", SECRET)
        parts = token.rsplit(".", 1)
        tampered = parts[0] + ".0000000000000000000000000000000000000000000000000000000000000000"
        uid = verify_admin_token(tampered, SECRET)
        assert uid is None

    def test_verify_empty_token(self) -> None:
        assert verify_admin_token("", SECRET) is None

    def test_verify_no_dot_token(self) -> None:
        assert verify_admin_token("nodottoken", SECRET) is None

    def test_verify_none_like(self) -> None:
        assert verify_admin_token(None, SECRET) is None  # type: ignore[arg-type]

    def test_verify_garbage(self) -> None:
        assert verify_admin_token("abc.def.ghi", SECRET) is None

    def test_different_users_different_tokens(self) -> None:
        t1 = generate_admin_token("U001", SECRET)
        t2 = generate_admin_token("U002", SECRET)
        assert t1 != t2

    def test_token_preserves_user_id(self) -> None:
        long_uid = "Ua97d88b2ee0ee7dfddee9a16cda04d1a"
        token = generate_admin_token(long_uid, SECRET)
        uid = verify_admin_token(token, SECRET)
        assert uid == long_uid


# ══════════════════════════════════════════════════
# UserStore New Methods
# ══════════════════════════════════════════════════

@pytest.fixture
def user_store(tmp_path: Path) -> UserStore:
    return UserStore(users_dir=tmp_path / "users")


class TestUserStoreSuspend:
    def test_suspend_active_user(self, user_store: UserStore) -> None:
        user_store.create(user_id="U001", status=UserStatus.ACTIVE)
        result = user_store.suspend("U001")
        assert result is not None
        assert result.status == UserStatus.SUSPENDED
        loaded = user_store.get("U001")
        assert loaded is not None
        assert loaded.status == UserStatus.SUSPENDED

    def test_suspend_nonexistent(self, user_store: UserStore) -> None:
        result = user_store.suspend("U404")
        assert result is None


class TestUserStoreDeleteUser:
    def test_delete_existing_user(self, user_store: UserStore) -> None:
        user_store.create(user_id="U001")
        assert user_store.exists("U001")
        deleted = user_store.delete_user("U001")
        assert deleted is True
        assert not user_store.exists("U001")
        assert user_store.get("U001") is None

    def test_delete_nonexistent(self, user_store: UserStore) -> None:
        deleted = user_store.delete_user("U404")
        assert deleted is False


class TestUserStoreUpdateRole:
    def test_update_role_to_manager(self, user_store: UserStore) -> None:
        user_store.create(user_id="U001", role=UserRole.USER, status=UserStatus.ACTIVE)
        result = user_store.update_role("U001", UserRole.MANAGER)
        assert result is not None
        assert result.role == UserRole.MANAGER
        # Should NOT trigger re-approval
        assert result.status == UserStatus.ACTIVE

    def test_update_role_to_user(self, user_store: UserStore) -> None:
        user_store.create(user_id="U001", role=UserRole.MANAGER, status=UserStatus.ACTIVE)
        result = user_store.update_role("U001", UserRole.USER)
        assert result is not None
        assert result.role == UserRole.USER

    def test_update_role_nonexistent(self, user_store: UserStore) -> None:
        result = user_store.update_role("U404", UserRole.MANAGER)
        assert result is None


class TestUserStoreUpdateDistrict:
    def test_update_district(self, user_store: UserStore) -> None:
        user_store.create(
            user_id="U001",
            district_id="jingmei",
            district_name="景美工務段",
            status=UserStatus.ACTIVE,
        )
        result = user_store.update_district("U001", "fuxing", "復興工務段")
        assert result is not None
        assert result.district_id == "fuxing"
        assert result.district_name == "復興工務段"
        # Should NOT trigger re-approval
        assert result.status == UserStatus.ACTIVE

    def test_update_district_nonexistent(self, user_store: UserStore) -> None:
        result = user_store.update_district("U404", "fuxing", "復興工務段")
        assert result is None


class TestUserStoreRestore:
    def test_restore_suspended_user(self, user_store: UserStore) -> None:
        user_store.create(user_id="U001", status=UserStatus.ACTIVE)
        user_store.suspend("U001")
        result = user_store.restore("U001")
        assert result is not None
        assert result.status == UserStatus.ACTIVE

    def test_restore_non_suspended(self, user_store: UserStore) -> None:
        user_store.create(user_id="U001", status=UserStatus.ACTIVE)
        result = user_store.restore("U001")
        assert result is None  # Cannot restore a non-suspended user

    def test_restore_nonexistent(self, user_store: UserStore) -> None:
        result = user_store.restore("U404")
        assert result is None


# ══════════════════════════════════════════════════
# User Model suspend()
# ══════════════════════════════════════════════════

class TestUserSuspend:
    def test_suspend_sets_status(self) -> None:
        user = User(user_id="U001", status=UserStatus.ACTIVE)
        user.suspend()
        assert user.status == UserStatus.SUSPENDED

    def test_suspend_from_pending(self) -> None:
        user = User(user_id="U001", status=UserStatus.PENDING)
        user.suspend()
        assert user.status == UserStatus.SUSPENDED


# ══════════════════════════════════════════════════
# API Endpoints (via TestClient)
# ══════════════════════════════════════════════════

@pytest.fixture
def app_with_users(tmp_path: Path):
    """Create a minimal FastAPI test app with users router + user store."""
    import os
    os.environ["LINE_CHANNEL_SECRET"] = SECRET
    os.environ["STORAGE_ROOT"] = str(tmp_path / "storage")
    os.environ["BOOTSTRAP_ADMIN_LINE_ID"] = ""

    import app.core.config as config_module
    old_settings = config_module._settings
    config_module._settings = None

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routers.users import router as users_router

    # Build a minimal app — skip lifespan (geology, LRS, etc.) entirely
    test_app = FastAPI()
    test_app.include_router(users_router, prefix="/api/users")

    # Attach user store directly on app.state
    users_dir = tmp_path / "storage" / "users"
    users_dir.mkdir(parents=True, exist_ok=True)
    us = UserStore(users_dir)
    test_app.state.user_store = us

    # Create a manager
    us.create(
        user_id="MANAGER1",
        display_name="管理員",
        real_name="管理員",
        role=UserRole.MANAGER,
        status=UserStatus.ACTIVE,
        district_id="all",
        district_name="全區",
    )
    # Create regular users
    us.create(
        user_id="USER1",
        display_name="使用者1",
        real_name="Alice",
        role=UserRole.USER,
        status=UserStatus.PENDING,
        district_id="jingmei",
        district_name="景美工務段",
    )
    us.create(
        user_id="USER2",
        display_name="使用者2",
        real_name="Bob",
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        district_id="fuxing",
        district_name="復興工務段",
    )

    client = TestClient(test_app)
    token = generate_admin_token("MANAGER1", SECRET)

    yield client, token, us

    config_module._settings = old_settings


class TestUsersAPI:
    def test_list_users_requires_token(self, app_with_users) -> None:
        client, _, _ = app_with_users
        resp = client.get("/api/users")
        assert resp.status_code == 401

    def test_list_users_invalid_token(self, app_with_users) -> None:
        client, _, _ = app_with_users
        resp = client.get("/api/users?token=invalid.token")
        assert resp.status_code == 401

    def test_list_users_success(self, app_with_users) -> None:
        client, token, _ = app_with_users
        resp = client.get(f"/api/users?token={token}")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 3  # manager + 2 users

    def test_list_users_filter_status(self, app_with_users) -> None:
        client, token, _ = app_with_users
        resp = client.get(f"/api/users?token={token}&status=pending")
        assert resp.status_code == 200
        data = resp.json()
        assert all(u["status"] == "pending" for u in data)

    def test_list_users_filter_district(self, app_with_users) -> None:
        client, token, _ = app_with_users
        resp = client.get(f"/api/users?token={token}&district=jingmei")
        assert resp.status_code == 200
        data = resp.json()
        assert all(u["district_id"] == "jingmei" for u in data)

    def test_approve_user(self, app_with_users) -> None:
        client, token, us = app_with_users
        resp = client.post(
            f"/api/users/action?token={token}",
            json={"action": "approve", "user_id": "USER1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["user"]["status"] == "active"

    def test_reject_user(self, app_with_users) -> None:
        client, token, us = app_with_users
        resp = client.post(
            f"/api/users/action?token={token}",
            json={"action": "reject", "user_id": "USER1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["user"]["status"] == "rejected"

    def test_suspend_user(self, app_with_users) -> None:
        client, token, us = app_with_users
        resp = client.post(
            f"/api/users/action?token={token}",
            json={"action": "suspend", "user_id": "USER2"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["user"]["status"] == "suspended"

    def test_restore_user(self, app_with_users) -> None:
        client, token, us = app_with_users
        # First suspend
        client.post(
            f"/api/users/action?token={token}",
            json={"action": "suspend", "user_id": "USER2"},
        )
        # Then restore
        resp = client.post(
            f"/api/users/action?token={token}",
            json={"action": "restore", "user_id": "USER2"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["user"]["status"] == "active"

    def test_action_on_self_blocked(self, app_with_users) -> None:
        client, token, _ = app_with_users
        resp = client.post(
            f"/api/users/action?token={token}",
            json={"action": "suspend", "user_id": "MANAGER1"},
        )
        assert resp.status_code == 400

    def test_invalid_action(self, app_with_users) -> None:
        client, token, _ = app_with_users
        resp = client.post(
            f"/api/users/action?token={token}",
            json={"action": "invalid_action", "user_id": "USER1"},
        )
        assert resp.status_code == 400

    def test_update_role(self, app_with_users) -> None:
        client, token, _ = app_with_users
        resp = client.patch(
            f"/api/users?token={token}",
            json={"user_id": "USER2", "role": "manager"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["user"]["role"] == "manager"

    def test_update_district(self, app_with_users) -> None:
        client, token, _ = app_with_users
        resp = client.patch(
            f"/api/users?token={token}",
            json={
                "user_id": "USER2",
                "district_id": "zhongli",
                "district_name": "中壢工務段",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["user"]["district_id"] == "zhongli"

    def test_update_invalid_role(self, app_with_users) -> None:
        client, token, _ = app_with_users
        resp = client.patch(
            f"/api/users?token={token}",
            json={"user_id": "USER2", "role": "superadmin"},
        )
        assert resp.status_code == 400

    def test_delete_user(self, app_with_users) -> None:
        client, token, us = app_with_users
        resp = client.request(
            "DELETE",
            f"/api/users?token={token}",
            json={"user_id": "USER1"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["deleted_user_id"] == "USER1"
        # Verify actually deleted
        assert us.get("USER1") is None

    def test_delete_self_blocked(self, app_with_users) -> None:
        client, token, _ = app_with_users
        resp = client.request(
            "DELETE",
            f"/api/users?token={token}",
            json={"user_id": "MANAGER1"},
        )
        assert resp.status_code == 400

    def test_delete_nonexistent(self, app_with_users) -> None:
        client, token, _ = app_with_users
        resp = client.request(
            "DELETE",
            f"/api/users?token={token}",
            json={"user_id": "U_GHOST"},
        )
        assert resp.status_code == 404

    def test_districts_endpoint(self, app_with_users) -> None:
        client, token, _ = app_with_users
        resp = client.get(f"/api/users/districts?token={token}")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # Check structure
        assert all("id" in d and "name" in d for d in data)

    def test_non_manager_token_rejected(self, app_with_users) -> None:
        client, _, us = app_with_users
        # Generate token for a regular user
        user_token = generate_admin_token("USER2", SECRET)
        resp = client.get(f"/api/users?token={user_token}")
        assert resp.status_code == 403
