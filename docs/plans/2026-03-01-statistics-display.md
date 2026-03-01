# Statistics Display System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a hybrid statistics display system — LINE Flex Message summary cards + Web dashboard with Chart.js — so decision-makers can monitor slope disaster cases at a glance from LINE and drill into detailed analytics on the web.

**Architecture:** Backend `CaseManager.get_statistics()` expands to compute all aggregations (budget, photo completeness, route frequency, time trends, damage types, processing time). A new `GET /api/statistics` endpoint exposes this data. LINE `FlexBuilder.statistics_flex()` is redesigned as a rich summary card with a "📊 查看完整統計" button linking to the web. A new `webgis/stats.html` page renders the full dashboard with 5 tabs using Chart.js.

**Tech Stack:** Python/FastAPI (backend), Pydantic (models), Chart.js 4.x (charts), vanilla HTML/CSS/JS (dashboard), LINE Flex Message (summary cards)

---

## Task 1: Expand Backend Statistics — `CaseStore.load_all_cases()` + `CaseManager.get_statistics()`

**Files:**
- Modify: `app/services/case_store.py:183-244` (add `load_all_cases()` method)
- Modify: `app/services/case_manager.py:288-298` (expand `get_statistics()`)
- Modify: `tests/test_case_manager.py:215-231` (expand `test_get_statistics`)
- Create: `tests/test_statistics.py` (dedicated statistics tests)

**Why `load_all_cases()`:** Current `count_by_status()` and `count_by_district()` each iterate all cases separately. For rich statistics we need budget sums, photo analysis, route grouping, time trends, damage type breakdown, and processing time — all from the same case list. Loading once and aggregating in Python avoids N redundant disk reads.

### Step 1: Write failing tests for expanded statistics

Create `tests/test_statistics.py`:

```python
"""Tests for expanded statistics computation."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.models.case import Case, ReviewStatus, EvidenceSummary, MilepostInfo
from app.services.audit_logger import AuditLogger
from app.services.case_manager import CaseManager
from app.services.case_store import CaseStore


@pytest.fixture
def manager(tmp_path: Path) -> CaseManager:
    cases_dir = tmp_path / "cases"
    locks_dir = tmp_path / "locks"
    store = CaseStore(cases_dir=cases_dir, locks_dir=locks_dir)
    audit = AuditLogger(cases_dir=cases_dir)
    return CaseManager(case_store=store, audit_logger=audit)


def _make_case(
    manager: CaseManager,
    *,
    user_id: str = "u1",
    district_id: str = "jingmei",
    district_name: str = "景美工務段",
    road_number: str = "",
    milepost_km: float | None = None,
    estimated_cost: float | None = None,
    damage_mode_category: str = "",
    damage_mode_name: str = "",
    photo_count: int = 0,
    review_status: ReviewStatus | None = None,
    created_at_override: str = "",
) -> Case:
    """Helper to create a case with optional overrides."""
    case = manager.create_case(
        user_id=user_id,
        district_id=district_id,
        district_name=district_name,
    )
    assert case is not None

    if road_number:
        case.road_number = road_number
    if milepost_km is not None:
        case.milepost = MilepostInfo(
            road=road_number or "台7線",
            milepost_km=milepost_km,
            milepost_display=f"{int(milepost_km)}K+{int((milepost_km % 1) * 1000):03d}",
            confidence=1.0,
        )
    if estimated_cost is not None:
        case.estimated_cost = estimated_cost
    if damage_mode_category:
        case.damage_mode_category = damage_mode_category
    if damage_mode_name:
        case.damage_mode_name = damage_mode_name
    case.photo_count = photo_count
    if created_at_override:
        case.created_at = created_at_override

    # Add dummy evidence summaries matching photo_count
    case.evidence_summary = [
        EvidenceSummary(
            evidence_id=f"ev_{i}",
            sha256=f"sha_{i}",
            original_filename=f"photo_{i}.jpg",
            content_type="image/jpeg",
            photo_type=f"P{i + 1}" if i < 4 else None,
        )
        for i in range(photo_count)
    ]

    manager.update_case(case, actor=user_id, actor_name="test", changes={"setup": "true"})

    if review_status and review_status != ReviewStatus.PENDING_REVIEW:
        if review_status == ReviewStatus.IN_PROGRESS:
            manager.transition_review_status(case.case_id, ReviewStatus.IN_PROGRESS, actor=user_id)
        elif review_status == ReviewStatus.CLOSED:
            manager.transition_review_status(case.case_id, ReviewStatus.IN_PROGRESS, actor=user_id)
            manager.transition_review_status(case.case_id, ReviewStatus.CLOSED, actor=user_id)
        elif review_status == ReviewStatus.RETURNED:
            manager.transition_review_status(case.case_id, ReviewStatus.RETURNED, actor=user_id, note="test")

    return manager.get_case(case.case_id)  # type: ignore[return-value]


def test_statistics_has_all_sections(manager: CaseManager) -> None:
    """Statistics response must contain all required top-level keys."""
    _make_case(manager, district_id="jingmei")

    stats = manager.get_statistics()

    required_keys = {
        "total_cases", "by_status", "by_district",
        "budget", "photo_completeness", "route_frequency",
        "time_trend", "damage_types", "processing_time",
        "today_new",
    }
    assert required_keys.issubset(stats.keys()), f"Missing keys: {required_keys - stats.keys()}"


def test_statistics_budget(manager: CaseManager) -> None:
    """Budget section aggregates estimated_cost correctly."""
    _make_case(manager, estimated_cost=100.0, review_status=ReviewStatus.CLOSED)
    _make_case(manager, estimated_cost=50.0, review_status=ReviewStatus.IN_PROGRESS)
    _make_case(manager, estimated_cost=None)  # No cost

    stats = manager.get_statistics()
    budget = stats["budget"]

    assert budget["total_estimated"] == 150.0
    assert budget["closed_estimated"] == 100.0
    assert budget["pending_estimated"] == 50.0
    assert budget["unfilled_count"] == 1


def test_statistics_photo_completeness(manager: CaseManager) -> None:
    """Photo completeness calculates P1-P4 coverage."""
    _make_case(manager, photo_count=4)  # Has P1-P4
    _make_case(manager, photo_count=2)  # Only P1, P2
    _make_case(manager, photo_count=0)  # No photos

    stats = manager.get_statistics()
    photo = stats["photo_completeness"]

    assert photo["total_cases"] == 3
    assert "overall_pct" in photo
    assert "by_photo_type" in photo


def test_statistics_route_frequency(manager: CaseManager) -> None:
    """Route frequency groups disasters by road."""
    _make_case(manager, road_number="台7線", milepost_km=32.4)
    _make_case(manager, road_number="台7線", milepost_km=35.0)
    _make_case(manager, road_number="台9線", milepost_km=10.0)

    stats = manager.get_statistics()
    routes = stats["route_frequency"]

    assert len(routes) >= 2
    # 台7線 should have 2 cases
    route_7 = next((r for r in routes if r["road"] == "台7線"), None)
    assert route_7 is not None
    assert route_7["count"] == 2


def test_statistics_damage_types(manager: CaseManager) -> None:
    """Damage types groups by category and name."""
    _make_case(manager, damage_mode_category="revetment_retaining", damage_mode_name="擋土牆破損")
    _make_case(manager, damage_mode_category="revetment_retaining", damage_mode_name="擋土牆破損")
    _make_case(manager, damage_mode_category="road_slope", damage_mode_name="邊坡滑動")

    stats = manager.get_statistics()
    damage = stats["damage_types"]

    assert "by_category" in damage
    assert damage["by_category"].get("revetment_retaining", 0) == 2
    assert damage["by_category"].get("road_slope", 0) == 1
    assert "by_name" in damage


def test_statistics_today_new(manager: CaseManager) -> None:
    """Today's new cases counted correctly."""
    _make_case(manager)
    _make_case(manager)

    stats = manager.get_statistics()

    # Cases created just now should count as today
    assert stats["today_new"] == 2


def test_statistics_time_trend(manager: CaseManager) -> None:
    """Time trend groups cases by date."""
    _make_case(manager)

    stats = manager.get_statistics()
    trend = stats["time_trend"]

    assert isinstance(trend, list)
    assert len(trend) >= 1
    assert "date" in trend[0]
    assert "count" in trend[0]


def test_statistics_processing_time(manager: CaseManager) -> None:
    """Processing time stats for closed cases."""
    case = _make_case(manager, review_status=ReviewStatus.CLOSED)

    stats = manager.get_statistics()
    proc = stats["processing_time"]

    assert "avg_hours" in proc
    assert "by_district" in proc


def test_load_all_cases(tmp_path: Path) -> None:
    """CaseStore.load_all_cases returns all Case objects."""
    cases_dir = tmp_path / "cases"
    locks_dir = tmp_path / "locks"
    store = CaseStore(cases_dir=cases_dir, locks_dir=locks_dir)
    audit = AuditLogger(cases_dir=cases_dir)
    mgr = CaseManager(case_store=store, audit_logger=audit)

    mgr.create_case(user_id="u1")
    mgr.create_case(user_id="u2")

    all_cases = store.load_all_cases()
    assert len(all_cases) == 2
    assert all(isinstance(c, Case) for c in all_cases)
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/test_statistics.py -v`
Expected: Multiple FAIL — `load_all_cases` not defined, `get_statistics` missing keys.

