from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from app.core.security import verify_vendor_api_key
from app.models.case import Case
from app.models.vendor import (
    VendorCaseDetail,
    VendorCaseListResponse,
    VendorCaseSummary,
    VendorCoordinate,
    VendorEvidenceItem,
    VendorMilepost,
)
from app.services.evidence_store import EvidenceStore

router = APIRouter()

DISTRICT_FALLBACK_COORDS: dict[str, tuple[float, float]] = {
    "jingmei": (24.9965, 121.5432),
    "zhonghe": (24.9980, 121.4950),
    "zhongli": (24.9533, 121.2256),
    "hsinchu": (24.8040, 120.9715),
    "fuxing": (24.8178, 121.3500),
    "keelung": (25.1306, 121.7392),
}

VISIBLE_WEBGIS_STATUSES = {"pending_review", "in_progress", "closed", "returned"}


def _is_webgis_visible_status(review_status: str) -> bool:
    return review_status in VISIBLE_WEBGIS_STATUSES


def _parse_iso_datetime(value: str) -> datetime:
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    return datetime.fromisoformat(cleaned)


def case_to_vendor_summary(case: Case, base_url: str) -> VendorCaseSummary:
    coordinate = None
    if case.primary_coordinate is not None:
        coordinate = VendorCoordinate(
            lat=case.primary_coordinate.lat,
            lon=case.primary_coordinate.lon,
            confidence=case.primary_coordinate.confidence,
        )
    elif case.coordinate_candidates:
        first = case.coordinate_candidates[0]
        coordinate = VendorCoordinate(lat=first.lat, lon=first.lon, confidence=first.confidence)
    elif case.review_status.value == "returned":
        district_center = DISTRICT_FALLBACK_COORDS.get(case.district_id)
        if district_center is not None:
            coordinate = VendorCoordinate(lat=district_center[0], lon=district_center[1], confidence=0.2)

    milepost = None
    if case.milepost is not None:
        milepost = VendorMilepost(
            road=case.milepost.road,
            milepost_display=case.milepost.milepost_display,
            milepost_km=case.milepost.milepost_km,
        )

    thumbnail_url = None
    if case.evidence_summary:
        first_ev = case.evidence_summary[0]
        thumbnail_url = (
            f"{base_url}/api/cases/{case.case_id}/evidence/{first_ev.evidence_id}/thumbnail"
        )

    return VendorCaseSummary(
        case_id=case.case_id,
        district_id=case.district_id,
        district_name=case.district_name,
        road_number=case.road_number,
        coordinate=coordinate,
        milepost=milepost,
        damage_mode_category=case.damage_mode_category,
        damage_mode_name=case.damage_mode_name,
        description=case.description,
        urgency=case.urgency.value,
        review_status=case.review_status.value,
        photo_count=max(case.photo_count, len(case.evidence_summary)),
        thumbnail_url=thumbnail_url,
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def case_to_vendor_detail(
    case: Case,
    base_url: str,
    evidence_store: EvidenceStore,
) -> VendorCaseDetail:
    summary = case_to_vendor_summary(case, base_url)

    survey_summary = []
    for item in case.site_survey:
        if item.checked:
            entry = item.item_name or item.item_id
            if item.note:
                entry = f"{entry}: {item.note}"
            survey_summary.append(entry)

    evidence_items = []
    manifest = evidence_store.get_manifest(case.case_id)
    for ev in manifest.evidence:
        thumb_url = f"{base_url}/api/cases/{case.case_id}/evidence/{ev.evidence_id}/thumbnail"
        full_url = f"{base_url}/api/cases/{case.case_id}/evidence/{ev.evidence_id}"
        annotations = []
        if ev.annotations.severity:
            annotations.append(ev.annotations.severity.label)
        annotations.extend(tag.label for tag in ev.annotations.tags)
        annotations.extend(note.text for note in ev.annotations.custom_notes)
        evidence_items.append(
            VendorEvidenceItem(
                evidence_id=ev.evidence_id,
                photo_type=ev.photo_type,
                photo_type_name=ev.photo_type_name,
                thumbnail_url=thumb_url,
                full_url=full_url,
                annotations_summary="; ".join(annotations),
            )
        )

    return VendorCaseDetail(
        case_id=summary.case_id,
        district_id=summary.district_id,
        district_name=summary.district_name,
        road_number=summary.road_number,
        coordinate=summary.coordinate,
        milepost=summary.milepost,
        damage_mode_category=summary.damage_mode_category,
        damage_mode_name=summary.damage_mode_name,
        damage_cause_names=case.damage_cause_names,
        description=summary.description,
        urgency=summary.urgency,
        review_status=summary.review_status,
        processing_stage=case.processing_stage.value,
        completeness_pct=case.completeness_pct,
        site_survey_summary=survey_summary,
        evidence_urls=evidence_items,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
    )


@router.get("/cases", dependencies=[Depends(verify_vendor_api_key)])
async def vendor_list_cases(
    request: Request,
    since: str | None = None,
    district_id: str | None = None,
    review_status: str | None = None,
    road: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    case_store = request.app.state.case_store
    base_url = str(request.base_url).rstrip("/")

    since_dt = None
    if since:
        try:
            since_dt = _parse_iso_datetime(since)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid since datetime") from exc

    matched = []
    for case_id in case_store.list_all():
        case = case_store.get(case_id)
        if case is None:
            continue
        if not _is_webgis_visible_status(case.review_status.value):
            continue
        if district_id and case.district_id != district_id:
            continue
        if review_status and case.review_status.value != review_status:
            continue
        if road and case.road_number != road:
            continue
        if since_dt is not None:
            try:
                if _parse_iso_datetime(case.updated_at) <= since_dt:
                    continue
            except ValueError:
                if case.updated_at <= since:
                    continue
        matched.append(case)

    total = len(matched)
    paged = matched[offset : offset + limit]
    return VendorCaseListResponse(
        total=total,
        limit=limit,
        offset=offset,
        cases=[case_to_vendor_summary(case, base_url) for case in paged],
    )


@router.get("/cases/{case_id}", dependencies=[Depends(verify_vendor_api_key)])
async def vendor_get_case(request: Request, case_id: str):
    case_manager = request.app.state.case_manager
    evidence_store = request.app.state.evidence_store
    base_url = str(request.base_url).rstrip("/")

    case = case_manager.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    return case_to_vendor_detail(case, base_url, evidence_store)


@router.delete(
    "/cases/{case_id}",
    dependencies=[Depends(verify_vendor_api_key)],
    status_code=204,
)
async def vendor_delete_case(request: Request, case_id: str):
    """
    Delete a case permanently.

    - Logs audit trail before deletion
    - Removes all case files from disk
    - Notifies LINE managers so 審核待辦 stays in sync
    """
    case_manager = request.app.state.case_manager
    notification_service = request.app.state.notification_service
    user_store = request.app.state.user_store

    # Load case info before deletion (for notification)
    case = case_manager.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    district_name = case.district_name or case.district_id
    road = case.road_number or ""
    creator_id = case.created_by.user_id if case.created_by else ""

    # Delete (audit logged inside case_manager)
    if not case_manager.delete_case(case_id, actor="webgis_admin", actor_name="WebGIS 管理員"):
        raise HTTPException(status_code=500, detail="Failed to delete case")

    # Notify LINE managers asynchronously (best-effort)
    try:
        managers = user_store.list_managers()
        manager_ids = [m.user_id for m in managers]
        if creator_id and creator_id not in manager_ids:
            # Also notify the case creator
            await notification_service.notify_user(
                creator_id,
                f"\u3010\u6848\u4ef6 {case_id}\u3011\u60a8\u7684\u6848\u4ef6\u5df2\u88ab\u7ba1\u7406\u54e1\u522a\u9664\u3002",
            )
        if manager_ids:
            await notification_service.notify_case_deleted(
                case_id=case_id,
                district_name=district_name,
                road=road,
                actor_name="WebGIS \u7ba1\u7406\u54e1",
                manager_ids=manager_ids,
            )
    except Exception as exc:
        # Deletion succeeded; notification failure is non-critical
        import logging
        logging.getLogger(__name__).warning("Delete notification failed: %s", exc)

    return Response(status_code=204)
