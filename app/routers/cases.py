from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.core.logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("")
async def list_cases(
    request: Request,
    district_id: str | None = None,
    review_status: str | None = None,
    user_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    case_store = request.app.state.case_store

    matched = []
    for case_id_value in case_store.list_all():
        case = case_store.get(case_id_value)
        if case is None:
            continue
        if district_id and case.district_id != district_id:
            continue
        if review_status and case.review_status.value != review_status:
            continue
        if user_id:
            created_by_user = case.created_by.user_id if case.created_by else ""
            if created_by_user != user_id:
                continue
        matched.append(case)

    total = len(matched)
    page = matched[offset : offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "cases": [item.model_dump() for item in page],
    }


@router.get("/{case_id}")
async def get_case(request: Request, case_id: str):
    case_manager = request.app.state.case_manager
    case = case_manager.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case.model_dump()


@router.get("/{case_id}/evidence/{evidence_id}")
async def get_evidence_file(request: Request, case_id: str, evidence_id: str):
    evidence_store = request.app.state.evidence_store
    evidence_data = evidence_store.get_evidence_file(case_id, evidence_id)
    if evidence_data is None:
        raise HTTPException(status_code=404, detail="Evidence file not found")

    file_bytes, content_type = evidence_data
    return Response(content=file_bytes, media_type=content_type)


@router.get("/{case_id}/evidence/{evidence_id}/thumbnail")
async def get_thumbnail(request: Request, case_id: str, evidence_id: str):
    evidence_store = request.app.state.evidence_store
    thumb = evidence_store.get_thumbnail_file(case_id, evidence_id)
    if thumb is None:
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return Response(content=thumb, media_type="image/jpeg")


@router.get("/{case_id}/evidence")
async def list_evidence(request: Request, case_id: str):
    case_manager = request.app.state.case_manager
    evidence_store = request.app.state.evidence_store

    case = case_manager.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    manifest = evidence_store.get_manifest(case_id)
    return manifest.model_dump()
