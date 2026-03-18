# Word 欄位補齊 (P1-P5) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 8 new reporting flow steps (P1 auto-fill, P2 selections, P3 inputs, P4 regulatory, P5 hazard summary) so the Case model captures all remaining Word document fields.

**Architecture:** New ReportingStep enum values inserted between ESTIMATED_COST and CONFIRM_SUBMIT. Each step has a FlexBuilder method, a handler block in line_flow.py, and corresponding Case model fields. P1 fields are auto-derived (no user step). P2/P3/P4/P5 are user-facing steps. Text-input fields offer "略過後補" skip option.

**Tech Stack:** Python, Pydantic, LINE Flex Messages, pytest

---

## Summary of Changes

### New ReportingStep enum values (in order, after ESTIMATED_COST):
1. `DISASTER_TYPE` — P2: 一般災害/專案 (single select, required)
2. `PROCESSING_TYPE` — P2: 搶修/復建 (single select, required)
3. `REPEAT_DISASTER` — P2: 是否重複致災 (single select, required, pre-fill from P9)
4. `ORIGINAL_PROTECTION` — P3: 原設計保護型式 (single select, required, pre-fill from P4)
5. `ANALYSIS_REVIEW` — P3: 分析與檢討 (text input, skippable)
6. `DESIGN_DOCS` — P3: 設計圖說上傳 PDF (file upload, skippable)
7. `SOIL_CONSERVATION` — P4: 水土保持計畫 (single select, required)
8. `SAFETY_ASSESSMENT` — P4: 整體安全評估 (text input, skippable)
9. `HAZARD_IDENTIFICATION` — P5: 工址環境危害辨識 (auto-summary + text supplement, skippable)

### New Case model fields:
- `reporting_agency: str` — P1: 寫死 "交通部公路局北區養護工程分局"
- `reporting_year: str` — P1: 自動帶入民國年
- `disaster_type: str` — P2: "一般" | "專案"
- `processing_type: str` — P2: "搶修" | "復建"
- `repeat_disaster: str` — P2: "是" | "否"
- `original_protection: str` — P3: 原設計保護型式
- `analysis_review: str` — P3: 分析與檢討文字
- `design_doc_evidence_id: str` — P3: 設計圖說 PDF evidence ID
- `soil_conservation: str` — P4: 水土保持計畫狀態
- `safety_assessment: str` — P4: 整體安全評估文字
- `hazard_summary: list[str]` — P5: 自動彙整的危害項目
- `hazard_supplement: str` — P5: 使用者補充說明

### P1 auto-fill logic (no user step):
- `reporting_agency` = "交通部公路局北區養護工程分局" (constant)
- `reporting_year` = current ROC year (西元年 - 1911)
- `承辦人` = `created_by.real_name` (already captured at registration)

### P5 hazard auto-extraction sources:
- P1 `site_risks` tags → map to hazard labels
- P6 `structure_hazard` judgment tags → map to hazard labels
- P8 `traffic_risk` judgment tags → map to hazard labels
- P10 `other_hazard` judgment tags → map to hazard labels
- `site_survey_selected` items → map to hazard labels

---

## Task 1: Add Case Model Fields

**Files:**
- Modify: `app/models/case.py`
- Test: `tests/test_case_model.py` (new)

**Step 1: Add new fields to Case model**

In `app/models/case.py`, add after the `cost_breakdown` field (line ~163):

```python
    # --- P1: Auto-fill ---
    reporting_agency: str = Field(default="交通部公路局北區養護工程分局", description="提報機關")
    reporting_year: str = Field(default="", description="年度 (民國年)")

    # --- P2: User selections ---
    disaster_type: str = Field(default="", description="災害類型: 一般 | 專案")
    processing_type: str = Field(default="", description="處理類型: 搶修 | 復建")
    repeat_disaster: str = Field(default="", description="是否重複致災: 是 | 否")

    # --- P3: Analysis ---
    original_protection: str = Field(default="", description="原設計保護型式")
    analysis_review: str = Field(default="", description="分析與檢討")
    design_doc_evidence_id: str = Field(default="", description="設計圖說 PDF evidence ID")

    # --- P4: Regulatory ---
    soil_conservation: str = Field(default="", description="水土保持計畫: 需要已核定 | 需要未核定 | 不需要")
    safety_assessment: str = Field(default="", description="整體安全評估")

    # --- P5: Hazard ---
    hazard_summary: list[str] = Field(default_factory=list, description="自動彙整工址環境危害項目")
    hazard_supplement: str = Field(default="", description="工址環境危害補充說明")
```

