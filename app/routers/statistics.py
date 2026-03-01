"""Statistics API router."""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("")
async def get_statistics(request: Request):
    """Return comprehensive case statistics."""
    case_manager = request.app.state.case_manager
    return case_manager.get_statistics()
