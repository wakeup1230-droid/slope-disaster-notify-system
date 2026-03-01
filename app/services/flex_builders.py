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
    def district_quick_reply() -> dict:
        items = [
            {
                "type": "postback",
                "label": district["name"],
                "data": _postback_data("select_district", district_id=district["id"]),
                "displayText": district["name"],
            }
            for district in _districts()
        ]
        return FlexBuilder.quick_reply_message("請選擇工務段：", items)

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
        return FlexBuilder.quick_reply_message("請選擇道路：", items)

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
    def optional_photo_chooser(already_uploaded_types: list[str]) -> dict:
        """Show buttons for optional photo types P5-P10, plus a finish button."""
        photo_tags = _photo_tags()
        items = []
        for photo_type in ["P5", "P6", "P7", "P8", "P9", "P10"]:
            if photo_type in already_uploaded_types:
                continue
            info = photo_tags.get(photo_type, {})
            items.append(
                {
                    "type": "postback",
                    "label": f"{photo_type} {info.get('name', '')}"[:20],
                    "data": _postback_data("choose_optional_type", photo_type=photo_type),
                    "displayText": info.get("name", photo_type),
                }
            )
        items.append(
            {
                "type": "postback",
                "label": "完成照片上傳",
                "data": _postback_data("finish_photos"),
                "displayText": "完成照片上傳",
            }
        )
        return FlexBuilder.quick_reply_message("✅ 4張必要照片已完成！\n可選擇上傳其他照片，或直接完成：", items)

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
        bubbles = []
        for case in cases[:10]:
            bubbles.append(
                {
                    "type": "bubble",
                    "hero": {
                        "type": "image",
                        "url": case.get("thumbnail_url") or "https://dummyimage.com/800x400/e9eef3/888888&text=No+Photo",
                        "size": "full",
                        "aspectRatio": "20:13",
                        "aspectMode": "cover",
                    },
                    "body": {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": case.get("case_id", ""), "weight": "bold", "wrap": True},
                            {"type": "text", "text": f"{case.get('district_name', '-')}/{case.get('road_number', '-')}", "size": "sm", "color": NEUTRAL_COLOR},
                            {"type": "text", "text": case.get("damage_mode_name", "未填"), "size": "sm", "wrap": True},
                        ],
                    },
                    "footer": {
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
                    },
                }
            )
        return {
            "type": "flex",
            "altText": "案件列表",
            "contents": {"type": "carousel", "contents": bubbles or [{"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [{"type": "text", "text": "目前沒有案件"}]}}]},
        }

    @staticmethod
    def case_detail_flex(case: dict) -> dict:
        sections = [
            ("位置資訊", [f"工務段：{case.get('district_name', '-')}", f"道路：{case.get('road_number', '-')}", f"里程：{case.get('milepost', '-')}"]),
            ("災情描述", [f"類型：{case.get('damage_mode_name', '-')}", f"原因：{','.join(case.get('damage_cause_names', [])) or '-'}", f"描述：{case.get('description', '-')}"]),
            ("現勘摘要", [f"照片數：{case.get('photo_count', 0)}", f"完整度：{case.get('completeness_pct', 0)}%", f"狀態：{case.get('review_status', '-')}"]),
            ("座標", [case.get("coordinate_text", "-")]),
        ]
        body_contents = []
        for title, lines in sections:
            body_contents.append({"type": "text", "text": title, "weight": "bold", "margin": "md"})
            for line in lines:
                body_contents.append({"type": "text", "text": line, "size": "sm", "wrap": True, "color": NEUTRAL_COLOR})

        return {
            "type": "flex",
            "altText": f"案件詳情 {case.get('case_id', '')}",
            "contents": {
                "type": "bubble",
                "header": {"type": "box", "layout": "vertical", "backgroundColor": INFO_COLOR, "contents": [{"type": "text", "text": case.get("case_id", ""), "color": "#FFFFFF", "weight": "bold"}]},
                "body": {"type": "box", "layout": "vertical", "contents": body_contents},
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "button", "style": "primary", "color": SUCCESS_COLOR, "action": {"type": "postback", "label": "通過", "data": _postback_data("review_action", decision="approve", case_id=case.get("case_id", ""))}},
                        {"type": "button", "style": "secondary", "action": {"type": "postback", "label": "退回", "data": _postback_data("review_action", decision="return", case_id=case.get("case_id", ""))}},
                        {"type": "button", "style": "primary", "color": URGENT_COLOR, "action": {"type": "postback", "label": "結案", "data": _postback_data("review_action", decision="close", case_id=case.get("case_id", ""))}},
                    ],
                },
            },
        }

    @staticmethod
    def statistics_flex(stats: dict) -> dict:
        by_status = stats.get("by_status", {})
        by_district = stats.get("by_district", {})
        body = [
            {"type": "text", "text": f"總案件：{stats.get('total_cases', 0)}", "weight": "bold", "size": "lg"},
            {"type": "separator", "margin": "md"},
            {"type": "text", "text": "依狀態", "weight": "bold", "margin": "md"},
        ]
        for key, value in by_status.items():
            body.append({"type": "text", "text": f"{key}: {value}", "size": "sm"})
        body.append({"type": "text", "text": "依工務段", "weight": "bold", "margin": "md"})
        for key, value in by_district.items():
            body.append({"type": "text", "text": f"{key}: {value}", "size": "sm"})
        return {
            "type": "flex",
            "altText": "統計摘要",
            "contents": {"type": "bubble", "header": {"type": "box", "layout": "vertical", "backgroundColor": SUCCESS_COLOR, "contents": [{"type": "text", "text": "系統統計", "color": "#FFFFFF", "weight": "bold"}]}, "body": {"type": "box", "layout": "vertical", "contents": body}},
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
            f"初估經費：{data.get('estimated_cost_text', '未填')}",
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
    def profile_flex(user: dict) -> dict:
        return {
            "type": "flex",
            "altText": "個人資訊",
            "contents": {
                "type": "bubble",
                "header": {"type": "box", "layout": "vertical", "backgroundColor": INFO_COLOR, "contents": [{"type": "text", "text": "個人資訊", "weight": "bold", "color": "#FFFFFF"}]},
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": f"姓名：{user.get('real_name', '-')}", "size": "sm"},
                        {"type": "text", "text": f"顯示名稱：{user.get('display_name', '-')}", "size": "sm"},
                        {"type": "text", "text": f"角色：{user.get('role_name', '-')}", "size": "sm"},
                        {"type": "text", "text": f"帳號狀態：{user.get('status_name', '-')}", "size": "sm"},
                        {"type": "text", "text": f"工務段：{user.get('district_name', '-')}", "size": "sm"},
                    ],
                },
            },
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
            "- 取消：中止目前流程",
            "- 返回：返回上一步",
        ]
        return FlexBuilder.text_message("\n".join(lines))

    @staticmethod
    def user_rich_menu_json() -> dict:
        return {
            "size": {"width": 2500, "height": 1686},
            "selected": False,
            "name": "使用者選單",
            "chatBarText": "開啟功能選單",
            "areas": [
                {"bounds": {"x": 0, "y": 0, "width": 833, "height": 843}, "action": {"type": "postback", "data": _postback_data("start_report"), "displayText": "通報災害"}},
                {"bounds": {"x": 833, "y": 0, "width": 833, "height": 843}, "action": {"type": "postback", "data": _postback_data("query_cases"), "displayText": "我的案件"}},
                {"bounds": {"x": 1666, "y": 0, "width": 834, "height": 843}, "action": {"type": "postback", "data": _postback_data("view_map"), "displayText": "查看地圖"}},
                {"bounds": {"x": 0, "y": 843, "width": 833, "height": 843}, "action": {"type": "postback", "data": _postback_data("supplement_photo"), "displayText": "補傳照片"}},
                {"bounds": {"x": 833, "y": 843, "width": 833, "height": 843}, "action": {"type": "postback", "data": _postback_data("help"), "displayText": "操作說明"}},
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
                {"bounds": {"x": 1666, "y": 0, "width": 834, "height": 843}, "action": {"type": "postback", "data": _postback_data("view_map"), "displayText": "查看地圖"}},
                {"bounds": {"x": 0, "y": 843, "width": 833, "height": 843}, "action": {"type": "postback", "data": _postback_data("review_pending"), "displayText": "審核待辦"}},
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
                    }
                )
            if len(excl_row) == 1:
                excl_row.append({"type": "filler", "flex": 1})
            body_contents.append({"type": "box", "layout": "horizontal", "spacing": "sm", "contents": excl_row})

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
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": SUCCESS_COLOR,
                            "action": {
                                "type": "postback",
                                "label": "確認選擇 ▶",
                                "data": _postback_data(confirm_action, set=photo_set_type, cat=category_id),
                            },
                        }
                    ],
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