**Step 2: Run existing tests to verify no breakage**

Run: `pytest tests/ -x -q`
Expected: All 186 tests pass (new fields have defaults, no breakage)

---

## Task 2: Add ReportingStep Enum Values

**Files:**
- Modify: `app/models/line_state.py`

**Step 1: Add new enum values after ESTIMATED_COST (line 49)**

Add these values between `ESTIMATED_COST` and `CONFIRM_SUBMIT`:

```python
    DISASTER_TYPE = "disaster_type"              # Step 12a - P2
    PROCESSING_TYPE = "processing_type"          # Step 12b - P2
    REPEAT_DISASTER = "repeat_disaster"          # Step 12c - P2
    ORIGINAL_PROTECTION = "original_protection"  # Step 12d - P3
    ANALYSIS_REVIEW = "analysis_review"          # Step 12e - P3
    DESIGN_DOCS = "design_docs"                  # Step 12f - P3
    SOIL_CONSERVATION = "soil_conservation"      # Step 12g - P4
    SAFETY_ASSESSMENT = "safety_assessment"      # Step 12h - P4
    HAZARD_IDENTIFICATION = "hazard_identification"  # Step 12i - P5
```

Keep CONFIRM_SUBMIT and DONE after these.

**Step 2: Run existing tests**

Run: `pytest tests/ -x -q`
Expected: All pass (enum values are additive)

---

## Task 3: Add FlexBuilder Methods for New Steps

**Files:**
- Modify: `app/services/flex_builders.py`
- Test: `tests/test_flex_builders.py` (add tests)

**Step 1: Add `disaster_type_select_flex` — P2 single select (一般/專案)**

```python
    @staticmethod
    def disaster_type_select_flex() -> dict:
        return {
            "type": "flex",
            "altText": "選擇災害類型",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box", "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [{"type": "text", "text": "災害類型", "weight": "bold", "color": "#FFFFFF"}],
                },
                "body": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "請選擇災害類型：", "size": "sm", "margin": "md"},
                        {
                            "type": "button", "style": "primary",
                            "action": {"type": "postback", "label": "一般災害", "data": _postback_data("select_disaster_type", value="一般")},
                            "margin": "md",
                        },
                        {
                            "type": "button", "style": "primary",
                            "action": {"type": "postback", "label": "專案", "data": _postback_data("select_disaster_type", value="專案")},
                            "margin": "sm",
                        },
                    ],
                },
            },
        }
```

**Step 2: Add `processing_type_select_flex` — P2 single select (搶修/復建)**

```python
    @staticmethod
    def processing_type_select_flex() -> dict:
        return {
            "type": "flex",
            "altText": "選擇處理類型",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box", "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [{"type": "text", "text": "處理類型", "weight": "bold", "color": "#FFFFFF"}],
                },
                "body": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "請選擇處理類型：", "size": "sm", "margin": "md"},
                        {
                            "type": "button", "style": "primary",
                            "action": {"type": "postback", "label": "搶修", "data": _postback_data("select_processing_type", value="搶修")},
                            "margin": "md",
                        },
                        {
                            "type": "button", "style": "primary",
                            "action": {"type": "postback", "label": "復建", "data": _postback_data("select_processing_type", value="復建")},
                            "margin": "sm",
                        },
                    ],
                },
            },
        }
```

**Step 3: Add `repeat_disaster_select_flex` — P2 single select with pre-fill indicator**