### Step 3: Implement `CaseStore.load_all_cases()`

In `app/services/case_store.py`, add after `list_all()` (after line 189):

```python
def load_all_cases(self) -> list[Case]:
    """Load all Case objects into memory. Use for batch aggregations."""
    cases: list[Case] = []
    for case_id in self.list_all():
        case = self.get(case_id)
        if case is not None:
            cases.append(case)
    return cases
```

### Step 4: Expand `CaseManager.get_statistics()`

Replace the entire `get_statistics()` method in `app/services/case_manager.py` (lines 288-298) with:

```python
def get_statistics(self) -> dict[str, Any]:
    """Get comprehensive system-wide case statistics."""
    all_cases = self._store.load_all_cases()
    today_str = datetime.now().strftime("%Y-%m-%d")

    # --- Basic counts ---
    by_status: dict[str, int] = {}
    by_district: dict[str, int] = {}
    today_new = 0

    # --- Budget ---
    total_estimated = 0.0
    closed_estimated = 0.0
    pending_estimated = 0.0
    unfilled_cost_count = 0

    # --- Photo completeness ---
    photo_type_counts: dict[str, int] = {"P1": 0, "P2": 0, "P3": 0, "P4": 0}
    cases_with_all_photos = 0

    # --- Route frequency ---
    route_counts: dict[str, list[float]] = {}  # road -> [milepost_km, ...]

    # --- Damage types ---
    damage_by_category: dict[str, int] = {}
    damage_by_name: dict[str, int] = {}

    # --- Time trend ---
    date_counts: dict[str, int] = {}

    # --- Processing time ---
    closed_durations: list[float] = []
    closed_by_district: dict[str, list[float]] = {}

    for case in all_cases:
        # Status
        status_val = case.review_status.value
        by_status[status_val] = by_status.get(status_val, 0) + 1

        # District
        by_district[case.district_id] = by_district.get(case.district_id, 0) + 1

        # Today
        if case.created_at.startswith(today_str):
            today_new += 1

        # Budget
        if case.estimated_cost is not None:
            total_estimated += case.estimated_cost
            if case.review_status == ReviewStatus.CLOSED:
                closed_estimated += case.estimated_cost
            else:
                pending_estimated += case.estimated_cost
        else:
            unfilled_cost_count += 1

        # Photo completeness
        photo_types_found: set[str] = set()
        for ev in case.evidence_summary:
            if ev.photo_type and ev.photo_type in photo_type_counts:
                photo_types_found.add(ev.photo_type)
                photo_type_counts[ev.photo_type] += 1
        if photo_types_found.issuperset({"P1", "P2", "P3", "P4"}):
            cases_with_all_photos += 1

        # Route frequency
        if case.road_number:
            if case.road_number not in route_counts:
                route_counts[case.road_number] = []
            if case.milepost:
                route_counts[case.road_number].append(case.milepost.milepost_km)

        # Damage types
        if case.damage_mode_category:
            damage_by_category[case.damage_mode_category] = damage_by_category.get(case.damage_mode_category, 0) + 1
        if case.damage_mode_name:
            damage_by_name[case.damage_mode_name] = damage_by_name.get(case.damage_mode_name, 0) + 1

        # Time trend
        case_date = case.created_at[:10]
        date_counts[case_date] = date_counts.get(case_date, 0) + 1

        # Processing time for closed cases
        if case.review_status == ReviewStatus.CLOSED:
            try:
                created = datetime.fromisoformat(case.created_at)
                updated = datetime.fromisoformat(case.updated_at)
                hours = (updated - created).total_seconds() / 3600
                closed_durations.append(hours)
                if case.district_id not in closed_by_district:
                    closed_by_district[case.district_id] = []
                closed_by_district[case.district_id].append(hours)
            except (ValueError, TypeError):
                pass

    total = len(all_cases)
    overall_photo_pct = round((cases_with_all_photos / total) * 100, 1) if total > 0 else 0.0

    # Build route frequency list sorted by count desc
    route_frequency = sorted(
        [
            {
                "road": road,
                "count": len(mileposts) if mileposts else by_district.get(road, 0),
                "mileposts": sorted(mileposts),
            }
            for road, mileposts in route_counts.items()
        ],
        key=lambda r: r["count"],
        reverse=True,
    )

    # Build time trend sorted by date
    time_trend = sorted(
        [{"date": d, "count": c} for d, c in date_counts.items()],
        key=lambda t: t["date"],
    )

    # Processing time stats
    avg_hours = round(sum(closed_durations) / len(closed_durations), 1) if closed_durations else 0.0
    proc_by_district = {
        district: round(sum(hours_list) / len(hours_list), 1)
        for district, hours_list in closed_by_district.items()
    }

    return {
        "total_cases": total,
        "today_new": today_new,
        "by_status": by_status,
        "by_district": by_district,
        "budget": {
            "total_estimated": round(total_estimated, 1),
            "closed_estimated": round(closed_estimated, 1),
            "pending_estimated": round(pending_estimated, 1),
            "unfilled_count": unfilled_cost_count,
        },
        "photo_completeness": {
            "total_cases": total,
            "cases_complete": cases_with_all_photos,
            "overall_pct": overall_photo_pct,
            "by_photo_type": {k: v for k, v in photo_type_counts.items()},
        },
        "route_frequency": route_frequency,
        "time_trend": time_trend,
        "damage_types": {
            "by_category": damage_by_category,
            "by_name": damage_by_name,
        },
        "processing_time": {
            "avg_hours": avg_hours,
            "total_closed": len(closed_durations),
            "by_district": proc_by_district,
        },
    }
```

