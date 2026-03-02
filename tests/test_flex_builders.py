from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import pytest

from app.services.flex_builders import (
    FlexBuilder,
    _damage_modes,
    _districts,
    _photo_tags,
    _postback_data,
)


def assert_text_message(msg: dict[str, Any], expected_substring: str | None = None) -> None:
    assert msg["type"] == "text"
    assert "text" in msg
    if expected_substring:
        assert expected_substring in msg["text"]


def assert_flex_message(msg: dict[str, Any], alt_text_contains: str | None = None) -> None:
    assert msg["type"] == "flex"
    assert "altText" in msg
    assert "contents" in msg
    if alt_text_contains:
        assert alt_text_contains in msg["altText"]


def assert_quick_reply_message(msg: dict[str, Any], min_items: int = 1) -> None:
    assert "type" in msg
    assert "quickReply" in msg
    items = msg["quickReply"]["items"]
    assert len(items) >= min_items


def test_text_message() -> None:
    msg = FlexBuilder.text_message("hello")
    assert msg == {"type": "text", "text": "hello"}


def test_quick_reply_message() -> None:
    msg = FlexBuilder.quick_reply_message(
        "choose",
        [{"type": "postback", "label": "A", "data": "action=a", "displayText": "A"}],
    )
    assert_text_message(msg, "choose")
    assert_quick_reply_message(msg, min_items=1)
    action = msg["quickReply"]["items"][0]["action"]
    assert action["type"] == "postback"
    assert action["label"] == "A"


def test_confirm_message() -> None:
    msg = FlexBuilder.confirm_message("確定嗎", "action=yes", "action=no")
    assert msg["type"] == "template"
    template = msg["template"]
    assert template["type"] == "confirm"
    assert template["text"] == "確定嗎"
    assert template["actions"][0]["label"] == "確認"
    assert template["actions"][1]["label"] == "取消"
    assert template["actions"][0]["data"] == "action=yes"
    assert template["actions"][1]["data"] == "action=no"


def test_district_quick_reply() -> None:
    msg = FlexBuilder.district_quick_reply()
    assert_text_message(msg, "工務段")
    assert_quick_reply_message(msg)

    items = msg["quickReply"]["items"]
    districts = _districts()
    assert len(items) == len(districts) == 7

    district_ids = {district["id"] for district in districts}
    for item in items:
        assert item["type"] == "action"
        action = item["action"]
        assert action["type"] == "postback"
        data = parse_qs(action["data"])
        assert data["action"] == ["select_district"]
        assert data["district_id"][0] in district_ids

def test_district_quick_reply_exclude_all() -> None:
    """When include_all=False, the '全區' option should be excluded."""
    msg = FlexBuilder.district_quick_reply(include_all=False)
    assert_text_message(msg, "工務段")
    assert_quick_reply_message(msg)
    items = msg["quickReply"]["items"]
    assert len(items) == 6  # 7 total - 1 ("all") = 6
    for item in items:
        data = parse_qs(item["action"]["data"])
        assert data["district_id"][0] != "all"


def test_registration_confirm_flex() -> None:
    data = {"real_name": "Amy", "role_name": "巡查人員", "district_name": "景美工務段"}
    msg = FlexBuilder.registration_confirm_flex(data)
    assert_flex_message(msg, "註冊")
    body = msg["contents"]["body"]["contents"]
    text_values = [line["text"] for line in body]
    assert any("姓名：Amy" in line for line in text_values)
    assert any("角色：巡查人員" in line for line in text_values)
    assert any("工務段：景美工務段" in line for line in text_values)


def test_road_quick_reply() -> None:
    district_id = "jingmei"
    msg = FlexBuilder.road_quick_reply(district_id)
    assert_text_message(msg, "道路")
    assert_quick_reply_message(msg)

    roads = next(d["roads"] for d in _districts() if d["id"] == district_id)
    items = msg["quickReply"]["items"]
    assert len(items) == len(roads)
    for item in items:
        action = item["action"]
        data = parse_qs(action["data"])
        assert data["action"] == ["select_road"]
        assert data["district_id"] == [district_id]
        assert data["road"][0] in roads


