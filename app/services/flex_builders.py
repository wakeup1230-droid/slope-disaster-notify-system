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
    def get_photo_tag_definition(photo_type: str) -> dict | None:
        return _photo_tags().get(photo_type)

    @staticmethod
    def get_survey_definition() -> list[dict]:
        return _site_survey()