```python
    @staticmethod
    def repeat_disaster_select_flex(prefill: str = "") -> dict:
        hint = f"\n（照片標註建議：{prefill}）" if prefill else ""
        return {
            "type": "flex",
            "altText": "是否重複致災",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box", "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [{"type": "text", "text": "是否重複致災", "weight": "bold", "color": "#FFFFFF"}],
                },
                "body": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": f"該地點是否屬於重複致災？{hint}", "size": "sm", "wrap": True, "margin": "md"},
                        {
                            "type": "button", "style": "primary",
                            "action": {"type": "postback", "label": "是—重複致災", "data": _postback_data("select_repeat_disaster", value="是")},
                            "margin": "md",
                        },
                        {
                            "type": "button", "style": "secondary",
                            "action": {"type": "postback", "label": "否—非重複致災", "data": _postback_data("select_repeat_disaster", value="否")},
                            "margin": "sm",
                        },
                    ],
                },
            },
        }
```

**Step 4: Add `original_protection_select_flex` — P3 with pre-fill from P4 annotation**

```python
    @staticmethod
    def original_protection_select_flex(prefill: str = "") -> dict:
        options = [
            ("重力式擋土牆", "重力式擋土牆"),
            ("懸臂式擋土牆", "懸臂式擋土牆"),
            ("加勁擋土牆", "加勁擋土牆"),
            ("護岸工", "護岸工"),
            ("護坡工", "護坡工"),
            ("地錨系統", "地錨系統"),
            ("無保護(自然邊坡)", "無保護(自然邊坡)"),
        ]
        hint = f"\n（照片標註建議：{prefill}）" if prefill else ""
        buttons = []
        for label, value in options:
            style = "primary" if value == prefill else "secondary"
            buttons.append({
                "type": "button", "style": style, "height": "sm",
                "action": {"type": "postback", "label": label, "data": _postback_data("select_original_protection", value=value)},
                "margin": "sm",
            })
        return {
            "type": "flex",
            "altText": "原設計保護型式",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box", "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [{"type": "text", "text": "原設計保護型式", "weight": "bold", "color": "#FFFFFF"}],
                },
                "body": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": f"請選擇原設計保護型式：{hint}", "size": "sm", "wrap": True, "margin": "md"},
                        *buttons,
                    ],
                },
            },
        }
```

**Step 5: Add `text_input_with_skip_flex` — generic skippable text input**

Used for: P3 分析與檢討, P4 整體安全評估, P5 補充說明

```python
    @staticmethod
    def text_input_with_skip_flex(title: str, prompt: str, skip_action: str, hint: str = "") -> dict:
        body_contents = []
        if hint:
            body_contents.append({"type": "text", "text": hint, "size": "xs", "color": NEUTRAL_COLOR, "wrap": True, "margin": "md"})
        body_contents.append({"type": "text", "text": prompt, "size": "sm", "wrap": True, "margin": "md"})
        return {
            "type": "flex",
            "altText": title,
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box", "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [{"type": "text", "text": title, "weight": "bold", "color": "#FFFFFF"}],
                },
                "body": {"type": "box", "layout": "vertical", "contents": body_contents},
                "footer": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {
                            "type": "button", "style": "secondary", "height": "sm",
                            "action": {"type": "postback", "label": "略過後補", "data": _postback_data(skip_action)},
                        },
                    ],
                },
            },
        }
```

**Step 6: Add `file_upload_with_skip_flex` — P3 設計圖說 PDF upload**

```python
    @staticmethod
    def file_upload_with_skip_flex(title: str, prompt: str, skip_action: str) -> dict:
        return {
            "type": "flex",
            "altText": title,
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box", "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [{"type": "text", "text": title, "weight": "bold", "color": "#FFFFFF"}],
                },
                "body": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": prompt, "size": "sm", "wrap": True, "margin": "md"},
                        {"type": "text", "text": "📎 請傳送 PDF 檔案", "size": "xs", "color": NEUTRAL_COLOR, "margin": "sm"},
                    ],
                },
                "footer": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {
                            "type": "button", "style": "secondary", "height": "sm",
                            "action": {"type": "postback", "label": "略過後補", "data": _postback_data(skip_action)},
                        },
                    ],
                },
            },
        }
```

**Step 7: Add `soil_conservation_select_flex` — P4 水土保持計畫**

