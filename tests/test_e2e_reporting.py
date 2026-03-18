from __future__ import annotations

# pyright: reportUnusedCallResult=false, reportUnusedImport=false

import uuid
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.case import Case, CreatedBy, ProcessingStage, ReviewStatus
from app.models.line_state import FlowType, GuidedPhotoSubStep, LineSession, RegistrationStep, ReportingStep
from app.models.user import User, UserRole, UserStatus
from app.services.line_flow import LineFlowController


def make_active_user(
    user_id: str = "test_user",
    role: UserRole = UserRole.USER,
    district_id: str = "jingmei",
    district_name: str = "景美工務段",
) -> User:
    return User(
        user_id=user_id,
        display_name="Test",
        real_name="Test User",
        district_id=district_id,
        district_name=district_name,
        role=role,
        status=UserStatus.ACTIVE,
    )


@pytest.fixture
def mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.app_base_url = "https://example.com"
    return settings


@pytest.fixture
def controller(tmp_path: Path, mock_settings: MagicMock) -> Any:
    from app.services.line_session import LineSessionStore

    session_store = LineSessionStore(sessions_dir=tmp_path / "sessions")
    user_store = MagicMock()
    case_manager = MagicMock()
    evidence_store = MagicMock()
    image_processor = MagicMock()
    lrs_service = MagicMock()
    notification_service = AsyncMock()

    with patch("app.services.line_flow.get_settings", return_value=mock_settings):
        ctrl = LineFlowController(
            line_session_store=session_store,
            user_store=user_store,
            case_manager=case_manager,
            evidence_store=evidence_store,
            image_processor=image_processor,
            lrs_service=lrs_service,
            notification_service=notification_service,
        )

    c = cast(Any, ctrl)
    c._users = user_store
    c._cases = case_manager
    c._evidence = evidence_store
    c._images = image_processor
    c._lrs = lrs_service
    c._notify = notification_service
    c._test_sessions = session_store
    return c


async def send_event(
    ctrl: Any,
    source_key: str = "test_user",
    event_id: str | None = None,
    display_name: str = "TestUser",
    message_type: str | None = "text",
    text: str | None = None,
    postback_data: str | None = None,
    image_content: bytes | None = None,
) -> list[dict[str, object]]:
    if event_id is None:
        event_id = str(uuid.uuid4())
    return await ctrl.handle_event(
        _event_type="message",
        source_key=source_key,
        event_id=event_id,
        display_name=display_name,
        message_type=message_type,
        text=text,
        postback_data=postback_data,
        image_content=image_content,
    )


def set_reporting_session(
    ctrl: Any,
    step: ReportingStep,
    *,
    sub_step: GuidedPhotoSubStep | None = None,
    data: dict[str, object] | None = None,
    draft_case_id: str | None = None,
) -> LineSession:
    session = ctrl._test_sessions.get("test_user")
    session.start_flow(FlowType.REPORTING, step.value)
    if sub_step is not None:
        session.set_sub_step(sub_step.value)
    if data:
        session.data.update(data)
    session.draft_case_id = draft_case_id
    ctrl._test_sessions.save(session)
    return session


def make_draft_case(case_id: str = "CASE-TEST-001") -> Case:
    return Case(
        case_id=case_id,
        district_id="jingmei",
        district_name="景美工務段",
        created_by=CreatedBy(user_id="test_user", display_name="Test", real_name="Test User"),
        review_status=ReviewStatus.PENDING_REVIEW,
        processing_stage=ProcessingStage.INGESTED,
    )


async def annotate_current_photo(ctrl: Any, disaster_type: str) -> None:
    session = ctrl._test_sessions.get("test_user")
    photo_type = session.get_data("guided_photo_type")
    definition = ctrl._resolve_photo_def(photo_type, disaster_type)
    categories = definition.get("photo_tags", [])

    for category in categories:
        category_id = category["category_id"]
        tags = category.get("tags", [])
        exclusion_tags = category.get("exclusion_tags", [])
        option_count = len(tags) + len(exclusion_tags)

        if not category.get("multi_select", True) and option_count <= 7:
            if tags:
                await send_event(
                    ctrl,
                    postback_data=f"action=select_tag&cat={category_id}&tag={tags[0]['id']}",
                )
            elif exclusion_tags:
                await send_event(
                    ctrl,
                    postback_data=f"action=select_exclusion&cat={category_id}&tag={exclusion_tags[0]['id']}",
                )
            continue

        chosen = tags[0] if tags else exclusion_tags[0]
        await send_event(
            ctrl,
            postback_data=f"action=toggle_tag&cat={category_id}&tag={chosen['id']}",
        )
        finish_action = "finish_tag_category" if category.get("multi_select", True) else "confirm_multi"
        await send_event(ctrl, postback_data=f"action={finish_action}")

    await send_event(ctrl, postback_data="action=skip_custom_note")
    await send_event(ctrl, postback_data="action=confirm_annotation_yes")


