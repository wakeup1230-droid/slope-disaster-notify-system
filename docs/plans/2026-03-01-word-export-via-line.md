# Word 報告匯出 + LINE 傳送 + 完成度顯示

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 案件送出後提供可選的「產生 Word 報告」功能，在 LINE 上顯示 Word 內容完成度百分比與缺填欄位清單，並附下載連結。

**Architecture:** 送出案件成功後，在原本的 "案件已成功送出" 訊息後增加一個 Flex 確認訊息（是否產生 Word 報告）。用戶點選「產生報告」後，系統呼叫 WordGenerator 產生 .docx 並存入 `storage/cases/{case_id}/report.docx`，同時計算完成度，回傳包含完成度百分比 + 缺填欄位 + 下載按鈕的 Flex Message。LINE 不支援直接傳送 .docx 檔案，因此新增 FastAPI endpoint `GET /api/cases/{case_id}/word` 提供下載。

**Tech Stack:** Python, FastAPI, python-docx (已有), LINE Messaging API (Flex Message + URI Action)

---

## Task 1: WordCompleteness — 完成度計算方法

**Files:**
- Modify: `app/services/word_generator.py` — 新增 `calculate_completeness` 靜態方法
- Test: `tests/test_word_generator.py` — 新增完成度相關測試

### 完成度欄位定義 (25 項)

```python
COMPLETENESS_FIELDS: list[tuple[str, str, bool]] = [
    # (field_key, display_name, is_required)
    ("reporting_year", "年度", True),
    ("disaster_type", "災害類型", True),
    ("processing_type", "處理類型", True),
    ("project_name", "工程名稱", True),
    ("disaster_date", "災害日期", True),
    ("town_village", "地點(鄉鎮里)", True),       # town_name + village_name
    ("nearby_landmark", "鄰近地標", False),
    ("repeat_disaster", "重複致災", True),
    ("coordinates", "座標", True),                  # primary_coordinate
    ("damage_mode", "破壞模式", True),              # damage_mode_name
    ("damage_cause", "致災原因", True),             # damage_cause_names
    ("description", "災損描述", True),
    ("location_map", "位置圖", True),               # primary_coordinate (有座標就能生成)
    ("photos", "照片", True),                       # photo_count > 0
    ("original_protection", "原設計保護型式", False),
    ("analysis_review", "分析與檢討", False),
    ("estimated_cost", "初估經費", True),
    ("cost_breakdown", "經費明細", True),
    ("design_docs", "設計圖說", False),             # design_doc_evidence_id
    ("soil_conservation", "水土保持", True),
    ("safety_assessment", "安全評估", False),
    ("site_survey", "工址環境危害", True),
    ("other_supplement", "其他補充", False),
    ("reporting_agency", "提報機關", True),
    ("created_by", "填報人", True),                 # created_by
]
```

### Step 1: 寫測試

在 `tests/test_word_generator.py` 末尾新增：