def test_damage_mode_carousel() -> None:
    msg = FlexBuilder.damage_mode_carousel()
    assert_flex_message(msg, "災害類別")
    contents = msg["contents"]
    assert contents["type"] == "carousel"
    bubbles = contents["contents"]
    assert len(bubbles) == len(_damage_modes())
    for bubble in bubbles:
        assert bubble["type"] == "bubble"
        button = bubble["footer"]["contents"][0]
        data = parse_qs(button["action"]["data"])
        assert data["action"] == ["select_damage_category"]


@pytest.mark.parametrize("category", ["revetment_retaining", "road_slope", "bridge"])
def test_damage_mode_list(category: str) -> None:
    msg = FlexBuilder.damage_mode_list(category)
    assert_text_message(msg, "災損型態")
    items = msg["quickReply"]["items"]
    modes = _damage_modes()[category]
    assert len(items) == len(modes)
    for item in items:
        data = parse_qs(item["action"]["data"])
        assert data["action"] == ["select_damage_mode"]
        assert data["category"] == [category]
        assert data["mode_id"][0] in {mode["id"] for mode in modes}


def test_damage_cause_quick_reply() -> None:
    mode_id = _damage_modes()["revetment_retaining"][0]["id"]
    causes = _damage_modes()["revetment_retaining"][0]["causes"]

    msg = FlexBuilder.damage_cause_quick_reply(mode_id)
    assert_text_message(msg, "災害原因")
    items = msg["quickReply"]["items"]
    assert len(items) == len(causes) + 2
    assert any(item["action"].get("displayText") == "地震" for item in items)

    finish = items[-1]["action"]
    finish_data = parse_qs(finish["data"])
    assert finish_data["action"] == ["finish_damage_cause"]


def test_damage_cause_quick_reply_no_duplicate_earthquake() -> None:
    mode_id = _damage_modes()["road_slope"][0]["id"]
    causes = _damage_modes()["road_slope"][0]["causes"]

    msg = FlexBuilder.damage_cause_quick_reply(mode_id)
    items = msg["quickReply"]["items"]
    earthquake_items = [item for item in items if item["action"].get("displayText") == "地震"]

    assert any(cause["name"] == "地震" for cause in causes)
    assert len(earthquake_items) == 1


def test_report_confirm_flex() -> None:
    data = {
        "district_name": "景美工務段",
        "road": "台9",
        "coordinates_text": "25.01,121.55",
        "milepost_display": "12K+300",
        "damage_mode_name": "落石",
        "damage_cause_names": ["降雨", "風化"],
        "photo_count": 4,
        "estimated_cost_text": "200 萬",
        "description": "路側落石影響通行",
    }
    msg = FlexBuilder.report_confirm_flex(data)
    assert_flex_message(msg, "案件送出")
    body = msg["contents"]["body"]["contents"]
    text_rows = [row["text"] for row in body if row["type"] == "text"]
    assert any("工務段：景美工務段" in row for row in text_rows)
    assert any("災因：降雨,風化" in row for row in text_rows)
    assert any("照片：4 張" in row for row in text_rows)
    assert any("描述：路側落石影響通行" in row for row in text_rows)


def test_cost_item_prompt_flex() -> None:
    msg = FlexBuilder.cost_item_prompt_flex(0, "人工看守費", "人日", 4000, "quantity")
    assert_flex_message(msg, "人工看守費")
    body_text = msg["contents"]["body"]["contents"][0]["text"]
    assert "項目 1/6: 人工看守費" in body_text
    assert "單價: 4,000元/人日" in body_text
    assert "請輸入數量（人日）：" in body_text
    skip_action = msg["contents"]["footer"]["contents"][0]["action"]
    assert parse_qs(skip_action["data"])["action"] == ["cost_skip"]


