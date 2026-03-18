"""User management API router.

Provides endpoints for the web-based admin panel to manage users.
All endpoints require a valid HMAC admin token (manager only).
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.core.security import verify_admin_token
from app.models.user import UserRole, UserStatus

logger = get_logger(__name__)

router = APIRouter()


# --- Token Auth Dependency ---

def _verify_token(request: Request) -> str:
    """
    Verify the admin token from query parameter and ensure user is a manager.

    Returns:
        The verified manager's user_id.

    Raises:
        HTTPException 401 if token is invalid/expired.
        HTTPException 403 if user is not an active manager.
    """
    token = request.query_params.get("token", "")
    settings = get_settings()
    user_id = verify_admin_token(token, settings.line_channel_secret)

    if not user_id:
        logger.warning("Admin token verification failed")
        raise HTTPException(status_code=401, detail="無效或已過期的管理令牌")

    user_store = request.app.state.user_store
    user = user_store.get(user_id)
    if not user or not user.is_active or not user.is_manager:
        logger.warning("Non-manager attempted admin access: %s", user_id)
        raise HTTPException(status_code=403, detail="僅限決策人員存取")

    return user_id


# --- Request/Response Models ---

class UserActionRequest(BaseModel):
    """Request body for user actions (approve, reject, suspend, restore)."""
    action: str = Field(description="Action: approve, reject, suspend, restore")
    user_id: str = Field(description="Target user's LINE User ID")


class UserUpdateRequest(BaseModel):
    """Request body for updating user role or district."""
    user_id: str = Field(description="Target user's LINE User ID")
    role: Optional[str] = Field(default=None, description="New role: user or manager")
    district_id: Optional[str] = Field(default=None, description="New district ID")
    district_name: Optional[str] = Field(default=None, description="New district name")


class UserDeleteRequest(BaseModel):
    """Request body for deleting a user."""
    user_id: str = Field(description="Target user's LINE User ID")


# --- Endpoints ---

@router.get("")
async def list_users(
    request: Request,
    token: str = Query(default="", description="Admin token"),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    district: Optional[str] = Query(default=None, description="Filter by district_id"),
):
    """
    List all users with optional filters.
    Returns user list as JSON array.
    """
    manager_id = _verify_token(request)
    user_store = request.app.state.user_store
    users = user_store.list_all()

    # Apply filters
    if status:
        users = [u for u in users if u.status.value == status]
    if district:
        users = [u for u in users if u.district_id == district]

    # Sort: pending first, then by registered_at desc
    status_order = {
        UserStatus.PENDING: 0,
        UserStatus.ACTIVE: 1,
        UserStatus.SUSPENDED: 2,
        UserStatus.REJECTED: 3,
    }
    users.sort(key=lambda u: (status_order.get(u.status, 9), u.registered_at or ""), reverse=False)

    logger.info("User list requested by %s (count=%d)", manager_id, len(users))
    return [u.model_dump() for u in users]


@router.post("/action")
async def user_action(
    request: Request,
    body: UserActionRequest,
    token: str = Query(default="", description="Admin token"),
):
    """
    Perform actions on users: approve, reject, suspend, restore.
    """
    manager_id = _verify_token(request)
    user_store = request.app.state.user_store
    action = body.action
    target_id = body.user_id

    if target_id == manager_id:
        raise HTTPException(status_code=400, detail="無法對自己執行此操作")

    result = None
    if action == "approve":
        manager = user_store.get(manager_id)
        approved_by = manager.real_name or manager.display_name if manager else manager_id
        result = user_store.approve(target_id, approved_by)
    elif action == "reject":
        result = user_store.reject(target_id)
    elif action == "suspend":
        result = user_store.suspend(target_id)
    elif action == "restore":
        result = user_store.restore(target_id)
    else:
        raise HTTPException(status_code=400, detail=f"不支援的操作：{action}")

    if result is None:
        raise HTTPException(status_code=404, detail="操作失敗，使用者不存在或狀態不允許此操作")

    logger.info("Admin %s performed '%s' on user %s", manager_id, action, target_id)
    return {"ok": True, "user": result.model_dump()}


@router.patch("")
async def update_user(
    request: Request,
    body: UserUpdateRequest,
    token: str = Query(default="", description="Admin token"),
):
    """
    Update user role and/or district.
    """
    manager_id = _verify_token(request)
    user_store = request.app.state.user_store
    target_id = body.user_id

    target = user_store.get(target_id)
    if not target:
        raise HTTPException(status_code=404, detail="使用者不存在")

    updated = False

    # Update role
    if body.role is not None:
        try:
            new_role = UserRole(body.role)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"無效的角色：{body.role}")
        result = user_store.update_role(target_id, new_role)
        if result:
            updated = True
            logger.info("Admin %s changed role of %s to %s", manager_id, target_id, body.role)

    # Update district
    if body.district_id is not None and body.district_name is not None:
        result = user_store.update_district(target_id, body.district_id, body.district_name)
        if result:
            updated = True
            logger.info("Admin %s changed district of %s to %s", manager_id, target_id, body.district_id)

    if not updated:
        raise HTTPException(status_code=400, detail="未提供有效的更新欄位")

    # Return refreshed user
    refreshed = user_store.get(target_id)
    return {"ok": True, "user": refreshed.model_dump() if refreshed else None}


@router.delete("")
async def delete_user(
    request: Request,
    body: UserDeleteRequest,
    token: str = Query(default="", description="Admin token"),
):
    """
    Permanently delete a user account (irreversible).
    """
    manager_id = _verify_token(request)
    user_store = request.app.state.user_store
    target_id = body.user_id

    if target_id == manager_id:
        raise HTTPException(status_code=400, detail="無法刪除自己的帳號")

    target = user_store.get(target_id)
    if not target:
        raise HTTPException(status_code=404, detail="使用者不存在")

    success = user_store.delete_user(target_id)
    if not success:
        raise HTTPException(status_code=500, detail="刪除失敗")

    logger.info("Admin %s deleted user %s (%s)", manager_id, target_id, target.real_name)
    return {"ok": True, "deleted_user_id": target_id, "deleted_name": target.real_name}


@router.get("/districts")
async def get_districts(
    request: Request,
    token: str = Query(default="", description="Admin token"),
):
    """
    Return available district options for the admin dropdown.
    """
    _verify_token(request)

    import os
    districts_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "app", "data", "districts.json"
    )
    try:
        with open(districts_path, "r", encoding="utf-8") as f:
            districts = json.load(f)
        return districts
    except Exception as e:
        logger.error("Failed to load districts: %s", e)
        raise HTTPException(status_code=500, detail="無法載入工務段資料")