```python
def test_completeness_full_case(generator: WordGenerator) -> None:
    """完整填寫的 Case 應該有 100% 完成度。"""
    case = Case(
        case_id="case_complete",
        reporting_year="114",
        disaster_type="一般",
        processing_type="搶修",
        project_name="測試工程",
        disaster_date="2025-08-15",
        town_name="復興",
        village_name="高義",
        nearby_landmark="台7線北側邊坡",
        repeat_disaster="是",
        primary_coordinate=CoordinateCandidate(lat=24.1, lon=121.6, source="manual", confidence=1.0),
        damage_mode_name="岩石崩塌",
        damage_cause_names=["豪雨"],
        description="測試描述",
        photo_count=2,
        original_protection="重力式擋土牆",
        analysis_review="分析內容",
        estimated_cost=240.0,
        cost_breakdown=[CostBreakdownItem(item_id="1", item_name="修復", amount=2400000)],
        design_doc_evidence_id="ev_001",
        soil_conservation="不需要",
        safety_assessment="安全",
        site_survey=[SiteSurveyItem(category_id="upslope", item_id="test", item_name="test", checked=True)],
        other_supplement="補充",
        reporting_agency="交通部公路局北區養護工程分局",
        created_by=CreatedBy(user_id="u001", real_name="王小明"),
    )
    result = WordGenerator.calculate_completeness(case)
    assert result["filled"] == 25
    assert result["total"] == 25
    assert result["percentage"] == 100
    assert result["missing"] == []


def test_completeness_minimal_case(generator: WordGenerator) -> None:
    """空 Case 應有低完成度，且列出缺填必填欄位。"""
    case = Case(case_id="case_empty")
    result = WordGenerator.calculate_completeness(case)
    assert result["percentage"] < 50
    assert result["total"] == 25
    assert len(result["missing"]) > 0
    # 必填欄位應在 missing 裡
    missing_names = [m["name"] for m in result["missing"]]
    assert "工程名稱" in missing_names
    assert "災害日期" in missing_names


def test_completeness_partial_case(generator: WordGenerator) -> None:
    """部分填寫的 Case 完成度介於 0~100%，且 missing 只列未填。"""
    case = Case(
        case_id="case_partial",
        reporting_year="114",
        disaster_type="一般",
        processing_type="搶修",
        project_name="工程A",
        disaster_date="2025-01-01",
        reporting_agency="交通部公路局北區養護工程分局",
        created_by=CreatedBy(user_id="u001", real_name="王小明"),
    )
    result = WordGenerator.calculate_completeness(case)
    assert 0 < result["percentage"] < 100
    assert result["filled"] == result["total"] - len(result["missing"])
```

### Step 2: 跑測試確認失敗

```bash
pytest tests/test_word_generator.py -k "completeness" -v
```
Expected: FAIL (calculate_completeness 不存在)

### Step 3: 實作 `calculate_completeness`

在 `word_generator.py` 的 `WordGenerator` 類別內新增：

```python
COMPLETENESS_FIELDS: list[tuple[str, str, bool]] = [
    ("reporting_year", "年度", True),
    ("disaster_type", "災害類型", True),
    ("processing_type", "處理類型", True),
    ("project_name", "工程名稱", True),
    ("disaster_date", "災害日期", True),
    ("town_village", "地點(鄉鎮里)", True),
    ("nearby_landmark", "鄰近地標", False),
    ("repeat_disaster", "重複致災", True),
    ("coordinates", "座標", True),
    ("damage_mode", "破壞模式", True),
    ("damage_cause", "致災原因", True),
    ("description", "災損描述", True),
    ("location_map", "位置圖", True),
    ("photos", "照片", True),
    ("original_protection", "原設計保護型式", False),
    ("analysis_review", "分析與檢討", False),
    ("estimated_cost", "初估經費", True),
    ("cost_breakdown", "經費明細", True),
    ("design_docs", "設計圖說", False),
    ("soil_conservation", "水土保持", True),
    ("safety_assessment", "安全評估", False),
    ("site_survey", "工址環境危害", True),
    ("other_supplement", "其他補充", False),
    ("reporting_agency", "提報機關", True),
    ("created_by", "填報人", True),
]

@staticmethod
def calculate_completeness(case: Case) -> dict:
    """Calculate Word document field completeness.
    
    Returns: {
        "filled": int,
        "total": int,
        "percentage": int,
        "missing": [{"key": str, "name": str, "required": bool}],
    }
    """
    def _is_filled(key: str) -> bool:
        match key:
            case "town_village":
                return bool(case.town_name or case.village_name)
            case "coordinates" | "location_map":
                return case.primary_coordinate is not None
            case "damage_mode":
                return bool(case.damage_mode_name)
            case "damage_cause":
                return bool(case.damage_cause_names)
            case "photos":
                return case.photo_count > 0
            case "cost_breakdown":
                return bool(case.cost_breakdown)
            case "design_docs":
                return bool(case.design_doc_evidence_id)
            case "site_survey":
                return bool(case.site_survey)
            case "created_by":
                return bool(case.created_by and case.created_by.real_name)
            case _:
                return bool(getattr(case, key, None))

    filled = 0
    missing = []
    for key, name, required in COMPLETENESS_FIELDS:
        if _is_filled(key):
            filled += 1
        else:
            missing.append({"key": key, "name": name, "required": required})
    total = len(COMPLETENESS_FIELDS)
    return {
        "filled": filled,
        "total": total,
        "percentage": round(filled * 100 / total) if total > 0 else 0,
        "missing": missing,
    }
```