```python
    @staticmethod
    def soil_conservation_select_flex() -> dict:
        return {
            "type": "flex",
            "altText": "水土保持計畫",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box", "layout": "vertical",
                    "backgroundColor": INFO_COLOR,
                    "contents": [{"type": "text", "text": "水土保持計畫", "weight": "bold", "color": "#FFFFFF"}],
                },
                "body": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": "本案是否需要水土保持計畫？", "size": "sm", "wrap": True, "margin": "md"},
                        {
                            "type": "button", "style": "primary",
                            "action": {"type": "postback", "label": "需要—已核定", "data": _postback_data("select_soil_conservation", value="需要已核定")},
                            "margin": "md",
                        },
                        {
                            "type": "button", "style": "primary",
                            "action": {"type": "postback", "label": "需要—未核定", "data": _postback_data("select_soil_conservation", value="需要未核定")},
                            "margin": "sm",
                        },
                        {
                            "type": "button", "style": "secondary",
                            "action": {"type": "postback", "label": "不需要", "data": _postback_data("select_soil_conservation", value="不需要")},
                            "margin": "sm",
                        },
                    ],
                },
            },
        }
```

**Step 8: Add `hazard_summary_flex` — P5 auto-summary with skip**

```python
    @staticmethod
    def hazard_summary_flex(hazard_items: list[str], skip_action: str) -> dict:
        if hazard_items:
            summary_text = "📋 根據照片標註與現場勘查，系統識別以下工址風險：\n\n" + "\n".join(f"• {item}" for item in hazard_items)
            prompt_text = "\n\n如需補充說明，請直接輸入文字；或點選「略過後補」。"
        else:
            summary_text = "📋 照片標註中未識別到特定工址風險。"
            prompt_text = "\n\n如需填寫工址環境危害辨識說明，請直接輸入文字；或點選「略過後補」。"
        return {
            "type": "flex",
            "altText": "工址環境危害辨識",
            "contents": {
                "type": "bubble",
                "header": {
                    "type": "box", "layout": "vertical",
                    "backgroundColor": JUDGMENT_COLOR,
                    "contents": [{"type": "text", "text": "工址環境危害辨識", "weight": "bold", "color": "#FFFFFF"}],
                },
                "body": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": summary_text + prompt_text, "size": "sm", "wrap": True},
                    ],
                },
                "footer": {
                    "type": "box", "layout": "vertical",
                    "contents": [
                        {
                            "type": "button", "style": "primary", "height": "sm",
                            "action": {"type": "postback", "label": "確認（不補充）", "data": _postback_data("hazard_confirm")},
                        },
                        {
                            "type": "button", "style": "secondary", "height": "sm",
                            "action": {"type": "postback", "label": "略過後補", "data": _postback_data(skip_action)},
                            "margin": "sm",
                        },
                    ],
                },
            },
        }
```

**Step 9: Update `report_confirm_flex` to include new fields**

Add these lines to the `lines` list in `report_confirm_flex`:

```python
            f"災害類型：{data.get('disaster_type', '-')}",
            f"處理類型：{data.get('processing_type', '-')}",
            f"重複致災：{data.get('repeat_disaster', '-')}",
            f"原設計保護：{data.get('original_protection', '-')}",
            f"分析與檢討：{data.get('analysis_review', '') or '略過後補'}",
            f"設計圖說：{'已上傳' if data.get('design_doc_uploaded') else '略過後補'}",
            f"水土保持：{data.get('soil_conservation', '-')}",
            f"安全評估：{data.get('safety_assessment', '') or '略過後補'}",
            f"工址危害：{data.get('hazard_summary_text', '') or '略過後補'}",
```

**Step 10: Write tests for new FlexBuilder methods**

Add to `tests/test_flex_builders.py`:

```python
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
```

**Step 11: Run all tests**

Run: `pytest tests/ -x -q`
Expected: All pass

---

## Task 4: Add Step Handlers in line_flow.py

**Files:**
- Modify: `app/services/line_flow.py`

This is the core task. Add handler blocks for each new step.

### Step transition chain:

Current: `ESTIMATED_COST → (cost_confirm) → CONFIRM_SUBMIT`

New: `ESTIMATED_COST → (cost_confirm) → DISASTER_TYPE → PROCESSING_TYPE → REPEAT_DISASTER → ORIGINAL_PROTECTION → ANALYSIS_REVIEW → DESIGN_DOCS → SOIL_CONSERVATION → SAFETY_ASSESSMENT → HAZARD_IDENTIFICATION → CONFIRM_SUBMIT`