### Step 5: Run tests to verify they pass

Run: `python -m pytest tests/test_statistics.py -v`
Expected: ALL PASS

### Step 6: Run full test suite for regression

Run: `python -m pytest -v`
Expected: ALL 94+ tests PASS (existing + new)

### Step 7: Commit

```bash
git add app/services/case_store.py app/services/case_manager.py tests/test_statistics.py
git commit -m "feat: expand statistics with budget, photo, route, damage, time trend data"
```

---

## Task 2: Add `GET /api/statistics` Endpoint

**Files:**
- Create: `app/routers/statistics.py`
- Modify: `app/main.py:130` (register new router)
- Create: `tests/test_statistics_api.py`

### Step 1: Write failing test

Create `tests/test_statistics_api.py`:

```python
"""Tests for statistics API endpoint."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    """Create test client with env overrides."""
    import os
    os.environ["CASES_DIR"] = str(tmp_path / "cases")
    os.environ["LOCKS_DIR"] = str(tmp_path / "locks")
    os.environ["SESSIONS_DIR"] = str(tmp_path / "sessions")
    os.environ["USERS_DIR"] = str(tmp_path / "users")
    os.environ["LINE_CHANNEL_SECRET"] = "test_secret"
    os.environ["LINE_CHANNEL_ACCESS_TOKEN"] = "test_token"

    app = create_app()
    return TestClient(app)


def test_statistics_endpoint_returns_200(client: TestClient) -> None:
    resp = client.get("/api/statistics")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_cases" in data
    assert "budget" in data
    assert "photo_completeness" in data
    assert "route_frequency" in data
    assert "time_trend" in data
    assert "damage_types" in data
    assert "processing_time" in data
    assert "today_new" in data
```