### Step 4: 跑測試確認通過

```bash
pytest tests/test_word_generator.py -k "completeness" -v
```
Expected: 3 passed

---

## Task 2: FlexBuilder — Word 報告相關 Flex 訊息

**Files:**
- Modify: `app/services/flex_builders.py` — 新增 3 個方法
- Test: 透過 Task 5 的 line_flow 測試間接覆蓋

### 新增方法

#### 2a. `word_report_prompt_flex()` — 詢問是否產生報告

送出案件成功後顯示，包含「產生報告」和「不需要」兩個按鈕。

```python
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
```

#### 2b. `word_report_result_flex(completeness, download_url)` — 報告產生結果

顯示完成度百分比 + 進度條 + 缺填欄位清單 + 下載按鈕。

```python
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
```

---

## Task 3: FastAPI 下載 Endpoint

**Files:**
- Create: `app/routers/word_download.py` — 新增下載路由
- Modify: `app/main.py` — 註冊路由

### Step 1: 建立 `app/routers/word_download.py`

```python
"""Word document download endpoint."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.core.logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/{case_id}/word")
async def download_word(request: Request, case_id: str):
    """Download generated Word report for a case."""
    case_store = request.app.state.case_store
    case = case_store.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    # 檢查是否已產生過報告（存於 storage/cases/{case_id}/report.docx）
    settings = request.app.state.settings
    report_path = settings.cases_dir / case_id / "report.docx"
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Word report not generated yet")

    file_bytes = report_path.read_bytes()
    filename = f"{case.project_name or case_id}.docx"
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

### Step 2: 在 `app/main.py` 註冊

在 import 區塊加上：
```python
from app.routers.word_download import router as word_download_router
```

在 `include_router` 區塊加上：
```python
app.include_router(word_download_router, prefix="/api/cases", tags=["Word Download"])
```

注意：此路由與 cases_router 同 prefix `/api/cases`，但 word_download 只有 `/{case_id}/word` 路徑，不會衝突。

---

## Task 4: LINE Flow — 報告產生流程

**Files:**
- Modify: `app/models/line_state.py` — 新增 `GENERATE_WORD` step
- Modify: `app/services/line_flow.py` — 修改 CONFIRM_SUBMIT handler + 新增 GENERATE_WORD handler
- Test: `tests/test_line_flow.py` — 新增測試

### 4a. 新增 ReportingStep

在 `line_state.py` 的 `ReportingStep` enum 裡，`DONE` 前面加：
```python
GENERATE_WORD = "generate_word"          # 產生 Word 報告（可選）
```

### 4b. 修改 CONFIRM_SUBMIT handler

現有邏輯（line 1150-1169）：
```python
if step == ReportingStep.CONFIRM_SUBMIT.value:
    if action != "submit_report":
        return [FlexBuilder.text_message("請按確認送出，或輸入取消。")]
    # ... submit logic ...
    session.advance_step(ReportingStep.DONE.value)
    session.reset()
    return [FlexBuilder.text_message(f"案件已成功送出，案件編號：{case.case_id}")]
```

改為：
```python
if step == ReportingStep.CONFIRM_SUBMIT.value:
    if action != "submit_report":
        return [FlexBuilder.text_message("請按確認送出，或輸入取消。")]
    # ... submit logic (keep lines 1154-1166 as-is) ...
    session.advance_step(ReportingStep.GENERATE_WORD.value)
    return [
        FlexBuilder.text_message(f"✅ 案件已成功送出，案件編號：{case.case_id}"),
        FlexBuilder.word_report_prompt_flex(),
    ]