@pytest.mark.asyncio
async def test_full_reporting_happy_path(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    candidate = MagicMock(
        road="台9",
        milepost_km=23.5,
        milepost_display="23K+500",
        confidence=0.95,
        is_interpolated=False,
    )
    controller._lrs.forward_lookup.return_value = [candidate]

    draft_case = make_draft_case()
    controller._cases.create_case.return_value = draft_case
    controller._cases.get_case.return_value = draft_case
    controller._cases.update_case.return_value = True

    image_result = MagicMock(
        is_valid=True,
        original_filename="test.jpg",
        content_type="image/jpeg",
        sha256="abc123",
        thumbnail_data=b"thumb",
        width=1920,
        height=1080,
        validation_errors=[],
        exif=MagicMock(
            gps_lat=25.033,
            gps_lon=121.567,
            datetime_original="2026-01-01",
            camera_make="Canon",
            camera_model="R5",
        ),
    )
    controller._images.process_image = AsyncMock(return_value=image_result)
    controller._evidence.store_evidence.side_effect = [
        MagicMock(evidence_id="ev-001", sha256="abc123", original_filename="test.jpg", content_type="image/jpeg", thumbnail_path=""),
        MagicMock(evidence_id="ev-002", sha256="abc124", original_filename="test2.jpg", content_type="image/jpeg", thumbnail_path=""),
        MagicMock(evidence_id="ev-003", sha256="abc125", original_filename="test3.jpg", content_type="image/jpeg", thumbnail_path=""),
        MagicMock(evidence_id="ev-004", sha256="abc126", original_filename="test4.jpg", content_type="image/jpeg", thumbnail_path=""),
    ]
    controller._evidence.store_thumbnail.return_value = "thumbnails/thumb.jpg"

    start = await send_event(controller, text="通報災害")
    assert "已套用您的工務段" in str(start[0]["text"])
    assert controller._test_sessions.get("test_user").step == ReportingStep.SELECT_ROAD.value

    await send_event(controller, postback_data="action=select_road&road=台9")
    assert controller._test_sessions.get("test_user").step == ReportingStep.INPUT_COORDINATES.value

    await send_event(controller, text="25.033,121.567")
    assert controller._test_sessions.get("test_user").step == ReportingStep.CONFIRM_MILEPOST.value

    await send_event(controller, postback_data="action=confirm_milepost&ok=1")
    assert controller._test_sessions.get("test_user").step == ReportingStep.CONFIRM_GEO_INFO.value

    await send_event(controller, postback_data="action=confirm_geo_info&ok=1")
    assert controller._test_sessions.get("test_user").step == ReportingStep.PROJECT_NAME.value

    # New steps: PROJECT_NAME -> DISASTER_DATE -> NEARBY_LANDMARK
    await send_event(controller, text="台9線32K+400邊坡搶修工程")
    assert controller._test_sessions.get("test_user").step == ReportingStep.DISASTER_DATE.value

    await send_event(controller, text="114/03/01")
    assert controller._test_sessions.get("test_user").step == ReportingStep.NEARBY_LANDMARK.value

    await send_event(controller, postback_data="action=skip_nearby_landmark")
    assert controller._test_sessions.get("test_user").step == ReportingStep.SELECT_DAMAGE_MODE.value

    await send_event(controller, postback_data="action=select_damage_category&category=revetment_retaining")
    await send_event(controller, postback_data="action=select_damage_mode&category=revetment_retaining&mode_id=rr1")
    await send_event(controller, postback_data="action=select_damage_cause&cause_id=rr1_c1&cause_name=河道沖刷")
    await send_event(controller, postback_data="action=finish_damage_cause")
    assert controller._test_sessions.get("test_user").step == ReportingStep.INPUT_DESCRIPTION.value

    await send_event(controller, text="邊坡崩塌約寬20m")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.UPLOAD_PHOTOS.value
    assert session.sub_step == GuidedPhotoSubStep.AWAITING_UPLOAD.value

    for _ in range(4):
        await send_event(controller, message_type="image", image_content=b"img-bytes")
        await annotate_current_photo(controller, "revetment_retaining")

    session_after_required = controller._test_sessions.get("test_user")
    assert session_after_required.sub_step == GuidedPhotoSubStep.CHOOSE_OPTIONAL.value

    await send_event(controller, postback_data="action=finish_photos")
    # SITE_SURVEY is now auto-filled from photo annotations, skips to ESTIMATED_COST
    assert controller._test_sessions.get("test_user").step == ReportingStep.ESTIMATED_COST.value

    for _ in range(6):
        await send_event(controller, postback_data="action=cost_skip")
    await send_event(controller, postback_data="action=cost_confirm")
    assert controller._test_sessions.get("test_user").step == ReportingStep.DISASTER_TYPE.value

    await send_event(controller, postback_data="action=select_disaster_type&value=一般")
    await send_event(controller, postback_data="action=select_processing_type&value=搶修")
    await send_event(controller, postback_data="action=select_repeat_disaster&value=否")
    await send_event(controller, postback_data="action=select_original_protection&value=無")
    await send_event(controller, postback_data="action=skip_analysis_review")
    await send_event(controller, postback_data="action=skip_design_docs")
    await send_event(controller, postback_data="action=select_soil_conservation&value=無")
    await send_event(controller, postback_data="action=skip_safety_assessment")
    await send_event(controller, postback_data="action=hazard_confirm")
    assert controller._test_sessions.get("test_user").step == ReportingStep.OTHER_SUPPLEMENT.value

    # Skip other supplement
    await send_event(controller, postback_data="action=skip_other_supplement")

    done = await send_event(controller, postback_data="action=submit_report")
    final_session = controller._test_sessions.get("test_user")
    assert "案件已成功送出" in str(done[0]["text"])
    assert controller._test_sessions.get("test_user").step == ReportingStep.GENERATE_WORD.value

    # Skip word generation
    skip_result = await send_event(controller, postback_data="action=skip_word")
    final_session = controller._test_sessions.get("test_user")
    assert "如需產生報告" in str(skip_result[0]["text"])
    assert final_session.flow == FlowType.IDLE
    assert controller._cases.update_case.call_count == 1
    assert controller._evidence.store_evidence.call_count == 4


@pytest.mark.asyncio
async def test_reporting_cancel_mid_flow(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()

    await send_event(controller, text="通報災害")
    await send_event(controller, postback_data="action=select_road&road=台9")
    result = await send_event(controller, text="取消")

    session = controller._test_sessions.get("test_user")
    assert "已取消" in str(result[0]["text"])
    assert session.flow == FlowType.IDLE
    assert session.step == ""


@pytest.mark.asyncio
async def test_reporting_back_navigation(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.INPUT_DESCRIPTION)

    await send_event(controller, text="返回")

    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.SELECT_DAMAGE_CAUSE.value


@pytest.mark.asyncio
async def test_reporting_milepost_input(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    controller._lrs.reverse_lookup.return_value = (25.033, 121.567)
    set_reporting_session(controller, ReportingStep.INPUT_COORDINATES, data={"road": "台9"})

    result = await send_event(controller, text="23K+500")
    session = controller._test_sessions.get("test_user")

    assert result[0]["type"] == "location"
    assert "是否確認" in str(result[1]["text"])
    assert "微調座標" in str(result[1])
    assert session.step == ReportingStep.CONFIRM_MILEPOST.value
    assert session.get_data("milepost")["milepost_display"] == "23K+500"


@pytest.mark.asyncio
async def test_reporting_invalid_coordinates(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.INPUT_COORDINATES, data={"road": "台9"})

    result = await send_event(controller, text="this-is-not-valid")

    assert "無法識別座標或里程" in str(result[0]["text"])
    assert controller._test_sessions.get("test_user").step == ReportingStep.INPUT_COORDINATES.value


@pytest.mark.asyncio
async def test_reporting_cost_entry(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.ESTIMATED_COST, data={"cost_current_index": 0, "cost_items": []})

    await send_event(controller, text="2")
    for _ in range(5):
        await send_event(controller, postback_data="action=cost_skip")
    await send_event(controller, postback_data="action=cost_confirm")

    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.DISASTER_TYPE.value
    assert session.get_data("estimated_cost") == 0.8


@pytest.mark.asyncio
async def test_reporting_cost_invalid_then_skip(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.ESTIMATED_COST, data={"cost_current_index": 0, "cost_items": []})

    invalid = await send_event(controller, text="abc")
    assert invalid[0]["type"] == "flex"
    assert controller._test_sessions.get("test_user").step == ReportingStep.ESTIMATED_COST.value

    for _ in range(6):
        await send_event(controller, postback_data="action=cost_skip")
    await send_event(controller, postback_data="action=cost_confirm")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.DISASTER_TYPE.value
    assert session.get_data("estimated_cost") is None


@pytest.mark.asyncio
async def test_reporting_site_survey_toggle(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.SITE_SURVEY, data={"site_survey_selected": []})

    await send_event(controller, postback_data="action=survey_toggle&item_id=upslope_rockfall")
    await send_event(controller, postback_data="action=survey_toggle&item_id=downslope_settlement")
    mid = controller._test_sessions.get("test_user")
    assert "upslope_rockfall" in mid.get_data("site_survey_selected")
    assert "downslope_settlement" in mid.get_data("site_survey_selected")

    await send_event(controller, postback_data="action=survey_done")
    final = controller._test_sessions.get("test_user")
    assert final.step == ReportingStep.ESTIMATED_COST.value


@pytest.mark.asyncio
async def test_reporting_unregistered_user_blocked(controller: Any) -> None:
    blocked_user = make_active_user()
    blocked_user.status = UserStatus.PENDING
    controller._users.get.return_value = blocked_user

    set_reporting_session(controller, ReportingStep.SELECT_DISTRICT)
    result = await send_event(controller, postback_data="action=select_district&district_id=jingmei")
    assert "尚未開通" in str(result[0]["text"])