**Note:** The test fixture may need adjustment based on how `create_app()` handles env vars. Check `app/core/config.py` for required env vars and adjust accordingly. If the existing test infra has a shared fixture for `TestClient`, reuse it instead.

### Step 2: Run test to verify it fails

Run: `python -m pytest tests/test_statistics_api.py -v`
Expected: FAIL — 404 because router doesn't exist yet.

### Step 3: Create the statistics router

Create `app/routers/statistics.py`:

```python
"""Statistics API router."""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("")
async def get_statistics(request: Request):
    """Return comprehensive case statistics."""
    case_manager = request.app.state.case_manager
    return case_manager.get_statistics()
```

### Step 4: Register the router in main.py

In `app/main.py`, add import at the top (after line 16):

```python
from app.routers.statistics import router as statistics_router
```

And add router registration after line 131 (after `vendor_router`):

```python
app.include_router(statistics_router, prefix="/api/statistics", tags=["Statistics"])
```

### Step 5: Run test to verify it passes

Run: `python -m pytest tests/test_statistics_api.py -v`
Expected: PASS

### Step 6: Run full test suite

Run: `python -m pytest -v`
Expected: ALL tests PASS

### Step 7: Commit

```bash
git add app/routers/statistics.py app/main.py tests/test_statistics_api.py
git commit -m "feat: add GET /api/statistics endpoint"
```

---

## Task 3: Redesign `FlexBuilder.statistics_flex()` for LINE Summary Cards

**Files:**
- Modify: `app/services/flex_builders.py:482-500` (redesign `statistics_flex`)
- Modify: `app/services/line_flow.py:159-160` (may need to pass base_url for web link)

**Design:** A rich Flex Message summary card with:
- Header: "📊 案件統計摘要" with blue background
- Key metrics: 今日新通報, 待處理, 處理中, 已結案, 退回待補件
- Per-district summary (compact)
- Footer button: "📊 查看完整統計" linking to `/webgis/stats.html`

### Step 1: Redesign `statistics_flex()` method

Replace `statistics_flex` in `app/services/flex_builders.py` (lines 482-500) with:

```python
@staticmethod
def statistics_flex(stats: dict, stats_url: str = "") -> dict:
    """Build a rich statistics summary card for LINE.

    Args:
        stats: Full statistics dict from CaseManager.get_statistics()
        stats_url: Absolute URL to the web stats page
    """
    by_status = stats.get("by_status", {})
    by_district = stats.get("by_district", {})
    today_new = stats.get("today_new", 0)
    total = stats.get("total_cases", 0)

    pending = by_status.get("pending_review", 0)
    in_progress = by_status.get("in_progress", 0)
    closed = by_status.get("closed", 0)
    returned = by_status.get("returned", 0)

    # --- Status metric row ---
    def _metric_box(label: str, value: int, color: str) -> dict:
        return {
            "type": "box",
            "layout": "vertical",
            "flex": 1,
            "alignItems": "center",
            "contents": [
                {"type": "text", "text": str(value), "size": "xxl", "weight": "bold", "color": color, "align": "center"},
                {"type": "text", "text": label, "size": "xs", "color": "#888888", "align": "center"},
            ],
        }

    status_row = {
        "type": "box",
        "layout": "horizontal",
        "margin": "lg",
        "spacing": "sm",
        "contents": [
            _metric_box("待處理", pending, "#FF9800"),
            _metric_box("處理中", in_progress, "#2196F3"),
            _metric_box("已結案", closed, "#4CAF50"),
            _metric_box("退回", returned, "#F44336"),
        ],
    }

    # --- District rows (compact) ---
    district_rows: list[dict] = []
    if by_district:
        district_rows.append({"type": "separator", "margin": "lg"})
        district_rows.append({"type": "text", "text": "各工務段件數", "weight": "bold", "size": "sm", "margin": "lg", "color": "#555555"})

        # Load district names from districts.json for display
        district_label_map = {d["id"]: d["name"] for d in _districts()}
        for did, count in sorted(by_district.items(), key=lambda x: -x[1]):
            display_name = district_label_map.get(did, did)
            district_rows.append({
                "type": "box",
                "layout": "horizontal",
                "margin": "sm",
                "contents": [
                    {"type": "text", "text": display_name, "size": "sm", "flex": 3, "color": "#555555"},
                    {"type": "text", "text": f"{count} 件", "size": "sm", "flex": 1, "align": "end", "weight": "bold"},
                ],
            })

    body_contents: list[dict] = [
        {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {"type": "text", "text": f"總案件 {total} 件", "weight": "bold", "size": "md", "flex": 3},
                {"type": "text", "text": f"今日 +{today_new}", "size": "sm", "color": "#FF6B6B", "align": "end", "flex": 2, "gravity": "center"},
            ],
        },
        status_row,
        *district_rows,
    ]

    bubble: dict = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": INFO_COLOR,
            "paddingAll": "16px",
            "contents": [
                {"type": "text", "text": "📊 案件統計摘要", "color": "#FFFFFF", "weight": "bold", "size": "lg"},
            ],
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "contents": body_contents,
        },
    }

    # Add footer with web link if URL provided
    if stats_url:
        bubble["footer"] = {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "action": {"type": "uri", "label": "📊 查看完整統計", "uri": stats_url},
                    "style": "primary",
                    "color": INFO_COLOR,
                    "height": "sm",
                },
            ],
        }

    return {
        "type": "flex",
        "altText": f"統計摘要：共 {total} 件案件",
        "contents": bubble,
    }
```

### Step 2: Update line_flow.py to pass stats_url

In `app/services/line_flow.py`, line 159-160, update the call to pass the stats page URL. The controller needs access to `app_base_url` from settings. Check how the controller is initialized — it may need the base URL injected at construction.

Find where `LineFlowController.__init__` is and add `base_url: str = ""` parameter. Then use it:

```python
# line 159-160 becomes:
if command == "統計摘要" or action == "statistics":
    stats_url = f"{self._base_url}/webgis/stats.html" if self._base_url else ""
    return [FlexBuilder.statistics_flex(self._cases.get_statistics(), stats_url=stats_url)]
```

**IMPORTANT:** Check `LineFlowController.__init__` signature to understand what's already passed. The `app_base_url` from settings should be threaded through. Check `main.py` where the controller is constructed (line 74-83) — you may need to add `base_url=settings.app_base_url` there.

### Step 3: Run full tests

