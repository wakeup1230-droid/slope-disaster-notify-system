# Issue #12: 位置資訊自動化 + 工程經費結構化 + 位置圖 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在座標確認後自動顯示鄉鎮市區/村里/國家公園資訊、改造工程經費為6品項結構化計算、發送 LINE LocationMessage 位置圖。

**Architecture:** 新建 AdminBoundaryService 仿照 GeologyService 模式（geopandas point-in-polygon），修改 ESTIMATED_COST 步驟為多品項互動流程，在 CONFIRM_MILEPOST 步驟增加 LocationMessage。

**Tech Stack:** Python, geopandas, pyproj, shapely, FastAPI, LINE Messaging API (LocationMessage)

---

## Task 1: AdminBoundaryService — 行政區反查服務

### 1A: 建立 admin_boundary_service.py

**Files:**
- Create: `app/services/admin_boundary_service.py`
- Test: `tests/test_admin_boundary_service.py`

**設計：**
- 仿照 `app/services/geology_service.py` 的模式
- 載入鄉鎮市區 shapefile + 村里 shapefile
- 提供 `query(lon, lat)` → 回傳 `AdminBoundaryResult(county, town, village)`
- Shapefile 來源：Input/ 目錄下的行政區邊界資料（TWD97/WGS84 EPSG:4326）
- 不需座標轉換（shapefile 本身為 WGS84）

**AdminBoundaryResult dataclass:**
```python
@dataclass(frozen=True)
class AdminBoundaryResult:
    county_name: str      # 縣市 e.g. "新北市"
    town_name: str        # 鄉鎮市區 e.g. "新店區"
    village_name: str     # 村里 e.g. "中正里"
```

**Service 架構：**
```python
class AdminBoundaryService:
    def __init__(self, town_shapefile_dir: Path, village_shapefile_dir: Path):
        self._towns: gpd.GeoDataFrame | None = None
        self._villages: gpd.GeoDataFrame | None = None
        self._load_shapefiles(town_shapefile_dir, village_shapefile_dir)
    
    def query(self, lon: float, lat: float) -> AdminBoundaryResult | None:
        # Point-in-polygon against town + village shapefiles
    
    def to_display_text(self, result: AdminBoundaryResult) -> str:
        # "📍 行政區：新北市 新店區 中正里"
```

**注意：**
- Shapefile 的欄位名稱需要在下載後確認（預期：COUNTYNAME, TOWNNAME, VILLNAME 等）
- 如果 shapefile 還沒下載到 Input/，先建好 service 並在測試中 mock 資料
- 先建立支持「沒有 shapefile 也能啟動」的容錯模式（同 GeologyService）

---

## Task 2: NationalParkService — 國家公園偵測

### 2A: 建立 national_park_service.py

**Files:**
- Create: `app/services/national_park_service.py`
- Test: `tests/test_national_park_service.py`

**設計：**
- 同樣仿 GeologyService 模式
- 載入國家公園邊界 shapefile
- 提供 `query(lon, lat)` → `NationalParkResult | None`
- 如果座標在任一國家公園範圍內，返回該公園名稱

**NationalParkResult dataclass:**
```python
@dataclass(frozen=True)
class NationalParkResult:
    park_name: str        # e.g. "太魯閣國家公園"
    is_within: bool       # True
```

**容錯：**
- 目前只有零散的國家公園資料（台江、陽明山）
- 如果 shapefile 不存在，service 回傳 None（不阻斷流程）
- 日後補齊其他公園的 shapefile 即可自動支援

---

## Task 3: 整合至 CONFIRM_MILEPOST 步驟 + LocationMessage

**Files:**
- Modify: `app/services/line_flow.py` (CONFIRM_MILEPOST handler, ~L432-454)
- Modify: `app/services/line_flow.py` (__init__, ~L52-77)
- Modify: `app/services/line_flow.py` (_apply_session_to_case, ~L1383-1470)
- Modify: `app/services/line_flow.py` (_build_report_summary, ~L1367-1381)
- Modify: `app/services/flex_builders.py` (report_confirm_flex, ~L793-816)
- Modify: `app/models/case.py` (新增欄位)
- Modify: `app/main.py` (初始化新 services)

### 3A: Case Model 新增欄位

在 `app/models/case.py` 的 Case class 中新增：

```python
# --- Location Detail ---
county_name: str = ""                    # 縣市
town_name: str = ""                      # 鄉鎮市區
village_name: str = ""                   # 村里
national_park: str = ""                  # 國家公園名稱（空=不在國家公園內）
```

### 3B: main.py 初始化

在 `app/main.py` 中：
1. import AdminBoundaryService, NationalParkService
2. 初始化兩個 service（指向 Input/ 下的 shapefile 目錄）
3. 傳入 LineFlowController

### 3C: LineFlowController 整合

**__init__ 新增參數：**
```python
admin_boundary_service: object | None = None,
national_park_service: object | None = None,
```

**CONFIRM_MILEPOST 步驟（確認後）增加：**
1. 查詢行政區（county_name, town_name, village_name）→ 儲存至 session data
2. 查詢國家公園 → 儲存至 session data  
3. 組合顯示文字（地質 + 行政區 + 國家公園）
4. 發送 LocationMessage（type: location, title: 災害回報位置, lat, lon）

**LocationMessage 格式：**
```python
{
    "type": "location",
    "title": "災害回報位置",
    "address": f"{town_name}{village_name} {road} {milepost_display}",
    "latitude": lat,
    "longitude": lon
}
```