def test_cost_summary_flex() -> None:
    msg = FlexBuilder.cost_summary_flex(
        [
            {
                "item_name": "人工看守費",
                "unit": "人日",
                "unit_price": 4000,
                "quantity": 2,
                "amount": 8000,
            },
            {
                "item_name": "其它費用",
                "unit": "元",
                "unit_price": None,
                "quantity": None,
                "amount": 12000,
            },
            {
                "item_name": "工程管理費",
                "unit": "元",
                "unit_price": None,
                "quantity": None,
                "amount": 0,
            },
        ],
        20000,
    )
    assert_flex_message(msg, "初估經費")
    body_rows = [row["text"] for row in msg["contents"]["body"]["contents"] if row["type"] == "text"]
    assert any("人工看守費: 2 人日 × 4,000 = 8,000元" in row for row in body_rows)
    assert any("其它費用: 12,000元" in row for row in body_rows)
    assert any("工程管理費: -" in row for row in body_rows)
    assert any("合計: 20,000元 (2.0萬元)" in row for row in body_rows)
    footer_actions = [parse_qs(btn["action"]["data"])["action"][0] for btn in msg["contents"]["footer"]["contents"]]
    assert footer_actions == ["cost_confirm", "cost_redo"]


def test_guided_photo_prompt() -> None:
    msg = FlexBuilder.guided_photo_prompt(2, "P2", "近景照", "請拍攝災點近距離")
    assert_text_message(msg)
    assert "第2張照片" in msg["text"]
    assert "近景照" in msg["text"]
    assert "請拍攝災點近距離" in msg["text"]


def test_optional_photo_chooser() -> None:
    msg = FlexBuilder.optional_photo_chooser(["P5", "P7"])
    assert msg["type"] == "flex"
    bubble = msg["contents"]
    assert bubble["type"] == "bubble"
    body = bubble["body"]
    # Body should contain: title, subtitle, separator, remaining P6/P8/P9/P10 rows,
    # separator, supplement title/desc, P1-P4 supplement rows, finish button
    # Find buttons with postback actions
    buttons_with_data = []
    def _collect_postback(node: dict[str, Any]) -> None:
        if node.get("type") == "button" and isinstance(node.get("action"), dict):
            act = node["action"]
            if act.get("type") == "postback" and "data" in act:
                buttons_with_data.append(act["data"])
        for child in node.get("contents", []):
            if isinstance(child, dict):
                _collect_postback(child)
    _collect_postback(body)
    # Should have 4 optional upload buttons (P6, P8, P9, P10) + 4 supplement buttons (P1-P4) + 1 finish = 9
    assert len(buttons_with_data) == 9
    assert any("action=finish_photos" in data for data in buttons_with_data)
    assert not any("photo_type=P5" in data and "choose_optional_type" in data for data in buttons_with_data)
    assert not any("photo_type=P7" in data and "choose_optional_type" in data for data in buttons_with_data)
    # P1-P4 supplement buttons should be present
    assert any("choose_supplement_type" in data and "photo_type=P1" in data for data in buttons_with_data)
    assert any("choose_supplement_type" in data and "photo_type=P4" in data for data in buttons_with_data)

    # Supplement section order should follow required order: P1 -> P2 -> P3 -> P4
    supplement_types = []
    for node in body["contents"]:
        if not isinstance(node, dict) or node.get("type") != "box":
            continue
        row_contents = node.get("contents", [])
        if len(row_contents) != 2:
            continue
        right = row_contents[1]
        action = right.get("action", {}) if isinstance(right, dict) else {}
        if action.get("type") != "postback" or "choose_supplement_type" not in action.get("data", ""):
            continue
        data = parse_qs(action.get("data", ""))
        supplement_types.append(data.get("photo_type", [""])[0])
    assert supplement_types == ["P1", "P2", "P3", "P4"]