Run: `python -m pytest -v`
Expected: ALL PASS (the Flex output is a dict, existing test_get_statistics doesn't test the Flex)

### Step 4: Commit

```bash
git add app/services/flex_builders.py app/services/line_flow.py app/main.py
git commit -m "feat: redesign LINE statistics flex with rich summary card and web link"
```

---

## Task 4: Create `webgis/stats.html` — Chart.js Dashboard

**Files:**
- Create: `webgis/stats.html`

**Design constraints from user approval:**
1. **5 tabs**: 總覽, 經費, 照片, 路線, 地圖
2. **Style**: Match `webgis/index.html` CSS variables (--bg-panel, --text-main, --stroke, --accent, etc.)
3. **Font**: "Noto Sans TC", same as index.html
4. **Chart library**: Chart.js 4.x via CDN
5. **Data source**: `GET /api/statistics` (relative path)
6. **Responsive**: Works on desktop and mobile
7. **Auto-refresh**: 60s interval

### Tab Contents (from approved design):

**Tab 1 — 總覽 (Overview)**
- Status pie chart (pending/in_progress/closed/returned)
- Time trend line chart (daily case creation)
- District bar chart (cases per district)
- Disaster type pie chart (by category)
- Damage mode bar chart (top modes by name)
- Processing time bar chart (avg hours per district)

**Tab 2 — 經費 (Budget)**
- 3 summary number cards (總初估, 已結案, 待處理) in 萬元
- Stacked bar per district (closed vs pending cost)
- Note text: "部分案件尚未填寫經費 (N件)"

**Tab 3 — 照片 (Photos)**
- Overall completion donut chart
- P1-P4 completion table with progress bars
- List of incomplete cases (expandable)

**Tab 4 — 路線 (Routes)**
- Route selector dropdown
- Mileage-based disaster distribution bar chart for selected route
- TOP 3 high-frequency segments table
- Click-to-map feature (link to webgis/index.html with params)

**Tab 5 — 地圖 (Map)**
- "查看地理分布" button → link to webgis/index.html

### Step 1: Create the complete stats.html file

Create `webgis/stats.html` as a single self-contained HTML file. Key structure:

```html
<!doctype html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>邊坡災害統計儀表板</title>
    <!-- Chart.js CDN -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <style>
        /* Use same CSS variables as webgis/index.html:
           --bg-panel, --text-main, --text-sub, --stroke, --shadow,
           --pending (#ff9800), --progress (#2196f3), --closed (#4caf50),
           --returned (#f44336), --accent (#0f6fbd)
           Same font-family: "Noto Sans TC", etc.
        */
        /* Tab navigation, responsive grid, card styles */
    </style>
</head>
<body>
    <!-- Tab navigation bar -->
    <!-- Tab content panels -->
    <script>
        const API_URL = '/api/statistics';

        // Tab switching logic
        // Data fetching
        // Chart rendering per tab
        // Auto-refresh
    </script>
</body>
</html>
```

**CRITICAL DETAILS for implementation:**

1. CSS variables MUST match webgis/index.html exactly:
```css
:root {
    --bg-panel: rgba(255, 255, 255, 0.94);
    --bg-panel-strong: rgba(255, 255, 255, 0.98);
    --bg-soft: #f4f7fb;
    --text-main: #1b2a3a;
    --text-sub: #4a5c6f;
    --stroke: #d6e2ee;
    --shadow: 0 16px 40px rgba(18, 40, 68, 0.16);
    --pending: #ff9800;
    --progress: #2196f3;
    --closed: #4caf50;
    --returned: #f44336;
    --accent: #0f6fbd;
}
```

2. Status color mapping for charts:
```javascript
const STATUS_COLORS = {
    pending_review: '#ff9800',
    in_progress: '#2196f3',
    closed: '#4caf50',
    returned: '#f44336',
};
const STATUS_LABELS = {
    pending_review: '待審核',
    in_progress: '處理中',
    closed: '已結案',
    returned: '已退回',
};
```

3. District label mapping:
```javascript
const DISTRICT_LABELS = {
    jingmei: '景美工務段',
    zhonghe: '中和工務段',
    zhongli: '中壢工務段',
    hsinchu: '新竹工務段',
    fuxing: '復興工務段',
    keelung: '基隆工務段',
};
```

4. Damage category labels:
```javascript
const DAMAGE_CATEGORY_LABELS = {
    revetment_retaining: '護岸/擋土牆類',
    road_slope: '道路邊坡類',
    bridge: '橋梁類',
};
```

5. Chart.js charts should be destroyed before re-creation on data refresh to prevent memory leaks.

6. All number formatting should use locale `zh-TW` where appropriate.

7. The "地圖" tab should have a single large button linking to `index.html` (relative path).

8. The "路線" tab's "click to map" should construct a URL like `index.html?road=台7線` (the index.html may not support this yet, but wire it so it can be added later).

9. Budget values are in 萬元 (10,000 NTD). Display with "萬元" suffix.

10. Auto-refresh: 60 second interval, same as index.html. Show "最後更新" timestamp.

### Step 2: Verify the page loads

Start the dev server and navigate to `/webgis/stats.html`. The page should:
- Load without console errors
- Show 5 tab buttons
- Fetch `/api/statistics` and render charts
- Handle empty data gracefully (0 cases = empty charts with "暫無資料" message)

### Step 3: Commit

```bash
git add webgis/stats.html
git commit -m "feat: create statistics dashboard with Chart.js (5 tabs)"
```

---

## Task 5: Integration Wiring + End-to-End Verification

**Files:**
- Possibly modify: `app/main.py` (if base_url threading needed)
- Possibly modify: `app/services/line_flow.py` (if base_url injection needed)

### Step 1: Verify the full flow

1. Start the server: `python -m uvicorn app.main:app --reload --port 8000`
2. Test API: `curl http://localhost:8000/api/statistics` → should return full JSON
3. Test web page: Open `http://localhost:8000/webgis/stats.html` → should render dashboard
4. Test LINE (if possible): Send "統計摘要" in LINE chat → should get rich Flex card

### Step 2: Run full test suite

Run: `python -m pytest -v`
Expected: ALL tests PASS

### Step 3: Check for LSP diagnostics

Run LSP diagnostics on all changed files:
- `app/services/case_store.py`
- `app/services/case_manager.py`
- `app/routers/statistics.py`
- `app/services/flex_builders.py`
- `app/services/line_flow.py`
- `app/main.py`

Expected: 0 errors on all files.

### Step 4: Final commit

```bash
git add -A
git commit -m "feat: complete statistics display system — LINE summary + web dashboard"
```

### Step 5: Update checkpoint

Update `CHECKPOINT_2026-02-28.md` (or create `CHECKPOINT_2026-03-01.md`) with:
- Statistics system implementation complete
- Files created/modified
- Test count (should be 94 + ~12 new = ~106)
- Next steps updated

---

## Dependency Order

```
Task 1 (backend stats) → Task 2 (API endpoint) → Task 3 (LINE flex) → Task 4 (web dashboard) → Task 5 (integration)
```

Tasks 3 and 4 are semi-independent (both depend on Task 1+2 data format, but don't depend on each other). Could be parallelized if using two subagents.

## Risk Notes

1. **Test fixture for API tests**: The `create_app()` may need specific env vars. Check existing test patterns (e.g., `tests/conftest.py`) before writing the API test fixture from scratch.
2. **`base_url` threading**: The LINE Flex needs an absolute URL for the "查看完整統計" button. Need to check how `app_base_url` propagates from settings → LineFlowController.
3. **Chart.js bundle size**: Using CDN so no bundle concern, but ensure the CDN URL is stable.
4. **Empty state**: All charts must handle 0 cases gracefully — don't divide by zero, show "暫無資料".
