from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.case import Case, CreatedBy, ReviewStatus
from app.models.evidence import EvidenceManifest, EvidenceMetadata
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


@pytest.mark.asyncio
async def test_new_user_starts_registration(controller: Any) -> None:
    controller._users.get.return_value = None
    result = await send_event(controller, text="你好")
    session = controller._test_sessions.get("test_user")
    assert result[0]["type"] == "text"
    assert "請先完成註冊" in str(result[0]["text"])
    assert session.flow == FlowType.REGISTRATION
    assert session.step == RegistrationStep.ASK_REAL_NAME.value


@pytest.mark.asyncio
async def test_registration_ask_real_name(controller: Any) -> None:
    controller._users.get.return_value = None
    await send_event(controller, text="hello")
    result = await send_event(controller, text="王小明")
    session = controller._test_sessions.get("test_user")
    assert "請選擇身分角色" in str(result[0]["text"])
    assert session.step == RegistrationStep.ASK_ROLE.value


@pytest.mark.asyncio
async def test_registration_ask_role(controller: Any) -> None:
    controller._users.get.return_value = None
    await send_event(controller, text="hello")
    await send_event(controller, text="王小明")
    result = await send_event(controller, postback_data="action=reg_role&role=user")
    session = controller._test_sessions.get("test_user")
    assert "請選擇工務段" in str(result[0]["text"])
    assert session.step == RegistrationStep.ASK_DISTRICT.value


@pytest.mark.asyncio
async def test_registration_full_flow(controller: Any) -> None:
    controller._users.get.return_value = None
    controller._users.create.return_value = make_active_user()
    await send_event(controller, text="hello")
    await send_event(controller, text="王小明")
    await send_event(controller, postback_data="action=reg_role&role=user")
    await send_event(controller, postback_data="action=select_district&district_id=jingmei")
    result = await send_event(controller, postback_data="action=confirm_registration")
    session = controller._test_sessions.get("test_user")
    assert "註冊完成" in str(result[0]["text"])
    assert session.flow == FlowType.IDLE