**Step 1: Modify cost_confirm transition**

Change the `cost_confirm` handler (line ~872) to advance to `DISASTER_TYPE` instead of `CONFIRM_SUBMIT`:

```python
            if action == "cost_confirm":
                total = sum(ci.get("amount", 0) or 0 for ci in cost_items_data)
                session.store_data("estimated_cost", total / 10000 if total > 0 else None)
                session.advance_step(ReportingStep.DISASTER_TYPE.value)
                return [FlexBuilder.disaster_type_select_flex()]
```

**Step 2: Add DISASTER_TYPE handler**

After the ESTIMATED_COST handler block:

```python
        if step == ReportingStep.DISASTER_TYPE.value:
            if action == "select_disaster_type":
                value = payload.get("value", "")
                if value in ("一般", "專案"):
                    session.store_data("disaster_type", value)
                    session.advance_step(ReportingStep.PROCESSING_TYPE.value)
                    return [FlexBuilder.processing_type_select_flex()]
            return [FlexBuilder.disaster_type_select_flex()]
```

**Step 3: Add PROCESSING_TYPE handler**

```python
        if step == ReportingStep.PROCESSING_TYPE.value:
            if action == "select_processing_type":
                value = payload.get("value", "")
                if value in ("搶修", "復建"):
                    session.store_data("processing_type", value)
                    # Pre-fill from P9 repeat_disaster judgment tag
                    prefill = self._extract_repeat_disaster_prefill(session)
                    session.advance_step(ReportingStep.REPEAT_DISASTER.value)
                    return [FlexBuilder.repeat_disaster_select_flex(prefill=prefill)]
            return [FlexBuilder.processing_type_select_flex()]
```

**Step 4: Add REPEAT_DISASTER handler**

```python
        if step == ReportingStep.REPEAT_DISASTER.value:
            if action == "select_repeat_disaster":
                value = payload.get("value", "")
                if value in ("是", "否"):
                    session.store_data("repeat_disaster", value)
                    prefill = self._extract_original_protection_prefill(session)
                    session.advance_step(ReportingStep.ORIGINAL_PROTECTION.value)
                    return [FlexBuilder.original_protection_select_flex(prefill=prefill)]
            prefill = self._extract_repeat_disaster_prefill(session)
            return [FlexBuilder.repeat_disaster_select_flex(prefill=prefill)]
```

**Step 5: Add ORIGINAL_PROTECTION handler**

```python
        if step == ReportingStep.ORIGINAL_PROTECTION.value:
            if action == "select_original_protection":
                value = payload.get("value", "")
                if value:
                    session.store_data("original_protection", value)
                    session.advance_step(ReportingStep.ANALYSIS_REVIEW.value)
                    return [FlexBuilder.text_input_with_skip_flex(
                        "分析與檢討",
                        "請輸入災害分析與檢討說明：",
                        "skip_analysis_review",
                    )]
            prefill = self._extract_original_protection_prefill(session)
            return [FlexBuilder.original_protection_select_flex(prefill=prefill)]
```

**Step 6: Add ANALYSIS_REVIEW handler (skippable text)**

```python
        if step == ReportingStep.ANALYSIS_REVIEW.value:
            if action == "skip_analysis_review":
                session.store_data("analysis_review", "")
                session.advance_step(ReportingStep.DESIGN_DOCS.value)
                return [FlexBuilder.file_upload_with_skip_flex(
                    "設計圖說",
                    "如有設計圖說請上傳 PDF 檔案：",
                    "skip_design_docs",
                )]
            if text:
                session.store_data("analysis_review", text)
                session.advance_step(ReportingStep.DESIGN_DOCS.value)
                return [FlexBuilder.file_upload_with_skip_flex(
                    "設計圖說",
                    "如有設計圖說請上傳 PDF 檔案：",
                    "skip_design_docs",
                )]
            return [FlexBuilder.text_input_with_skip_flex(
                "分析與檢討",
                "請輸入災害分析與檢討說明：",
                "skip_analysis_review",
            )]
```

**Step 7: Add DESIGN_DOCS handler (skippable PDF upload)**