def test_optional_photo_chooser_prefers_damage_specific_names() -> None:
    msg = FlexBuilder.optional_photo_chooser([], damage_category="road_slope")
    body = msg["contents"]["body"]
    supplement_types = []
    supplement_titles = []
    for node in body["contents"]:
        if not isinstance(node, dict) or node.get("type") != "box":
            continue
        row_contents = node.get("contents", [])
        if len(row_contents) != 2:
            continue
        right = row_contents[1]
        action = right.get("action", {}) if isinstance(right, dict) else {}
        if action.get("type") != "postback" or "choose_supplement_type" not in action.get("data", ""):
            continue
        data = parse_qs(action.get("data", ""))
        supplement_types.append(data.get("photo_type", [""])[0])
        left = row_contents[0]
        left_contents = left.get("contents", []) if isinstance(left, dict) else []
        if left_contents and isinstance(left_contents[0], dict):
            supplement_titles.append(left_contents[0].get("text", ""))

    assert supplement_types == ["P1", "P2", "P3", "P4"]
    assert supplement_titles[1].startswith("P2 ")
    assert supplement_titles[2].startswith("P3 ")


def test_tag_single_select_quick_reply() -> None:
    tags = [{"id": "north", "label": "北向"}, {"id": "south", "label": "南向"}]
    exclusions = [{"id": "none", "label": "無"}]
    msg = FlexBuilder.tag_single_select_quick_reply(
        category_name="拍攝方向",
        tags=tags,
        photo_set_type="P1",
        category_id="direction",
        current_index=1,
        total_count=2,
        source="photo",
        exclusion_tags=exclusions,
    )
    assert_text_message(msg)
    assert "(1/2)" in msg["text"]
    items = msg["quickReply"]["items"]
    assert len(items) == 3
    assert any(item["action"]["label"].startswith("⊘") for item in items)
    for item in items:
        data = parse_qs(item["action"]["data"])
        assert data["set"] == ["P1"]
        assert data["cat"] == ["direction"]


def test_tag_multi_select_flex() -> None:
    tags = [
        {"id": "a", "label": "A"},
        {"id": "b", "label": "B"},
        {"id": "c", "label": "C"},
    ]
    exclusions = [{"id": "x", "label": "排除X"}]
    msg = FlexBuilder.tag_multi_select_flex(
        category_name="現場風險",
        tags=tags,
        exclusion_tags=exclusions,
        photo_set_type="P1",
        category_id="site_risks",
        selected_tags=["b", "x"],
        current_index=2,
        total_count=4,
        source="photo",
    )
    assert_flex_message(msg)
    bubble = msg["contents"]
    assert bubble["type"] == "bubble"
    footer_button = bubble["footer"]["contents"][0]["action"]
    footer_data = parse_qs(footer_button["data"])
    assert footer_data["action"] == ["confirm_multi"]
    assert footer_data["set"] == ["P1"]
    assert footer_data["cat"] == ["site_risks"]


def test_annotation_summary_flex() -> None:
    annotations = {
        "photo_type_name": "全景照",
        "tags": [
            {"category_name": "方向", "label": "北向"},
            {"category_name": "天氣", "label": "晴天"},
        ],
        "custom_note": "現場有零星落石",
    }
    msg = FlexBuilder.annotation_summary_flex(0, annotations)
    assert_flex_message(msg, "照片標註")
    lines = [item["text"] for item in msg["contents"]["body"]["contents"]]
    assert any("照片 #1" in line for line in lines)
    assert any("方向：北向" in line for line in lines)
    assert any("天氣：晴天" in line for line in lines)
    assert any("備註：現場有零星落石" in line for line in lines)


def test_case_list_carousel_empty() -> None:
    msg = FlexBuilder.case_list_carousel([])
    assert_flex_message(msg, "案件列表")
    bubbles = msg["contents"]["contents"]
    assert len(bubbles) == 1
    first_text = bubbles[0]["body"]["contents"][0]["text"]
    assert "目前沒有案件" in first_text


def test_case_list_carousel_with_cases() -> None:
    cases = [
        {
            "case_id": "case_20260101_0001",
            "district_name": "景美工務段",
            "road_number": "台9",
            "damage_mode_name": "落石",
            "thumbnail_url": "",
        },
        {
            "case_id": "case_20260101_0002",
            "district_name": "中和工務段",
            "road_number": "台64",
            "damage_mode_name": "崩塌",
            "thumbnail_url": "https://example.com/a.jpg",
        },
    ]
    msg = FlexBuilder.case_list_carousel(cases)
    assert_flex_message(msg, "案件列表")
    bubbles = msg["contents"]["contents"]
    assert len(bubbles) == 2
    first_button_data = parse_qs(bubbles[0]["footer"]["contents"][0]["action"]["data"])
    assert first_button_data["action"] == ["open_case"]
    assert first_button_data["case_id"] == ["case_20260101_0001"]


