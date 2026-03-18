"""
User data models.

Defines user profiles with role-based access control.
Two roles: 使用者人員 (user) and 決策人員 (manager).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    """User roles in the system."""
    USER = "user"
    MANAGER = "manager"


class UserStatus(str, Enum):
    """User account status."""
    PENDING = "pending"
    ACTIVE = "active"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class User(BaseModel):
    """
    User profile.

    Users register via LINE and are identified by their LINE user_id.
    Managers must approve new user registrations.
    """
    # --- Identity ---
    user_id: str = Field(description="LINE User ID (Uxxxxxxxx...)")
    display_name: str = Field(default="", description="LINE display name")
    real_name: str = Field(default="", description="Real name entered during registration")

    # --- Organization ---
    district_id: str = Field(default="", description="District ID, e.g., 'fuxing'")
    district_name: str = Field(default="", description="District name, e.g., '復興工務段'")

    # --- Role & Status ---
    role: UserRole = UserRole.USER
    status: UserStatus = UserStatus.PENDING

    # --- Timestamps ---
    registered_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    last_active: Optional[str] = None

    # --- Statistics ---
    cases_created: int = 0
    cases_reviewed: int = 0

    @property
    def is_active(self) -> bool:
        """Check if user account is active."""
        return self.status == UserStatus.ACTIVE

    @property
    def is_manager(self) -> bool:
        """Check if user has manager role."""
        return self.role == UserRole.MANAGER

    def activate(self, approved_by: str) -> None:
        """Approve and activate the user."""
        self.status = UserStatus.ACTIVE
        self.approved_at = datetime.now().isoformat()
        self.approved_by = approved_by

    def reject(self) -> None:
        """Reject the user registration."""
        self.status = UserStatus.REJECTED

    def reapply(self) -> None:
        """Re-apply after rejection or suspension — sets status back to PENDING."""
        self.status = UserStatus.PENDING
        self.approved_at = None
        self.approved_by = None

    def touch(self) -> None:
        """Update last_active timestamp."""
        self.last_active = datetime.now().isoformat()

    def suspend(self) -> None:
        """Suspend the user account."""
        self.status = UserStatus.SUSPENDED