```python
        if step == ReportingStep.DESIGN_DOCS.value:
            if action == "skip_design_docs":
                session.store_data("design_doc_evidence_id", "")
                session.advance_step(ReportingStep.SOIL_CONSERVATION.value)
                return [FlexBuilder.soil_conservation_select_flex()]
            if message_type == "file":
                # Store the PDF file — use existing evidence_store
                case_id = self._ensure_draft_case(session, source_key, display_name, "")
                if case_id and content_bytes:
                    content_type = getattr(content_bytes, 'content_type', 'application/pdf') if hasattr(content_bytes, 'content_type') else 'application/pdf'
                    evidence = self._evidence.store_evidence(
                        case_id=case_id,
                        original_filename="design_doc.pdf",
                        content_type="application/pdf",
                        content=content_bytes,
                    )
                    if evidence:
                        session.store_data("design_doc_evidence_id", evidence.evidence_id)
                        session.advance_step(ReportingStep.SOIL_CONSERVATION.value)
                        return [
                            FlexBuilder.text_message("✅ 設計圖說已上傳"),
                            FlexBuilder.soil_conservation_select_flex(),
                        ]
                return [FlexBuilder.text_message("❌ 檔案上傳失敗，請重試或略過。")]
            return [FlexBuilder.file_upload_with_skip_flex(
                "設計圖說",
                "如有設計圖說請上傳 PDF 檔案：",
                "skip_design_docs",
            )]
```

NOTE: The DESIGN_DOCS handler needs access to file content. Check how UPLOAD_PHOTOS currently handles image uploads to match the pattern. The actual implementation may need to download the file from LINE via `message_content` API. The subagent implementing this MUST study the UPLOAD_PHOTOS handler pattern and replicate it for PDF files.

**Step 8: Add SOIL_CONSERVATION handler**

```python
        if step == ReportingStep.SOIL_CONSERVATION.value:
            if action == "select_soil_conservation":
                value = payload.get("value", "")
                if value:
                    session.store_data("soil_conservation", value)
                    session.advance_step(ReportingStep.SAFETY_ASSESSMENT.value)
                    return [FlexBuilder.text_input_with_skip_flex(
                        "整體安全評估",
                        "請輸入整體安全評估說明：",
                        "skip_safety_assessment",
                    )]
            return [FlexBuilder.soil_conservation_select_flex()]
```

**Step 9: Add SAFETY_ASSESSMENT handler (skippable text)**

```python
        if step == ReportingStep.SAFETY_ASSESSMENT.value:
            if action == "skip_safety_assessment":
                session.store_data("safety_assessment", "")
                hazard_items = self._extract_hazard_items(session)
                session.store_data("hazard_summary", hazard_items)
                session.advance_step(ReportingStep.HAZARD_IDENTIFICATION.value)
                return [FlexBuilder.hazard_summary_flex(hazard_items, "skip_hazard")]
            if text:
                session.store_data("safety_assessment", text)
                hazard_items = self._extract_hazard_items(session)
                session.store_data("hazard_summary", hazard_items)
                session.advance_step(ReportingStep.HAZARD_IDENTIFICATION.value)
                return [FlexBuilder.hazard_summary_flex(hazard_items, "skip_hazard")]
            return [FlexBuilder.text_input_with_skip_flex(
                "整體安全評估",
                "請輸入整體安全評估說明：",
                "skip_safety_assessment",
            )]
```

**Step 10: Add HAZARD_IDENTIFICATION handler**

```python
        if step == ReportingStep.HAZARD_IDENTIFICATION.value:
            if action == "hazard_confirm":
                session.store_data("hazard_supplement", "")
                session.advance_step(ReportingStep.CONFIRM_SUBMIT.value)
                return [
                    FlexBuilder.report_confirm_flex(self._build_report_summary(session)),
                    FlexBuilder.confirm_message("確認送出案件？", "action=submit_report", "action=cancel"),
                ]
            if action == "skip_hazard":
                session.store_data("hazard_supplement", "")
                session.advance_step(ReportingStep.CONFIRM_SUBMIT.value)
                return [
                    FlexBuilder.report_confirm_flex(self._build_report_summary(session)),
                    FlexBuilder.confirm_message("確認送出案件？", "action=submit_report", "action=cancel"),
                ]
            if text:
                session.store_data("hazard_supplement", text)
                session.advance_step(ReportingStep.CONFIRM_SUBMIT.value)
                return [
                    FlexBuilder.report_confirm_flex(self._build_report_summary(session)),
                    FlexBuilder.confirm_message("確認送出案件？", "action=submit_report", "action=cancel"),
                ]
            hazard_items = session.get_data("hazard_summary", [])
            return [FlexBuilder.hazard_summary_flex(hazard_items, "skip_hazard")]
```

