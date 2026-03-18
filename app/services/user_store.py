"""
User store service.

Manages user profiles stored as JSON files.
Handles registration, approval, and lookup operations.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from app.core.logging_config import get_logger
from app.models.user import User, UserRole, UserStatus

logger = get_logger(__name__)


class UserStore:
    """
    File-based user storage.

    Each user is stored as {users_dir}/{user_id}.json.
    """

    def __init__(self, users_dir: Path) -> None:
        self._users_dir = users_dir
        self._users_dir.mkdir(parents=True, exist_ok=True)

    def _user_path(self, user_id: str) -> Path:
        return self._users_dir / f"{user_id}.json"

    def get(self, user_id: str) -> Optional[User]:
        """
        Get a user by their LINE user_id.

        Returns:
            User object or None if not found.
        """
        path = self._user_path(user_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return User(**data)
        except (json.JSONDecodeError, ValueError, OSError) as e:
            logger.error("Failed to load user %s: %s", user_id, e)
            return None

    def save(self, user: User) -> bool:
        """
        Save a user profile to disk.

        Uses atomic write (write to tmp, then rename) to prevent corruption.

        Returns:
            True if successful.
        """
        path = self._user_path(user.user_id)
        tmp_path = path.with_suffix(".tmp")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(user.model_dump_json(indent=2))
            tmp_path.replace(path)
            logger.debug("Saved user: %s (%s)", user.user_id, user.real_name)
            return True
        except OSError as e:
            logger.error("Failed to save user %s: %s", user.user_id, e)
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return False

    def exists(self, user_id: str) -> bool:
        """Check if a user exists."""
        return self._user_path(user_id).exists()

    def create(
        self,
        user_id: str,
        display_name: str = "",
        real_name: str = "",
        district_id: str = "",
        district_name: str = "",
        role: UserRole = UserRole.USER,
        status: UserStatus = UserStatus.PENDING,
    ) -> Optional[User]:
        """
        Create a new user.

        Returns:
            The created User or None if creation failed.
        """
        if self.exists(user_id):
            logger.warning("User already exists: %s", user_id)
            return self.get(user_id)

        user = User(
            user_id=user_id,
            display_name=display_name,
            real_name=real_name,
            district_id=district_id,
            district_name=district_name,
            role=role,
            status=status,
        )

        if self.save(user):
            logger.info("Created user: %s role=%s", user_id, role.value)
            return user
        return None

    def approve(self, user_id: str, approved_by: str) -> Optional[User]:
        """
        Approve a pending user registration.

        Returns:
            Updated User or None if not found/failed.
        """
        user = self.get(user_id)
        if user is None:
            logger.warning("Cannot approve non-existent user: %s", user_id)
            return None

        user.activate(approved_by)
        if self.save(user):
            logger.info("Approved user: %s by %s", user_id, approved_by)
            return user
        return None

    def reject(self, user_id: str) -> Optional[User]:
        """Reject a pending user registration."""
        user = self.get(user_id)
        if user is None:
            return None

        user.reject()
        if self.save(user):
            logger.info("Rejected user: %s", user_id)
            return user
        return None

    def reapply(self, user_id: str) -> Optional[User]:
        """Re-apply for registration (rejected/suspended → pending)."""
        user = self.get(user_id)
        if user is None:
            return None
        user.reapply()
        if self.save(user):
            logger.info("User reapplied: %s", user_id)
            return user
        return None

    def update_profile(
        self,
        user_id: str,
        *,
        real_name: str | None = None,
        role: UserRole | None = None,
        district_id: str | None = None,
        district_name: str | None = None,
    ) -> Optional[User]:
        """Update user profile fields and set status to PENDING for re-approval."""
        user = self.get(user_id)
        if user is None:
            return None
        if real_name is not None:
            user.real_name = real_name
        if role is not None:
            user.role = role
        if district_id is not None:
            user.district_id = district_id
        if district_name is not None:
            user.district_name = district_name
        # Any profile change requires re-approval
        user.reapply()
        if self.save(user):
            logger.info("Profile updated (pending re-approval): %s", user_id)
            return user
        return None

    def list_by_status(self, status: UserStatus) -> list[User]:
        """List all users with a given status."""
        users = []
        for path in self._users_dir.glob("*.json"):
            user = self.get(path.stem)
            if user and user.status == status:
                users.append(user)
        return users

    def list_pending(self) -> list[User]:
        """List all pending registration requests."""
        return self.list_by_status(UserStatus.PENDING)

    def list_by_district(self, district_id: str) -> list[User]:
        """List all active users in a district."""
        users = []
        for path in self._users_dir.glob("*.json"):
            user = self.get(path.stem)
            if user and user.is_active and user.district_id == district_id:
                users.append(user)
        return users

    def list_managers(self) -> list[User]:
        """List all active managers."""
        managers = []
        for path in self._users_dir.glob("*.json"):
            user = self.get(path.stem)
            if user and user.is_active and user.is_manager:
                managers.append(user)
        return managers

    def list_all(self) -> list[User]:
        """List all users."""
        users = []
        for path in self._users_dir.glob("*.json"):
            user = self.get(path.stem)
            if user:
                users.append(user)
        return users

    def ensure_bootstrap_admin(self, line_id: str, name: str) -> User:
        """
        Ensure the bootstrap admin account exists.
        Creates it if missing, as active manager.

        Args:
            line_id: LINE User ID of the admin.
            name: Display name for the admin.

        Returns:
            The admin User object.
        """
        existing = self.get(line_id)
        if existing:
            # Ensure they're active manager regardless of current state
            if not existing.is_active or not existing.is_manager:
                existing.role = UserRole.MANAGER
                existing.status = UserStatus.ACTIVE
                self.save(existing)
            return existing

        admin = User(
            user_id=line_id,
            display_name=name,
            real_name=name,
            role=UserRole.MANAGER,
            status=UserStatus.ACTIVE,
        )
        self.save(admin)
        logger.info("Bootstrap admin created: %s (%s)", line_id, name)
        return admin

    def suspend(self, user_id: str) -> Optional[User]:
        """Suspend an active user account."""
        user = self.get(user_id)
        if user is None:
            logger.warning("Cannot suspend non-existent user: %s", user_id)
            return None
        user.suspend()
        if self.save(user):
            logger.info("Suspended user: %s", user_id)
            return user
        return None

    def delete_user(self, user_id: str) -> bool:
        """
        Permanently delete a user account (irreversible).

        Returns:
            True if successfully deleted.
        """
        path = self._user_path(user_id)
        if not path.exists():
            logger.warning("Cannot delete non-existent user: %s", user_id)
            return False
        try:
            path.unlink()
            logger.info("Deleted user: %s", user_id)
            return True
        except OSError as e:
            logger.error("Failed to delete user %s: %s", user_id, e)
            return False

    def update_role(self, user_id: str, role: UserRole) -> Optional[User]:
        """Update user role without triggering re-approval."""
        user = self.get(user_id)
        if user is None:
            return None
        user.role = role
        if self.save(user):
            logger.info("Updated role for user %s to %s", user_id, role.value)
            return user
        return None

    def update_district(
        self, user_id: str, district_id: str, district_name: str
    ) -> Optional[User]:
        """Update user district without triggering re-approval."""
        user = self.get(user_id)
        if user is None:
            return None
        user.district_id = district_id
        user.district_name = district_name
        if self.save(user):
            logger.info("Updated district for user %s to %s", user_id, district_id)
            return user
        return None

    def restore(self, user_id: str) -> Optional[User]:
        """Restore a suspended user account to active."""
        user = self.get(user_id)
        if user is None:
            return None
        if user.status != UserStatus.SUSPENDED:
            logger.warning("Cannot restore non-suspended user: %s (status=%s)", user_id, user.status.value)
            return None
        user.status = UserStatus.ACTIVE
        if self.save(user):
            logger.info("Restored user: %s", user_id)
            return user
        return None
