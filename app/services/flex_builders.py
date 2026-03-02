# pyright: basic
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode


SUCCESS_COLOR = "#1DB446"
URGENT_COLOR = "#FF6B6B"
INFO_COLOR = "#4A90D9"
NEUTRAL_COLOR = "#888888"
JUDGMENT_COLOR = "#E8A317"
EXCLUSION_COLOR = "#CCCCCC"


def _data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data"


@lru_cache(maxsize=1)
def _districts() -> list[dict]:
    with open(_data_dir() / "districts.json", "r", encoding="utf-8") as file:
        return json.load(file)


@lru_cache(maxsize=1)
def _damage_modes() -> dict:
    with open(_data_dir() / "damage_modes.json", "r", encoding="utf-8") as file:
        return json.load(file)


@lru_cache(maxsize=1)
def _photo_tags() -> dict:
    with open(_data_dir() / "photo_tags.json", "r", encoding="utf-8") as file:
        return json.load(file)


@lru_cache(maxsize=1)
def _site_survey() -> list[dict]:
    with open(_data_dir() / "site_survey.json", "r", encoding="utf-8") as file:
        return json.load(file)


def _resolve_photo_tags(photo_type: str, disaster_type: str = "") -> dict | None:
    """Resolve photo tag definition from hierarchical photo_tags.json.

    P1, P3 are in 'common'. P2, P4 are disaster-type-specific.
    Falls back to common if disaster_type not found.
    """
    data = _photo_tags()
    common = data.get("common", {})
    if photo_type in common:
        return common[photo_type]
    if disaster_type:
        type_specific = data.get(disaster_type, {})
        if photo_type in type_specific:
            return type_specific[photo_type]
    for key in ["revetment_retaining", "road_slope", "bridge"]:
        section = data.get(key, {})
        if photo_type in section:
            return section[photo_type]
    # Check optional section (P5-P10)
    optional_section = data.get("optional", {})
    if photo_type in optional_section:
        return optional_section[photo_type]
    return None

def _postback_data(action: str, **kwargs: str | int | float) -> str:
    payload = {"action": action}
    payload.update({k: str(v) for k, v in kwargs.items()})
    return urlencode(payload)


def _quick_reply_items(items: list[dict]) -> dict:
    return {"items": [{"type": "action", "action": item} for item in items[:13]]}


