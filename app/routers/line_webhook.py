from __future__ import annotations

import inspect

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.core.logging_config import get_logger
from app.core.security import verify_line_signature

router = APIRouter()
logger = get_logger(__name__)


async def download_line_content(message_id: str, access_token: str) -> bytes:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://api-data.line.me/v2/bot/message/{message_id}/content",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.content


async def reply_messages(
    reply_token: str,
    messages: list[dict[str, object]],
    access_token: str,
) -> None:
    if not messages or not reply_token:
        return

    async with httpx.AsyncClient() as client:
        await client.post(
            "https://api.line.me/v2/bot/message/reply",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"replyToken": reply_token, "messages": messages[:5]},
            timeout=10.0,
        )


@router.post("")
async def handle_webhook(request: Request):
    settings = request.app.state.settings
    line_flow = request.app.state.line_flow

    body = await request.body()
    signature = request.headers.get("X-Line-Signature", "")

    if not verify_line_signature(body, signature, settings.line_channel_secret):
        raise HTTPException(status_code=401, detail="Invalid LINE signature")

    payload = await request.json()
    events = payload.get("events", [])

    for event in events:
        try:
            event_type = str(event.get("type", ""))
            source = event.get("source", {}) or {}
            source_key = str(source.get("userId", ""))
            reply_token = str(event.get("replyToken", ""))
            event_id = str(
                event.get("webhookEventId")
                or event.get("deliveryContext", {}).get("eventId")
                or event.get("timestamp", "")
            )
            display_name = str(source.get("displayName", ""))

            message_type = ""
            text = None
            postback_data = None
            image_content = None

            if event_type == "message":
                message = event.get("message", {}) or {}
                message_type = str(message.get("type", ""))

                if message_type == "text":
                    text = str(message.get("text", ""))
                elif message_type == "image":
                    message_id = str(message.get("id", ""))
                    if message_id:
                        image_content = await download_line_content(
                            message_id,
                            settings.line_channel_access_token,
                        )
                elif message_type == "location":
                    lat = message.get("latitude")
                    lon = message.get("longitude")
                    if lat is not None and lon is not None:
                        text = f"{lat},{lon}"
                elif message_type == "sticker":
                    text = str(message.get("stickerId", ""))

            elif event_type == "postback":
                postback = event.get("postback", {}) or {}
                postback_data = str(postback.get("data", ""))

            result = line_flow.handle_event(
                event_type=event_type,
                source_key=source_key,
                event_id=event_id,
                display_name=display_name,
                message_type=message_type,
                text=text,
                postback_data=postback_data,
                image_content=image_content,
            )
            if inspect.isawaitable(result):
                result = await result

            response_messages = result if isinstance(result, list) else []
            if response_messages and reply_token:
                await reply_messages(
                    reply_token,
                    response_messages,
                    settings.line_channel_access_token,
                )
        except Exception:
            logger.exception("Failed to process LINE event")

    return {"ok": True}
