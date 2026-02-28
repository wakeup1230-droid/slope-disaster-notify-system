# pyright: basic
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol
from urllib.parse import parse_qs

from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.models.case import (
    Case,
    CoordinateCandidate,
    EvidenceSummary,
    MilepostInfo,
    ProcessingStage,
    ReviewStatus,
    SiteSurveyItem,
)
from app.models.line_state import AnnotationSubStep, FlowType, LineSession, RegistrationStep, ReportingStep
from app.models.user import UserRole, UserStatus
from app.services.case_manager import CaseManager
from app.services.evidence_store import EvidenceStore
from app.services.flex_builders import FlexBuilder
from app.services.image_processor import ImageProcessor
from app.services.line_session import LineSessionStore
from app.services.lrs_service import LRSService
from app.services.user_store import UserStore


logger = get_logger(__name__)


class NotificationService(Protocol):
    async def notify_managers(self, message: str) -> None: ...

    async def notify_user(self, user_id: str, message: str) -> None: ...


class LineFlowController:
    def __init__(
        self,
        line_session_store: LineSessionStore,
        user_store: UserStore,
        case_manager: CaseManager,
        evidence_store: EvidenceStore,
        image_processor: ImageProcessor,
        lrs_service: LRSService,
        notification_service: NotificationService,
    ) -> None:
        self._sessions = line_session_store
        self._users = user_store
        self._cases = case_manager
        self._evidence = evidence_store
        self._images = image_processor
        self._lrs = lrs_service
        self._notify = notification_service
        self._settings = get_settings()
        self._districts = self._load_json("districts.json")
        self._damage_modes = self._load_json("damage_modes.json")
        self._photo_tags = self._load_json("photo_tags.json")
        self._site_survey = self._load_json("site_survey.json")

    async def handle_event(
        self,
        _event_type: str,
        source_key: str,
        event_id: str,
        display_name: str,
        message_type: str | None,
        text: str | None,
        postback_data: str | None,
        image_content: bytes | None,
    ) -> list[dict]:
        session = self._sessions.get(source_key)
        if session.is_duplicate_event(event_id):
            return []

        session.touch()
        incoming_text = (text or "").strip()
        payload = self._parse_postback(postback_data)
        action = payload.get("action", "")

        if incoming_text == "取消" or action == "cancel":
            session.reset()
            self._sessions.save(session)
            return [FlexBuilder.text_message("已取消目前流程，您可以重新選擇功能。")]

        if incoming_text == "返回":
            messages = self._handle_back(session)
            self._sessions.save(session)
            return messages

        user = self._users.get(source_key)

        if session.flow == FlowType.IDLE and user is None:
            messages = self._start_registration(session, display_name)
            self._sessions.save(session)
            return messages

        try:
            if session.flow == FlowType.IDLE:
                messages = await self._handle_idle(session, user, incoming_text, payload)
            elif session.flow == FlowType.REGISTRATION:
                messages = await self._handle_registration(session, source_key, display_name, incoming_text, payload)
            elif session.flow == FlowType.REPORTING:
                messages = await self._handle_reporting(session, source_key, display_name, message_type, incoming_text, payload, image_content)
            elif session.flow == FlowType.QUERY:
                messages = await self._handle_query(session, source_key, user, incoming_text, payload)
            elif session.flow == FlowType.MANAGEMENT:
                messages = await self._handle_management(session, source_key, user, incoming_text, payload)
            elif session.flow == FlowType.PHOTO_ANNOTATION:
                messages = await self._handle_photo_annotation(session, source_key, incoming_text, payload)
            else:
                session.reset()
                messages = [FlexBuilder.text_message("流程狀態異常，已重置。")]
        finally:
            self._sessions.save(session)

        return messages

    async def _handle_idle(self, session: LineSession, user, text: str, payload: dict[str, str]) -> list[dict]:
        action = payload.get("action", "")
        command = text
        if command in {"通報災害"} or action == "start_report":
            session.start_flow(FlowType.REPORTING, ReportingStep.SELECT_DISTRICT.value)
            return await self._prompt_reporting_district(session, user)

        if command in {"我的案件", "查詢案件"} or action == "query_cases":
            session.start_flow(FlowType.QUERY)
            return await self._handle_query(session, session.source_key, user, text, payload)

        if command == "查看地圖" or action == "view_map":
            map_url = f"{self._settings.app_base_url.rstrip('/')}/webgis"
            return [FlexBuilder.text_message(f"請開啟地圖：{map_url}")]

        if command == "審核待辦" or action == "review_pending":
            if not user or not user.is_manager:
                return [FlexBuilder.text_message("此功能僅限決策人員使用。")]
            session.start_flow(FlowType.MANAGEMENT)
            return await self._handle_management(session, session.source_key, user, text, payload)

        if command == "統計摘要" or action == "statistics":
            return [FlexBuilder.statistics_flex(self._cases.get_statistics())]

        if command == "個人資訊" or action == "profile":
            if not user:
                return self._start_registration(session, "")
            role_name = "決策人員" if user.role == UserRole.MANAGER else "使用者人員"
            status_name = {
                UserStatus.PENDING: "待審核",
                UserStatus.ACTIVE: "啟用中",
                UserStatus.REJECTED: "已退件",
                UserStatus.SUSPENDED: "停用",
            }.get(user.status, user.status.value)
            return [
                FlexBuilder.profile_flex(
                    {
                        "real_name": user.real_name,
                        "display_name": user.display_name,
                        "role_name": role_name,
                        "status_name": status_name,
                        "district_name": user.district_name,
                    }
                )
            ]

        if command == "操作說明" or action == "help":
            return [FlexBuilder.help_message()]

        return [FlexBuilder.text_message("請使用下方選單，或輸入「操作說明」查看可用指令。")]

    def _start_registration(self, session: LineSession, display_name: str) -> list[dict]:
        session.start_flow(FlowType.REGISTRATION, RegistrationStep.ASK_REAL_NAME.value)
        session.store_data("display_name", display_name)
        return [FlexBuilder.text_message("歡迎使用邊坡災害通報系統，請先完成註冊。\n請輸入您的真實姓名：")]

    async def _handle_registration(
        self,
        session: LineSession,
        source_key: str,
        display_name: str,
        text: str,
        payload: dict[str, str],
    ) -> list[dict]:
        step = session.step
        action = payload.get("action", "")

        if step == RegistrationStep.ASK_REAL_NAME.value:
            if not text:
                return [FlexBuilder.text_message("請輸入您的真實姓名。")]
            session.store_data("real_name", text)
            session.advance_step(RegistrationStep.ASK_ROLE.value)
            return [
                FlexBuilder.quick_reply_message(
                    "請選擇身分角色：",
                    [
                        {"type": "postback", "label": "使用者人員", "data": "action=reg_role&role=user", "displayText": "使用者人員"},
                        {"type": "postback", "label": "決策人員", "data": "action=reg_role&role=manager", "displayText": "決策人員"},
                    ],
                )
            ]

        if step == RegistrationStep.ASK_ROLE.value:
            role_value = payload.get("role") if action == "reg_role" else ""
            if role_value not in {"user", "manager"}:
                return [FlexBuilder.text_message("請使用按鈕選擇角色。")]
            session.store_data("role", role_value)
            session.advance_step(RegistrationStep.ASK_DISTRICT.value)
            return [FlexBuilder.district_quick_reply()]

        if step == RegistrationStep.ASK_DISTRICT.value:
            district_id = (payload.get("district_id") or "") if action == "select_district" else ""
            district = self._district_by_id(district_id)
            if not district:
                return [FlexBuilder.text_message("請使用按鈕選擇工務段。"), FlexBuilder.district_quick_reply()]
            session.store_data("district_id", district["id"])
            session.store_data("district_name", district["name"])
            session.advance_step(RegistrationStep.CONFIRM.value)
            role = session.get_data("role", "user")
            role_name = "決策人員" if role == "manager" else "使用者人員"
            return [
                FlexBuilder.registration_confirm_flex(
                    {
                        "real_name": session.get_data("real_name", ""),
                        "role_name": role_name,
                        "district_name": district["name"],
                    }
                ),
                FlexBuilder.confirm_message("確認送出註冊資料？", "action=confirm_registration", "action=cancel"),
            ]

        if step == RegistrationStep.CONFIRM.value:
            if action != "confirm_registration":
                return [FlexBuilder.text_message("請按下確認送出註冊。")]

            role = UserRole.MANAGER if session.get_data("role") == "manager" else UserRole.USER
            status = UserStatus.PENDING if role == UserRole.MANAGER else UserStatus.ACTIVE
            created = self._users.create(
                user_id=source_key,
                display_name=display_name,
                real_name=session.get_data("real_name", ""),
                district_id=session.get_data("district_id", ""),
                district_name=session.get_data("district_name", ""),
                role=role,
                status=status,
            )
            if created is None:
                return [FlexBuilder.text_message("註冊失敗，請稍後再試。")]

            if status == UserStatus.PENDING:
                await self._notify.notify_managers(f"新決策人員註冊待審核：{created.real_name} ({created.user_id})")
                done_text = "註冊已送出，等待管理員審核。"
            else:
                done_text = "註冊完成，您可以開始通報災害。"

            session.advance_step(RegistrationStep.DONE.value)
            session.reset()
            return [FlexBuilder.text_message(done_text)]

        return [FlexBuilder.text_message("註冊流程狀態異常，請重新開始。")]

    async def _prompt_reporting_district(self, session: LineSession, user) -> list[dict]:
        if user and user.district_id:
            district = self._district_by_id(user.district_id)
            if district:
                session.store_data("district_id", district["id"])
                session.store_data("district_name", district["name"])
                session.advance_step(ReportingStep.SELECT_ROAD.value)
                return [
                    FlexBuilder.text_message(f"已套用您的工務段：{district['name']}") ,
                    FlexBuilder.road_quick_reply(district["id"]),
                ]
        return [FlexBuilder.district_quick_reply()]

    async def _handle_reporting(
        self,
        session: LineSession,
        source_key: str,
        display_name: str,
        message_type: str | None,
        text: str,
        payload: dict[str, str],
        image_content: bytes | None,
    ) -> list[dict]:
        user = self._users.get(source_key)
        if not user or not user.is_active:
            return [FlexBuilder.text_message("請先完成並通過註冊審核後再進行災害通報。")]

        step = session.step
        action = payload.get("action", "")

        if step == ReportingStep.SELECT_DISTRICT.value:
            if action != "select_district":
                return [FlexBuilder.district_quick_reply()]
            district = self._district_by_id(payload.get("district_id") or "")
            if not district:
                return [FlexBuilder.text_message("請重新選擇工務段。"), FlexBuilder.district_quick_reply()]
            session.store_data("district_id", district["id"])
            session.store_data("district_name", district["name"])
            session.advance_step(ReportingStep.SELECT_ROAD.value)
            return [FlexBuilder.road_quick_reply(district["id"])]

        if step == ReportingStep.SELECT_ROAD.value:
            if action != "select_road":
                return [FlexBuilder.road_quick_reply(session.get_data("district_id", ""))]
            session.store_data("road", payload.get("road", ""))
            session.advance_step(ReportingStep.INPUT_COORDINATES.value)
            return [FlexBuilder.text_message("請分享定位或輸入座標（格式：lat,lon）。")]

        if step == ReportingStep.INPUT_COORDINATES.value:
            coord = self._parse_coordinates(text)
            if message_type == "location" and not coord:
                coord = self._parse_coordinates(text)
            if coord is None:
                return [FlexBuilder.text_message("無法識別座標，請輸入格式：25.1234,121.5678")]

            lat, lon = coord
            session.store_data("coordinates", {"lat": lat, "lon": lon})
            candidates = self._lrs.forward_lookup(lat, lon, road_filter=session.get_data("road", ""))
            if not candidates:
                session.advance_step(ReportingStep.CONFIRM_MILEPOST.value)
                session.store_data(
                    "milepost",
                    {
                        "road": session.get_data("road", ""),
                        "milepost_km": 0.0,
                        "milepost_display": "無法判定",
                        "confidence": 0.0,
                        "is_interpolated": True,
                        "source": "manual",
                    },
                )
                return [
                    FlexBuilder.quick_reply_message(
                        "查無里程資料，是否以座標估值繼續？",
                        [
                            {"type": "postback", "label": "確認", "data": "action=confirm_milepost&ok=1", "displayText": "確認"},
                            {"type": "postback", "label": "重新輸入", "data": "action=confirm_milepost&ok=0", "displayText": "重新輸入"},
                        ],
                    )
                ]

            best = candidates[0]
            label = best.milepost_display
            if best.confidence < 0.7:
                label = f"{label}（估值）"
            session.store_data(
                "milepost",
                {
                    "road": best.road,
                    "milepost_km": best.milepost_km,
                    "milepost_display": label,
                    "confidence": best.confidence,
                    "is_interpolated": best.is_interpolated,
                    "source": "auto",
                },
            )
            session.advance_step(ReportingStep.CONFIRM_MILEPOST.value)
            return [
                FlexBuilder.quick_reply_message(
                    f"系統推估里程：{label}（信心 {best.confidence:.2f}）\n是否確認？",
                    [
                        {"type": "postback", "label": "確認", "data": "action=confirm_milepost&ok=1", "displayText": "確認"},
                        {"type": "postback", "label": "重新輸入", "data": "action=confirm_milepost&ok=0", "displayText": "重新輸入"},
                    ],
                )
            ]

        if step == ReportingStep.CONFIRM_MILEPOST.value:
            if action != "confirm_milepost":
                return [FlexBuilder.text_message("請選擇確認或重新輸入。")]
            if payload.get("ok") != "1":
                session.advance_step(ReportingStep.INPUT_COORDINATES.value)
                return [FlexBuilder.text_message("請重新輸入座標（lat,lon）。")]
            session.advance_step(ReportingStep.SELECT_DAMAGE_MODE.value)
            return [FlexBuilder.damage_mode_carousel()]

        if step == ReportingStep.SELECT_DAMAGE_MODE.value:
            if action == "select_damage_category":
                return [FlexBuilder.damage_mode_list(payload.get("category", ""))]
            if action != "select_damage_mode":
                return [FlexBuilder.damage_mode_carousel()]

            category = payload.get("category", "")
            mode_id = payload.get("mode_id", "")
            mode = self._find_damage_mode(mode_id)
            session.store_data("damage_category", category)
            session.store_data("damage_mode_id", mode_id)
            session.store_data("damage_mode_name", mode.get("mode_name", ""))
            session.store_data("damage_cause_ids", [])
            session.store_data("damage_cause_names", [])
            session.advance_step(ReportingStep.SELECT_DAMAGE_CAUSE.value)
            return [FlexBuilder.damage_cause_quick_reply(mode_id)]

        if step == ReportingStep.SELECT_DAMAGE_CAUSE.value:
            selected_ids = session.get_data("damage_cause_ids", [])
            selected_names = session.get_data("damage_cause_names", [])
            if action == "select_damage_cause":
                cause_id = payload.get("cause_id", "")
                cause_name = payload.get("cause_name", "")
                if cause_id and cause_id not in selected_ids:
                    selected_ids.append(cause_id)
                    selected_names.append(cause_name)
                session.store_data("damage_cause_ids", selected_ids)
                session.store_data("damage_cause_names", selected_names)
                return [FlexBuilder.damage_cause_quick_reply(session.get_data("damage_mode_id", ""))]
            if action != "finish_damage_cause" or not selected_ids:
                return [FlexBuilder.text_message("請至少選擇一項災害原因。"), FlexBuilder.damage_cause_quick_reply(session.get_data("damage_mode_id", ""))]

            session.advance_step(ReportingStep.INPUT_DESCRIPTION.value)
            return [FlexBuilder.text_message("請描述災情內容（可包含影響範圍、危險情形、即時處置）。")]

        if step == ReportingStep.INPUT_DESCRIPTION.value:
            if not text:
                return [FlexBuilder.text_message("請輸入災情描述。")]
            session.store_data("description", text)
            session.advance_step(ReportingStep.UPLOAD_PHOTOS.value)
            return [FlexBuilder.text_message("請上傳照片（至少4張必要照片：全景照、災損近照、道路影響照、邊坡全景）。")]

        if step == ReportingStep.UPLOAD_PHOTOS.value:
            if action == "start_annotation":
                photos = session.get_data("uploaded_evidence", [])
                if len(photos) < 1:
                    return [FlexBuilder.text_message("尚無照片，請先上傳。")]
                session.flow = FlowType.PHOTO_ANNOTATION
                session.step = ReportingStep.ANNOTATE_PHOTOS.value
                session.set_sub_step(AnnotationSubStep.SELECT_PHOTO.value)
                return [self._photo_select_carousel(photos)]

            if message_type != "image" or image_content is None:
                return [FlexBuilder.text_message("此步驟請上傳照片；至少4張後可開始標註。")]

            draft_case = self._ensure_draft_case(session, source_key, display_name, user.real_name)
            if draft_case is None:
                return [FlexBuilder.text_message("建立草稿案件失敗，請稍後再試。")]

            image_result = await self._images.process_image(image_content, f"line_{session.last_event_id or 'image'}.jpg")
            if not image_result.is_valid:
                return [FlexBuilder.text_message("照片格式不符或解析失敗，請重新上傳。")]

            ev = self._evidence.store_evidence(
                case_id=draft_case,
                file_data=image_content,
                original_filename=image_result.original_filename,
                content_type=image_result.content_type,
            )
            if ev is None:
                return [FlexBuilder.text_message("照片儲存失敗，請重試。")]

            thumb_path = self._evidence.store_thumbnail(draft_case, image_result.sha256, image_result.thumbnail_data)
            if thumb_path:
                self._evidence.update_thumbnail_path(draft_case, ev.evidence_id, thumb_path)
            self._evidence.update_exif(
                draft_case,
                ev.evidence_id,
                gps_lat=image_result.exif.gps_lat,
                gps_lon=image_result.exif.gps_lon,
                datetime_original=image_result.exif.datetime_original,
                camera=f"{image_result.exif.camera_make or ''} {image_result.exif.camera_model or ''}".strip() or None,
                width=image_result.width,
                height=image_result.height,
            )

            uploaded = session.get_data("uploaded_evidence", [])
            thumb_url = f"{self._settings.app_base_url.rstrip('/')}/cases/{draft_case}/{thumb_path}" if thumb_path else ""
            uploaded.append(
                {
                    "evidence_id": ev.evidence_id,
                    "sha256": ev.sha256,
                    "thumbnail_path": thumb_path or "",
                    "thumbnail_url": thumb_url,
                    "original_filename": ev.original_filename,
                    "content_type": ev.content_type,
                }
            )
            session.store_data("uploaded_evidence", uploaded)
            session.store_data("photo_count", len(uploaded))

            if len(uploaded) >= 4:
                return [
                    FlexBuilder.quick_reply_message(
                        f"已上傳 {len(uploaded)} 張照片。可繼續上傳或開始標註。",
                        [
                            {"type": "postback", "label": "開始標註", "data": "action=start_annotation", "displayText": "開始標註"},
                            {"type": "postback", "label": "繼續上傳", "data": "action=continue_upload", "displayText": "繼續上傳"},
                        ],
                    )
                ]

            return [FlexBuilder.text_message(f"已上傳 {len(uploaded)} 張，至少還需要 {4 - len(uploaded)} 張必要照片。")]

        if step == ReportingStep.SITE_SURVEY.value:
            selected = session.get_data("site_survey_selected", [])
            if action == "survey_toggle":
                item_id = payload.get("item_id", "")
                if item_id in selected:
                    selected.remove(item_id)
                else:
                    selected.append(item_id)
                session.store_data("site_survey_selected", selected)
            elif action == "survey_done":
                session.advance_step(ReportingStep.ESTIMATED_COST.value)
                return [
                    FlexBuilder.quick_reply_message(
                        "初估經費（萬元）？可輸入數字或按跳過。",
                        [{"type": "postback", "label": "跳過", "data": "action=skip_cost", "displayText": "跳過"}],
                    )
                ]

            return [self._site_survey_quick_reply(selected)]

        if step == ReportingStep.ESTIMATED_COST.value:
            if action == "skip_cost":
                session.store_data("estimated_cost", None)
            else:
                try:
                    if text:
                        session.store_data("estimated_cost", float(text))
                    else:
                        raise ValueError("missing")
                except ValueError:
                    return [
                        FlexBuilder.quick_reply_message(
                            "請輸入數字（萬元），或按跳過。",
                            [{"type": "postback", "label": "跳過", "data": "action=skip_cost", "displayText": "跳過"}],
                        )
                    ]

            session.advance_step(ReportingStep.CONFIRM_SUBMIT.value)
            return [
                FlexBuilder.report_confirm_flex(self._build_report_summary(session)),
                FlexBuilder.confirm_message("確認送出案件？", "action=submit_report", "action=cancel"),
            ]

        if step == ReportingStep.CONFIRM_SUBMIT.value:
            if action != "submit_report":
                return [FlexBuilder.text_message("請按確認送出，或輸入取消。")]

            case_id = session.draft_case_id
            if not case_id:
                return [FlexBuilder.text_message("草稿案件不存在，請重新通報。")]
            case = self._cases.get_case(case_id)
            if case is None:
                return [FlexBuilder.text_message("案件資料讀取失敗，請重新通報。")]

            self._apply_session_to_case(case, session, user.user_id, user.display_name, user.real_name)
            ok = self._cases.update_case(case, actor=user.user_id, actor_name=user.real_name or user.display_name)
            if not ok:
                return [FlexBuilder.text_message("案件送出失敗，請稍後再試。")]

            await self._notify.notify_managers(f"新案件待審核：{case.case_id}（{case.district_name} {case.road_number}）")
            session.advance_step(ReportingStep.DONE.value)
            session.reset()
            return [FlexBuilder.text_message(f"案件已成功送出，案件編號：{case.case_id}")]

        if step == ReportingStep.ANNOTATE_PHOTOS.value:
            session.flow = FlowType.PHOTO_ANNOTATION
            session.set_sub_step(AnnotationSubStep.SELECT_PHOTO.value)
            photos = session.get_data("uploaded_evidence", [])
            return [self._photo_select_carousel(photos)]

        return [FlexBuilder.text_message("通報流程狀態異常，請重新開始。")]

    async def _handle_photo_annotation(
        self,
        session: LineSession,
        _source_key: str,
        text: str,
        payload: dict[str, str],
    ) -> list[dict]:
        sub_step = session.sub_step or AnnotationSubStep.SELECT_PHOTO.value
        action = payload.get("action", "")
        photos = session.get_data("uploaded_evidence", [])
        if not photos:
            session.flow = FlowType.REPORTING
            session.advance_step(ReportingStep.UPLOAD_PHOTOS.value)
            return [FlexBuilder.text_message("尚未上傳照片，請先上傳。")]

        if sub_step == AnnotationSubStep.SELECT_PHOTO.value:
            if action == "finish_annotations":
                session.flow = FlowType.REPORTING
                session.advance_step(ReportingStep.SITE_SURVEY.value)
                return [self._site_survey_quick_reply(session.get_data("site_survey_selected", []))]
            if action != "select_photo":
                return [self._photo_select_carousel(photos)]
            idx = int(payload.get("index", "0"))
            if idx < 0 or idx >= len(photos):
                return [FlexBuilder.text_message("照片索引不存在，請重新選擇。")]
            session.current_photo_index = idx
            session.set_sub_step(AnnotationSubStep.SELECT_TYPE.value)
            return [FlexBuilder.photo_type_quick_reply()]

        if sub_step == AnnotationSubStep.SELECT_TYPE.value:
            if action != "select_photo_type":
                return [FlexBuilder.photo_type_quick_reply()]
            photo_type = payload.get("photo_type", "")
            tag_def = self._photo_tags.get(photo_type)
            if not tag_def:
                return [FlexBuilder.text_message("照片類型不存在，請重新選擇。")]
            session.annotation_accumulator = {
                "photo_type": photo_type,
                "photo_type_name": tag_def.get("name", photo_type),
                "tag_index": 0,
                "selected_tags": [],
                "custom_note": "",
            }
            session.pending_tags = []
            session.set_sub_step(AnnotationSubStep.SELECT_TAGS.value)
            return [self._current_tag_category_message(session)]

        if sub_step == AnnotationSubStep.SELECT_TAGS.value:
            if action == "tag":
                cat_id = payload.get("cat", "")
                tag_id = payload.get("tag", "")
                self._toggle_tag(session, cat_id, tag_id)
                return [self._current_tag_category_message(session)]

            if action != "finish_tag_category":
                return [self._current_tag_category_message(session)]

            tag_index = int(session.annotation_accumulator.get("tag_index", 0)) + 1
            session.annotation_accumulator["tag_index"] = tag_index
            categories = self._current_tag_categories(session)
            if tag_index < len(categories):
                return [self._current_tag_category_message(session)]

            session.set_sub_step(AnnotationSubStep.CUSTOM_INPUT.value)
            return [
                FlexBuilder.quick_reply_message(
                    "如有其他描述，請直接輸入文字，或按「跳過」。",
                    [{"type": "postback", "label": "跳過", "data": "action=skip_custom_note", "displayText": "跳過"}],
                )
            ]

        if sub_step == AnnotationSubStep.CUSTOM_INPUT.value:
            if action == "skip_custom_note":
                session.annotation_accumulator["custom_note"] = ""
            else:
                session.annotation_accumulator["custom_note"] = text
            session.set_sub_step(AnnotationSubStep.CONFIRM_ANNOTATION.value)
            summary = self._build_annotation_summary(session)
            return [
                FlexBuilder.annotation_summary_flex(session.current_photo_index, summary),
                FlexBuilder.confirm_message("確認此張照片標註？", "action=confirm_annotation_yes", "action=confirm_annotation_no"),
            ]

        if sub_step == AnnotationSubStep.CONFIRM_ANNOTATION.value:
            if action == "confirm_annotation_no":
                session.set_sub_step(AnnotationSubStep.SELECT_TYPE.value)
                return [FlexBuilder.photo_type_quick_reply()]
            if action != "confirm_annotation_yes":
                return [FlexBuilder.text_message("請確認是否套用此標註。")]

            idx = session.current_photo_index
            annotations = session.get_data("photo_annotations", {})
            summary = self._build_annotation_summary(session)
            annotations[str(idx)] = summary
            session.store_data("photo_annotations", annotations)
            self._persist_annotation(session, idx, summary)

            session.set_sub_step(AnnotationSubStep.NEXT_PHOTO.value)
            return [
                FlexBuilder.quick_reply_message(
                    "此照片標註完成。",
                    [
                        {"type": "postback", "label": "下一張", "data": "action=next_photo", "displayText": "下一張"},
                        {"type": "postback", "label": "完成標註", "data": "action=finish_annotations", "displayText": "完成標註"},
                    ],
                )
            ]

        if sub_step == AnnotationSubStep.NEXT_PHOTO.value:
            if action == "finish_annotations":
                session.flow = FlowType.REPORTING
                session.advance_step(ReportingStep.SITE_SURVEY.value)
                return [self._site_survey_quick_reply(session.get_data("site_survey_selected", []))]

            if action != "next_photo":
                return [FlexBuilder.text_message("請選擇下一張或完成標註。")]

            session.set_sub_step(AnnotationSubStep.SELECT_PHOTO.value)
            return [self._photo_select_carousel(photos)]

        return [FlexBuilder.text_message("照片標註流程異常，請重新選擇。")]

    async def _handle_query(
        self,
        session: LineSession,
        source_key: str,
        user,
        _text: str,
        payload: dict[str, str],
    ) -> list[dict]:
        if not user:
            session.reset()
            return [FlexBuilder.text_message("尚未註冊，請先完成註冊。")]

        action = payload.get("action", "")
        if user.role == UserRole.USER:
            cases = self._cases.get_cases_by_user(source_key)
            cards = [self._case_to_card_dict(case) for case in cases]
            session.reset()
            return [FlexBuilder.case_list_carousel(cards)]

        if action == "query_filter_district":
            district_id = payload.get("district_id", "")
            cases = self._cases.get_cases_by_district(district_id)
            cards = [self._case_to_card_dict(case) for case in cases]
            session.reset()
            return [FlexBuilder.case_list_carousel(cards)]

        if action == "query_filter_status":
            status = payload.get("status", "")
            if status == ReviewStatus.PENDING_REVIEW.value:
                cases = self._cases.get_pending_cases()
            else:
                district_cases = []
                for district in self._districts:
                    district_cases.extend(self._cases.get_cases_by_district(district["id"]))
                cases = [c for c in district_cases if c.review_status.value == status]
            cards = [self._case_to_card_dict(case) for case in cases]
            session.reset()
            return [FlexBuilder.case_list_carousel(cards)]

        district_items = [
            {
                "type": "postback",
                "label": d["name"],
                "data": f"action=query_filter_district&district_id={d['id']}",
                "displayText": d["name"],
            }
            for d in self._districts
        ]
        status_items = [
            {"type": "postback", "label": "待審核", "data": f"action=query_filter_status&status={ReviewStatus.PENDING_REVIEW.value}", "displayText": "待審核"},
            {"type": "postback", "label": "處理中", "data": f"action=query_filter_status&status={ReviewStatus.IN_PROGRESS.value}", "displayText": "處理中"},
            {"type": "postback", "label": "已退回", "data": f"action=query_filter_status&status={ReviewStatus.RETURNED.value}", "displayText": "已退回"},
            {"type": "postback", "label": "已結案", "data": f"action=query_filter_status&status={ReviewStatus.CLOSED.value}", "displayText": "已結案"},
        ]
        return [
            FlexBuilder.quick_reply_message("請選擇工務段篩選：", district_items),
            FlexBuilder.quick_reply_message("或依狀態篩選：", status_items),
        ]

    async def _handle_management(
        self,
        session: LineSession,
        source_key: str,
        user,
        text: str,
        payload: dict[str, str],
    ) -> list[dict]:
        if not user or not user.is_manager:
            session.reset()
            return [FlexBuilder.text_message("僅決策人員可使用審核功能。")]

        action = payload.get("action", "")
        if action == "open_case":
            case = self._cases.get_case(payload.get("case_id", ""))
            if not case:
                return [FlexBuilder.text_message("案件不存在。")]
            session.store_data("review_case_id", case.case_id)
            return [FlexBuilder.case_detail_flex(self._case_to_detail_dict(case))]

        if action == "review_action":
            decision = payload.get("decision", "")
            case_id = payload.get("case_id", "")
            if decision == "return":
                session.step = "await_return_reason"
                session.store_data("review_case_id", case_id)
                return [FlexBuilder.text_message("請輸入退回原因：")]
            if decision == "approve":
                updated = self._cases.transition_review_status(case_id, ReviewStatus.IN_PROGRESS, source_key, user.real_name or user.display_name)
                if not updated:
                    return [FlexBuilder.text_message("案件狀態更新失敗。")]
                await self._notify.notify_user(updated.created_by.user_id if updated.created_by else "", f"您的案件 {case_id} 已通過審核，進入處理中。")
                return [FlexBuilder.text_message(f"案件 {case_id} 已通過審核。")]
            if decision == "close":
                updated = self._cases.transition_review_status(case_id, ReviewStatus.CLOSED, source_key, user.real_name or user.display_name)
                if not updated:
                    return [FlexBuilder.text_message("案件結案失敗。")]
                await self._notify.notify_user(updated.created_by.user_id if updated.created_by else "", f"您的案件 {case_id} 已結案。")
                return [FlexBuilder.text_message(f"案件 {case_id} 已結案。")]

        if session.step == "await_return_reason":
            case_id = session.get_data("review_case_id", "")
            if not text:
                return [FlexBuilder.text_message("請輸入退回原因。")]
            updated = self._cases.transition_review_status(case_id, ReviewStatus.RETURNED, source_key, user.real_name or user.display_name, note=text)
            session.step = ""
            if not updated:
                return [FlexBuilder.text_message("退回失敗。")]
            await self._notify.notify_user(updated.created_by.user_id if updated.created_by else "", f"您的案件 {case_id} 已退回，原因：{text}")
            return [FlexBuilder.text_message(f"案件 {case_id} 已退回。")]

        pending = self._cases.get_pending_cases()
        cards = [self._case_to_card_dict(case) for case in pending]
        return [FlexBuilder.case_list_carousel(cards)]

    def _handle_back(self, session: LineSession) -> list[dict]:
        if session.flow == FlowType.REPORTING:
            order = [
                ReportingStep.SELECT_DISTRICT.value,
                ReportingStep.SELECT_ROAD.value,
                ReportingStep.INPUT_COORDINATES.value,
                ReportingStep.CONFIRM_MILEPOST.value,
                ReportingStep.SELECT_DAMAGE_MODE.value,
                ReportingStep.SELECT_DAMAGE_CAUSE.value,
                ReportingStep.INPUT_DESCRIPTION.value,
                ReportingStep.UPLOAD_PHOTOS.value,
                ReportingStep.SITE_SURVEY.value,
                ReportingStep.ESTIMATED_COST.value,
                ReportingStep.CONFIRM_SUBMIT.value,
            ]
            if session.step in order and order.index(session.step) > 0:
                session.step = order[order.index(session.step) - 1]
                return [FlexBuilder.text_message(f"已返回上一步：{session.step}")]

        if session.flow == FlowType.REGISTRATION:
            order = [
                RegistrationStep.ASK_REAL_NAME.value,
                RegistrationStep.ASK_ROLE.value,
                RegistrationStep.ASK_DISTRICT.value,
                RegistrationStep.CONFIRM.value,
            ]
            if session.step in order and order.index(session.step) > 0:
                session.step = order[order.index(session.step) - 1]
                return [FlexBuilder.text_message("已返回上一步。")]

        if session.flow == FlowType.PHOTO_ANNOTATION:
            sub_order = [
                AnnotationSubStep.SELECT_PHOTO.value,
                AnnotationSubStep.SELECT_TYPE.value,
                AnnotationSubStep.SELECT_TAGS.value,
                AnnotationSubStep.CUSTOM_INPUT.value,
                AnnotationSubStep.CONFIRM_ANNOTATION.value,
                AnnotationSubStep.NEXT_PHOTO.value,
            ]
            if session.sub_step in sub_order and sub_order.index(session.sub_step) > 0:
                session.sub_step = sub_order[sub_order.index(session.sub_step) - 1]
                return [FlexBuilder.text_message("已返回上一步。")]

        return [FlexBuilder.text_message("目前無法再返回，請繼續或輸入取消。")]

    def _site_survey_quick_reply(self, selected: list[str]) -> dict:
        items = []
        for category in self._site_survey:
            for item in category.get("items", []):
                checked = "✓" if item["item_id"] in selected else ""
                items.append(
                    {
                        "type": "postback",
                        "label": f"{checked}{item['item_name']}"[:20],
                        "data": f"action=survey_toggle&item_id={item['item_id']}",
                        "displayText": item["item_name"],
                    }
                )
                if len(items) >= 12:
                    break
            if len(items) >= 12:
                break
        items.append({"type": "postback", "label": "完成勾選", "data": "action=survey_done", "displayText": "完成勾選"})
        return FlexBuilder.quick_reply_message("現勘項目（可複選）：", items)

    def _photo_select_carousel(self, photos: list[dict]) -> dict:
        bubbles = []
        for idx, photo in enumerate(photos[:10]):
            bubbles.append(
                {
                    "type": "bubble",
                    "hero": {
                        "type": "image",
                        "url": photo.get("thumbnail_url") or "https://dummyimage.com/800x400/e9eef3/888888&text=Photo",
                        "size": "full",
                        "aspectRatio": "20:13",
                        "aspectMode": "cover",
                    },
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": f"照片 #{idx + 1}", "weight": "bold"},
                            {"type": "text", "text": photo.get("original_filename", ""), "size": "xs", "color": "#888888", "wrap": True},
                        ],
                    },
                    "footer": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "button",
                                "style": "primary",
                                "color": "#4A90D9",
                                "action": {
                                    "type": "postback",
                                    "label": "標註",
                                    "data": f"action=select_photo&index={idx}",
                                    "displayText": f"標註照片{idx + 1}",
                                },
                            }
                        ],
                    },
                }
            )
        bubbles.append(
            {
                "type": "bubble",
                "body": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": "已完成標註可按下方按鈕繼續", "wrap": True}]},
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#1DB446",
                            "action": {"type": "postback", "label": "完成標註", "data": "action=finish_annotations", "displayText": "完成標註"},
                        }
                    ],
                },
            }
        )
        return {"type": "flex", "altText": "請選擇照片進行標註", "contents": {"type": "carousel", "contents": bubbles}}

    def _current_tag_categories(self, session: LineSession) -> list[dict]:
        photo_type = session.annotation_accumulator.get("photo_type", "")
        definition = self._photo_tags.get(photo_type, {})
        return definition.get("tag_categories", [])

    def _current_tag_category_message(self, session: LineSession) -> dict:
        categories = self._current_tag_categories(session)
        idx = int(session.annotation_accumulator.get("tag_index", 0))
        if idx >= len(categories):
            return FlexBuilder.text_message("標籤類別已完成。")
        category = categories[idx]
        selected = [tag["tag_id"] for tag in session.annotation_accumulator.get("selected_tags", []) if tag.get("category") == category.get("category_id")]
        return FlexBuilder.tag_category_buttons(session.current_photo_index, category, selected)

    def _toggle_tag(self, session: LineSession, category_id: str, tag_id: str) -> None:
        categories = {c["category_id"]: c for c in self._current_tag_categories(session)}
        category = categories.get(category_id)
        if not category:
            return
        tag_info = next((t for t in category.get("tags", []) if t["id"] == tag_id), None)
        if not tag_info:
            return

        selected = session.annotation_accumulator.get("selected_tags", [])
        exists = next((item for item in selected if item["category"] == category_id and item["tag_id"] == tag_id), None)

        if exists:
            selected.remove(exists)
        else:
            if not category.get("multi_select", True):
                selected = [item for item in selected if item["category"] != category_id]
            selected.append(
                {
                    "category": category_id,
                    "category_name": category.get("category_name", ""),
                    "tag_id": tag_id,
                    "label": tag_info.get("label", ""),
                }
            )
        session.annotation_accumulator["selected_tags"] = selected

    def _build_annotation_summary(self, session: LineSession) -> dict:
        return {
            "photo_type": session.annotation_accumulator.get("photo_type", ""),
            "photo_type_name": session.annotation_accumulator.get("photo_type_name", ""),
            "tags": session.annotation_accumulator.get("selected_tags", []),
            "custom_note": session.annotation_accumulator.get("custom_note", ""),
        }

    def _persist_annotation(self, session: LineSession, idx: int, summary: dict) -> None:
        case_id = session.draft_case_id
        photos = session.get_data("uploaded_evidence", [])
        if not case_id or idx >= len(photos):
            return
        evidence_id = photos[idx].get("evidence_id")
        if not evidence_id:
            return

        annotations_data = {
            "tags": [
                {
                    "category": tag.get("category", ""),
                    "tag_id": tag.get("tag_id", ""),
                    "label": tag.get("label", ""),
                    "source": "user_select",
                }
                for tag in summary.get("tags", [])
            ],
            "custom_notes": [{"text": summary.get("custom_note", ""), "source": "user_input"}] if summary.get("custom_note") else [],
        }
        self._evidence.update_annotations(case_id, evidence_id, annotations_data)

    def _build_report_summary(self, session: LineSession) -> dict:
        coordinates = session.get_data("coordinates", {})
        milepost = session.get_data("milepost", {})
        cost = session.get_data("estimated_cost", None)
        return {
            "district_name": session.get_data("district_name", ""),
            "road": session.get_data("road", ""),
            "coordinates_text": f"{coordinates.get('lat', '-')},{coordinates.get('lon', '-')}" if coordinates else "-",
            "milepost_display": milepost.get("milepost_display", "-"),
            "damage_mode_name": session.get_data("damage_mode_name", ""),
            "damage_cause_names": session.get_data("damage_cause_names", []),
            "description": session.get_data("description", ""),
            "photo_count": session.get_data("photo_count", 0),
            "estimated_cost_text": "未填" if cost is None else f"{cost:.1f} 萬元",
        }

    def _apply_session_to_case(self, case: Case, session: LineSession, user_id: str, display_name: str, real_name: str) -> None:
        district = self._district_by_id(session.get_data("district_id", ""))
        coordinates = session.get_data("coordinates", {})
        milepost = session.get_data("milepost", {})

        case.district_id = session.get_data("district_id", "")
        case.district_name = district.get("name", "") if district else session.get_data("district_name", "")
        case.road_number = session.get_data("road", "")
        case.damage_mode_category = session.get_data("damage_category", "")
        case.damage_mode_id = session.get_data("damage_mode_id", "")
        case.damage_mode_name = session.get_data("damage_mode_name", "")
        case.damage_cause_ids = session.get_data("damage_cause_ids", [])
        case.damage_cause_names = session.get_data("damage_cause_names", [])
        case.description = session.get_data("description", "")
        case.estimated_cost = session.get_data("estimated_cost", None)
        case.photo_count = int(session.get_data("photo_count", 0))
        case.processing_stage = ProcessingStage.PHOTOS_PROCESSED if case.photo_count > 0 else ProcessingStage.INGESTED
        case.review_status = ReviewStatus.PENDING_REVIEW

        if coordinates:
            candidate = CoordinateCandidate(
                lat=float(coordinates.get("lat", 0.0)),
                lon=float(coordinates.get("lon", 0.0)),
                source="manual",
                confidence=1.0,
                label="LINE使用者輸入",
            )
            case.coordinate_candidates = [candidate]
            case.primary_coordinate = candidate

        if milepost:
            case.milepost = MilepostInfo(
                road=milepost.get("road", ""),
                milepost_km=float(milepost.get("milepost_km", 0.0)),
                milepost_display=milepost.get("milepost_display", ""),
                confidence=float(milepost.get("confidence", 0.0)),
                is_interpolated=bool(milepost.get("is_interpolated", False)),
                source=milepost.get("source", "auto"),
            )
            case.processing_stage = ProcessingStage.MILEPOST_RESOLVED

        uploaded = session.get_data("uploaded_evidence", [])
        case.evidence_summary = [
            EvidenceSummary(
                evidence_id=item.get("evidence_id", ""),
                sha256=item.get("sha256", ""),
                original_filename=item.get("original_filename", ""),
                content_type=item.get("content_type", ""),
                photo_type=(session.get_data("photo_annotations", {}).get(str(i), {}).get("photo_type")),
            )
            for i, item in enumerate(uploaded)
        ]

        selected_items = set(session.get_data("site_survey_selected", []))
        survey_items: list[SiteSurveyItem] = []
        for category in self._site_survey:
            for item in category.get("items", []):
                survey_items.append(
                    SiteSurveyItem(
                        category_id=category.get("category_id", ""),
                        item_id=item.get("item_id", ""),
                        item_name=item.get("item_name", ""),
                        checked=item.get("item_id", "") in selected_items,
                    )
                )
        case.site_survey = survey_items
        if case.processing_stage == ProcessingStage.MILEPOST_RESOLVED:
            case.processing_stage = ProcessingStage.COMPLETE

        if case.created_by:
            case.created_by.user_id = user_id
            case.created_by.display_name = display_name
            case.created_by.real_name = real_name

    def _ensure_draft_case(self, session: LineSession, user_id: str, display_name: str, real_name: str) -> str | None:
        if session.draft_case_id:
            return session.draft_case_id
        created = self._cases.create_case(
            user_id=user_id,
            display_name=display_name,
            real_name=real_name,
            district_id=session.get_data("district_id", ""),
            district_name=session.get_data("district_name", ""),
        )
        if created is None:
            return None
        session.draft_case_id = created.case_id
        return created.case_id

    def _case_to_card_dict(self, case: Case) -> dict:
        thumb = ""
        if case.evidence_summary and (session_thumb := self._thumb_for_case(case.case_id, case.evidence_summary[0].evidence_id)):
            thumb = f"{self._settings.app_base_url.rstrip('/')}/cases/{case.case_id}/{session_thumb}"
        return {
            "case_id": case.case_id,
            "district_name": case.district_name,
            "road_number": case.road_number,
            "damage_mode_name": case.damage_mode_name,
            "review_status": case.review_status.value,
            "thumbnail_url": thumb,
        }

    def _case_to_detail_dict(self, case: Case) -> dict:
        coordinate_text = "-"
        if case.primary_coordinate:
            coordinate_text = f"{case.primary_coordinate.lat:.6f},{case.primary_coordinate.lon:.6f}"
        milepost = case.milepost.milepost_display if case.milepost else "-"
        return {
            "case_id": case.case_id,
            "district_name": case.district_name,
            "road_number": case.road_number,
            "milepost": milepost,
            "damage_mode_name": case.damage_mode_name,
            "damage_cause_names": case.damage_cause_names,
            "description": case.description,
            "photo_count": case.photo_count,
            "completeness_pct": case.completeness_pct,
            "review_status": case.review_status.value,
            "coordinate_text": coordinate_text,
        }

    def _thumb_for_case(self, case_id: str, evidence_id: str) -> str:
        evidence = self._evidence.get_evidence(case_id, evidence_id)
        return evidence.thumbnail_path if evidence and evidence.thumbnail_path else ""

    def _parse_postback(self, postback_data: str | None) -> dict[str, str]:
        if not postback_data:
            return {}
        parsed = parse_qs(postback_data, keep_blank_values=True)
        return {key: value[0] if value else "" for key, value in parsed.items()}

    def _parse_coordinates(self, text: str) -> tuple[float, float] | None:
        if not text or "," not in text:
            return None
        left, right = text.split(",", 1)
        try:
            lat = float(left.strip())
            lon = float(right.strip())
        except ValueError:
            return None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None
        return lat, lon

    def _district_by_id(self, district_id: str) -> dict | None:
        return next((item for item in self._districts if item.get("id") == district_id), None)

    def _find_damage_mode(self, mode_id: str) -> dict:
        for modes in self._damage_modes.values():
            found = next((mode for mode in modes if mode.get("id") == mode_id), None)
            if found:
                return found
        return {}

    def _load_json(self, name: str):
        path = Path(__file__).resolve().parents[1] / "data" / name
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