def test_case_detail_flex() -> None:
    case = {
        "case_id": "case_20260101_0099",
        "district_name": "景美工務段",
        "road_number": "台9",
        "milepost": "13K+250",
        "damage_mode_name": "落石",
        "damage_cause_names": ["降雨", "風化"],
        "description": "邊坡落石",
        "photo_count": 5,
        "completeness_pct": 80,
        "review_status": "待審核",
        "coordinate_text": "25.0,121.5",
    }
    msg = FlexBuilder.case_detail_flex(case)
    assert_flex_message(msg, "案件詳情")
    footer = msg["contents"]["footer"]["contents"]
    actions = [parse_qs(btn["action"]["data"])["decision"][0] for btn in footer]
    assert actions == ["approve", "return", "close"]


def test_case_detail_flex_readonly_has_no_review_buttons() -> None:
    case = {"case_id": "case_20260101_0100"}
    msg = FlexBuilder.case_detail_flex(case, include_review_actions=False)
    assert_flex_message(msg, "案件詳情")
    footer = msg["contents"]["footer"]["contents"]
    assert footer == []


def test_statistics_flex() -> None:
    stats = {
        "total_cases": 10,
        "by_status": {"pending_review": 3, "in_progress": 2, "closed": 4, "returned": 1},
        "by_district": {"jingmei": 6, "zhonghe": 4},
        "today_new": 2,
    }
    msg = FlexBuilder.statistics_flex(stats, stats_url="https://example.com/stats")
    assert_flex_message(msg, "統計")
    assert "共 10 件案件" in msg["altText"]
    assert "footer" in msg["contents"]
    uri_action = msg["contents"]["footer"]["contents"][0]["action"]
    assert uri_action["type"] == "uri"
    assert uri_action["uri"] == "https://example.com/stats"


def test_profile_flex() -> None:
    user = {
        "real_name": "王小明",
        "display_name": "Ming",
        "role_name": "決策人員",
        "status_name": "啟用",
        "district_name": "景美工務段",
    }
    msg = FlexBuilder.profile_flex(user)
    assert_flex_message(msg, "個人資訊")
    text_rows = [item["text"] for item in msg["contents"]["body"]["contents"]]
    assert any("姓名：王小明" in row for row in text_rows)
    assert any("顯示名稱：Ming" in row for row in text_rows)
    assert any("角色：決策人員" in row for row in text_rows)


def test_help_message() -> None:
    msg = FlexBuilder.help_message()
    assert_text_message(msg)
    assert "可用指令" in msg["text"]
    assert "通報災害" in msg["text"]
    assert "個人資訊" in msg["text"]


def test_postback_data_encoding() -> None:
    data = _postback_data("select_tag", cat="direction", tag="north")
    parsed = parse_qs(data)
    assert parsed["action"] == ["select_tag"]
    assert parsed["cat"] == ["direction"]
    assert parsed["tag"] == ["north"]


def test_postback_data_special_chars() -> None:
    data = _postback_data("save_note", note="台9 雨勢大", value="a&b=c")
    parsed = parse_qs(data)
    assert parsed["action"] == ["save_note"]
    assert parsed["note"] == ["台9 雨勢大"]
    assert parsed["value"] == ["a&b=c"]


def test_district_data_matches_json_file() -> None:
    data_path = Path(__file__).resolve().parents[1] / "app" / "data" / "districts.json"
    with open(data_path, "r", encoding="utf-8") as file:
        raw = json.load(file)
    assert len(raw) == len(_districts()) == 7
    assert {item["id"] for item in raw} == {item["id"] for item in _districts()}