---

## Task 5: Add Helper Methods to LineFlowController

**Files:**
- Modify: `app/services/line_flow.py`

**Step 1: Add `_extract_repeat_disaster_prefill`**

Extract from P9 photo annotation `repeat_disaster` judgment tag:

```python
    def _extract_repeat_disaster_prefill(self, session: LineSession) -> str:
        """Extract repeat_disaster pre-fill from P9 photo annotation."""
        annotations = session.get_data("photo_annotations", {})
        for _idx, ann in annotations.items():
            if ann.get("photo_type") == "P9":
                for tag in ann.get("tags", []):
                    if tag.get("category") == "repeat_disaster":
                        tag_id = tag.get("tag_id", "")
                        if tag_id == "repeat_yes":
                            return "是"
                        elif tag_id == "repeat_no":
                            return "否"
        return ""
```

**Step 2: Add `_extract_original_protection_prefill`**

Extract from P4 photo annotation `original_protection` judgment tag:

```python
    # Mapping from photo_tags.json tag IDs to display labels
    _PROTECTION_TAG_MAP = {
        "gravity_wall": "重力式擋土牆",
        "cantilever_wall": "懸臂式擋土牆",
        "reinforced_earth": "加勁擋土牆",
        "revetment": "護岸工",
        "slope_protection_eng": "護坡工",
        "ground_anchor_sys": "地錨系統",
        "no_protection": "無保護(自然邊坡)",
    }

    def _extract_original_protection_prefill(self, session: LineSession) -> str:
        """Extract original_protection pre-fill from P4 photo annotation."""
        annotations = session.get_data("photo_annotations", {})
        for _idx, ann in annotations.items():
            if ann.get("photo_type") == "P4":
                for tag in ann.get("tags", []):
                    if tag.get("category") == "original_protection":
                        tag_id = tag.get("tag_id", "")
                        return self._PROTECTION_TAG_MAP.get(tag_id, "")
        return ""
```

**Step 3: Add `_extract_hazard_items`**

Collect from multiple annotation sources + site survey:

```python
    def _extract_hazard_items(self, session: LineSession) -> list[str]:
        """Extract hazard items from photo annotations and site survey for P5 auto-summary."""
        hazard_items: list[str] = []
        seen: set[str] = set()

        annotations = session.get_data("photo_annotations", {})

        # Source 1: P1 site_risks tags
        # Source 2: P6 structure_hazard judgment tags
        # Source 3: P8 traffic_risk judgment tags
        # Source 4: P10 other_hazard judgment tags
        hazard_categories = {
            "site_risks",
            "structure_hazard",
            "traffic_risk",
            "other_hazard",
        }

        for _idx, ann in annotations.items():
            for tag in ann.get("tags", []):
                category = tag.get("category", "")
                if category in hazard_categories:
                    label = tag.get("label", "")
                    if label and label not in seen:
                        seen.add(label)
                        hazard_items.append(label)

        # Source 5: site_survey selected items
        selected_survey = set(session.get_data("site_survey_selected", []))
        for category in self._site_survey:
            for item in category.get("items", []):
                item_id = item.get("item_id", "")
                if item_id in selected_survey:
                    label = item.get("item_name", "")
                    if label and label not in seen:
                        seen.add(label)
                        hazard_items.append(label)

        return hazard_items
```

---

## Task 6: Update _build_report_summary and _apply_session_to_case

**Files:**
- Modify: `app/services/line_flow.py`

**Step 1: Update `_build_report_summary`**

Add new fields to the returned dict:

```python
            "disaster_type": session.get_data("disaster_type", ""),
            "processing_type": session.get_data("processing_type", ""),
            "repeat_disaster": session.get_data("repeat_disaster", ""),
            "original_protection": session.get_data("original_protection", ""),
            "analysis_review": session.get_data("analysis_review", ""),
            "design_doc_uploaded": bool(session.get_data("design_doc_evidence_id", "")),
            "soil_conservation": session.get_data("soil_conservation", ""),
            "safety_assessment": session.get_data("safety_assessment", ""),
            "hazard_summary_text": "、".join(session.get_data("hazard_summary", [])) or "",
```

**Step 2: Update `_apply_session_to_case`**

Add after the existing field assignments:

```python
        # P1 auto-fill
        from datetime import datetime as _dt
        case.reporting_agency = "交通部公路局北區養護工程分局"
        case.reporting_year = str(_dt.now().year - 1911)

        # P2
        case.disaster_type = session.get_data("disaster_type", "")
        case.processing_type = session.get_data("processing_type", "")
        case.repeat_disaster = session.get_data("repeat_disaster", "")

        # P3
        case.original_protection = session.get_data("original_protection", "")
        case.analysis_review = session.get_data("analysis_review", "")
        case.design_doc_evidence_id = session.get_data("design_doc_evidence_id", "")

        # P4
        case.soil_conservation = session.get_data("soil_conservation", "")
        case.safety_assessment = session.get_data("safety_assessment", "")

        # P5
        case.hazard_summary = session.get_data("hazard_summary", [])
        case.hazard_supplement = session.get_data("hazard_supplement", "")
```

---

## Task 7: Update Back Navigation

**Files:**
- Modify: `app/services/line_flow.py`

Update the "返回" (back) handler to support navigating back through the new steps. The back navigation should follow the reverse of the forward chain. Each new step should be able to go back to the previous step.

Find the existing back navigation logic and add entries for each new step mapping to its previous step.

---

## Task 8: Write Integration Tests

**Files:**
- Test: `tests/test_line_flow.py` (add tests)

```python
def test_disaster_type_step():
    """Test that DISASTER_TYPE step accepts valid selection and advances."""
    # Setup session at DISASTER_TYPE step
    # Send postback with action=select_disaster_type&value=一般
    # Verify session advances to PROCESSING_TYPE
    # Verify session.data["disaster_type"] == "一般"

def test_processing_type_step():
    """Similar test for PROCESSING_TYPE."""

def test_repeat_disaster_prefill_from_p9():
    """Test that P9 repeat_disaster annotation pre-fills the select."""
    # Setup session with P9 annotation containing repeat_yes tag
    # Advance to REPEAT_DISASTER step
    # Verify the flex message includes "照片標註建議：是"

def test_analysis_review_skip():
    """Test that skip_analysis_review advances to DESIGN_DOCS."""

def test_design_docs_skip():
    """Test that skip_design_docs advances to SOIL_CONSERVATION."""

def test_hazard_extraction():
    """Test _extract_hazard_items collects from all sources."""
    # Setup session with:
    #   - P1 annotation with site_risks tags
    #   - P10 annotation with other_hazard tags
    #   - site_survey_selected items
    # Call _extract_hazard_items
    # Verify all unique hazard labels are collected

def test_full_flow_with_new_steps():
    """E2E test walking through all new steps to CONFIRM_SUBMIT."""
```

---

## Task 9: Run All Tests and Verify

Run: `pytest tests/ -x -v`
Expected: All tests pass (186 existing + ~20 new = ~206)

Run: `python -m py_compile app/services/line_flow.py`
Expected: No syntax errors

Run: LSP diagnostics on all modified files
Expected: No type errors

---

## Execution Notes

- Tasks 1-2 are independent and can be done in parallel
- Task 3 depends on Task 2 (uses new enum values in postback data)
- Tasks 4-6 depend on Tasks 1-3
- Task 7 depends on Tasks 4-6
- Task 8 depends on all previous tasks

### Key risks:
1. DESIGN_DOCS PDF upload — needs to match existing UPLOAD_PHOTOS pattern for downloading LINE file content
2. Back navigation — must be tested carefully for all 9 new steps
3. Hazard extraction — depends on photo_annotations data structure being consistent

### P1 auto-fill fields require NO user step:
- `reporting_agency` and `reporting_year` are set in `_apply_session_to_case` only
- `承辦人` is already `created_by.real_name`