```

注意：不再 `session.reset()` — 等 GENERATE_WORD 步驟完成後才 reset。

### 4c. 新增 GENERATE_WORD handler

在 CONFIRM_SUBMIT handler 之後、ANNOTATE_PHOTOS handler 之前插入：

```python
if step == ReportingStep.GENERATE_WORD.value:
    case_id = session.draft_case_id
    if action == "skip_word":
        session.advance_step(ReportingStep.DONE.value)
        session.reset()
        return [FlexBuilder.text_message("好的，如需產生報告可隨時在案件查詢中操作。")]

    if action == "generate_word":
        if not case_id:
            session.advance_step(ReportingStep.DONE.value)
            session.reset()
            return [FlexBuilder.text_message("案件不存在，無法產生報告。")]

        case = self._cases.get_case(case_id)
        if case is None:
            session.advance_step(ReportingStep.DONE.value)
            session.reset()
            return [FlexBuilder.text_message("案件資料讀取失敗。")]

        try:
            from app.services.word_generator import WordGenerator
            gen = WordGenerator(cases_dir=self._settings.cases_dir)
            manifest = self._evidence.get_manifest(case_id)
            doc_bytes = gen.generate(case=case, manifest=manifest)

            # 存檔
            report_dir = self._settings.cases_dir / case_id
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / "report.docx"
            report_path.write_bytes(doc_bytes)

            # 完成度
            completeness = WordGenerator.calculate_completeness(case)
            download_url = f"{self._settings.app_base_url}/api/cases/{case_id}/word"

            session.advance_step(ReportingStep.DONE.value)
            session.reset()
            return [FlexBuilder.word_report_result_flex(completeness, download_url)]

        except Exception as exc:
            logger.error("Word 報告產生失敗: case_id=%s, error=%s", case_id, exc)
            session.advance_step(ReportingStep.DONE.value)
            session.reset()
            return [FlexBuilder.text_message(f"報告產生失敗：{exc}")]

    return [FlexBuilder.word_report_prompt_flex()]
```

### 4d. LineFlowController 需要引用 `app_base_url`

`self._settings` 已經有了（line 87: `self._settings = get_settings()`），直接用 `self._settings.app_base_url`。
`self._settings.cases_dir` 也已可用。

---

## Task 5: 測試

**Files:**
- Modify: `tests/test_word_generator.py` — Task 1 已加完成度測試
- Modify: `tests/test_line_flow.py` — 新增 GENERATE_WORD 流程測試

### line_flow 測試新增

```python
@pytest.mark.asyncio
async def test_generate_word_flow(line_flow, ...):
    """送出案件後選擇產生 Word 報告。"""
    # 先走完到 CONFIRM_SUBMIT 送出
    # ... (使用現有 helper 推進到送出)
    # 驗證送出後收到 word_report_prompt_flex
    # 再送 action=generate_word postback
    # 驗證收到 word_report_result_flex 包含完成度和下載連結


@pytest.mark.asyncio
async def test_skip_word_flow(line_flow, ...):
    """送出案件後選擇不產生 Word 報告。"""
    # 走到送出 → 收到 prompt → 送 action=skip_word
    # 驗證收到略過訊息
```

---

## Task 6: 驗證 & 記憶

### Step 1: 跑全部測試
```bash
pytest --tb=short
```
Expected: 全部通過

### Step 2: LSP 診斷
檢查所有修改檔案無 error

### Step 3: 儲存記憶
更新 OpenMemory

---

## 變更檔案總覽

| 檔案 | 動作 | 說明 |
|------|------|------|
| `app/services/word_generator.py` | 修改 | 新增 `COMPLETENESS_FIELDS` + `calculate_completeness()` |
| `app/services/flex_builders.py` | 修改 | 新增 `word_report_prompt_flex()` + `word_report_result_flex()` |
| `app/models/line_state.py` | 修改 | 新增 `GENERATE_WORD` enum |
| `app/services/line_flow.py` | 修改 | 修改 CONFIRM_SUBMIT + 新增 GENERATE_WORD handler |
| `app/routers/word_download.py` | **新增** | `GET /api/cases/{case_id}/word` endpoint |
| `app/main.py` | 修改 | 註冊 word_download_router |
| `tests/test_word_generator.py` | 修改 | 新增 3 個完成度測試 |
| `tests/test_line_flow.py` | 修改 | 新增 2 個報告流程測試 |