@pytest.mark.asyncio
async def test_registration_manager_pending(controller: Any) -> None:
    controller._users.get.return_value = None
    pending_manager = make_active_user(role=UserRole.MANAGER)
    pending_manager.status = UserStatus.PENDING
    controller._users.create.return_value = pending_manager
    await send_event(controller, text="hello")
    await send_event(controller, text="王主管")
    await send_event(controller, postback_data="action=reg_role&role=manager")
    await send_event(controller, postback_data="action=select_district&district_id=jingmei")
    result = await send_event(controller, postback_data="action=confirm_registration")
    assert "等待管理員審核" in str(result[0]["text"])
    controller._notify.notify_managers.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_reporting(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    result = await send_event(controller, text="通報災害")
    session = controller._test_sessions.get("test_user")
    assert "已套用您的工務段" in str(result[0]["text"])
    assert session.step == ReportingStep.SELECT_ROAD.value


@pytest.mark.asyncio
async def test_reporting_select_district(controller: Any) -> None:
    controller._users.get.return_value = make_active_user(district_id="", district_name="")
    await send_event(controller, text="通報災害")
    result = await send_event(controller, postback_data="action=select_district&district_id=jingmei")
    session = controller._test_sessions.get("test_user")
    assert "請選擇道路" in str(result[0]["text"])
    assert session.step == ReportingStep.SELECT_ROAD.value


@pytest.mark.asyncio
async def test_reporting_select_road(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.SELECT_ROAD, data={"district_id": "jingmei"})
    result = await send_event(controller, postback_data="action=select_road&road=台7線")
    session = controller._test_sessions.get("test_user")
    assert "請選擇輸入方式" in str(result[0])
    assert session.step == ReportingStep.INPUT_COORDINATES.value


@pytest.mark.asyncio
async def test_reporting_milepost_input(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    controller._lrs.reverse_lookup.return_value = (25.033, 121.567)
    set_reporting_session(controller, ReportingStep.INPUT_COORDINATES, data={"road": "台7線"})
    result = await send_event(controller, text="23K+500")
    session = controller._test_sessions.get("test_user")
    assert result[0]["type"] == "location"
    assert result[0]["title"] == "📍 里程轉換座標"
    assert "是否確認" in str(result[1]["text"])
    assert "微調座標" in str(result[1])
    assert session.step == ReportingStep.CONFIRM_MILEPOST.value
    assert session.get_data("milepost")["milepost_display"] == "23K+500"


@pytest.mark.asyncio
async def test_reporting_coordinate_input(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    candidate = MagicMock(road="台7線", milepost_km=23.5, milepost_display="23K+500", confidence=0.95, is_interpolated=False)
    controller._lrs.forward_lookup.return_value = [candidate]
    set_reporting_session(controller, ReportingStep.INPUT_COORDINATES, data={"road": "台7線"})
    result = await send_event(controller, text="25.033,121.567")
    session = controller._test_sessions.get("test_user")
    assert result[0]["type"] == "location"
    assert "系統推估里程" in str(result[1]["text"])
    assert "微調座標" in str(result[1])
    assert session.step == ReportingStep.CONFIRM_MILEPOST.value


@pytest.mark.asyncio
async def test_confirm_milepost_adjust_then_location_override(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    candidate = MagicMock(road="台7線", milepost_km=24.0, milepost_display="24K+000", confidence=0.98, is_interpolated=False)
    controller._lrs.forward_lookup.return_value = [candidate]
    set_reporting_session(
        controller,
        ReportingStep.CONFIRM_MILEPOST,
        data={
            "road": "台7線",
            "coordinates": {"lat": 25.033, "lon": 121.567},
            "milepost": {"milepost_display": "23K+500"},
        },
    )

    adjust_prompt = await send_event(controller, postback_data="action=confirm_milepost&ok=adjust")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.INPUT_COORDINATES.value
    assert "請在地圖上選擇正確位置" in str(adjust_prompt[0]["text"])

    result = await send_event(controller, message_type="location", text="25.044,121.577")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.CONFIRM_MILEPOST.value
    assert result[0]["type"] == "location"


@pytest.mark.asyncio
async def test_confirm_geo_info_requires_click_then_advances(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.CONFIRM_GEO_INFO)

    remind = await send_event(controller, text="直接輸入")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.CONFIRM_GEO_INFO.value
    assert "請點選「已閱讀，繼續」" in str(remind[0]["text"])

    proceed = await send_event(controller, postback_data="action=confirm_geo_info&ok=1")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.PROJECT_NAME.value
    assert proceed[0]["type"] == "flex"


@pytest.mark.asyncio
async def test_confirm_milepost_manual_input_skips_duplicate_location_map(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(
        controller,
        ReportingStep.CONFIRM_MILEPOST,
        data={
            "road": "台7線",
            "coordinates": {"lat": 25.033, "lon": 121.567},
            "milepost": {
                "road": "台7線",
                "milepost_km": 23.5,
                "milepost_display": "23K+500",
                "confidence": 1.0,
                "is_interpolated": False,
                "source": "manual_milepost",
            },
        },
    )

    result = await send_event(controller, postback_data="action=confirm_milepost&ok=1")

    assert all(msg.get("type") != "location" for msg in result)
    assert result[-1]["type"] == "text"
    assert "已閱讀，繼續" in str(result[-1])


@pytest.mark.asyncio
async def test_confirm_milepost_non_manual_keeps_location_map(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(
        controller,
        ReportingStep.CONFIRM_MILEPOST,
        data={
            "road": "台7線",
            "coordinates": {"lat": 25.033, "lon": 121.567},
            "milepost": {
                "road": "台7線",
                "milepost_km": 23.5,
                "milepost_display": "23K+500",
                "confidence": 0.95,
                "is_interpolated": False,
                "source": "auto",
            },
        },
    )

    result = await send_event(controller, postback_data="action=confirm_milepost&ok=1")

    assert any(msg.get("type") == "location" for msg in result)


@pytest.mark.asyncio
async def test_reporting_damage_mode_selection(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.SELECT_DAMAGE_MODE)
    await send_event(controller, postback_data="action=select_damage_category&category=revetment_retaining")
    mode_result = await send_event(controller, postback_data="action=select_damage_mode&category=revetment_retaining&mode_id=rr1")
    await send_event(controller, postback_data="action=select_damage_cause&cause_id=rr1_c1&cause_name=河道沖刷")
    finish_result = await send_event(controller, postback_data="action=finish_damage_cause")
    session = controller._test_sessions.get("test_user")
    assert "請選擇災害原因" in str(mode_result[0]["text"])
    assert "請描述災情內容" in str(finish_result[0])
    assert session.step == ReportingStep.INPUT_DESCRIPTION.value


@pytest.mark.asyncio
async def test_reporting_description(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.INPUT_DESCRIPTION)
    result = await send_event(controller, text="邊坡土石滑落")
    session = controller._test_sessions.get("test_user")
    assert result[0]["type"] in {"text", "flex"}
    assert session.step == ReportingStep.UPLOAD_PHOTOS.value


@pytest.mark.asyncio
async def test_reporting_full_happy_path(controller: Any) -> None:
    controller._users.get.return_value = make_active_user(district_id="", district_name="")
    candidate = MagicMock(road="台7線", milepost_km=23.5, milepost_display="23K+500", confidence=0.95, is_interpolated=False)
    controller._lrs.forward_lookup.return_value = [candidate]
    case = Case(case_id="case_20260301_0001", created_by=CreatedBy(user_id="test_user"))
    controller._cases.get_case.return_value = case
    controller._cases.update_case.return_value = True
    await send_event(controller, text="通報災害")
    await send_event(controller, postback_data="action=select_district&district_id=jingmei")
    await send_event(controller, postback_data="action=select_road&road=台7線")
    await send_event(controller, text="25.033,121.567")
    await send_event(controller, postback_data="action=confirm_milepost&ok=1")
    await send_event(controller, postback_data="action=confirm_geo_info&ok=1")

    await send_event(controller, text="台9線32K+400邊坡搶修工程")
    await send_event(controller, text="114/03/01")
    await send_event(controller, postback_data="action=skip_nearby_landmark")

    await send_event(controller, postback_data="action=select_damage_mode&category=revetment_retaining&mode_id=rr1")
    await send_event(controller, postback_data="action=select_damage_cause&cause_id=rr1_c1&cause_name=河道沖刷")
    await send_event(controller, postback_data="action=finish_damage_cause")
    await send_event(controller, text="描述內容")
    session = controller._test_sessions.get("test_user")
    session.step = ReportingStep.UPLOAD_PHOTOS.value
    session.sub_step = GuidedPhotoSubStep.CHOOSE_OPTIONAL.value
    session.draft_case_id = "case_20260301_0001"
    session.data["photo_annotations"] = {"0": {"photo_type": "P1"}, "1": {"photo_type": "P2"}, "2": {"photo_type": "P3"}, "3": {"photo_type": "P4"}}
    controller._test_sessions.save(session)
    await send_event(controller, postback_data="action=finish_photos")
    await send_event(controller, postback_data="action=survey_done")
    for _ in range(6):
        await send_event(controller, postback_data="action=cost_skip")
    await send_event(controller, postback_data="action=cost_confirm")
    await send_event(controller, postback_data="action=select_disaster_type&value=一般")
    await send_event(controller, postback_data="action=select_processing_type&value=搶修")
    await send_event(controller, postback_data="action=select_repeat_disaster&value=否")
    await send_event(controller, postback_data="action=select_original_protection&value=無")
    await send_event(controller, postback_data="action=skip_analysis_review")
    await send_event(controller, postback_data="action=skip_design_docs")
    await send_event(controller, postback_data="action=select_soil_conservation&value=無")
    await send_event(controller, postback_data="action=skip_safety_assessment")
    await send_event(controller, postback_data="action=hazard_confirm")
    await send_event(controller, postback_data="action=skip_other_supplement")
    result = await send_event(controller, postback_data="action=submit_report")
    assert "案件已成功送出" in str(result[0]["text"])


@pytest.mark.asyncio
async def test_photo_awaiting_upload_rejects_text(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.UPLOAD_PHOTOS, sub_step=GuidedPhotoSubStep.AWAITING_UPLOAD, data={"guided_photo_type": "P1", "guided_photo_step": 0, "guided_phase": "required"})
    result = await send_event(controller, message_type="text", text="不是圖片")
    assert result[0]["type"] in {"text", "flex"}


@pytest.mark.asyncio
async def test_photo_upload_stores_evidence(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.UPLOAD_PHOTOS, sub_step=GuidedPhotoSubStep.AWAITING_UPLOAD, data={"guided_photo_type": "P1", "guided_photo_step": 0, "guided_phase": "required"})
    controller._cases.create_case.return_value = MagicMock(case_id="case_20260301_0001")
    img_result = MagicMock(is_valid=True, validation_errors=[], original_filename="test.jpg", content_type="image/jpeg", sha256="abc123", width=800, height=600, thumbnail_data=b"thumb")
    img_result.exif = MagicMock(gps_lat=None, gps_lon=None, datetime_original=None, camera_make=None, camera_model=None)
    controller._images.process_image = AsyncMock(return_value=img_result)
    ev = MagicMock(evidence_id="ev_001", sha256="abc123", original_filename="test.jpg", content_type="image/jpeg")
    controller._evidence.store_evidence.return_value = ev
    controller._evidence.store_thumbnail.return_value = "thumbnails/abc123.jpg"
    await send_event(controller, message_type="image", image_content=b"img-bytes")
    controller._images.process_image.assert_awaited_once()
    controller._evidence.store_evidence.assert_called_once()


@pytest.mark.asyncio
async def test_photo_upload_invalid_image(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.UPLOAD_PHOTOS, sub_step=GuidedPhotoSubStep.AWAITING_UPLOAD, data={"guided_photo_type": "P1", "guided_photo_step": 0, "guided_phase": "required"})
    controller._cases.create_case.return_value = MagicMock(case_id="case_20260301_0001")
    bad_result = MagicMock(is_valid=False, validation_errors=["格式錯誤"])
    controller._images.process_image = AsyncMock(return_value=bad_result)
    result = await send_event(controller, message_type="image", image_content=b"bad")
    assert "照片驗證失敗" in str(result[0]["text"])


@pytest.mark.asyncio
async def test_photo_annotation_tag_selection(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.UPLOAD_PHOTOS, sub_step=GuidedPhotoSubStep.PHOTO_VISIBLE_TAGS)
    session = controller._test_sessions.get("test_user")
    session.annotation_accumulator = {"photo_type": "P1", "photo_type_name": "全景照", "tag_index": 0, "selected_tags": [], "custom_note": ""}
    controller._test_sessions.save(session)
    await send_event(controller, postback_data="action=select_tag&cat=direction&tag=upslope")
    session_after = controller._test_sessions.get("test_user")
    assert any(item["tag_id"] == "upslope" for item in session_after.annotation_accumulator.get("selected_tags", []))


@pytest.mark.asyncio
async def test_photo_annotation_exclusion_in_multi_select_advances(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.UPLOAD_PHOTOS, sub_step=GuidedPhotoSubStep.PHOTO_VISIBLE_TAGS)
    session = controller._test_sessions.get("test_user")
    session.annotation_accumulator = {
        "photo_type": "P1",
        "photo_type_name": "全景照",
        "tag_index": 4,
        "selected_tags": [],
        "custom_note": "",
    }
    controller._test_sessions.save(session)

    await send_event(controller, postback_data="action=select_exclusion&cat=site_risks&tag=no_risk")
    session_after = controller._test_sessions.get("test_user")

    assert session_after.sub_step == GuidedPhotoSubStep.CUSTOM_INPUT.value
    assert any(item["category"] == "site_risks" and item["tag_id"] == "no_risk" for item in session_after.annotation_accumulator.get("selected_tags", []))


@pytest.mark.asyncio
async def test_photo_annotation_multi_select_waits_for_confirm(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.UPLOAD_PHOTOS, sub_step=GuidedPhotoSubStep.PHOTO_VISIBLE_TAGS)
    session = controller._test_sessions.get("test_user")
    session.annotation_accumulator = {
        "photo_type": "P1",
        "photo_type_name": "全景照",
        "tag_index": 4,
        "selected_tags": [],
        "custom_note": "",
    }
    controller._test_sessions.save(session)

    await send_event(controller, postback_data="action=toggle_tag&cat=site_risks&tag=subgrade_gap")
    mid = controller._test_sessions.get("test_user")
    assert mid.sub_step == GuidedPhotoSubStep.PHOTO_VISIBLE_TAGS.value
    assert int(mid.annotation_accumulator.get("tag_index", -1)) == 4

    await send_event(controller, postback_data="action=confirm_multi&cat=site_risks")
    session_after = controller._test_sessions.get("test_user")
    assert session_after.sub_step == GuidedPhotoSubStep.CUSTOM_INPUT.value


@pytest.mark.asyncio
async def test_photo_annotation_confirm_advances(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.UPLOAD_PHOTOS, sub_step=GuidedPhotoSubStep.CONFIRM_ANNOTATION, data={"guided_phase": "required", "guided_photo_step": 0, "guided_photo_type": "P1", "damage_category": "revetment_retaining", "uploaded_evidence": [{"evidence_id": "ev_001", "photo_type": "P1"}], "photo_annotations": {}}, draft_case_id="case_20260301_0001")
    session = controller._test_sessions.get("test_user")
    session.current_photo_index = 0
    session.annotation_accumulator = {"photo_type": "P1", "photo_type_name": "全景照", "tag_index": 0, "selected_tags": [{"category": "direction", "tag_id": "upslope", "label": "往上邊坡"}], "custom_note": ""}
    controller._test_sessions.save(session)
    await send_event(controller, postback_data="action=confirm_annotation_yes")
    session_after = controller._test_sessions.get("test_user")
    assert session_after.sub_step == GuidedPhotoSubStep.AWAITING_UPLOAD.value
    assert session_after.get_data("guided_photo_type") == "P2"


@pytest.mark.asyncio
async def test_photo_finish_required_shows_optional(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.UPLOAD_PHOTOS, sub_step=GuidedPhotoSubStep.CONFIRM_ANNOTATION, data={"guided_phase": "required", "guided_photo_step": 3, "guided_photo_type": "P4", "uploaded_evidence": [{"evidence_id": "ev_003", "photo_type": "P4"}], "photo_annotations": {}}, draft_case_id="case_20260301_0001")
    session = controller._test_sessions.get("test_user")
    session.current_photo_index = 0
    session.annotation_accumulator = {"photo_type": "P3", "photo_type_name": "路面狀況", "tag_index": 0, "selected_tags": [], "custom_note": ""}
    controller._test_sessions.save(session)
    await send_event(controller, postback_data="action=confirm_annotation_yes")
    session_after = controller._test_sessions.get("test_user")
    assert session_after.sub_step == GuidedPhotoSubStep.CHOOSE_OPTIONAL.value


@pytest.mark.asyncio
async def test_photo_finish_photos_advances(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.UPLOAD_PHOTOS, sub_step=GuidedPhotoSubStep.CHOOSE_OPTIONAL, data={"photo_annotations": {"0": {"photo_type": "P1"}, "1": {"photo_type": "P2"}, "2": {"photo_type": "P3"}, "3": {"photo_type": "P4"}}})
    await send_event(controller, postback_data="action=finish_photos")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.ESTIMATED_COST.value


@pytest.mark.asyncio
async def test_cancel_resets_session(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.SELECT_ROAD)
    result = await send_event(controller, text="取消")
    session = controller._test_sessions.get("test_user")
    assert "已取消" in str(result[0]["text"])
    assert session.flow == FlowType.IDLE


@pytest.mark.asyncio
async def test_back_in_reporting(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.SELECT_ROAD)
    await send_event(controller, text="返回")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.SELECT_DISTRICT.value


@pytest.mark.asyncio
async def test_back_in_photo_annotation(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.UPLOAD_PHOTOS, sub_step=GuidedPhotoSubStep.CONFIRM_ANNOTATION, data={"guided_photo_type": "P1", "guided_photo_step": 0, "guided_phase": "required"})
    await send_event(controller, text="返回")
    session = controller._test_sessions.get("test_user")
    assert session.sub_step == GuidedPhotoSubStep.CUSTOM_INPUT.value


@pytest.mark.asyncio
async def test_duplicate_event_ignored(controller: Any) -> None:
    controller._users.get.return_value = None
    first = await send_event(controller, event_id="evt1", text="hello")
    second = await send_event(controller, event_id="evt1", text="hello")
    assert first
    assert second == []


@pytest.mark.asyncio
async def test_unregistered_user_reporting_blocked(controller: Any) -> None:
    inactive = make_active_user()
    inactive.status = UserStatus.PENDING
    controller._users.get.return_value = inactive
    set_reporting_session(controller, ReportingStep.SELECT_DISTRICT)
    result = await send_event(controller, postback_data="action=select_district&district_id=jingmei")
    assert "尚未開通" in str(result[0]["text"])


@pytest.mark.asyncio
async def test_invalid_coordinate_format(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.INPUT_COORDINATES, data={"road": "台7線"})
    result = await send_event(controller, text="bad")
    assert "無法識別座標或里程" in str(result[0]["text"])


@pytest.mark.asyncio
async def test_management_requires_manager(controller: Any) -> None:
    controller._users.get.return_value = make_active_user(role=UserRole.USER)
    result = await send_event(controller, text="審核待辦")
    assert "僅限決策人員" in str(result[0]["text"])


@pytest.mark.asyncio
async def test_idle_unknown_command(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    result = await send_event(controller, text="????")
    assert "請使用下方選單" in str(result[0]["text"])


@pytest.mark.asyncio
async def test_site_survey_toggle(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.SITE_SURVEY, data={"site_survey_selected": []})
    await send_event(controller, postback_data="action=survey_toggle&item_id=upslope_rockfall")
    session = controller._test_sessions.get("test_user")
    assert "upslope_rockfall" in session.get_data("site_survey_selected")
    await send_event(controller, postback_data="action=survey_toggle&item_id=upslope_rockfall")
    session = controller._test_sessions.get("test_user")
    assert "upslope_rockfall" not in session.get_data("site_survey_selected")


@pytest.mark.asyncio
async def test_estimated_cost_calculator_confirm(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.ESTIMATED_COST, data={"cost_current_index": 0, "cost_items": []})

    await send_event(controller, text="2")
    await send_event(controller, postback_data="action=cost_skip")
    await send_event(controller, postback_data="action=cost_skip")
    await send_event(controller, postback_data="action=cost_skip")
    await send_event(controller, postback_data="action=cost_skip")
    summary = await send_event(controller, text="5000")

    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.ESTIMATED_COST.value
    assert summary[0]["type"] == "flex"
    assert len(session.get_data("cost_items")) == 6

    await send_event(controller, postback_data="action=cost_confirm")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.DISASTER_TYPE.value
    assert session.get_data("estimated_cost") == 1.3


@pytest.mark.asyncio
async def test_estimated_cost_skip(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.ESTIMATED_COST, data={"cost_current_index": 0, "cost_items": []})
    for _ in range(6):
        await send_event(controller, postback_data="action=cost_skip")
    await send_event(controller, postback_data="action=cost_confirm")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.DISASTER_TYPE.value
    assert session.get_data("estimated_cost") is None


@pytest.mark.asyncio
async def test_confirm_submit(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.CONFIRM_SUBMIT, draft_case_id="case_20260301_0001", data={"district_id": "jingmei", "district_name": "景美工務段", "road": "台7線", "coordinates": {"lat": 25.033, "lon": 121.567}, "milepost": {"road": "台7線", "milepost_km": 23.5, "milepost_display": "23K+500", "confidence": 0.95, "is_interpolated": False, "source": "auto"}, "damage_category": "revetment_retaining", "damage_mode_id": "rr1", "damage_mode_name": "基礎掏空流失", "damage_cause_ids": ["rr1_c1"], "damage_cause_names": ["河道沖刷"], "description": "描述", "photo_count": 0, "site_survey_selected": [], "uploaded_evidence": []})
    case = Case(case_id="case_20260301_0001", created_by=CreatedBy(user_id="test_user"))
    controller._cases.get_case.return_value = case
    controller._cases.update_case.return_value = True
    result = await send_event(controller, postback_data="action=submit_report")
    session = controller._test_sessions.get("test_user")
    assert "案件已成功送出" in str(result[0]["text"])
    assert any(r.get("altText") == "是否產生 Word 報告？" for r in result)
    assert session.step == ReportingStep.GENERATE_WORD.value


@pytest.mark.asyncio
async def test_query_user_returns_case_carousel(controller: Any) -> None:
    controller._users.get.return_value = make_active_user(role=UserRole.USER)
    controller._cases.get_cases_by_user.return_value = [Case(case_id="case_20260301_0001")]
    result = await send_event(controller, text="查詢案件")
    assert result[0]["type"] == "flex"


@pytest.mark.asyncio
async def test_query_manager_filter_by_status_pending(controller: Any) -> None:
    controller._users.get.return_value = make_active_user(role=UserRole.MANAGER)
    await send_event(controller, text="查詢案件")
    controller._cases.get_pending_cases.return_value = [Case(case_id="case_20260301_0001", review_status=ReviewStatus.PENDING_REVIEW)]
    result = await send_event(controller, postback_data=f"action=query_filter_status&status={ReviewStatus.PENDING_REVIEW.value}")
    assert result[0]["type"] == "flex"


@pytest.mark.asyncio
async def test_query_open_case_shows_detail(controller: Any) -> None:
    controller._users.get.return_value = make_active_user(role=UserRole.MANAGER)
    session = controller._test_sessions.get("test_user")
    session.start_flow(FlowType.QUERY)
    controller._test_sessions.save(session)
    controller._cases.get_case.return_value = Case(case_id="case_20260301_0001")

    result = await send_event(controller, postback_data="action=open_case&case_id=case_20260301_0001")

    assert result[0]["type"] == "flex"
    assert "案件詳情" in str(result[0].get("altText", ""))


@pytest.mark.asyncio
async def test_open_case_from_idle_keeps_manager_review_actions(controller: Any) -> None:
    controller._users.get.return_value = make_active_user(role=UserRole.MANAGER)
    controller._cases.get_case.return_value = Case(case_id="case_20260301_0002")

    result = await send_event(controller, postback_data="action=open_case&case_id=case_20260301_0002")

    assert result[0]["type"] == "flex"
    contents = result[0].get("contents", {})
    footer = contents.get("footer", {}).get("contents", []) if isinstance(contents, dict) else []
    assert len(footer) == 3


@pytest.mark.asyncio
async def test_review_action_from_idle_routes_to_management_handler(controller: Any) -> None:
    controller._users.get.return_value = make_active_user(role=UserRole.MANAGER)
    controller._cases.transition_review_status.return_value = Case(
        case_id="case_20260301_0003",
        created_by=CreatedBy(user_id="creator_1"),
    )

    result = await send_event(controller, postback_data="action=review_action&decision=approve&case_id=case_20260301_0003")

    assert "已通過審核" in str(result[0]["text"])


@pytest.mark.asyncio
async def test_management_approve_notifies_user(controller: Any) -> None:
    controller._users.get.return_value = make_active_user(role=UserRole.MANAGER)
    session = controller._test_sessions.get("test_user")
    session.start_flow(FlowType.MANAGEMENT)
    controller._test_sessions.save(session)
    controller._cases.transition_review_status.return_value = Case(case_id="case_1", created_by=CreatedBy(user_id="creator_1"))
    result = await send_event(controller, postback_data="action=review_action&decision=approve&case_id=case_1")
    assert "已通過審核" in str(result[0]["text"])
    controller._notify.notify_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_disaster_type_selection(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.DISASTER_TYPE)
    await send_event(controller, postback_data="action=select_disaster_type&value=一般")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.PROCESSING_TYPE.value


@pytest.mark.asyncio
async def test_processing_type_selection(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.PROCESSING_TYPE)
    await send_event(controller, postback_data="action=select_processing_type&value=搶修")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.REPEAT_DISASTER.value


@pytest.mark.asyncio
async def test_repeat_disaster_selection(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.REPEAT_DISASTER)
    await send_event(controller, postback_data="action=select_repeat_disaster&value=否")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.ORIGINAL_PROTECTION.value
    assert session.get_data("repeat_disaster") == "否"


@pytest.mark.asyncio
async def test_original_protection_selection(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.ORIGINAL_PROTECTION)
    await send_event(controller, postback_data="action=select_original_protection&value=無")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.ANALYSIS_REVIEW.value
    assert session.get_data("original_protection") == "無"


@pytest.mark.asyncio
async def test_analysis_review_text_input(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.ANALYSIS_REVIEW)
    await send_event(controller, text="分析內容")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.DESIGN_DOCS.value
    assert session.get_data("analysis_review") == "分析內容"


@pytest.mark.asyncio
async def test_analysis_review_skip(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.ANALYSIS_REVIEW)
    await send_event(controller, postback_data="action=skip_analysis_review")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.DESIGN_DOCS.value
    assert session.get_data("analysis_review") == ""


@pytest.mark.asyncio
async def test_design_docs_skip(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.DESIGN_DOCS)
    await send_event(controller, postback_data="action=skip_design_docs")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.SOIL_CONSERVATION.value
    assert session.get_data("design_doc_evidence_id") == ""


@pytest.mark.asyncio
async def test_soil_conservation_selection(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.SOIL_CONSERVATION)
    await send_event(controller, postback_data="action=select_soil_conservation&value=無")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.SAFETY_ASSESSMENT.value


@pytest.mark.asyncio
async def test_safety_assessment_skip(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.SAFETY_ASSESSMENT)
    await send_event(controller, postback_data="action=skip_safety_assessment")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.HAZARD_IDENTIFICATION.value


@pytest.mark.asyncio
async def test_hazard_confirm_advances(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(
        controller,
        ReportingStep.HAZARD_IDENTIFICATION,
        draft_case_id="case_test",
        data={
            "hazard_summary": ["item1"],
            "district_id": "jingmei",
            "district_name": "景美工務段",
            "road": "台9",
            "milepost": {"milepost_display": "1K+000"},
            "damage_category": "revetment_retaining",
            "damage_mode_name": "基礎掏空流失",
            "damage_cause_names": ["河道沖刷"],
            "description": "test",
            "photo_count": 0,
            "site_survey_selected": [],
            "uploaded_evidence": [],
        },
    )
    await send_event(controller, postback_data="action=hazard_confirm")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.OTHER_SUPPLEMENT.value


@pytest.mark.asyncio
async def test_back_from_disaster_type(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.DISASTER_TYPE)
    await send_event(controller, text="返回")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.ESTIMATED_COST.value


@pytest.mark.asyncio
async def test_reporting_project_name_input(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.PROJECT_NAME)

    await send_event(controller, text="台9線32K+400邊坡搶修工程")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.DISASTER_DATE.value
    assert session.get_data("project_name") == "台9線32K+400邊坡搶修工程"


@pytest.mark.asyncio
async def test_reporting_project_name_empty_reprompts(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.PROJECT_NAME)

    result = await send_event(controller, postback_data="action=some_random")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.PROJECT_NAME.value
    assert result[0]["type"] == "flex"


@pytest.mark.asyncio
async def test_reporting_disaster_date_input(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.DISASTER_DATE)

    await send_event(controller, text="114/03/01")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.NEARBY_LANDMARK.value
    assert session.get_data("disaster_date") == "114/03/01"


@pytest.mark.asyncio
async def test_reporting_nearby_landmark_skip(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.NEARBY_LANDMARK)

    await send_event(controller, postback_data="action=skip_nearby_landmark")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.SELECT_DAMAGE_MODE.value
    assert session.get_data("nearby_landmark") == ""


@pytest.mark.asyncio
async def test_reporting_nearby_landmark_text(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.NEARBY_LANDMARK)

    await send_event(controller, text="蘇花公路清水斷崖")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.SELECT_DAMAGE_MODE.value
    assert session.get_data("nearby_landmark") == "蘇花公路清水斷崖"


@pytest.mark.asyncio
async def test_reporting_other_supplement_skip(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.OTHER_SUPPLEMENT)

    await send_event(controller, postback_data="action=skip_other_supplement")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.CONFIRM_SUBMIT.value
    assert session.get_data("other_supplement") == ""


@pytest.mark.asyncio
async def test_reporting_other_supplement_text(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.OTHER_SUPPLEMENT)

    await send_event(controller, text="建議增加排水設施")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.CONFIRM_SUBMIT.value
    assert session.get_data("other_supplement") == "建議增加排水設施"


@pytest.mark.asyncio
async def test_reporting_repeat_disaster_yes_with_year(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.REPEAT_DISASTER)

    await send_event(controller, postback_data="action=select_repeat_disaster&value=是")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.REPEAT_DISASTER.value
    assert session.get_data("repeat_disaster") == "是"

    await send_event(controller, text="108")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.ORIGINAL_PROTECTION.value
    assert session.get_data("repeat_disaster_year") == "108"


@pytest.mark.asyncio
async def test_reporting_repeat_disaster_no_clears_year(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.REPEAT_DISASTER)

    await send_event(controller, postback_data="action=select_repeat_disaster&value=否")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.ORIGINAL_PROTECTION.value
    assert session.get_data("repeat_disaster") == "否"
    assert session.get_data("repeat_disaster_year") == ""


@pytest.mark.asyncio
async def test_reporting_hazard_to_other_supplement(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.HAZARD_IDENTIFICATION, data={"hazard_summary": ["上邊坡崩塌"]})

    await send_event(controller, postback_data="action=hazard_confirm")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.OTHER_SUPPLEMENT.value


@pytest.mark.asyncio
async def test_reporting_back_from_project_name(controller: Any) -> None:
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.PROJECT_NAME)

    await send_event(controller, text="返回")
    session = controller._test_sessions.get("test_user")
    assert session.step == ReportingStep.CONFIRM_GEO_INFO.value


@pytest.mark.asyncio
async def test_generate_word_flow(controller: Any) -> None:
    """After submit, user chooses to generate Word report."""
    controller._users.get.return_value = make_active_user()
    set_reporting_session(
        controller,
        ReportingStep.GENERATE_WORD,
        draft_case_id="case_20260301_0001",
    )
    case = Case(
        case_id="case_20260301_0001",
        created_by=CreatedBy(user_id="test_user", real_name="Test User"),
        project_name="測試工程",
    )
    controller._cases.get_case.return_value = case
    controller._evidence.get_manifest.return_value = MagicMock(photos=[])

    with patch("app.services.word_generator.WordGenerator") as mock_wg_cls:
        mock_gen = MagicMock()
        mock_gen.generate.return_value = b"fake-docx-bytes"
        mock_wg_cls.return_value = mock_gen
        mock_wg_cls.calculate_completeness.return_value = {
            "filled": 5, "total": 25, "percentage": 20,
            "missing": [{"key": "disaster_type", "name": "災害類型", "required": True}],
        }

        result = await send_event(controller, postback_data="action=generate_word")

    session = controller._test_sessions.get("test_user")
    assert session.flow == FlowType.IDLE
    assert any("Word 報告已產生" in str(r.get("altText", "")) for r in result)


@pytest.mark.asyncio
async def test_skip_word_flow(controller: Any) -> None:
    """After submit, user chooses to skip Word report."""
    controller._users.get.return_value = make_active_user()
    set_reporting_session(
        controller,
        ReportingStep.GENERATE_WORD,
        draft_case_id="case_20260301_0001",
    )

    result = await send_event(controller, postback_data="action=skip_word")
    session = controller._test_sessions.get("test_user")
    assert session.flow == FlowType.IDLE
    assert "如需產生報告" in str(result[0]["text"])


# ── Permission Gate Tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_permission_gate_blocks_pending_user(controller: Any) -> None:
    """Pending user is blocked from 通報災害."""
    pending = make_active_user()
    pending.status = UserStatus.PENDING
    controller._users.get.return_value = pending
    result = await send_event(controller, text="通報災害")
    assert "待審核" in str(result[0]["text"])
    assert "無法使用此功能" in str(result[0]["text"])


@pytest.mark.asyncio
async def test_permission_gate_blocks_rejected_user(controller: Any) -> None:
    """Rejected user is blocked from 查詢案件."""
    rejected = make_active_user()
    rejected.status = UserStatus.REJECTED
    controller._users.get.return_value = rejected
    result = await send_event(controller, text="查詢案件")
    assert "已退件" in str(result[0]["text"])
    assert "無法使用此功能" in str(result[0]["text"])


@pytest.mark.asyncio
async def test_permission_gate_blocks_suspended_user(controller: Any) -> None:
    """Suspended user is blocked from 審核待辦."""
    suspended = make_active_user()
    suspended.status = UserStatus.SUSPENDED
    controller._users.get.return_value = suspended
    result = await send_event(controller, text="審核待辦")
    assert "已停用" in str(result[0]["text"])
    assert "無法使用此功能" in str(result[0]["text"])


@pytest.mark.asyncio
async def test_permission_gate_allows_profile_for_pending(controller: Any) -> None:
    """Pending user can access 個人資訊."""
    pending = make_active_user()
    pending.status = UserStatus.PENDING
    controller._users.get.return_value = pending
    result = await send_event(controller, text="個人資訊")
    assert result[0]["type"] == "flex"
    assert "個人資訊" in str(result[0].get("altText", ""))


@pytest.mark.asyncio
async def test_permission_gate_allows_help_for_rejected(controller: Any) -> None:
    """Rejected user can access 操作說明."""
    rejected = make_active_user()
    rejected.status = UserStatus.REJECTED
    controller._users.get.return_value = rejected
    result = await send_event(controller, text="操作說明")
    assert "可用指令" in str(result[0]["text"])


@pytest.mark.asyncio
async def test_permission_gate_resets_non_idle_flow(controller: Any) -> None:
    """Non-active user in REPORTING flow gets blocked and reset."""
    suspended = make_active_user()
    suspended.status = UserStatus.SUSPENDED
    controller._users.get.return_value = suspended
    set_reporting_session(controller, ReportingStep.SELECT_ROAD)
    result = await send_event(controller, text="anything")
    assert "尚未開通" in str(result[0]["text"])
    session = controller._test_sessions.get("test_user")
    assert session.flow == FlowType.IDLE


# ── Profile Edit / Reapply Tests ─────────────────────────────


@pytest.mark.asyncio
async def test_profile_shows_edit_button_for_active_user(controller: Any) -> None:
    """Active user sees '更改資訊' button in profile."""
    controller._users.get.return_value = make_active_user()
    result = await send_event(controller, text="個人資訊")
    assert result[0]["type"] == "flex"
    flex_str = str(result[0])
    assert "更改資訊" in flex_str
    # Active user should NOT see 再次申請
    assert "再次申請" not in flex_str


@pytest.mark.asyncio
async def test_profile_shows_reapply_button_for_rejected(controller: Any) -> None:
    """Rejected user sees both '更改資訊' and '再次申請' buttons."""
    rejected = make_active_user()
    rejected.status = UserStatus.REJECTED
    controller._users.get.return_value = rejected
    result = await send_event(controller, text="個人資訊")
    flex_str = str(result[0])
    assert "更改資訊" in flex_str
    assert "再次申請" in flex_str


@pytest.mark.asyncio
async def test_profile_edit_name_flow(controller: Any) -> None:
    """Edit profile: change name → confirm → update + notify managers."""
    user = make_active_user()
    controller._users.get.return_value = user
    updated_user = make_active_user()
    updated_user.real_name = "New Name"
    updated_user.status = UserStatus.PENDING
    controller._users.update_profile.return_value = updated_user

    # Step 1: Click edit_profile
    result = await send_event(controller, postback_data="action=edit_profile")
    session = controller._test_sessions.get("test_user")
    assert session.flow == FlowType.PROFILE
    assert "要修改的項目" in str(result[0]["text"])

    # Step 2: Choose edit name
    result = await send_event(controller, postback_data="action=edit_real_name")
    session = controller._test_sessions.get("test_user")
    assert "請輸入新的姓名" in str(result[0]["text"])

    # Step 3: Enter new name
    result = await send_event(controller, text="New Name")
    assert "確認更新" in str(result[0]["text"])
    assert "New Name" in str(result[0]["text"])

    # Step 4: Confirm
    result = await send_event(controller, postback_data="action=confirm_edit_profile")
    assert "已更新" in str(result[0]["text"])
    controller._users.update_profile.assert_called_once()
    controller._notify.notify_managers.assert_awaited()
    session = controller._test_sessions.get("test_user")
    assert session.flow == FlowType.IDLE


@pytest.mark.asyncio
async def test_profile_edit_role_flow(controller: Any) -> None:
    """Edit profile: change role → confirm."""
    user = make_active_user()
    controller._users.get.return_value = user
    updated_user = make_active_user()
    updated_user.role = UserRole.MANAGER
    updated_user.status = UserStatus.PENDING
    controller._users.update_profile.return_value = updated_user

    await send_event(controller, postback_data="action=edit_profile")
    result = await send_event(controller, postback_data="action=edit_role")
    assert "角色" in str(result[0]["text"])

    result = await send_event(controller, postback_data="action=set_role&role=manager")
    assert "確認更新" in str(result[0]["text"])
    assert "決策人員" in str(result[0]["text"])

    result = await send_event(controller, postback_data="action=confirm_edit_profile")
    assert "已更新" in str(result[0]["text"])
    session = controller._test_sessions.get("test_user")
    assert session.flow == FlowType.IDLE


@pytest.mark.asyncio
async def test_profile_reapply_flow(controller: Any) -> None:
    """Rejected user can reapply → confirm → back to pending + notify."""
    rejected = make_active_user()
    rejected.status = UserStatus.REJECTED
    controller._users.get.return_value = rejected
    reapplied = make_active_user()
    reapplied.status = UserStatus.PENDING
    controller._users.reapply.return_value = reapplied

    # Step 1: Click reapply from profile
    result = await send_event(controller, postback_data="action=reapply")
    session = controller._test_sessions.get("test_user")
    assert session.flow == FlowType.PROFILE
    assert "重新申請" in str(result[0]["text"])

    # Step 2: Confirm
    result = await send_event(controller, postback_data="action=confirm_reapply")
    assert "已送出" in str(result[0]["text"])
    controller._users.reapply.assert_called_once_with("test_user")
    controller._notify.notify_managers.assert_awaited()
    session = controller._test_sessions.get("test_user")
    assert session.flow == FlowType.IDLE


@pytest.mark.asyncio
async def test_profile_reapply_not_available_for_active(controller: Any) -> None:
    """Active user cannot reapply — status doesn't match."""
    user = make_active_user()
    controller._users.get.return_value = user
    result = await send_event(controller, postback_data="action=reapply")
    assert "無法執行再次申請" in str(result[0]["text"])


@pytest.mark.asyncio
async def test_profile_edit_cancel(controller: Any) -> None:
    """User can cancel profile edit flow."""
    user = make_active_user()
    controller._users.get.return_value = user
    await send_event(controller, postback_data="action=edit_profile")
    result = await send_event(controller, text="取消")
    assert "已取消" in str(result[0]["text"])
    session = controller._test_sessions.get("test_user")
    assert session.flow == FlowType.IDLE


# ── 桌面版選單功能測試 ───────────────────────────────────


@pytest.mark.asyncio
async def test_menu_command_returns_flex_menu(controller: Any) -> None:
    """輸入「選單」應回傳 Flex Bubble 功能選單卡片。"""
    controller._users.get.return_value = make_active_user()
    result = await send_event(controller, text="選單")
    assert len(result) == 1
    assert result[0]["type"] == "flex"
    assert result[0]["altText"] == "功能選單"


@pytest.mark.asyncio
async def test_menu_command_alias_gongneng(controller: Any) -> None:
    """輸入「功能」也應回傳 Flex Bubble 功能選單卡片。"""
    controller._users.get.return_value = make_active_user()
    result = await send_event(controller, text="功能")
    assert len(result) == 1
    assert result[0]["type"] == "flex"
    assert result[0]["altText"] == "功能選單"


@pytest.mark.asyncio
async def test_menu_command_manager_includes_review(controller: Any) -> None:
    """決策人員的選單卡片應包含「審核待辦」按鈕。"""
    controller._users.get.return_value = make_active_user(role=UserRole.MANAGER)
    result = await send_event(controller, text="選單")
    bubble = result[0]["contents"]
    body_text = str(bubble)
    assert "審核待辦" in body_text


@pytest.mark.asyncio
async def test_menu_command_user_excludes_review(controller: Any) -> None:
    """使用者人員的選單卡片不應包含「審核待辦」按鈕。"""
    controller._users.get.return_value = make_active_user(role=UserRole.USER)
    result = await send_event(controller, text="選單")
    bubble = result[0]["contents"]
    body_text = str(bubble)
    assert "審核待辦" not in body_text


@pytest.mark.asyncio
async def test_menu_postback_main_menu(controller: Any) -> None:
    """postback action=main_menu 應回傳功能選單卡片。"""
    controller._users.get.return_value = make_active_user()
    result = await send_event(controller, postback_data="action=main_menu")
    assert result[0]["type"] == "flex"
    assert result[0]["altText"] == "功能選單"


@pytest.mark.asyncio
async def test_menu_global_command_resets_flow(controller: Any) -> None:
    """在非 IDLE 狀態輸入「選單」應重設流程並回傳選單。"""
    controller._users.get.return_value = make_active_user()
    # 先進入通報流程
    await send_event(controller, text="通報災害")
    session = controller._test_sessions.get("test_user")
    assert session.flow != FlowType.IDLE
    # 輸入「選單」應重設
    result = await send_event(controller, text="選單")
    assert result[0]["type"] == "flex"
    assert result[0]["altText"] == "功能選單"
    session = controller._test_sessions.get("test_user")
    assert session.flow == FlowType.IDLE


@pytest.mark.asyncio
async def test_registration_complete_includes_menu(controller: Any) -> None:
    """一般使用者註冊完成後應同時回傳功能選單卡片。"""
    controller._users.get.return_value = None
    controller._users.create.return_value = make_active_user()
    await send_event(controller, text="hello")
    await send_event(controller, text="王小明")
    await send_event(controller, postback_data="action=reg_role&role=user")
    await send_event(controller, postback_data="action=select_district&district_id=jingmei")
    result = await send_event(controller, postback_data="action=confirm_registration")
    assert len(result) == 2
    assert "註冊完成" in str(result[0]["text"])
    assert result[1]["type"] == "flex"
    assert result[1]["altText"] == "功能選單"


@pytest.mark.asyncio
async def test_idle_fallback_mentions_menu(controller: Any) -> None:
    """無法識別的指令回覆應提示可輸入「選單」。"""
    controller._users.get.return_value = make_active_user()
    result = await send_event(controller, text="不知道的指令")
    assert "選單" in str(result[0]["text"])


# ── 快捷操作卡片整合測試 ──────────────────────────────────────────


def _find_quick_action(result: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find the quick_action_card in a result list."""
    for msg in result:
        if msg.get("type") == "flex" and msg.get("altText") == "快捷操作":
            return msg
    return None


@pytest.mark.asyncio
async def test_query_user_includes_quick_action(controller: Any) -> None:
    """一般使用者查詢案件後應附帶 query_done 快捷卡片。"""
    controller._users.get.return_value = make_active_user(role=UserRole.USER)
    controller._cases.get_cases_by_user.return_value = [Case(case_id="case_20260301_0001")]
    result = await send_event(controller, text="查詢案件")
    qc = _find_quick_action(result)
    assert qc is not None
    assert "查詢完成" in qc["contents"]["header"]["contents"][0]["text"]


@pytest.mark.asyncio
async def test_query_manager_filter_includes_quick_action(controller: Any) -> None:
    """決策人員篩選查詢後應附帶 query_done 快捷卡片。"""
    controller._users.get.return_value = make_active_user(role=UserRole.MANAGER)
    await send_event(controller, text="查詢案件")
    controller._cases.get_pending_cases.return_value = [Case(case_id="case_1", review_status=ReviewStatus.PENDING_REVIEW)]
    result = await send_event(controller, postback_data=f"action=query_filter_status&status={ReviewStatus.PENDING_REVIEW.value}")
    qc = _find_quick_action(result)
    assert qc is not None
    assert "查詢完成" in qc["contents"]["header"]["contents"][0]["text"]


@pytest.mark.asyncio
async def test_skip_word_includes_quick_action(controller: Any) -> None:
    """跳過 Word 報告後應附帶 word_done 快捷卡片。"""
    controller._users.get.return_value = make_active_user()
    set_reporting_session(controller, ReportingStep.GENERATE_WORD, draft_case_id="case_20260301_0001")
    result = await send_event(controller, postback_data="action=skip_word")
    qc = _find_quick_action(result)
    assert qc is not None
    header_text = qc["contents"]["header"]["contents"][0]["text"]
    assert "報告已產生" in header_text


@pytest.mark.asyncio
async def test_approve_user_includes_quick_action(controller: Any) -> None:
    """核准使用者後應附帶 review_done 快捷卡片。"""
    controller._users.get.return_value = make_active_user(role=UserRole.MANAGER)
    session = controller._test_sessions.get("test_user")
    session.start_flow(FlowType.MANAGEMENT)
    controller._test_sessions.save(session)
    approved_user = make_active_user(user_id="target_1")
    controller._users.approve.return_value = approved_user
    result = await send_event(controller, postback_data="action=approve_user&user_id=target_1")
    qc = _find_quick_action(result)
    assert qc is not None
    assert "審核完成" in qc["contents"]["header"]["contents"][0]["text"]


@pytest.mark.asyncio
async def test_reject_user_includes_quick_action(controller: Any) -> None:
    """退件使用者後應附帶 review_done 快捷卡片。"""
    controller._users.get.return_value = make_active_user(role=UserRole.MANAGER)
    session = controller._test_sessions.get("test_user")
    session.start_flow(FlowType.MANAGEMENT)
    controller._test_sessions.save(session)
    rejected_user = make_active_user(user_id="target_2")
    controller._users.reject.return_value = rejected_user
    result = await send_event(controller, postback_data="action=reject_user&user_id=target_2")
    qc = _find_quick_action(result)
    assert qc is not None
    assert "審核完成" in qc["contents"]["header"]["contents"][0]["text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["statistics", "query_cases", "profile", "help", "start_report"])
async def test_management_flow_global_postback_routes_correctly(controller: Any, action: str) -> None:
    controller._users.get.return_value = make_active_user(role=UserRole.MANAGER)
    session = controller._test_sessions.get("test_user")
    session.start_flow(FlowType.MANAGEMENT)
    controller._test_sessions.save(session)

    result = await send_event(controller, postback_data=f"action={action}")
    assert "請選擇審核類別" not in str(result)

    updated = controller._test_sessions.get("test_user")
    if action == "start_report":
        assert updated.flow == FlowType.REPORTING
    elif action == "query_cases":
        assert updated.flow == FlowType.QUERY
    elif action == "profile":
        assert updated.flow == FlowType.IDLE


def test_apply_session_to_case_does_not_use_exif_as_fallback(controller: Any) -> None:
    session = controller._test_sessions.get("test_user")
    session.store_data("district_id", "jingmei")
    session.store_data("district_name", "景美工務段")
    session.store_data("road", "台7線")
    session.store_data("description", "測試描述")
    session.store_data("uploaded_evidence", [{"evidence_id": "ev_001", "sha256": "abc", "original_filename": "p1.jpg", "content_type": "image/jpeg"}])
    session.store_data("photo_annotations", {"0": {"photo_type": "P1"}})
    session.draft_case_id = "case_20260302_0001"
    controller._test_sessions.save(session)

    manifest = EvidenceManifest(
        case_id="case_20260302_0001",
        evidence=[
            EvidenceMetadata(
                evidence_id="ev_001",
                sha256="abc",
                original_filename="p1.jpg",
                content_type="image/jpeg",
                evidence_path="evidence/p1.jpg",
                exif_gps_lat=24.1234,
                exif_gps_lon=121.5678,
                exif_datetime="2026-03-02T10:30:00",
            )
        ],
    )
    controller._evidence.get_manifest.return_value = manifest
    controller._admin_boundary = MagicMock()

    case = Case(case_id="case_20260302_0001")
    controller._apply_session_to_case(case, session, "test_user", "Test", "Test User")

    assert case.primary_coordinate is None
    assert case.town_name == ""
    assert case.village_name == ""
    assert case.disaster_date == ""
    controller._admin_boundary.query.assert_not_called()


def test_persist_annotation_updates_photo_type(controller: Any) -> None:
    session = controller._test_sessions.get("test_user")
    session.draft_case_id = "case_20260302_0002"
    session.store_data("uploaded_evidence", [{"evidence_id": "ev_001"}])
    summary = {
        "photo_type": "P2",
        "photo_type_name": "災損近照",
        "tags": [{"category": "visible_damage", "tag_id": "debris_flow", "label": "土石流"}],
        "custom_note": "備註",
    }

    controller._persist_annotation(session, 0, summary)

    controller._evidence.update_photo_type.assert_called_once_with(
        "case_20260302_0002", "ev_001", "P2", "災損近照"
    )
    controller._evidence.update_annotations.assert_called_once()
