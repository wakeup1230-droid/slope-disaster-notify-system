from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request

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
    base_url = str(request.app.state.settings.app_base_url).rstrip("/")

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
    base_url = str(request.app.state.settings.app_base_url).rstrip("/")

    case = case_manager.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    return case_to_vendor_detail(case, base_url, evidence_store)