class FlexBuilder:
    @staticmethod
    def text_message(text: str) -> dict:
        return {"type": "text", "text": text}

    @staticmethod
    def quick_reply_message(text: str, items: list[dict]) -> dict:
        return {
            "type": "text",
            "text": text,
            "quickReply": _quick_reply_items(items),
        }

    @staticmethod
    def confirm_message(text: str, yes_data: str, no_data: str) -> dict:
        return {
            "type": "template",
            "altText": "請確認操作",
            "template": {
                "type": "confirm",
                "text": text,
                "actions": [
                    {"type": "postback", "label": "確認", "data": yes_data},
                    {"type": "postback", "label": "取消", "data": no_data},
                ],
            },
        }

    @staticmethod
    def district_quick_reply(include_all: bool = True) -> dict:
        districts = _districts()
        if not include_all:
            districts = [d for d in districts if d["id"] != "all"]
        items = [
            {
                "type": "postback",
                "label": district["name"],
                "data": _postback_data("select_district", district_id=district["id"]),
                "displayText": district["name"],
            }
            for district in districts
        ]
        return FlexBuilder.quick_reply_message(
            "請選擇工務段：\n\n💡 輸入「取消」可取消流程，輸入「返回」可回上一步。",
            items,
        )

    @staticmethod
    def road_quick_reply(district_id: str) -> dict:
        district = next((item for item in _districts() if item["id"] == district_id), None)
        roads = district.get("roads", []) if district else []
        items = [
            {
                "type": "postback",
                "label": road,
                "data": _postback_data("select_road", district_id=district_id, road=road),
                "displayText": road,
            }
            for road in roads
        ]
        return FlexBuilder.quick_reply_message(
            "請選擇道路：\n\n💡 輸入「取消」可取消流程，輸入「返回」可回上一步。",
            items,
        )

    @staticmethod
    def damage_mode_carousel() -> dict:
        categories = [
            ("revetment_retaining", "護岸/擋土牆類", "護岸、擋土牆、排水設施等災損"),
            ("road_slope", "道路邊坡類", "落石、崩塌、滑動、路基流失等"),
            ("bridge", "橋梁類", "橋梁構造、橋墩、引道等損害"),
        ]
        bubbles = []
        for category_id, title, description in categories:
            bubbles.append(
                {
                    "type": "bubble",
                    "header": {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": INFO_COLOR,
                        "contents": [{"type": "text", "text": title, "weight": "bold", "color": "#FFFFFF"}],
                    },
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [{"type": "text", "text": description, "wrap": True, "size": "sm"}],
                    },
                    "footer": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "button",
                                "style": "primary",
                                "color": SUCCESS_COLOR,
                                "action": {
                                    "type": "postback",
                                    "label": "選擇",
                                    "data": _postback_data("select_damage_category", category=category_id),
                                    "displayText": f"選擇{title}",
                                },
                            }
                        ],
                    },
                }
            )
        return {
            "type": "flex",
            "altText": "請選擇災害類別",
            "contents": {"type": "carousel", "contents": bubbles},
        }

    @staticmethod
    def damage_mode_list(category: str) -> dict:
        modes = _damage_modes().get(category, [])
        items = [
            {
                "type": "postback",
                "label": mode["mode_name"][:20],
                "data": _postback_data(
                    "select_damage_mode",
                    category=category,
                    mode_id=mode["id"],
                ),
                "displayText": mode["mode_name"],
            }
            for mode in modes
        ]
        return FlexBuilder.quick_reply_message("請選擇災損型態：", items)

    @staticmethod
    def damage_cause_quick_reply(mode_id: str) -> dict:
        mode = None
        for modes in _damage_modes().values():
            found = next((item for item in modes if item["id"] == mode_id), None)
            if found:
                mode = found
                break

        causes = mode.get("causes", []) if mode else []
        has_earthquake = any(cause.get("name") == "地震" for cause in causes)
        if not has_earthquake:
            causes = causes + [{"id": "common_cause_earthquake", "name": "地震"}]
        items = [
            {
                "type": "postback",
                "label": cause["name"],
                "data": _postback_data("select_damage_cause", cause_id=cause["id"], cause_name=cause["name"]),
                "displayText": cause["name"],
            }
            for cause in causes
        ]
        items.append(
            {
                "type": "postback",
                "label": "完成選擇",
                "data": _postback_data("finish_damage_cause"),
                "displayText": "完成災因選擇",
            }
        )
        return FlexBuilder.quick_reply_message("請選擇災害原因（可複選）：", items)

    @staticmethod
    def photo_type_quick_reply() -> dict:
        photo_tags = _photo_tags()
        items = []
        for photo_type in sorted(photo_tags.keys(), key=lambda x: int(x[1:])):
            info = photo_tags[photo_type]
            items.append(
                {
                    "type": "postback",
                    "label": f"{photo_type} {info['name']}"[:20],
                    "data": _postback_data("select_photo_type", photo_type=photo_type),
                    "displayText": f"{photo_type} {info['name']}",
                }
            )
        return FlexBuilder.quick_reply_message("請選擇照片類型：", items)

    @staticmethod
    def guided_photo_prompt(photo_number: int, photo_type: str, photo_name: str, photo_desc: str) -> dict:
        """Prompt for uploading a specific photo type in the guided flow."""
        hint = "\n\n💡 輸入「取消」可取消流程，輸入「返回」可回上一步。"
        display_name = photo_name or photo_type
        return FlexBuilder.text_message(f"📸 請上傳第{photo_number}張照片：{display_name}\n{photo_desc}{hint}")

    @staticmethod
    def optional_photo_chooser(already_uploaded_types: list[str], damage_category: str = "") -> dict:
        """Show Flex Bubble with optional photo types P5-P10 and P1-P4 supplement."""
        photo_tags = _photo_tags()
        optional_section = photo_tags.get("optional", {})
        buttons: list[dict] = []
        for photo_type in ["P5", "P6", "P7", "P8", "P9", "P10"]:
            if photo_type in already_uploaded_types:
                continue
            info = optional_section.get(photo_type, {})
            name = info.get("name", photo_type)
            desc = info.get("description", "")
            buttons.append({
                "type": "box",
                "layout": "horizontal",
                "margin": "md",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "flex": 4,
                        "contents": [
                            {"type": "text", "text": f"{photo_type} {name}", "weight": "bold", "size": "sm", "color": "#333333"},
                            {"type": "text", "text": desc, "size": "xs", "color": "#888888", "wrap": True},
                        ],
                    },
                    {
                        "type": "button",
                        "flex": 2,
                        "style": "primary",
                        "color": INFO_COLOR,
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": "上傳",
                            "data": _postback_data("choose_optional_type", photo_type=photo_type),
                            "displayText": f"上傳{name}",
                        },
                    },
                ],
            })

        # --- P1-P4 supplement section ---
        common = photo_tags.get("common", {})
        type_specific = photo_tags.get(damage_category, {}) if damage_category else {}
        supplement_buttons: list[dict] = []
        p1p4_prompts = {
            "P1": "記錄災點整體環境與現場概況。",
            "P2": "拍攝邊坡整體型態、崩塌範圍與既有保護設施。",
            "P3": "拍攝目前會再致災的邊坡細節，清楚呈現損壞狀況。",
            "P4": "記錄道路路面狀況與影響範圍。",
        }
        for photo_type in ["P1", "P2", "P3", "P4"]:
            info = type_specific.get(photo_type) or common.get(photo_type, {})
            name = info.get("name", photo_type)
            desc = p1p4_prompts.get(photo_type, "")
            uploaded = photo_type in already_uploaded_types
            status_icon = "✅ " if uploaded else ""
            supplement_buttons.append({
                "type": "box",
                "layout": "horizontal",
                "margin": "md",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "flex": 4,
                        "contents": [
                            {"type": "text", "text": f"{status_icon}{photo_type} {name}", "weight": "bold", "size": "sm", "color": "#333333"},
                            {"type": "text", "text": desc, "size": "xs", "color": "#888888", "wrap": True},
                        ],
                    },
                    {
                        "type": "button",
                        "flex": 2,
                        "style": "primary",
                        "color": "#999999" if uploaded else JUDGMENT_COLOR,
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": "補傳" if uploaded else "上傳",
                            "data": _postback_data("choose_supplement_type", photo_type=photo_type),
                            "displayText": f"補傳{name}" if uploaded else f"上傳{name}",
                        },
                    },
                ],
            })

        # Finish button at bottom
        finish_btn = {
            "type": "button",
            "style": "primary",
            "color": SUCCESS_COLOR,
            "margin": "xl",
            "action": {
                "type": "postback",
                "label": "✅ 完成照片上傳",
                "data": _postback_data("finish_photos"),
                "displayText": "完成照片上傳",
            },
        }
        body_contents: list[dict] = [
            {"type": "text", "text": "✅ 4張必要照片已完成！", "weight": "bold", "size": "lg", "color": SUCCESS_COLOR},
            {"type": "text", "text": "以下為選填照片，可協助後續報告與 AI 分析：", "size": "xs", "color": "#888888", "wrap": True, "margin": "sm"},
            {"type": "separator", "margin": "md"},
        ]
        body_contents.extend(buttons)
        body_contents.append({"type": "separator", "margin": "lg"})
        body_contents.append({"type": "text", "text": "📸 補傳必要照片", "weight": "bold", "size": "md", "color": JUDGMENT_COLOR, "margin": "lg"})
        body_contents.append({"type": "text", "text": "如需補拍或追加必要照片，可點選下方按鈕：", "size": "xs", "color": "#888888", "wrap": True, "margin": "sm"})
        body_contents.extend(supplement_buttons)
        body_contents.append(finish_btn)
        bubble = {
            "type": "bubble",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": SUCCESS_COLOR,
                "paddingAll": "12px",
                "contents": [{"type": "text", "text": "📷 選填照片", "color": "#FFFFFF", "weight": "bold", "size": "md"}],
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": body_contents,
            },
        }
        return {"type": "flex", "altText": "必要照片已完成，請選擇選填照片或完成", "contents": bubble}

    @staticmethod
    def tag_category_buttons(photo_index: int, category: dict, selected_tags: list[str]) -> dict:
        selected = set(selected_tags)
        actions = []
        for tag in category.get("tags", []):
            label = f"✓{tag['label']}" if tag["id"] in selected else tag["label"]
            actions.append(
                {
                    "type": "button",
                    "style": "secondary" if tag["id"] in selected else "primary",
                    "color": NEUTRAL_COLOR if tag["id"] in selected else INFO_COLOR,
                    "margin": "sm",
                    "adjustMode": "shrink-to-fit",
                    "action": {
                        "type": "postback",
                        "label": label[:20],
                        "data": _postback_data(
                            "tag",
                            photo=photo_index,
                            cat=category.get("category_id", ""),
                            tag=tag.get("id", ""),
                        ),
                        "displayText": tag["label"],
                    },
                }
            )

        actions.append(
            {
                "type": "button",
                "style": "primary",
                "color": SUCCESS_COLOR,
                "margin": "md",
                "action": {
                    "type": "postback",
                    "label": "完成此類別",
                    "data": _postback_data(
                        "finish_tag_category",
                        photo=photo_index,
                        cat=category.get("category_id", ""),
                    ),
                    "displayText": "完成此類別",
                },
            }
        )

        return {
            "type": "flex",
            "altText": "請選擇標註標籤",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [{"type": "text", "text": category.get("category_name", "標籤"), "color": "#FFFFFF", "weight": "bold"}],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": actions,
                },
            },
        }

    @staticmethod
    def site_survey_flex(categories: list[dict]) -> dict:
        contents = []
        for category in categories:
            contents.append(
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "md",
                    "contents": [
                        {"type": "text", "text": category.get("category_name", ""), "weight": "bold", "size": "sm"},
                        {
                            "type": "text",
                            "text": "、".join(item.get("item_name", "") for item in category.get("items", [])) or "無",
                            "wrap": True,
                            "size": "xs",
                            "color": NEUTRAL_COLOR,
                        },
                    ],
                }
            )
        return {
            "type": "flex",
            "altText": "現勘檢核表",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [{"type": "text", "text": "現勘項目（可複選）", "weight": "bold", "color": "#FFFFFF"}],
                },
                "body": {"type": "box", "layout": "vertical", "contents": contents},
            },
        }

    @staticmethod
    def cost_item_prompt_flex(item_index: int, item_name: str, unit: str, unit_price: float | None, input_type: str) -> dict:
        index_text = f"項目 {item_index + 1}/6: {item_name}"
        if input_type == "quantity":
            prompt_text = f"{index_text}\n單價: {(unit_price or 0):,.0f}元/{unit}\n請輸入數量（{unit}）："
        else:
            prompt_text = f"{index_text}\n請輸入金額（元）："

        return {
            "type": "flex",
            "altText": f"{item_name}輸入",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [{"type": "text", "text": "初估經費試算", "weight": "bold", "color": "#FFFFFF"}],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": prompt_text, "wrap": True, "size": "sm"},
                    ],
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "style": "secondary",
                            "action": {
                                "type": "postback",
                                "label": "跳過",
                                "data": _postback_data("cost_skip"),
                                "displayText": "跳過",
                            },
                        }
                    ],
                },
            },
        }

    @staticmethod
    def cost_summary_flex(cost_items: list[dict], total: float) -> dict:
        rows: list[dict] = []
        for item in cost_items:
            item_name = item.get("item_name", "")
            amount = item.get("amount")
            input_quantity = item.get("quantity")
            unit = item.get("unit", "")
            unit_price = item.get("unit_price")

            if not amount:
                line = f"{item_name}: -"
            elif input_quantity is not None and unit_price is not None:
                line = f"{item_name}: {input_quantity:g} {unit} × {unit_price:,.0f} = {amount:,.0f}元"
            else:
                line = f"{item_name}: {amount:,.0f}元"
            rows.append({"type": "text", "text": line, "size": "sm", "wrap": True, "margin": "sm"})

        rows.append({"type": "separator", "margin": "md"})
        rows.append(
            {
                "type": "text",
                "text": f"合計: {total:,.0f}元 ({total/10000:.1f}萬元)",
                "size": "md",
                "weight": "bold",
                "color": SUCCESS_COLOR,
                "margin": "md",
            }
        )

        return {
            "type": "flex",
            "altText": "初估經費總覽",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [{"type": "text", "text": "經費明細確認", "weight": "bold", "color": "#FFFFFF"}],
                },
                "body": {"type": "box", "layout": "vertical", "contents": rows},
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": SUCCESS_COLOR,
                            "action": {
                                "type": "postback",
                                "label": "確認",
                                "data": _postback_data("cost_confirm"),
                                "displayText": "確認",
                            },
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "action": {
                                "type": "postback",
                                "label": "重新填寫",
                                "data": _postback_data("cost_redo"),
                                "displayText": "重新填寫",
                            },
                        },
                    ],
                },
            },
        }

    @staticmethod
    def case_summary_flex(case: dict) -> dict:
        return {
            "type": "flex",
            "altText": f"案件摘要 {case.get('case_id', '')}",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [{"type": "text", "text": case.get("case_id", "案件"), "weight": "bold", "color": "#FFFFFF"}],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": f"工務段：{case.get('district_name', '-')}", "size": "sm"},
                        {"type": "text", "text": f"道路：{case.get('road_number', '-')}", "size": "sm"},
                        {"type": "text", "text": f"審查狀態：{case.get('review_status', '-')}", "size": "sm"},
                    ],
                },
            },
        }

    @staticmethod
    def case_list_carousel(cases: list[dict]) -> dict:
        """Build a carousel of case cards. Handles missing thumbnails and empty fields."""
        PLACEHOLDER_IMG = "https://dummyimage.com/800x400/e9eef3/888888&text=No+Photo"
        bubbles = []
        for case in cases[:10]:
            thumb_url = case.get("thumbnail_url") or ""
            # LINE requires https:// for hero images
            has_valid_hero = thumb_url.startswith("https://")
            bubble: dict = {"type": "bubble"}
            if has_valid_hero:
                bubble["hero"] = {
                    "type": "image",
                    "url": thumb_url,
                    "size": "full",
                    "aspectRatio": "20:13",
                    "aspectMode": "cover",
                }
            bubble["body"] = {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": case.get("case_id") or "(無編號)", "weight": "bold", "wrap": True},
                    {"type": "text", "text": f"{case.get('district_name') or '-'}/{case.get('road_number') or '-'}", "size": "sm", "color": NEUTRAL_COLOR},
                    {"type": "text", "text": case.get("damage_mode_name") or "未填", "size": "sm", "wrap": True},
                ],
            }
            bubble["footer"] = {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": INFO_COLOR,
                        "action": {
                            "type": "postback",
                            "label": "查看",
                            "data": _postback_data("open_case", case_id=case.get("case_id", "")),
                        },
                    }
                ],
            }
            bubbles.append(bubble)
        return {
            "type": "flex",
            "altText": "案件列表",
            "contents": {"type": "carousel", "contents": bubbles or [{"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": "目前沒有案件"}]}}]},
        }

    @staticmethod
    def case_detail_flex(case: dict, include_review_actions: bool = True) -> dict:
        sections = [
            ("位置資訊", [f"工務段：{case.get('district_name') or '-'}", f"道路：{case.get('road_number') or '-'}", f"里程：{case.get('milepost') or '-'}"]),
            ("災情描述", [f"類型：{case.get('damage_mode_name') or '-'}", f"原因：{','.join(case.get('damage_cause_names', [])) or '-'}", f"描述：{case.get('description') or '-'}"]),
            ("現勘摘要", [f"照片數：{case.get('photo_count', 0)}", f"完整度：{case.get('completeness_pct', 0)}%", f"狀態：{case.get('review_status') or '-'}"]),
            ("座標", [case.get("coordinate_text") or "-"]),
        ]
        body_contents = []
        for title, lines in sections:
            body_contents.append({"type": "text", "text": title or "-", "weight": "bold", "margin": "md"})
            for line in lines:
                body_contents.append({"type": "text", "text": line or "-", "size": "sm", "wrap": True, "color": NEUTRAL_COLOR})

        return {
            "type": "flex",
            "altText": f"案件詳情 {case.get('case_id') or ''}",
            "contents": {
                "type": "bubble",
                "header": {"type": "box", "layout": "vertical", "backgroundColor": INFO_COLOR, "contents": [{"type": "text", "text": case.get("case_id") or "(無編號)", "color": "#FFFFFF", "weight": "bold"}]},
                "body": {"type": "box", "layout": "vertical", "contents": body_contents},
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": (
                        [
                            {"type": "button", "style": "primary", "color": SUCCESS_COLOR, "action": {"type": "postback", "label": "通過", "data": _postback_data("review_action", decision="approve", case_id=case.get("case_id", ""))}},
                            {"type": "button", "style": "secondary", "action": {"type": "postback", "label": "退回", "data": _postback_data("review_action", decision="return", case_id=case.get("case_id", ""))}},
                            {"type": "button", "style": "primary", "color": URGENT_COLOR, "action": {"type": "postback", "label": "結案", "data": _postback_data("review_action", decision="close", case_id=case.get("case_id", ""))}},
                        ]
                        if include_review_actions
                        else []
                    ),
                },
            },
        }

    @staticmethod
    def statistics_flex(stats: dict, stats_url: str = "") -> dict:
        total = stats.get("total_cases", 0)
        by_status = stats.get("by_status", {})
        by_district = stats.get("by_district", {})
        today_new = stats.get("today_new", 0)
        
        # Get district mapping
        districts_list = _districts()
        district_map = {d["id"]: d["name"] for d in districts_list}
        
        body = []
        
        # Row 1: Total cases + today new
        body.append({
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": f"總案件 {total} 件",
                    "weight": "bold",
                    "size": "md",
                    "flex": 1
                },
                {
                    "type": "text",
                    "text": f"今日 +{today_new}",
                    "color": URGENT_COLOR,
                    "size": "sm",
                    "align": "end",
                    "flex": 1
                }
            ]
        })
        
        # Row 2: Status metric boxes (4 columns)
        status_colors = {
            "pending_review": "#FF9800",
            "in_progress": "#2196F3",
            "closed": "#4CAF50",
            "returned": "#F44336"
        }
        status_labels = {
            "pending_review": "待處理",
            "in_progress": "處理中",
            "closed": "已結案",
            "returned": "退回"
        }
        
        status_boxes = []
        for key in ["pending_review", "in_progress", "closed", "returned"]:
            count = by_status.get(key, 0)
            status_boxes.append({
                "type": "box",
                "layout": "vertical",
                "flex": 1,
                "spacing": "sm",
                "contents": [
                    {
                        "type": "text",
                        "text": str(count),
                        "size": "xxl",
                        "weight": "bold",
                        "color": status_colors[key],
                        "align": "center"
                    },
                    {
                        "type": "text",
                        "text": status_labels[key],
                        "size": "xs",
                        "color": NEUTRAL_COLOR,
                        "align": "center"
                    }
                ]
            })
        
        body.append({
            "type": "box",
            "layout": "horizontal",
            "spacing": "sm",
            "contents": status_boxes
        })
        
        # Separator
        body.append({"type": "separator", "margin": "md"})
        
        # District statistics section
        body.append({
            "type": "text",
            "text": "各工務段件數",
            "weight": "bold",
            "size": "sm",
            "margin": "md"
        })
        
        # Sort districts by count (descending)
        sorted_districts = sorted(
            by_district.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        for district_id, count in sorted_districts:
            district_name = district_map.get(district_id, district_id)
            body.append({
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {
                        "type": "text",
                        "text": district_name,
                        "flex": 1,
                        "size": "sm"
                    },
                    {
                        "type": "text",
                        "text": f"{count} 件",
                        "weight": "bold",
                        "align": "end",
                        "size": "sm"
                    }
                ]
            })
        
        footer = None
        if stats_url:
            footer = {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "button",
                        "action": {
                            "type": "uri",
                            "uri": stats_url,
                            "label": "📊 查看完整統計"
                        },
                        "style": "primary",
                        "color": INFO_COLOR
                    }
                ]
            }
        
        contents = {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": INFO_COLOR,
                "paddingAll": "16px",
                "contents": [
                    {
                        "type": "text",
                        "text": "📊 案件統計摘要",
                        "color": "#FFFFFF",
                        "size": "lg",
                        "weight": "bold"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": body
            }
        }
        
        if footer:
            contents["footer"] = footer
        
        return {
            "type": "flex",
            "altText": f"統計摘要：共 {total} 件案件",
            "contents": contents
        }

    @staticmethod
    def registration_confirm_flex(data: dict) -> dict:
        return {
            "type": "flex",
            "altText": "註冊資料確認",
            "contents": {
                "type": "bubble",
                "header": {"type": "box", "layout": "vertical", "backgroundColor": INFO_COLOR, "contents": [{"type": "text", "text": "註冊資料確認", "color": "#FFFFFF", "weight": "bold"}]},
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": f"姓名：{data.get('real_name', '-')}", "size": "sm"},
                        {"type": "text", "text": f"角色：{data.get('role_name', '-')}", "size": "sm"},
                        {"type": "text", "text": f"工務段：{data.get('district_name', '-')}", "size": "sm"},
                    ],
                },
            },
        }

    @staticmethod
    def report_confirm_flex(data: dict) -> dict:
        lines = [
            f"工務段：{data.get('district_name', '-')}",
            f"道路：{data.get('road', '-')}",
            f"座標：{data.get('coordinates_text', '-')}",
            f"里程：{data.get('milepost_display', '-')}",
            f"災損：{data.get('damage_mode_name', '-')}",
            f"災因：{','.join(data.get('damage_cause_names', [])) or '-'}",
            f"照片：{data.get('photo_count', 0)} 張",
            f"行政區：{data.get('county_name', '') + data.get('town_name', '') + data.get('village_name', '') or '-'}",
            f"國家公園：{data.get('national_park', '') or '否'}",
            f"工程名稱：{data.get('project_name', '') or '-'}",
            f"災害日期：{data.get('disaster_date', '') or '-'}",
            f"鄰近地標：{data.get('nearby_landmark', '') or '略過後補'}",
            f"初估經費：{data.get('estimated_cost_text', '未填')}",
            f"災害類型：{data.get('disaster_type', '-')}",
            f"處理類型：{data.get('processing_type', '-')}",
            f"重複致災：{data.get('repeat_disaster', '-')}",
            f"致災年份：{data.get('repeat_disaster_year', '') or '-'}",
            f"原設計保護：{data.get('original_protection', '-')}",
            f"分析與檢討：{data.get('analysis_review', '') or '略過後補'}",
            f"設計圖說：{'已上傳' if data.get('design_doc_uploaded') else '略過後補'}",
            f"水土保持：{data.get('soil_conservation', '-')}",
            f"安全評估：{data.get('safety_assessment', '') or '略過後補'}",
            f"工址危害：{data.get('hazard_summary_text', '') or '略過後補'}",
            f"其他補充：{data.get('other_supplement', '') or '略過後補'}",
        ]
        body = [{"type": "text", "text": line, "size": "sm", "wrap": True, "margin": "sm"} for line in lines]
        body.append({"type": "separator", "margin": "md"})
        body.append({"type": "text", "text": f"描述：{data.get('description', '-')}", "size": "sm", "wrap": True, "margin": "md"})
        return {
            "type": "flex",
            "altText": "案件送出確認",
            "contents": {
                "type": "bubble",
                "header": {"type": "box", "layout": "vertical", "backgroundColor": SUCCESS_COLOR, "contents": [{"type": "text", "text": "案件送出確認", "weight": "bold", "color": "#FFFFFF"}]},
                "body": {"type": "box", "layout": "vertical", "contents": body},
            },
        }

    @staticmethod
    def profile_flex(user: dict, *, show_actions: bool = True) -> dict:
        """Build profile card with optional action buttons."""
        status_name = user.get('status_name', '-')
        status_value = user.get('status', '')  # raw enum value
        body_contents: list[dict] = [
            {"type": "text", "text": f"姓名：{user.get('real_name', '-')}", "size": "sm"},
            {"type": "text", "text": f"顯示名稱：{user.get('display_name', '-')}", "size": "sm"},
            {"type": "text", "text": f"角色：{user.get('role_name', '-')}", "size": "sm"},
            {"type": "text", "text": f"帳號狀態：{status_name}", "size": "sm"},
            {"type": "text", "text": f"工務段：{user.get('district_name', '-')}", "size": "sm"},
        ]

        footer_buttons: list[dict] = []
        if show_actions:
            # 更改資訊: all statuses
            footer_buttons.append({
                "type": "button", "style": "primary",
                "action": {"type": "postback", "label": "✒️ 更改資訊", "data": _postback_data("edit_profile")},
            })
            # 再次申請: only for rejected/suspended
            if status_value in ('rejected', 'suspended'):
                footer_buttons.append({
                    "type": "button", "style": "secondary",
                    "action": {"type": "postback", "label": "🔄 再次申請", "data": _postback_data("reapply")},
                })

        bubble: dict = {
            "type": "bubble",
            "header": {"type": "box", "layout": "vertical", "backgroundColor": INFO_COLOR, "contents": [{"type": "text", "text": "個人資訊", "weight": "bold", "color": "#FFFFFF"}]},
            "body": {"type": "box", "layout": "vertical", "contents": body_contents},
        }
        if footer_buttons:
            bubble["footer"] = {
                "type": "box", "layout": "vertical", "spacing": "sm",
                "contents": footer_buttons,
            }

        return {
            "type": "flex",
            "altText": "個人資訊",
            "contents": bubble,
        }

    @staticmethod
    def help_message() -> dict:
        lines = [
            "可用指令：",
            "- 通報災害：開始填報災情",
            "- 我的案件 / 查詢案件：查看案件進度",
            "- 查看地圖：開啟 WebGIS",
            "- 審核待辦：決策人員案件審核",
            "- 統計摘要：查看系統統計",
            "- 個人資訊：查看帳號資料",
            "- 選單：開啟功能選單卡片（電腦版必用）",
            "- 取消：中止目前流程",
            "- 返回：返回上一步",
            "",
            "💻 電腦版用戶請輸入「選單」開啟可點選的功能列表",
        ]
        return FlexBuilder.text_message("\n".join(lines))

    @staticmethod
    def main_menu_flex(is_manager: bool = False) -> dict:
        """精緻版 Flex Bubble 功能選單 — 分類分組、色彩標識、桌機/手機通用。"""

        # ── Helper: category header with colored left accent bar ──
        def _category_header(label: str, accent_color: str) -> dict:
            return {
                "type": "box", "layout": "horizontal",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "box", "layout": "vertical",
                        "width": "4px", "backgroundColor": accent_color,
                        "contents": [{"type": "filler"}],
                    },
                    {
                        "type": "text", "text": label,
                        "weight": "bold", "size": "sm", "color": "#333333",
                    },
                ],
            }

        # ── Helper: clickable function row (icon + name + description) ──
        def _func_row(emoji: str, name: str, desc: str, action_name: str, display: str, accent: str) -> dict:
            return {
                "type": "box", "layout": "horizontal",
                "spacing": "md",
                "paddingAll": "md",
                "cornerRadius": "md",
                "borderWidth": "light",
                "borderColor": "#E8E8E8",
                "action": {
                    "type": "postback",
                    "data": _postback_data(action_name),
                    "displayText": display,
                },
                "contents": [
                    {
                        "type": "box", "layout": "vertical",
                        "width": "40px", "height": "40px",
                        "cornerRadius": "xl",
                        "backgroundColor": accent + "18",
                        "justifyContent": "center", "alignItems": "center",
                        "contents": [{"type": "text", "text": emoji, "size": "lg", "align": "center"}],
                    },
                    {
                        "type": "box", "layout": "vertical",
                        "flex": 1,
                        "contents": [
                            {"type": "text", "text": name, "weight": "bold", "size": "sm", "color": "#333333"},
                            {"type": "text", "text": desc, "size": "xxs", "color": "#999999", "wrap": True},
                        ],
                    },
                    {
                        "type": "text", "text": "›",
                        "size": "xl", "color": "#CCCCCC",
                        "gravity": "center", "align": "end",
                    },
                ],
            }

        # ── Build category groups ──
        group_emergency = {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [
                _category_header("緊急操作", URGENT_COLOR),
                _func_row("🚨", "通報災害", "快速通報邊坡災害事件", "start_report", "通報災害", URGENT_COLOR),
            ],
        }

        mgmt_items: list[dict] = [
            _category_header("案件管理", INFO_COLOR),
            _func_row("🔍", "查詢案件", "查看與追蹤通報案件", "query_cases", "查詢案件", INFO_COLOR),
        ]
        if is_manager:
            mgmt_items.append(
                _func_row("📝", "審核待辦", "審核案件與人員申請", "review_pending", "審核待辦", JUDGMENT_COLOR),
            )
        group_management = {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": mgmt_items,
        }

        group_tools = {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [
                _category_header("資訊工具", SUCCESS_COLOR),
                _func_row("🗺️", "查看地圖", "開啟 WebGIS 災害地圖", "view_map", "查看地圖", SUCCESS_COLOR),
                _func_row("📊", "統計摘要", "瀏覽災害統計數據", "statistics", "統計摘要", SUCCESS_COLOR),
            ],
        }

        group_personal = {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": [
                _category_header("個人設定", NEUTRAL_COLOR),
                _func_row("👤", "個人資訊", "查看與修改個人檔案", "profile", "個人資訊", NEUTRAL_COLOR),
                _func_row("❓", "操作說明", "查看系統使用指南", "help", "操作說明", NEUTRAL_COLOR),
            ],
        }

        # ── Assemble bubble ──
        bubble: dict = {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box", "layout": "vertical",
                "backgroundColor": "#1B2838",
                "paddingAll": "xl",
                "contents": [
                    {
                        "type": "text", "text": "📋 邊坡災害通報系統",
                        "weight": "bold", "size": "lg", "color": "#FFFFFF",
                    },
                    {
                        "type": "text", "text": "點選下方功能開始操作",
                        "size": "xxs", "color": "#FFFFFFAA",
                        "margin": "sm",
                    },
                ],
            },
            "body": {
                "type": "box", "layout": "vertical",
                "spacing": "lg", "paddingAll": "lg",
                "contents": [
                    group_emergency,
                    {"type": "separator", "color": "#F0F0F0"},
                    group_management,
                    {"type": "separator", "color": "#F0F0F0"},
                    group_tools,
                    {"type": "separator", "color": "#F0F0F0"},
                    group_personal,
                ],
            },
            "footer": {
                "type": "box", "layout": "vertical",
                "paddingAll": "sm",
                "contents": [
                    {
                        "type": "text",
                        "text": "💡 隨時輸入「選單」開啟此面板",
                        "size": "xxs", "color": NEUTRAL_COLOR,
                        "align": "center",
                    },
                ],
            },
        }

        return {
            "type": "flex",
            "altText": "功能選單",
            "contents": bubble,
        }

    @staticmethod
    def quick_action_card(context: str = "general", is_manager: bool = False) -> dict:
        """操作完成後的精簡快捷小卡 — 依情境顯示 2-3 個常用功能按鈕。"""

        # ── Context → header config ──
        ctx_config: dict[str, tuple[str, str]] = {
            "report_done": ("✅ 通報已送出", SUCCESS_COLOR),
            "query_done": ("📋 查詢完成", INFO_COLOR),
            "review_done": ("✅ 審核完成", JUDGMENT_COLOR),
            "word_done": ("📄 報告已產生", SUCCESS_COLOR),
            "general": ("✅ 操作完成", NEUTRAL_COLOR),
        }
        title, header_color = ctx_config.get(context, ctx_config["general"])

        # ── Button definitions ──
        def _qbtn(emoji: str, label: str, action_name: str, display: str, color: str) -> dict:
            return {
                "type": "button",
                "style": "link",
                "height": "sm",
                "color": color,
                "action": {
                    "type": "postback",
                    "label": f"{emoji} {label}",
                    "data": _postback_data(action_name),
                    "displayText": display,
                },
            }

        btn_report = _qbtn("🚨", "再次通報", "start_report", "通報災害", URGENT_COLOR)
        btn_query = _qbtn("🔍", "查詢案件", "query_cases", "查詢案件", INFO_COLOR)
        btn_map = _qbtn("🗺️", "查看地圖", "view_map", "查看地圖", SUCCESS_COLOR)
        btn_review = _qbtn("📝", "繼續審核", "review_pending", "審核待辦", JUDGMENT_COLOR)
        btn_menu = _qbtn("📋", "回選單", "main_menu", "選單", NEUTRAL_COLOR)

        # ── Context → button set ──
        button_map: dict[str, list[dict]] = {
            "report_done": [btn_query, btn_report, btn_menu],
            "query_done": [btn_report, btn_map, btn_menu],
            "review_done": [btn_review, btn_menu],
            "word_done": [btn_query, btn_menu],
            "general": [btn_report, btn_query, btn_menu],
        }
        buttons = button_map.get(context, button_map["general"])

        bubble: dict = {
            "type": "bubble",
            "size": "kilo",
            "header": {
                "type": "box", "layout": "vertical",
                "backgroundColor": header_color,
                "paddingAll": "md",
                "contents": [
                    {
                        "type": "text", "text": title,
                        "weight": "bold", "size": "sm", "color": "#FFFFFF",
                        "align": "center",
                    },
                ],
            },
            "body": {
                "type": "box", "layout": "vertical",
                "spacing": "none", "paddingAll": "sm",
                "contents": buttons,
            },
            "footer": {
                "type": "box", "layout": "vertical",
                "paddingAll": "xs",
                "contents": [
                    {
                        "type": "text",
                        "text": "💡 隨時輸入「選單」開啟完整功能面板",
                        "size": "xxs", "color": "#AAAAAA",
                        "align": "center", "wrap": True,
                    },
                ],
            },
        }

        return {
            "type": "flex",
            "altText": "快捷操作",
            "contents": bubble,
        }

    @staticmethod
    def user_rich_menu_json() -> dict:
        return {
            "size": {"width": 2500, "height": 1686},
            "selected": False,
            "name": "使用者選單",
            "chatBarText": "開啟功能選單",
            "areas": [
                {"bounds": {"x": 0, "y": 0, "width": 833, "height": 843}, "action": {"type": "postback", "data": _postback_data("start_report"), "displayText": "通報災害"}},
                {"bounds": {"x": 833, "y": 0, "width": 833, "height": 843}, "action": {"type": "postback", "data": _postback_data("query_cases"), "displayText": "查詢案件"}},
                {"bounds": {"x": 1666, "y": 0, "width": 834, "height": 843}, "action": {"type": "postback", "data": _postback_data("help"), "displayText": "操作說明"}},
                {"bounds": {"x": 0, "y": 843, "width": 833, "height": 843}, "action": {"type": "postback", "data": _postback_data("view_map"), "displayText": "查看地圖"}},
                {"bounds": {"x": 833, "y": 843, "width": 833, "height": 843}, "action": {"type": "postback", "data": _postback_data("statistics"), "displayText": "統計摘要"}},
                {"bounds": {"x": 1666, "y": 843, "width": 834, "height": 843}, "action": {"type": "postback", "data": _postback_data("profile"), "displayText": "個人資訊"}},
            ],
        }

    @staticmethod
    def manager_rich_menu_json() -> dict:
        return {
            "size": {"width": 2500, "height": 1686},
            "selected": False,
            "name": "決策人員選單",
            "chatBarText": "開啟管理選單",
            "areas": [
                {"bounds": {"x": 0, "y": 0, "width": 833, "height": 843}, "action": {"type": "postback", "data": _postback_data("start_report"), "displayText": "通報災害"}},
                {"bounds": {"x": 833, "y": 0, "width": 833, "height": 843}, "action": {"type": "postback", "data": _postback_data("query_cases"), "displayText": "查詢案件"}},
                {"bounds": {"x": 1666, "y": 0, "width": 834, "height": 843}, "action": {"type": "postback", "data": _postback_data("review_pending"), "displayText": "審核待辦"}},
                {"bounds": {"x": 0, "y": 843, "width": 833, "height": 843}, "action": {"type": "postback", "data": _postback_data("view_map"), "displayText": "查看地圖"}},
                {"bounds": {"x": 833, "y": 843, "width": 833, "height": 843}, "action": {"type": "postback", "data": _postback_data("statistics"), "displayText": "統計摘要"}},
                {"bounds": {"x": 1666, "y": 843, "width": 834, "height": 843}, "action": {"type": "postback", "data": _postback_data("profile"), "displayText": "個人資訊"}},
            ],
        }

    @staticmethod
    def pending_users_carousel(users: list) -> dict:
        bubbles = []
        for user in users[:10]:
            user_id = user.user_id if hasattr(user, "user_id") else user.get("user_id", "")
            real_name = user.real_name if hasattr(user, "real_name") else user.get("real_name", "")
            district_name = user.district_name if hasattr(user, "district_name") else user.get("district_name", "")
            role = user.role.value if hasattr(user, "role") else user.get("role", "")
            bubbles.append(
                {
                    "type": "bubble",
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": real_name or user_id, "weight": "bold"},
                            {"type": "text", "text": f"工務段：{district_name or '-'}", "size": "sm"},
                            {"type": "text", "text": f"角色：{role}", "size": "sm"},
                        ],
                    },
                    "footer": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "button", "style": "primary", "color": SUCCESS_COLOR, "action": {"type": "postback", "label": "核准", "data": _postback_data("approve_user", user_id=user_id)}},
                            {"type": "button", "style": "secondary", "action": {"type": "postback", "label": "退件", "data": _postback_data("reject_user", user_id=user_id)}},
                        ],
                    },
                }
            )
        return {
            "type": "flex",
            "altText": "待核准使用者",
            "contents": {"type": "carousel", "contents": bubbles or [{"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": "目前沒有待審核使用者"}]}}]},
        }

    @staticmethod
    def annotation_summary_flex(photo_index: int, annotations: dict) -> dict:
        tags = annotations.get("tags", [])
        lines = [f"照片 #{photo_index + 1}", f"照片類型：{annotations.get('photo_type_name', '-')}"]
        for tag in tags:
            lines.append(f"- {tag.get('category_name', '')}：{tag.get('label', '')}")
        note = annotations.get("custom_note")
        if note:
            lines.append(f"備註：{note}")
        return {
            "type": "flex",
            "altText": "照片標註摘要",
            "contents": {
                "type": "bubble",
                "header": {"type": "box", "layout": "vertical", "backgroundColor": SUCCESS_COLOR, "contents": [{"type": "text", "text": "照片標註確認", "color": "#FFFFFF", "weight": "bold"}]},
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [{"type": "text", "text": line, "size": "sm", "wrap": True, "margin": "sm"} for line in lines],
                },
            },
        }

    @staticmethod
    def get_photo_tag_definition(photo_type: str, disaster_type: str = "") -> dict | None:
        return _resolve_photo_tags(photo_type, disaster_type)

    @staticmethod
    def get_survey_definition() -> list[dict]:
        return _site_survey()

    # ── Photo-set annotation UI methods ──────────────────────────────

    @staticmethod
    def photo_set_entry_card(
        photo_set_type: str,
        photo_set_name: str,
        disaster_type: str,
        photo_number: int,
        is_required: bool,
        max_photos: int,
    ) -> dict:
        """Entry card for starting annotation on a photo set."""
        header_color = INFO_COLOR if is_required else NEUTRAL_COLOR
        req_label = "必要" if is_required else "選填"
        return {
            "type": "flex",
            "altText": f"📸 {photo_set_name}",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": header_color,
                    "contents": [
                        {"type": "text", "text": f"📸 {photo_set_name}", "weight": "bold", "color": "#FFFFFF", "size": "lg"},
                    ],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": f"第{photo_number}張照片 ({req_label})", "size": "sm", "color": NEUTRAL_COLOR},
                        {"type": "text", "text": f"類型：{photo_set_type} {photo_set_name}", "size": "sm", "margin": "md", "wrap": True},
                        {"type": "text", "text": f"最多可拍 {max_photos} 張", "size": "xs", "color": NEUTRAL_COLOR, "margin": "sm"},
                    ],
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": SUCCESS_COLOR,
                            "action": {
                                "type": "postback",
                                "label": "開始標註",
                                "data": _postback_data("start_annotation", set=photo_set_type),
                            },
                        }
                    ],
                },
            },
        }

    @staticmethod
    def tag_single_select_quick_reply(
        category_name: str,
        tags: list[dict],
        photo_set_type: str,
        category_id: str,
        current_index: int,
        total_count: int,
        source: str = "photo",
        exclusion_tags: list[dict] | None = None,
    ) -> dict:
        """Quick Reply for single-select categories with ≤7 options."""
        emoji = "📷" if source == "photo" else "🧠"
        prompt = f"{emoji} ({current_index}/{total_count}) {category_name}"
        items: list[dict] = []
        for tag in tags[:11]:
            items.append(
                {
                    "type": "postback",
                    "label": tag.get("label", "")[:20],
                    "data": _postback_data("select_tag", set=photo_set_type, cat=category_id, tag=tag.get("id", "")),
                    "displayText": tag.get("label", ""),
                }
            )
        if exclusion_tags:
            for etag in exclusion_tags[:2]:
                items.append(
                    {
                        "type": "postback",
                        "label": f"⊘{etag.get('label', '')}"[:20],
                        "data": _postback_data("select_exclusion", set=photo_set_type, cat=category_id, tag=etag.get("id", "")),
                        "displayText": etag.get("label", ""),
                    }
                )
        if current_index > 1:
            items.append(
                {
                    "type": "postback",
                    "label": "◀ 上一項",
                    "data": _postback_data("prev_tag_category", set=photo_set_type, cat=category_id),
                    "displayText": "上一項",
                }
            )
        return FlexBuilder.quick_reply_message(prompt, items)

    @staticmethod
    def tag_multi_select_flex(
        category_name: str,
        tags: list[dict],
        exclusion_tags: list[dict],
        photo_set_type: str,
        category_id: str,
        selected_tags: list[str],
        current_index: int,
        total_count: int,
        source: str = "photo",
        geology_hint: str | None = None,
        multi_select: bool = True,
    ) -> dict:
        """Flex Bubble for multi-select or 8+ option categories with dual-column layout."""
        header_color = INFO_COLOR if source == "photo" else JUDGMENT_COLOR
        emoji = "📷" if source == "photo" else "🧠"
        selected_set = set(selected_tags)
        toggle_action = "toggle_tag" if source == "photo" else "toggle_judgment"

        # Build dual-column rows
        rows: list[dict] = []
        for i in range(0, len(tags), 2):
            cols: list[dict] = []
            for tag in tags[i:i + 2]:
                tid = tag.get("id", "")
                is_sel = tid in selected_set
                label = f"✓{tag.get('label', '')}" if is_sel else tag.get("label", "")
                cols.append(
                    {
                        "type": "button",
                        "style": "secondary" if is_sel else "primary",
                        "color": NEUTRAL_COLOR if is_sel else INFO_COLOR,
                        "flex": 1,
                        "margin": "sm",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": label[:20],
                            "data": _postback_data(toggle_action, set=photo_set_type, cat=category_id, tag=tid),
                            "displayText": tag.get("label", ""),
                        },
                        "adjustMode": "shrink-to-fit",
                    }
                )
            if len(cols) == 1:
                cols.append({"type": "filler", "flex": 1})
            rows.append({"type": "box", "layout": "horizontal", "spacing": "sm", "contents": cols})

        body_contents: list[dict] = list(rows)

        # Exclusion section
        if exclusion_tags:
            body_contents.append({"type": "separator", "margin": "md"})
            body_contents.append({"type": "text", "text": "排除選項", "size": "xs", "color": NEUTRAL_COLOR, "margin": "sm"})
            excl_row: list[dict] = []
            for etag in exclusion_tags:
                etid = etag.get("id", "")
                is_esel = etid in selected_set
                elabel = f"✓{etag.get('label', '')}" if is_esel else etag.get("label", "")
                excl_row.append(
                    {
                        "type": "button",
                        "style": "secondary" if is_esel else "primary",
                        "color": NEUTRAL_COLOR if is_esel else EXCLUSION_COLOR,
                        "flex": 1,
                        "margin": "sm",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": elabel[:20],
                            "data": _postback_data("select_exclusion", set=photo_set_type, cat=category_id, tag=etid),
                            "displayText": etag.get("label", ""),
                        },
                        "adjustMode": "shrink-to-fit",
                    }
                )
            if len(excl_row) == 1:
                excl_row.append({"type": "filler", "flex": 1})
            body_contents.append({"type": "box", "layout": "horizontal", "spacing": "sm", "contents": excl_row})

        # ── 地質參考資訊（P4 邊坡地質概估）──────────────────
        if geology_hint:
            body_contents.append({"type": "separator", "margin": "md"})
            hint_lines: list[dict] = [
                {
                    "type": "text",
                    "text": "📋 系統地質參考資訊",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#1a237e",
                },
            ]
            for line in geology_hint.split("\n"):
                stripped = line.strip()
                if stripped:
                    hint_lines.append(
                        {
                            "type": "text",
                            "text": stripped,
                            "wrap": True,
                            "size": "xs",
                            "color": "#333333",
                            "margin": "sm",
                        }
                    )
            hint_lines.append(
                {
                    "type": "text",
                    "text": "⚠ 以上為系統自動查詢，請依現場實際狀況判斷",
                    "size": "xxs",
                    "color": "#999999",
                    "margin": "sm",
                    "wrap": True,
                }
            )
            body_contents.append(
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "md",
                    "backgroundColor": "#F0F4F8",
                    "cornerRadius": "md",
                    "paddingAll": "md",
                    "contents": hint_lines,
                }
            )

        confirm_action = "confirm_multi" if source == "photo" else "confirm_judgment"
        return {
            "type": "flex",
            "altText": f"{emoji} {category_name}",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": header_color,
                    "contents": [{"type": "text", "text": f"{emoji} ({current_index}/{total_count}) {category_name}", "color": "#FFFFFF", "weight": "bold"}],
                },
                "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": body_contents},
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": (
                        [
                            {
                                "type": "button",
                                "style": "primary",
                                "color": SUCCESS_COLOR,
                                "action": {
                                    "type": "postback",
                                    "label": "確認選擇 ▶",
                                    "data": _postback_data(confirm_action, set=photo_set_type, cat=category_id),
                                },
                            },
                            {
                                "type": "text",
                                "text": "可複選，全部選完再按確認",
                                "size": "xs",
                                "color": "#999999",
                                "align": "center",
                                "margin": "sm",
                            },
                        ] if multi_select else []
                    ) + (
                        [
                            {
                                "type": "text",
                                "text": "👆 點選後自動進入下一項",
                                "size": "xs",
                                "color": "#999999",
                                "align": "center",
                                "margin": "sm",
                            },
                        ] if not multi_select else []
                    ) + (
                        [
                            {
                                "type": "button",
                                "style": "secondary",
                                "color": NEUTRAL_COLOR,
                                "margin": "sm",
                                "height": "sm",
                                "action": {
                                    "type": "postback",
                                    "label": "◀ 上一項",
                                    "data": _postback_data("prev_tag_category", set=photo_set_type, cat=category_id),
                                    "displayText": "上一項",
                                },
                            }
                    ] if current_index > 1 else []),
                },
            },
        }

    @staticmethod
    def photo_complete_card(
        photo_set_type: str,
        photo_set_name: str,
        photo_order: int,
        max_photos: int,
        has_more_photos_allowed: bool,
    ) -> dict:
        """Green card shown after completing photo visible tags."""
        buttons: list[dict] = []
        if has_more_photos_allowed:
            btn_label = f"📸 補充照片{photo_order + 1}"[:20]
            buttons.append(
                {
                    "type": "button",
                    "style": "primary",
                    "color": INFO_COLOR,
                    "action": {
                        "type": "postback",
                        "label": btn_label,
                        "data": _postback_data("supplement_photo", set=photo_set_type),
                    },
                }
            )
        buttons.append(
            {
                "type": "button",
                "style": "primary",
                "color": JUDGMENT_COLOR,
                "action": {
                    "type": "postback",
                    "label": "🧠 填寫判斷標籤",
                    "data": _postback_data("start_judgment", set=photo_set_type),
                },
            }
        )
        buttons.append(
            {
                "type": "button",
                "style": "secondary",
                "color": NEUTRAL_COLOR,
                "action": {
                    "type": "postback",
                    "label": "⏭ 跳過判斷標籤",
                    "data": _postback_data("skip_judgment", set=photo_set_type),
                },
            }
        )
        return {
            "type": "flex",
            "altText": "✅ 照片標註完成",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": SUCCESS_COLOR,
                    "contents": [{"type": "text", "text": "✅ 照片標註完成", "weight": "bold", "color": "#FFFFFF"}],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": f"已完成第{photo_order}張 {photo_set_name} 的照片可見標註", "wrap": True, "size": "sm"},
                    ],
                },
                "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": buttons},
            },
        }

    @staticmethod
    def differential_tag_flex(
        category_name: str,
        new_tags: list[dict],
        already_tagged: list[dict],
        photo_set_type: str,
        category_id: str,
        current_index: int,
        total_count: int,
    ) -> dict:
        """Flex for supplement photos showing already-tagged items and new options."""
        body_contents: list[dict] = []

        # Already tagged section
        if already_tagged:
            body_contents.append({"type": "text", "text": "已從前照片標註：", "size": "xs", "color": NEUTRAL_COLOR})
            tagged_labels = "、".join(t.get("label", "") for t in already_tagged)
            body_contents.append({"type": "text", "text": tagged_labels, "size": "xs", "color": NEUTRAL_COLOR, "wrap": True, "margin": "sm"})
            body_contents.append({"type": "separator", "margin": "md"})

        # New tags dual-column
        for i in range(0, len(new_tags), 2):
            cols: list[dict] = []
            for tag in new_tags[i:i + 2]:
                cols.append(
                    {
                        "type": "button",
                        "style": "primary",
                        "color": INFO_COLOR,
                        "flex": 1,
                        "margin": "sm",
                        "height": "sm",
                        "action": {
                            "type": "postback",
                            "label": tag.get("label", "")[:20],
                            "data": _postback_data("toggle_tag", set=photo_set_type, cat=category_id, tag=tag.get("id", "")),
                            "displayText": tag.get("label", ""),
                        },
                    }
                )
            if len(cols) == 1:
                cols.append({"type": "filler", "flex": 1})
            body_contents.append({"type": "box", "layout": "horizontal", "spacing": "sm", "contents": cols})

        return {
            "type": "flex",
            "altText": f"📷 補充照片標註 {category_name}",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [{"type": "text", "text": f"📷 補充照片 ({current_index}/{total_count}) {category_name}", "color": "#FFFFFF", "weight": "bold"}],
                },
                "body": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": body_contents},
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": SUCCESS_COLOR,
                            "action": {
                                "type": "postback",
                                "label": "確認 ▶",
                                "data": _postback_data("confirm_multi", set=photo_set_type, cat=category_id),
                            },
                        }
                    ],
                },
            },
        }

    @staticmethod
    def photo_set_summary_flex(
        photo_set_type: str,
        photo_set_name: str,
        photos_data: list[dict],
        judgment_data: dict,
    ) -> dict:
        """Summary of entire photo set with per-photo diffs and judgment tags."""
        body_contents: list[dict] = []
        for photo in photos_data:
            order = photo.get("order", 1)
            body_contents.append({"type": "text", "text": f"照片 {order}", "weight": "bold", "size": "sm", "margin": "md"})
            visible = photo.get("visible_tags", {})
            if visible:
                for cat_id, tag_ids in visible.items():
                    labels = tag_ids if isinstance(tag_ids, list) else [tag_ids]
                    body_contents.append({"type": "text", "text": f"  {cat_id}：{'、'.join(str(l) for l in labels)}", "size": "xs", "wrap": True, "color": NEUTRAL_COLOR})
            else:
                body_contents.append({"type": "text", "text": "  (無標註)", "size": "xs", "color": NEUTRAL_COLOR})

        # Judgment section
        body_contents.append({"type": "separator", "margin": "md"})
        body_contents.append({"type": "text", "text": "🧠 判斷標籤", "weight": "bold", "size": "sm", "margin": "md"})
        if judgment_data:
            for cat_id, tag_ids in judgment_data.items():
                labels = tag_ids if isinstance(tag_ids, list) else [tag_ids]
                body_contents.append({"type": "text", "text": f"  {cat_id}：{'、'.join(str(l) for l in labels)}", "size": "xs", "wrap": True, "color": NEUTRAL_COLOR})
        else:
            body_contents.append({"type": "text", "text": "  (未填寫)", "size": "xs", "color": NEUTRAL_COLOR})

        return {
            "type": "flex",
            "altText": f"📋 {photo_set_name} 標註摘要",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": SUCCESS_COLOR,
                    "contents": [{"type": "text", "text": f"📋 {photo_set_name} 標註摘要", "weight": "bold", "color": "#FFFFFF"}],
                },
                "body": {"type": "box", "layout": "vertical", "contents": body_contents},
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": SUCCESS_COLOR,
                            "action": {
                                "type": "postback",
                                "label": "繼續下一組 ▶",
                                "data": _postback_data("next_set", set=photo_set_type),
                            },
                        }
                    ],
                },
            },
        }

    @staticmethod
    def annotation_progress_carousel(photo_sets_status: list[dict]) -> dict:
        """Carousel showing progress for all photo sets."""
        bubbles: list[dict] = []
        for ps in photo_sets_status[:12]:
            status = ps.get("status", "pending")
            is_required = ps.get("is_required", True)
            if status == "complete":
                color = SUCCESS_COLOR
                status_text = "✅ 完成"
            elif is_required:
                color = URGENT_COLOR
                status_text = "❗ 未完成" if status == "pending" else "🔄 進行中"
            else:
                color = NEUTRAL_COLOR
                status_text = "未完成" if status == "pending" else "🔄 進行中"
            btn_label = "繼續" if status == "in_progress" else "開始"
            if status == "complete":
                btn_label = "查看"
            bubbles.append(
                {
                    "type": "bubble",
                    "size": "micro",
                    "header": {
                        "type": "box",
                        "layout": "vertical",
                        "backgroundColor": color,
                        "contents": [{"type": "text", "text": ps.get("type", ""), "color": "#FFFFFF", "weight": "bold", "align": "center"}],
                    },
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": ps.get("name", "")[:20], "weight": "bold", "size": "sm", "wrap": True},
                            {"type": "text", "text": status_text, "size": "xs", "color": NEUTRAL_COLOR, "margin": "sm"},
                            {"type": "text", "text": f"照片：{ps.get('photo_count', 0)}張", "size": "xs", "color": NEUTRAL_COLOR},
                        ],
                    },
                    "footer": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "button",
                                "style": "primary",
                                "color": color,
                                "height": "sm",
                                "action": {
                                    "type": "postback",
                                    "label": btn_label,
                                    "data": _postback_data("goto_set", set=ps.get("type", "")),
                                },
                            }
                        ],
                    },
                }
            )
        if not bubbles:
            bubbles.append({"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": "無照片組資料"}]}})
        return {
            "type": "flex",
            "altText": "照片標註進度",
            "contents": {"type": "carousel", "contents": bubbles},
        }

    @staticmethod
    def judgment_category_flex(
        category_name: str,
        tags: list[dict],
        exclusion_tags: list[dict],
        photo_set_type: str,
        category_id: str,
        selected_tags: list[str],
        current_index: int,
        total_count: int,
    ) -> dict:
        """Judgment tag Flex with JUDGMENT_COLOR header — orange 🧠 variant."""
        return FlexBuilder.tag_multi_select_flex(
            category_name=category_name,
            tags=tags,
            exclusion_tags=exclusion_tags,
            photo_set_type=photo_set_type,
            category_id=category_id,
            selected_tags=selected_tags,
            current_index=current_index,
            total_count=total_count,
            source="judgment",
        )

    @staticmethod
    def geology_hint_flex(hint_text: str) -> dict:
        """Standalone geology reference info Flex Bubble shown after coordinate confirmation."""
        hint_lines: list[dict] = [
            {
                "type": "text",
                "text": "📋 系統地質參考資訊",
                "weight": "bold",
                "size": "md",
                "color": "#1a237e",
            },
        ]
        for line in hint_text.split("\n"):
            stripped = line.strip()
            if stripped:
                hint_lines.append(
                    {
                        "type": "text",
                        "text": stripped,
                        "wrap": True,
                        "size": "sm",
                        "color": "#333333",
                        "margin": "sm",
                    }
                )
        hint_lines.append(
            {
                "type": "text",
                "text": "⚠ 以上為系統自動查詢，請依現場實際狀況判斷",
                "size": "xs",
                "color": "#999999",
                "margin": "md",
                "wrap": True,
            }
        )
        return {
            "type": "flex",
            "altText": "📋 系統地質參考資訊",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#1a237e",
                    "contents": [
                        {
                            "type": "text",
                            "text": "🌍 座標地質查詢結果",
                            "color": "#FFFFFF",
                            "weight": "bold",
                            "size": "md",
                        }
                    ],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "backgroundColor": "#F0F4F8",
                    "paddingAll": "lg",
                    "contents": hint_lines,
                },
            },
        }

    @staticmethod
    def disaster_type_select_flex() -> dict:
        return {
            "type": "flex",
            "altText": "選擇災害類型",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [
                        {"type": "text", "text": "災害類型", "weight": "bold", "color": "#FFFFFF"},
                    ],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "請選擇災害類型：", "size": "sm"},
                        {
                            "type": "text",
                            "text": "💡 輸入「取消」可取消流程，輸入「返回」可回上一步。",
                            "size": "xxs",
                            "color": NEUTRAL_COLOR,
                            "wrap": True,
                            "margin": "lg",
                        },
                    ],
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "action": {
                                "type": "postback",
                                "label": "一般災害",
                                "data": _postback_data("select_disaster_type", value="一般"),
                            },
                        },
                        {
                            "type": "button",
                            "style": "primary",
                            "action": {
                                "type": "postback",
                                "label": "專案",
                                "data": _postback_data("select_disaster_type", value="專案"),
                            },
                        },
                    ],
                },
            },
        }

    @staticmethod
    def processing_type_select_flex() -> dict:
        return {
            "type": "flex",
            "altText": "選擇處理類型",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [
                        {"type": "text", "text": "處理類型", "weight": "bold", "color": "#FFFFFF"},
                    ],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "請選擇處理類型：", "size": "sm"},
                        {
                            "type": "text",
                            "text": "💡 輸入「取消」可取消流程，輸入「返回」可回上一步。",
                            "size": "xxs",
                            "color": NEUTRAL_COLOR,
                            "wrap": True,
                            "margin": "lg",
                        },
                    ],
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "action": {
                                "type": "postback",
                                "label": "搶修",
                                "data": _postback_data("select_processing_type", value="搶修"),
                            },
                        },
                        {
                            "type": "button",
                            "style": "primary",
                            "action": {
                                "type": "postback",
                                "label": "復建",
                                "data": _postback_data("select_processing_type", value="復建"),
                            },
                        },
                    ],
                },
            },
        }

    @staticmethod
    def repeat_disaster_select_flex(prefill: str = "") -> dict:
        hint = f"\n（照片標註建議：{prefill}）" if prefill else ""
        return {
            "type": "flex",
            "altText": "是否重複致災",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [
                        {"type": "text", "text": "是否重複致災", "weight": "bold", "color": "#FFFFFF"},
                    ],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": f"該地點是否屬於重複致災？{hint}", "size": "sm", "wrap": True},
                        {
                            "type": "text",
                            "text": "💡 輸入「取消」可取消流程，輸入「返回」可回上一步。",
                            "size": "xxs",
                            "color": NEUTRAL_COLOR,
                            "wrap": True,
                            "margin": "lg",
                        },
                    ],
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "action": {
                                "type": "postback",
                                "label": "是—重複致災",
                                "data": _postback_data("select_repeat_disaster", value="是"),
                            },
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "action": {
                                "type": "postback",
                                "label": "否—非重複致災",
                                "data": _postback_data("select_repeat_disaster", value="否"),
                            },
                        },
                    ],
                },
            },
        }

    @staticmethod
    def repeat_disaster_year_input_flex() -> dict:
        return {
            "type": "flex",
            "altText": "重複致災年份",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [
                        {"type": "text", "text": "重複致災年份", "weight": "bold", "color": "#FFFFFF"},
                    ],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "格式：民國年，例如：108", "size": "xs", "color": NEUTRAL_COLOR, "wrap": True},
                        {"type": "text", "text": "請輸入興建年份：", "size": "sm", "wrap": True, "margin": "sm"},
                    ],
                },
            },
        }

    @staticmethod
    def original_protection_select_flex(prefill: str = "") -> dict:
        options = [
            "重力式擋土牆",
            "懸臂式擋土牆",
            "加勁擋土牆",
            "護岸工",
            "護坡工",
            "地錨系統",
            "無保護(自然邊坡)",
        ]
        hint = f"\n（照片標註建議：{prefill}）" if prefill else ""
        return {
            "type": "flex",
            "altText": "原設計保護型式",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [
                        {"type": "text", "text": "原設計保護型式", "weight": "bold", "color": "#FFFFFF"},
                    ],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": f"請選擇原設計保護型式：{hint}", "size": "sm", "wrap": True},
                        {
                            "type": "text",
                            "text": "💡 輸入「取消」可取消流程，輸入「返回」可回上一步。",
                            "size": "xxs",
                            "color": NEUTRAL_COLOR,
                            "wrap": True,
                            "margin": "lg",
                        },
                    ],
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary" if option == prefill else "secondary",
                            "height": "sm",
                            "action": {
                                "type": "postback",
                                "label": option,
                                "data": _postback_data("select_original_protection", value=option),
                            },
                        }
                        for option in options
                    ],
                },
            },
        }

    @staticmethod
    def text_input_with_skip_flex(title: str, prompt: str, skip_action: str, hint: str = "") -> dict:
        body_contents = []
        if hint:
            body_contents.append({"type": "text", "text": hint, "size": "xs", "color": NEUTRAL_COLOR, "wrap": True})
        body_contents.append({"type": "text", "text": prompt, "size": "sm", "wrap": True, "margin": "sm" if hint else "none"})
        body_contents.append(
            {
                "type": "text",
                "text": "✏️ 請打字回應",
                "size": "xs",
                "color": INFO_COLOR,
                "weight": "bold",
                "margin": "md",
            }
        )
        body_contents.append(
            {
                "type": "text",
                "text": "💡 輸入「取消」可取消流程，輸入「返回」可回上一步。",
                "size": "xxs",
                "color": NEUTRAL_COLOR,
                "wrap": True,
                "margin": "lg",
            }
        )

        return {
            "type": "flex",
            "altText": title,
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [
                        {"type": "text", "text": title, "weight": "bold", "color": "#FFFFFF"},
                    ],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": body_contents,
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "style": "secondary",
                            "action": {
                                "type": "postback",
                                "label": "略過後補",
                                "data": _postback_data(skip_action),
                            },
                        }
                    ],
                },
            },
        }

    @staticmethod
    def text_input_flex(title: str, prompt: str, hint: str = "") -> dict:
        body_contents = []
        if hint:
            body_contents.append({"type": "text", "text": hint, "size": "xs", "color": NEUTRAL_COLOR, "wrap": True})
        body_contents.append({"type": "text", "text": prompt, "size": "sm", "wrap": True, "margin": "sm" if hint else "none"})
        body_contents.append(
            {
                "type": "text",
                "text": "✏️ 請打字回應",
                "size": "xs",
                "color": INFO_COLOR,
                "weight": "bold",
                "margin": "md",
            }
        )
        body_contents.append(
            {
                "type": "text",
                "text": "💡 輸入「取消」可取消流程，輸入「返回」可回上一步。",
                "size": "xxs",
                "color": NEUTRAL_COLOR,
                "wrap": True,
                "margin": "lg",
            }
        )

        return {
            "type": "flex",
            "altText": title,
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [
                        {"type": "text", "text": title, "weight": "bold", "color": "#FFFFFF"},
                    ],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": body_contents,
                },
            },
        }

    @staticmethod
    def project_name_input_flex() -> dict:
        return FlexBuilder.text_input_with_skip_flex(
            "工程名稱",
            "請輸入工程名稱：",
            "skip_project_name",
            hint="例如：台7線32K+400邊坡災害搶修工程",
        )

    @staticmethod
    def disaster_date_input_flex() -> dict:
        return FlexBuilder.text_input_with_skip_flex(
            "災害發生日期",
            "請輸入災害發生日期：",
            "skip_disaster_date",
            hint="格式：民國年/月/日，例如：114/03/01",
        )

    @staticmethod
    def coordinate_input_flex() -> dict:
        return FlexBuilder.text_input_flex(
            "輸入位置",
            "請選擇輸入方式：\n1️⃣ 分享LINE定位\n2️⃣ 輸入座標（格式：25.033,121.567）\n3️⃣ 輸入里程樁號（格式：23K+500）",
        )

    @staticmethod
    def description_input_flex() -> dict:
        return FlexBuilder.text_input_flex(
            "災情描述",
            "請描述災情內容（自由填寫）：\n\n可包含：\n• 影響範圍（崩塌面積、佔用車道）\n• 危險情形（是否持續滑動、裂縫擴大）\n• 即時處置（交管、封路、警示）",
            hint="📝 範例：『邊坡滑動約寬20m高15m，土石佔用外側車道，目前交管單線通行。』",
        )

    @staticmethod
    def file_upload_with_skip_flex(title: str, prompt: str, skip_action: str) -> dict:
        return {
            "type": "flex",
            "altText": title,
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [
                        {"type": "text", "text": title, "weight": "bold", "color": "#FFFFFF"},
                    ],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": prompt, "size": "sm", "wrap": True},
                        {"type": "text", "text": "📎 請傳送 PDF 檔案", "size": "xs", "color": NEUTRAL_COLOR, "wrap": True, "margin": "sm"},
                    ],
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "style": "secondary",
                            "action": {
                                "type": "postback",
                                "label": "略過後補",
                                "data": _postback_data(skip_action),
                            },
                        }
                    ],
                },
            },
        }

    @staticmethod
    def soil_conservation_select_flex() -> dict:
        return {
            "type": "flex",
            "altText": "水土保持計畫",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [
                        {"type": "text", "text": "水土保持計畫", "weight": "bold", "color": "#FFFFFF"},
                    ],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "本案是否需要水土保持計畫？", "size": "sm", "wrap": True},
                        {
                            "type": "text",
                            "text": "💡 輸入「取消」可取消流程，輸入「返回」可回上一步。",
                            "size": "xxs",
                            "color": NEUTRAL_COLOR,
                            "wrap": True,
                            "margin": "lg",
                        },
                    ],
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "action": {
                                "type": "postback",
                                "label": "需要—已核定",
                                "data": _postback_data("select_soil_conservation", value="需要已核定"),
                            },
                        },
                        {
                            "type": "button",
                            "style": "primary",
                            "action": {
                                "type": "postback",
                                "label": "需要—未核定",
                                "data": _postback_data("select_soil_conservation", value="需要未核定"),
                            },
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "action": {
                                "type": "postback",
                                "label": "不需要",
                                "data": _postback_data("select_soil_conservation", value="不需要"),
                            },
                        },
                    ],
                },
            },
        }

    @staticmethod
    def hazard_summary_flex(hazard_items: list[str], skip_action: str) -> dict:
        if hazard_items:
            bullet_list = "\n".join([f"- {item}" for item in hazard_items])
            summary_text = (
                "📋 根據照片標註與現場勘查，系統識別以下工址風險：\n\n"
                f"{bullet_list}\n\n"
                "如需補充，請直接輸入說明。"
            )
        else:
            summary_text = "📋 照片標註中未識別到特定工址風險。\n\n如需補充，請直接輸入說明。"

        return {
            "type": "flex",
            "altText": "工址環境危害辨識",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": JUDGMENT_COLOR,
                    "contents": [
                        {"type": "text", "text": "工址環境危害辨識", "weight": "bold", "color": "#FFFFFF"},
                    ],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": summary_text, "size": "sm", "wrap": True},
                    ],
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "action": {
                                "type": "postback",
                                "label": "確認（不補充）",
                                "data": _postback_data("hazard_confirm"),
                            },
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "action": {
                                "type": "postback",
                                "label": "略過後補",
                                "data": _postback_data(skip_action),
                            },
                        },
                    ],
                },
            },
        }

    @staticmethod
    def word_report_prompt_flex() -> dict:
        """Prompt user to generate Word report after submission."""
        return {
            "type": "flex",
            "altText": "是否產生 Word 報告？",
            "contents": {
                "type": "bubble",
                "size": "kilo",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": "#2196F3",
                    "contents": [
                        {"type": "text", "text": "📄 Word 報告", "weight": "bold", "color": "#FFFFFF", "size": "md"}
                    ],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "是否產生公路災害工程內容概述表？", "wrap": True, "size": "sm"},
                        {"type": "text", "text": "系統將自動填入已收集的資料", "wrap": True, "size": "xs", "color": "#888888", "margin": "sm"},
                    ],
                },
                "footer": {
                    "type": "box",
                    "layout": "horizontal",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "action": {"type": "postback", "label": "產生報告", "data": "action=generate_word"},
                            "style": "primary",
                            "color": "#2196F3",
                        },
                        {
                            "type": "button",
                            "action": {"type": "postback", "label": "不需要", "data": "action=skip_word"},
                            "style": "secondary",
                        },
                    ],
                },
            },
        }

    @staticmethod
    def word_report_result_flex(completeness: dict, download_url: str) -> dict:
        """Display Word report completeness and download link."""
        pct = completeness["percentage"]
        filled = completeness["filled"]
        total = completeness["total"]
        missing = completeness.get("missing", [])

        # 進度條用 box + width ratio
        bar_filled_flex = max(1, pct)
        bar_empty_flex = max(1, 100 - pct)

        # 顏色
        if pct >= 80:
            bar_color = "#4CAF50"  # green
        elif pct >= 50:
            bar_color = "#FF9800"  # orange
        else:
            bar_color = "#F44336"  # red

        body_contents: list[dict] = [
            {"type": "text", "text": f"完成度：{pct}% ({filled}/{total})", "weight": "bold", "size": "md"},
            {
                "type": "box",
                "layout": "horizontal",
                "margin": "md",
                "contents": [
                    {"type": "box", "layout": "vertical", "flex": bar_filled_flex, "height": "6px", "backgroundColor": bar_color, "contents": []},
                    {"type": "box", "layout": "vertical", "flex": bar_empty_flex, "height": "6px", "backgroundColor": "#EEEEEE", "contents": []},
                ],
            },
        ]

        if missing:
            body_contents.append({"type": "separator", "margin": "lg"})
            body_contents.append({"type": "text", "text": "未填欄位：", "size": "sm", "weight": "bold", "margin": "md"})
            for item in missing[:10]:  # 最多顯示 10 項
                marker = "⚠️" if item.get("required") else "ℹ️"
                body_contents.append({
                    "type": "text",
                    "text": f"{marker} {item['name']}{'（必填）' if item.get('required') else '（選填）'}",
                    "size": "xs",
                    "color": "#666666",
                    "margin": "sm",
                    "wrap": True,
                })
            if len(missing) > 10:
                body_contents.append({"type": "text", "text": f"...還有 {len(missing) - 10} 項", "size": "xs", "color": "#999999", "margin": "sm"})

        return {
            "type": "flex",
            "altText": f"Word 報告已產生 (完成度 {pct}%)",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "backgroundColor": bar_color,
                    "contents": [
                        {"type": "text", "text": "📄 Word 報告已產生", "weight": "bold", "color": "#FFFFFF", "size": "md"}
                    ],
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": body_contents,
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "action": {"type": "uri", "label": "📥 下載 Word 檔案", "uri": download_url},
                            "style": "primary",
                            "color": "#2196F3",
                        },
                    ],
                },
            },
        }
