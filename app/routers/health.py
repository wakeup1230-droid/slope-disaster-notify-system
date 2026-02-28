from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health_check(request: Request):
    settings = request.app.state.settings
    return {
        "status": "ok",
        "env": settings.app_env,
        "version": "1.0.0-phase1",
        "system": "邊坡災害通報與資訊整合管理系統",
    }
