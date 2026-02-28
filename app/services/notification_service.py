from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast

import httpx

from app.core.logging_config import get_logger

logger = get_logger(__name__)


class NotificationService:
    """
    LINE push message service.
    Sends notifications to users/managers via LINE Messaging API.
    """

    def __init__(self, channel_access_token: str) -> None:
        self._token: str = channel_access_token
        self._push_url: str = "https://api.line.me/v2/bot/message/push"

    @staticmethod
    def _to_int(value: object) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int | float):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if text.isdigit():
                return int(text)
        return 0

    async def push_message(self, user_id: str, messages: Sequence[Mapping[str, object]]) -> bool:
        """Send push messages to a specific LINE user."""
        if not self._token or not self._token.strip():
            logger.warning("LINE 推播失敗：缺少 channel access token，user_id=%s", user_id)
            return False
        if not user_id.strip() or not messages:
            logger.warning("LINE 推播失敗：參數無效，user_id=%s", user_id)
            return False

        payload = {
            "to": user_id,
            "messages": [dict(message) for message in messages[:5]],
        }
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self._push_url, headers=headers, json=payload)
            if response.is_success:
                logger.info("LINE 推播成功：user_id=%s, messages=%d", user_id, len(payload["messages"]))
                return True

            logger.warning(
                "LINE 推播失敗：user_id=%s, status=%s, body=%s",
                user_id,
                response.status_code,
                response.text,
            )
            return False
        except httpx.HTTPError as exc:
            logger.error("LINE 推播例外：user_id=%s, error=%s", user_id, exc)
            return False

    async def notify_managers(self, message: str, manager_ids: list[str] | None = None) -> int:
        """
        Send notification to all managers or specific manager IDs.
        Returns count of successfully notified managers.
        If manager_ids not provided, this is a no-op (caller should provide IDs).
        """
        if not manager_ids:
            logger.info("未提供管理員名單，略過通知。")
            return 0

        text_message: list[dict[str, object]] = [{"type": "text", "text": message}]
        success_count = 0

        for manager_id in manager_ids:
            if await self.push_message(manager_id, text_message):
                success_count += 1

        logger.info("管理員通知完成：成功 %d / %d", success_count, len(manager_ids))
        return success_count

    async def notify_user(self, user_id: str, message: str) -> bool:
        """Send a simple text notification to a user."""
        return await self.push_message(user_id, [{"type": "text", "text": message}])

    async def notify_new_case(
        self,
        case_id: str,
        district_name: str,
        road: str,
        damage_mode: str,
        manager_ids: list[str],
    ) -> int:
        """Notify managers about a new case submission."""
        bubble = {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {"type": "text", "text": "新案件通報", "weight": "bold", "size": "lg"},
                    {"type": "text", "text": f"案件編號：{case_id}", "wrap": True},
                    {"type": "text", "text": f"工務段：{district_name}", "wrap": True},
                    {"type": "text", "text": f"道路：{road}", "wrap": True},
                    {"type": "text", "text": f"災害型態：{damage_mode}", "wrap": True},
                ],
            },
        }
        message: list[dict[str, object]] = [
            {
                "type": "flex",
                "altText": f"新案件 {case_id} 已送出",
                "contents": bubble,
            }
        ]

        success_count = 0
        for manager_id in manager_ids:
            if await self.push_message(manager_id, message):
                success_count += 1

        logger.info("新案件通知完成：case_id=%s, 成功 %d / %d", case_id, success_count, len(manager_ids))
        return success_count

    async def notify_case_status_change(self, case_id: str, new_status: str, user_id: str, note: str = "") -> bool:
        """Notify the case creator about status change."""
        status_text_map = {
            "approved": "案件已審核通過，將進入後續處理流程。",
            "returned": "案件已退回，請依退回原因修正後重新送出。",
            "closed": "案件已結案，感謝您的通報。",
        }
        message = status_text_map.get(new_status, f"案件狀態已更新為：{new_status}")
        if note.strip():
            message = f"{message}\n備註：{note.strip()}"
        return await self.notify_user(user_id, f"【案件 {case_id}】{message}")

    async def notify_case_returned(self, case_id: str, reason: str, user_id: str) -> bool:
        """Notify user their case was returned with reason."""
        text = f"【案件 {case_id} 已退回】\n退回原因：{reason.strip() or '未提供'}\n請補充資料後再送出。"
        return await self.notify_user(user_id, text)

    async def send_daily_summary(self, manager_id: str, stats: dict[str, object]) -> bool:
        """Send daily statistics summary to a manager."""
        by_status_raw = stats.get("by_status")
        by_district_raw = stats.get("by_district")

        by_status: dict[str, object] = {}
        by_district: dict[str, object] = {}
        if isinstance(by_status_raw, dict):
            status_dict = cast(dict[object, object], by_status_raw)
            by_status = {str(key): value for key, value in status_dict.items()}
        if isinstance(by_district_raw, dict):
            district_dict = cast(dict[object, object], by_district_raw)
            by_district = {str(key): value for key, value in district_dict.items()}

        total_raw = stats.get("total", 0)
        total = self._to_int(total_raw)

        pending = self._to_int(by_status.get("pending_review", 0))
        in_progress = self._to_int(by_status.get("in_progress", 0))
        closed = self._to_int(by_status.get("closed", 0))
        returned = self._to_int(by_status.get("returned", 0))
        lines = [
            "【每日案件摘要】",
            f"日期：{datetime.now().strftime('%Y-%m-%d')}",
            f"總案件數：{total}",
            "",
            "狀態統計：",
            f"- 待審核：{pending}",
            f"- 處理中：{in_progress}",
            f"- 已結案：{closed}",
            f"- 已退回：{returned}",
            "",
            "工務段統計：",
        ]

        if by_district:
            for district, count in by_district.items():
                lines.append(f"- {district}：{self._to_int(count)}")
        else:
            lines.append("- 無資料")

        return await self.notify_user(manager_id, "\n".join(lines))