def test_damage_mode_categories_match_json_file() -> None:
    data_path = Path(__file__).resolve().parents[1] / "app" / "data" / "damage_modes.json"
    with open(data_path, "r", encoding="utf-8") as file:
        raw = json.load(file)
    assert set(raw.keys()) == set(_damage_modes().keys()) == {
        "revetment_retaining",
        "road_slope",
        "bridge",
    }


def test_photo_tags_contains_common_p1_definition() -> None:
    tags = _photo_tags()
    assert "common" in tags
    assert "P1" in tags["common"]
    p1 = tags["common"]["P1"]
    assert p1["required"] is True
    assert isinstance(p1["photo_tags"], list)


def test_disaster_type_select_flex():
    msg = FlexBuilder.disaster_type_select_flex()
    assert msg["type"] == "flex"
    assert "一般" in json.dumps(msg, ensure_ascii=False)
    assert "專案" in json.dumps(msg, ensure_ascii=False)


def test_processing_type_select_flex():
    msg = FlexBuilder.processing_type_select_flex()
    assert msg["type"] == "flex"
    assert "搶修" in json.dumps(msg, ensure_ascii=False)


def test_repeat_disaster_select_flex_with_prefill():
    msg = FlexBuilder.repeat_disaster_select_flex(prefill="是")
    text = json.dumps(msg, ensure_ascii=False)
    assert "照片標註建議" in text


def test_repeat_disaster_select_flex_no_prefill():
    msg = FlexBuilder.repeat_disaster_select_flex()
    text = json.dumps(msg, ensure_ascii=False)
    assert "照片標註建議" not in text


def test_original_protection_select_flex_with_prefill():
    msg = FlexBuilder.original_protection_select_flex(prefill="護岸工")
    assert msg["type"] == "flex"


def test_text_input_with_skip_flex():
    msg = FlexBuilder.text_input_with_skip_flex("測試", "請輸入", "skip_test")
    text = json.dumps(msg, ensure_ascii=False)
    assert "略過後補" in text


def test_text_input_with_skip_flex_with_hint():
    msg = FlexBuilder.text_input_with_skip_flex("測試", "請輸入", "skip_test", hint="提示")
    text = json.dumps(msg, ensure_ascii=False)
    assert "提示" in text


def test_file_upload_with_skip_flex():
    msg = FlexBuilder.file_upload_with_skip_flex("圖說上傳", "請上傳PDF", "skip_design")
    text = json.dumps(msg, ensure_ascii=False)
    assert "PDF" in text
    assert "略過後補" in text


def test_soil_conservation_select_flex():
    msg = FlexBuilder.soil_conservation_select_flex()
    text = json.dumps(msg, ensure_ascii=False)
    assert "已核定" in text
    assert "不需要" in text


def test_hazard_summary_flex_with_items():
    msg = FlexBuilder.hazard_summary_flex(["落石", "崩塌"], "skip_hazard")
    text = json.dumps(msg, ensure_ascii=False)
    assert "落石" in text
    assert "崩塌" in text


def test_hazard_summary_flex_empty():
    msg = FlexBuilder.hazard_summary_flex([], "skip_hazard")
    text = json.dumps(msg, ensure_ascii=False)
    assert "未識別" in text


def test_report_confirm_flex_new_fields():
    data = {
        "district_name": "桃園",
        "road": "台7線",
        "coordinates_text": "24.5, 121.3",
        "milepost_display": "32K+400",
        "damage_mode_name": "崩塌",
        "damage_cause_names": ["暴雨"],
        "photo_count": 4,
        "county_name": "桃園市",
        "town_name": "復興區",
        "village_name": "",
        "national_park": "",
        "estimated_cost_text": "50 萬元",
        "description": "邊坡崩塌",
        "disaster_type": "一般",
        "processing_type": "搶修",
        "repeat_disaster": "否",
        "original_protection": "護岸工",
        "analysis_review": "地質條件不佳",
        "design_doc_uploaded": True,
        "soil_conservation": "需要已核定",
        "safety_assessment": "安全無虞",
        "hazard_summary_text": "落石、崩塌",
    }
    msg = FlexBuilder.report_confirm_flex(data)
    text = json.dumps(msg, ensure_ascii=False)
    assert "災害類型：一般" in text
    assert "處理類型：搶修" in text
    assert "重複致災：否" in text
    assert "水土保持：需要已核定" in text
    assert "已上傳" in text