**_apply_session_to_case 增加：**
```python
case.county_name = session.get_data("county_name", "")
case.town_name = session.get_data("town_name", "")
case.village_name = session.get_data("village_name", "")
case.national_park = session.get_data("national_park", "")
```

**_build_report_summary 增加：**
```python
"town_village": f"{session.get_data('county_name', '')}{session.get_data('town_name', '')}{session.get_data('village_name', '')}",
"national_park": session.get_data("national_park", ""),
```

**flex_builders report_confirm_flex 增加顯示行：**
```python
f"行政區：{data.get('town_village', '-')}",
f"國家公園：{data.get('national_park', '否')}",
```

---

## Task 4: 工程經費結構化

**Files:**
- Create: `app/data/cost_items.json`
- Modify: `app/services/line_flow.py` (ESTIMATED_COST handler, ~L804-825)
- Modify: `app/services/flex_builders.py` (新增 cost item flex)
- Modify: `app/models/case.py` (cost_breakdown 欄位)
- Modify: `app/services/line_flow.py` (_apply_session_to_case, _build_report_summary)

### 4A: cost_items.json

```json
{
  "items": [
    {"id": "labor_guard", "name": "人工看守費", "unit": "人日", "unit_price": 4000, "input_type": "quantity"},
    {"id": "large_truck", "name": "大型貨車租用", "unit": "日", "unit_price": 8000, "input_type": "quantity"},
    {"id": "small_excavator", "name": "小型鏟土車", "unit": "日", "unit_price": 7000, "input_type": "quantity"},
    {"id": "cms_vehicle", "name": "cms交維車", "unit": "日", "unit_price": 5000, "input_type": "quantity"},
    {"id": "other_cost", "name": "其它費用", "unit": "元", "unit_price": null, "input_type": "amount"},
    {"id": "management_fee", "name": "工程管理費", "unit": "元", "unit_price": null, "input_type": "amount"}
  ]
}
```

### 4B: Case Model

在 `case.py` 中：
- 新增 `CostBreakdownItem` sub-model
- 替換 `estimated_cost` 為同時保留 `estimated_cost` (自動計算總和) + 新增 `cost_breakdown: list[CostBreakdownItem]`

```python
class CostBreakdownItem(BaseModel):
    item_id: str = ""
    item_name: str = ""
    unit: str = ""
    unit_price: Optional[float] = None
    quantity: Optional[float] = None
    amount: Optional[float] = None  # quantity * unit_price (for items 1-4) or direct input (items 5-6)
```

### 4C: LINE 互動流程

改造 ESTIMATED_COST 步驟：

1. 進入步驟時，送出第一個品項的 Flex Message（品項名稱 + 單價 + 輸入提示）
2. 使用者輸入數量（或金額）→ 計算複價 → 存入 session → 進入下一品項
3. 每個品項都可以「跳過」（數量=0）
4. 6 品項全部完成後，顯示經費明細表 + 總計

**session data 結構：**
```python
session.store_data("cost_items", [
    {"id": "labor_guard", "name": "人工看守費", "unit_price": 4000, "quantity": 3, "amount": 12000},
    ...
])
session.store_data("cost_current_index", 0)  # 當前品項 index
```

**Flex Message for each item (品項 1-4)：**
```
📋 工程經費 (1/6)
━━━━━━━━━
項目：人工看守費
單價：4,000 元/人日

請輸入數量（人日），或按「跳過」
[跳過]
```

**Flex Message for items 5-6：**
```
📋 工程經費 (5/6)
━━━━━━━━━
項目：其它費用

請輸入金額（元），或按「跳過」
[跳過]
```

**完成後的摘要 Flex：**
```
📊 工程經費明細
━━━━━━━━━
1. 人工看守費：3人日 × 4,000 = 12,000
2. 大型貨車租用：跳過
3. 小型鏟土車：2日 × 7,000 = 14,000
4. cms交維車：跳過
5. 其它費用：5,000
6. 工程管理費：3,000
━━━━━━━━━
初估總經費：34,000 元 (3.4 萬元)
[確認] [重新填寫]
```

---

## Task 5: 更新測試

**Files:**
- Create: `tests/test_admin_boundary_service.py`
- Create: `tests/test_national_park_service.py`
- Modify: `tests/test_e2e_reporting.py` (更新 cost flow)
- Modify: `tests/test_line_flow.py` (更新 cost flow)
- Modify: `tests/test_flex_builders.py` (新增 cost flex tests)

---

## Task 6: 下載 Shapefile 資料

**Files:**
- Download to: `Input/行政區邊界/` (鄉鎮市區 + 村里 shapefiles)
- Download to: `Input/國家公園邊界/` (台江 + 陽明山)

---

## Implementation Order

1. Task 4A: cost_items.json（資料，無依賴）
2. Task 1A: AdminBoundaryService + tests
3. Task 2A: NationalParkService + tests  
4. Task 3A: Case model 新增欄位
5. Task 4B: CostBreakdownItem model
6. Task 3B+3C: 整合至 line_flow + main.py（行政區 + 國家公園 + LocationMessage）
7. Task 4C: 工程經費 LINE 互動流程
8. Task 5: 更新/新增所有測試
9. Task 6: 下載 shapefile（可在測試通過後）
10. 最終驗證：全部測試通過