# ── quick_action_card 測試 ───────────────────────────────────


def test_quick_action_card_report_done() -> None:
    """通報完成情境應回傳正確 header 與按鈕組合。"""
    msg = FlexBuilder.quick_action_card("report_done", is_manager=False)
    assert msg["type"] == "flex"
    assert msg["altText"] == "快捷操作"
    bubble = msg["contents"]
    assert bubble["type"] == "bubble"
    assert bubble["size"] == "kilo"
    header_text = bubble["header"]["contents"][0]["text"]
    assert "通報已送出" in header_text
    buttons = bubble["body"]["contents"]
    assert len(buttons) == 3  # 查詢案件, 再次通報, 回選單
    labels = [b["action"]["label"] for b in buttons]
    assert any("查詢" in l for l in labels)
    assert any("通報" in l for l in labels)
    assert any("選單" in l for l in labels)


def test_quick_action_card_query_done() -> None:
    """查詢完成情境應回傳正確按鈕組合。"""
    msg = FlexBuilder.quick_action_card("query_done")
    bubble = msg["contents"]
    header_text = bubble["header"]["contents"][0]["text"]
    assert "查詢完成" in header_text
    buttons = bubble["body"]["contents"]
    assert len(buttons) == 3  # 通報災害, 查看地圖, 回選單
    labels = [b["action"]["label"] for b in buttons]
    assert any("通報" in l for l in labels)
    assert any("地圖" in l for l in labels)


def test_quick_action_card_review_done() -> None:
    """審核完成情境應只有 2 個按鈕。"""
    msg = FlexBuilder.quick_action_card("review_done", is_manager=True)
    bubble = msg["contents"]
    header_text = bubble["header"]["contents"][0]["text"]
    assert "審核完成" in header_text
    buttons = bubble["body"]["contents"]
    assert len(buttons) == 2  # 繼續審核, 回選單
    labels = [b["action"]["label"] for b in buttons]
    assert any("審核" in l for l in labels)
    assert any("選單" in l for l in labels)


def test_quick_action_card_word_done() -> None:
    """Word 報告產生完成情境應有 2 個按鈕。"""
    msg = FlexBuilder.quick_action_card("word_done")
    bubble = msg["contents"]
    header_text = bubble["header"]["contents"][0]["text"]
    assert "報告已產生" in header_text
    buttons = bubble["body"]["contents"]
    assert len(buttons) == 2  # 查詢案件, 回選單


def test_quick_action_card_general_fallback() -> None:
    """未知 context 應 fallback 至 general 按鈕組合。"""
    msg = FlexBuilder.quick_action_card("unknown_context")
    bubble = msg["contents"]
    header_text = bubble["header"]["contents"][0]["text"]
    assert "操作完成" in header_text
    buttons = bubble["body"]["contents"]
    assert len(buttons) == 3  # 通報災害, 查詢案件, 回選單


def test_quick_action_card_buttons_use_postback() -> None:
    """所有按鈕都應使用 postback action。"""
    for ctx in ["report_done", "query_done", "review_done", "word_done", "general"]:
        msg = FlexBuilder.quick_action_card(ctx)
        for btn in msg["contents"]["body"]["contents"]:
            assert btn["type"] == "button"
            assert btn["action"]["type"] == "postback"
            assert "data" in btn["action"]


def test_quick_action_card_header_colors_differ() -> None:
    """不同情境的 header 顏色應有區分。"""
    colors = set()
    for ctx in ["report_done", "query_done", "review_done", "word_done", "general"]:
        msg = FlexBuilder.quick_action_card(ctx)
        color = msg["contents"]["header"]["backgroundColor"]
        colors.add(color)
    # report_done 與 word_done 同色 (SUCCESS), review_done (JUDGMENT), query_done (INFO), general (NEUTRAL)
    assert len(colors) >= 4
