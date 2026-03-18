# 邊坡災害通報與資訊整合管理系統 — 階段性記憶檢查點
# 時間：2026-03-02 21:10（里程確認後避免重複顯示災害回報位置地圖）

## 專案狀態：Phase 1 開發完成，里程樁號格式增強 + 道路邊坡照片 P2/P4 重構 + 選填補傳同步 + 里程確認後去除重複地圖已實作，333/333 測試全數通過

---

## 已完成工作

### ✅ 開發（Phase 1 核心）
1. 全部 57+ 原始碼檔案實作完成（LSP clean, compile clean）
2. Git commits:
   - `46fe2b2` — 完整實作（42 files, 8,662 lines）
   - `ff06a8b` — DOCX 規劃文件修正
   - `086b617` — 照片標註三層架構重建
   - `e40c383` — 統計後端擴展（budget, photo, route, damage, time trend）
   - `48b0458` — 統計顯示系統（API, LINE摘要卡, Web儀表板）

### ✅ NLSC 國土測繪圖資整合 — 完成 (2026-03-01)
- `webgis/index.html` (1054行) — 整合 NLSC WMTS 圖資至 WebGIS + 響應式設計 + 動態圖層載入
- **底圖 (5選1)**：電子地圖(含等高線/EMAP5, 預設)、電子地圖(EMAP)、正射影像(PHOTO2)、混合影像(PHOTO_MIX)、OpenStreetMap
- **疊加圖層 (8個可切換)**：⚠地質敏感區(山崩地滑/GeoSensitive2)、地質敏感區(全區)、道路路網、鄉鎮區界、段籍圖、國土利用現況、土壤液化潛勢、電子地圖標註(透明)
- 圖層控制器 `L.control.layers` 置於左上角，樣式與現有面板一致
- `markerLayer.bringToFront()` 確保案件標記永遠在最上層
- 所有 WMTS URL 使用 GoogleMapsCompatible TileMatrixSet，無需 API key
- CSS 覆寫 Leaflet 內建控制器樣式以符合系統設計語言
- `webgis/layers.json` (153行) — 獨立圖層設定檔（5底圖 + 8疊加圖層），供外部程式介接
- LSP 0 errors, 174 tests pass

### ✅ 桌面版 LINE 選單改善 — Phase B 完成 (2026-03-02)
- **問題**：LINE 桌面版 (Windows/Mac) 不支援 Rich Menu，也不支援 Quick Reply，用戶無法使用任何功能按鈕
- **解決方案**：實作文字指令觸發的 Flex Message 選單卡片作為 fallback
- **研究結果**（librarian 確認）：Rich Menu 桌面版官方不支援、Quick Reply 僅 iOS/Android、Flex Message 全平台支援、LINE API 無法偵測裝置類型
- **Phase A — 基礎選單指令支援** (已完成)：
  - `line_flow.py`：`_GLOBAL_COMMANDS` 新增「選單」「功能」、`_handle_idle()` 選單命令處理、閒置 fallback 提示、註冊完成附帶選單
  - `flex_builders.py`：`help_message()` 新增電腦版用戶提示
  - 8 個測試
- **Phase B — Premium 視覺升級** (已完成)：
  - `flex_builders.py` — `main_menu_flex()` 全面重新設計：
    - 深色 header (#1B2838)、系統標題「📋 邊坡災害通報系統」
    - 4 分類群組（緊急操作🔴/案件管理🔵/資訊工具🟢/個人設定⚫）
    - 彩色左邊 accent bar + 圓形圖示 + 粗體名稱 + 說明 + 箭頭 ›
    - 可點擊列設計（cornerRadius, borderWidth）
    - 管理員額外顯示「審核待辦」
  - `flex_builders.py` — 新增 `quick_action_card(context, is_manager)`：
    - 5 種情境：report_done / query_done / review_done / word_done / general
    - 每情境 2-3 個快捷按鈕（link 風格、彩色）
    - 對應 header 顏色（SUCCESS/INFO/JUDGMENT/NEUTRAL）
    - kilo size 精簡設計
  - `line_flow.py` — 9 個整合點加入 quick_action_card：
    - 通報送出後 → report_done
    - 跳過 Word 報告 → word_done
    - Word 報告產生成功 → word_done
    - Word 報告產生失敗 → general
    - 查詢案件結果（使用者/依區/依狀態，共 3 點）→ query_done
    - 核准使用者 → review_done
    - 退件使用者 → review_done
  - 測試：7 個 flex_builders 單元測試 + 5 個 line_flow 整合測試（共 12 個新測試）
- LSP 0 errors, 330 tests pass（含方案 A 修改）
- **方案 A — 常駐選單提示** (已完成)：
  - `flex_builders.py`：`quick_action_card()` bubble 新增 footer「💡 隨時輸入「選單」開啟完整功能面板」(xxs, #AAAAAA)
  - `line_flow.py`：新增 `HINT_MENU` 常數（"\n\n💡 輸入「選單」開啟功能面板"）
  - `line_flow.py`：8 個終端訊息追加 HINT_MENU：
    - 取消流程（L119）
    - 帳號狀態封鎖（L153-156）
    - 帳號未開通封鎖（L161）
    - 流程狀態異常重置（L189）
    - 未註冊使用者查詢（L1343）
    - 重新申請送出（L1468）
    - 個人資訊更新後待審核（L1541）
    - 非決策人員使用審核功能（L1573）
  - 修正 `quick_action_card()` bubble dict 缺少關閉大括號的語法錯誤
3. **330/330 測試全數通過**（包含 19 個 word_generator 測試、44 個 users API 測試、9 個 E2E 端對端測試、60 個 LINE flow 測試（+8 選單 +5 快捷卡片）、35 個 Flex builder 測試（+7 快捷卡片）、6 個 user_store 新測試、103+ 個基礎測試）
4. LRS CSV 資料已載入（29,384 markers, 101 roads）
5. DOCX 規劃文件已產生並驗證可開啟


### ✅ 里程樁號格式增強 — 完成 (2026-03-02)
- **問題**：使用者輸入里程樁號格式不一致（`12.4`, `12k+400`, `12K+400`），系統無法統一處理
- **修改 `lrs_service.py`**：`_parse_milepost_km()` 新增 `.upper()` 處理大小寫 K
- **支援格式**：`12K+400`, `12k+400`, `12K400`, `12k400`, `12.4`, `5k`, `10K` — 全部正規化為 `12K+400` 格式
- **測試**：`test_lrs_service.py` 擴充從 2 個斷言至 12 個
- 330/330 測試通過

### ✅ 道路邊坡照片重構 P2/P4 — 完成 (2026-03-02)
- **需求**：調整上傳順序、移動標註類別、重新命名照片描述
- **`photo_tags.json` 變更** (~2290 行)：
  - P2 重新命名：「災損近照」→「邊坡災害近照」
  - P2 `visible_damage` 移除 6 個崩塌類標籤（rockfall, shallow_slide, debris_flow, debris_avalanche, rock_mass_slide, rock_topple）
  - P2 `(3/7)` 類別名稱由「可見損壞型態」改為「易致災狀況」，並移除 `deep_slide`（深層滑動）與 `mud_flow`（泥流）
  - P2 移除 `slide_surface` 和 `vegetation` 類別
  - P4 新增 `collapse_type` 類別（崩塌類型）4 個標籤：rockfall, debris_avalanche, rock_mass_slide, debris_flow
  - P4 接收 `slide_surface` 和 `vegetation` 類別（從 P2 移過來）
  - P2 `(5/7)`「道路影響損壞範圍估計」移至 P4，並改名為「道路受災害影響範圍」
  - 最新統計：P2: 6 個 photo_tag 類別，P4: 14 個 photo_tag 類別
- **`line_flow.py` 變更** (~2437 行)：
  - `REQUIRED_PHOTO_TYPES` 從 `["P1","P2","P3","P4"]` 改為 `["P1","P4","P2","P3"]`
  - P2 提示文字更新為「拍攝目前會再致災的邊坡細節，清楚呈現損壞狀況。」
  - 新增 `_COLLAPSE_TYPE_TO_SURVEY` 對應 dict + `_auto_fill_site_survey()` 新增 `collapse_type` 分支
- **設計決策**：採用方案 A（重新排序 `REQUIRED_PHOTO_TYPES` 列表）而非方案 B（交換 P2/P4 內容），避免影響現有儲存資料的 photo_type 參照
- **測試更新**：`test_line_flow.py` 更新 photo step 測試 fixture（P2→P4 作為第二步）
- 330/330 測試通過，0 LSP errors

### ✅ 選填照片補傳必要照片順序/名稱同步 — 完成 (2026-03-02)
- **問題**：四張必要照片完成後進入「選填照片」時，「補傳必要照片」區塊仍使用舊順序（P1→P2→P3→P4）與舊提示文案
- **`flex_builders.py` 修正**：
  - 補傳必要照片順序改為 `P1 → P4 → P2 → P3`（與 `REQUIRED_PHOTO_TYPES` 一致）
  - 補傳提示文案同步新版需求（P2 改為「拍攝目前會再致災的邊坡細節...」）
  - 名稱解析改為優先使用災害類型專屬定義（`type_specific` 優先於 `common`），避免顯示舊名稱
- **測試**：`tests/test_flex_builders.py` 新增/更新 2 個測試，驗證補傳順序與 road_slope 類別名稱解析
- 331/331 測試通過

### ✅ 里程確認後去除重複位置地圖 — 完成 (2026-03-02)
- **問題**：使用者輸入里程樁號並確認後，系統在「座標/地質/國家範圍」資訊中又重複顯示一次「📍 災害回報位置」地圖
- **`line_flow.py` 修正**：在 `ReportingStep.CONFIRM_MILEPOST` 中，若 `milepost.source == "manual_milepost"`，不再追加 `location` 訊息；保留地質/行政區/國家公園與「已閱讀，繼續」按鈕
- **保留行為**：非手動里程來源（如 `source="auto"` 的座標推估）仍顯示位置地圖
- **測試**：`tests/test_line_flow.py` 新增 2 個測試（manual_milepost 不顯示地圖、non-manual 仍顯示地圖）
- 333/333 測試通過

### ✅ 工務段管轄路線修正 — 完成 (2026-03-02)
- **變更**：台9甲 從景美工務段移至中和工務段
- **修改檔案**：`app/data/districts.json`、`CHECKPOINT_2026-02-28.md`
- 330/330 測試通過

### ✅ 地質服務整合 — 完成 (2026-03-01)
- `geology_service.py`（428行）已接入系統
- `Case` model 新增 `geology_info` dict 欄位
- `main.py` 啟動時載入 Shapefile（a1p/b1l/c1l），try/except 保護
- `LineFlowController._apply_session_to_case()` 座標確認後靜默查詢地質
- 地質資訊 = 輔助建議值，背景帶入不顯示，人可改（Phase 2）
- `tests/test_geology_service.py` 8 個新測試
- LSP diagnostics clean

### ✅ LINE Bot 整合 — 運作中
- ngrok tunnel 運行中：https://unmurmurously-uncarted-nahla.ngrok-free.dev
- LINE Webhook URL 已設定並驗證成功
- Bot 能正常回覆訊息
- 使用者已註冊為「決策人員」

### ✅ Rich Menu — 正式圖片已上傳
- Manager menu: `richmenu-23a128b719187d3a4198e9d5d2250f52`
- User menu: `richmenu-a2142adbeac019680308ec72ccffae94`
- 按鍵排列：左上(通報災害) / 上中(查詢案件) / 右上(操作說明|審核待辦) / 左下(查看地圖) / 下中(統計摘要) / 右下(個人資訊)
- `rich_menu_ids.json` 儲存 menu ID
- `create_rich_menus.py` — 一鍵上傳壓縮腳本

### ✅ 座標/里程雙向轉換
- Branch A: 里程樁號 → 座標 (reverse_lookup)
- Branch B: 座標/GPS定位 → 里程 (forward_lookup)

### ✅ HEIC 照片支援
- 安裝 `pillow-heif`，註冊 HEIC opener
- 修正 MIME type vs Pillow format name 不一致問題
- 放寬最小尺寸要求（640×480 → 100×100）

### ✅ 照片標註系統 — 完整重建完成 (2026-03-01)

#### 設計決策（全部已由使用者確認）

**災害類型分類方案（方案A）：**
- 護岸/擋土牆類 (revetment_retaining): Row 1-11 + Row 14
- 道路邊坡類 (road_slope): Row 12-13 + Row 14 (pure slope only)
- 橋梁類 (bridge): Row 18-26
- 邏輯：「有牆→擋土牆類、無牆純坡→邊坡類、有橋→橋梁類」

**三層標註架構（Three-Tier）：**
| 層級 | 填寫者 | 時機 | 用途 |
|------|--------|------|------|
| required | 現場人員 | 現場 | 報告產出 |
| optional | 現場人員 | 有空時 | 補充細節 |
| ai_prefill | 系統(Phase2)/人(Phase1) | Phase 2 自動 | VisionLM 訓練資料 |

**兩區塊來源架構（Anti-Pollution）：**
| 來源 | 意義 | AI 訓練用 |
|------|------|-----------|
| photo (📷) | 照片中可見 | ✅ VisionLM |
| judgment (🧠) | 現場判斷，不一定在照片中 | ❌ 僅報告 |

**照片集架構（Multi-Photo per Type）：**
- 每個照片類型 (P1-P4) 為一個「照片集」，允許 1-3 張
- Per-photo `visible_tags`（只標該張照片可見的）
- Per-set `judgment_tags`（所有照片看完後填一次）
- 差異標記：第 2/3 張照片只顯示尚未標記的項目

**LINE UI/UX 設計決策：**
| 決策 | 選擇 |
|------|------|
| 互動元素 | Mixed：≤7 單選→Quick Reply；8+或多選→Flex Bubble |
| 進度顯示 | 每個項目都顯示 (3/14) |
| 導航 | 自動推進：系統自動推送下一項 |
| 填寫順序 | 📷 先填所有照片可見項 → 🧠 再填所有判斷項 |
| 多選佈局 | 雙欄 2×N |
| 排除選項 | 底部獨立區塊，有分隔線 |
| 多選確認 | 即時記錄 + 「下一項」按鈕 |
| 補拍照片 | 每張照片📷標籤完成後立即詢問 |
| 差異標記 | Per-item 自動推進，只顯示未標記選項 |
| 核心 UX 原則 | 每張卡片強調「看這張照片」防止標註污染 |

**色彩系統：**
| 用途 | 色彩 | Hex |
|------|------|-----|
| 📷 Photo visible header | Blue | #4A90D9 |
| 🧠 Judgment header | Orange | #E8A317 |
| ✅ Complete header | Green | #1DB446 |
| 🔴 Required marker | Red | #FF6B6B |
| Selected button | Gray | #888888 |
| Unselected button | Blue | #4A90D9 |
| Exclusion option | Light gray | #CCCCCC |

#### 已實作檔案

**`app/data/photo_tags.json` (~2290 lines) — ✅ 完成且驗證（含 road_slope P2/P4 重構）**
- 層級結構：`{ "common": { "P1", "P3" }, "revetment_retaining": { "P2", "P4" }, "road_slope": { "P2", "P4" }, "bridge": { "P2", "P4" } }`
- JSON 語法驗證通過

**`app/models/evidence.py` (~183 lines) — ✅ 完成且驗證**
- 新增 `PhotoSetPhoto` (photo_id, order, evidence_id, file_path, visible_tags)
- 新增 `PhotoSetAnnotation` (photo_set_type, photo_set_name, disaster_type, max_photos, is_required, photos, judgment_tags, merged_visible_tags, photo_tags_complete, judgment_tags_complete, is_complete)
- 包含 `merge_visible_tags()` 和 `mark_complete()` 方法
- 所有既有類別保持不變，LSP clean

**`app/models/line_state.py` (~167 lines) — ✅ 完成且驗證**
- 新增 5 個 `GuidedPhotoSubStep` enum：PHOTO_VISIBLE_TAGS, SUPPLEMENT_PHOTO, JUDGMENT_TAGS, TEXT_INPUT, SET_COMPLETE
- 原有值保持不變，LSP clean

**`app/services/flex_builders.py` (1337 lines) — ✅ 完成且驗證**
- 新增常數：`JUDGMENT_COLOR = "#E8A317"`, `EXCLUSION_COLOR = "#CCCCCC"`
- 新增模組級 `_resolve_photo_tags()` 輔助函式
- 更新 `get_photo_tag_definition()` 接受 `disaster_type` 參數
- 新增 8 個照片標註相關 `@staticmethod` 方法
- 重新設計 `statistics_flex()` — 富卡片摘要（狀態色彩方塊、工務段排序、Web按鈕）
- LSP: 0 errors

**`app/services/line_flow.py` (1448 lines) — ✅ 完成且驗證**
- 新增 `_resolve_photo_def()` — 從層級 photo_tags.json 解析定義
- 新增 `_photo_type_prompt()` — 各照片類型的靜態提示文字
- 修正 `_current_tag_categories()` — 使用 `photo_tags` 而非舊的 `tag_categories`
- 統計摘要傳入 `stats_url` 連結至 `/webgis/stats.html`
- LSP: 0 errors

### ✅ 統計顯示系統 — 完成 (2026-03-01)

#### 設計決策（使用者確認方案 C — 混合式）
- **LINE**: Flex Message 快速摘要卡片（今日通報、各狀態數、各工務段件數、連結至Web）
- **Web**: Chart.js 儀表板（5個分頁：總覽/經費/照片/路線/地圖）
- **API**: `GET /api/statistics` 提供完整數據

#### 已實作檔案

**`app/services/case_store.py` (~275 lines) — ✅ 新增 `load_all_cases()`**
- 批次載入所有案件用於統計計算

**`app/services/case_manager.py` (~370 lines) — ✅ 擴展 `get_statistics()`**
- 單趟聚合計算：total_cases, today_new, by_status, by_district, budget, photo_completeness, route_frequency, time_trend, damage_types, processing_time
- 向下相容（原有 total_cases, by_status, by_district 鍵值不變）

**`app/routers/statistics.py` (14 lines) — ✅ 新增**
- `GET /api/statistics` → 呼叫 `case_manager.get_statistics()`

**`app/main.py` (~145 lines) — ✅ 新增路由註冊**
- `app.include_router(statistics_router, prefix="/api/statistics", tags=["Statistics"])`

**`tests/test_statistics.py` (~170 lines) — ✅ 9 個新測試**
- 涵蓋：空資料、各狀態計數、工務段計數、預算、照片完整度、路線頻率、時間趨勢、損壞類型、處理時間

**`webgis/stats.html` (710 lines) — ✅ Chart.js 儀表板**
- 5 分頁：總覽（6張圖表）、經費（摘要卡+長條圖）、照片（甜甜圈+進度表）、路線（選單+里程分布+TOP5）、地圖（連結按鈕）
- CSS 變數與 index.html 完全一致
- 60 秒自動更新 + 最後更新時間戳
- 響應式設計（桌面+手機）
- Chart.js 實例重建前銷毀（防記憶體洩漏）
- 空資料顯示「暫無資料」

### ✅ WebGIS 響應式設計 — 完成 (2026-03-01)
- `webgis/index.html` (1054行) — 完整響應式 CSS，支援桌面/平板/手機
- 斷點：900px, 768px, 480px
- 手機/LINE 內建瀏覽器：篩選面板改為底部抽屜，圖例+資訊面板改為水平底部欄
- 資訊面板從右下移至左上（圖例上方）
- 篩選面板改用 `fit-content` 寬度（225px，佔視窗 21.7%）
- Playwright 驗證（桌面 + 手機 375×667）

### ✅ WebGIS 圖層設定獨立化 — 完成 (2026-03-01)
- `webgis/layers.json` (153行) — 獨立 JSON 設定檔，5 底圖 + 8 疊加圖層
- `webgis/index.html` — 原硬編碼 ~100 行 JS 替換為 `loadLayers()` 非同步函式
- 載入失敗自動 fallback 至 OSM
- 全域變數：`baseMaps = {}`, `overlayMaps = {}`, `layerControl = null`

### ✅ E2E 端對端測試 — 完成 (2026-03-01)
- `tests/test_e2e_reporting.py` (9 個測試) — 完整 12 步驟通報流程 API 模擬測試
- 涵蓋：完整 happy path（含 4 張照片上傳+標註）、中途取消、返回導航、里程輸入(23K+500)、無效座標、經費輸入、經費跳過、現場勘查切換、未註冊使用者阻擋
- 包含可重用 `annotate_current_photo()` helper，動態讀取 photo_tags.json 處理單選/多選標註
- 174/174 測試全數通過

**`docs/plans/2026-03-01-statistics-display.md` (951 lines) — ✅ 實作計畫**
- 5 任務分解、TDD 流程、完整程式碼規格

### ✅ 照片標註值調整 + 勾稽功能 — 完成 (2026-03-01~02)
- `photo_tags.json` — 標註值 rename（全層級一致），新增 6 個勾稽用標註
- `flex_builders.py` — 「跳過」按鈕修正
- `word_generator.py` — Table 1 & Table 2 checkbox 勾選邏輯（勾稽）
- `line_flow.py` — `visible_damage` auto-fill 擴展

### ✅ 全區選項 + word_generator 日期修復 — 完成 (2026-03-02)

#### 全區選項
- `app/data/districts.json` — 新增 `{"id": "all", "name": "全區", "roads": []}` 為第一筆
- `app/services/flex_builders.py` — `district_quick_reply()` 新增 `include_all: bool = True` 參數
- `app/services/line_flow.py` — 通報流程排除全區（`include_all=False`），註冊/個人資訊包含全區
- 全區 = 管理所有工務段，權限等同系統開發者
- `tests/test_flex_builders.py` — 更新 district count 6→7，新增 `test_district_quick_reply_exclude_all`

#### word_generator 日期 mojibake 修復
- **根因**：Word 模板 `paragraphs[5]` 有 7 個 runs（非程式碼預期的 10 個），導致日期填入條件 `len(p5.runs) >= 10` 永遠不成立
- **模板結構**：run[0]=災害發生日期：, run[1]=年份空格, run[2]=年, run[3]=月份空格, run[4]=月, run[5]=日期空格, run[6]=日
- **修復**：`word_generator.py` line 297 — 條件改為 `>= 7`，run indices 從 `[1,4,7]` 改為 `[1,3,5]`
- 19 個 word_generator 測試全數通過（含 `test_generate_date_fill_iso` 和 `test_generate_date_fill_minguo`）

#### IndexError 調查結論
- `_set_cell_text()` (line 962) 已有 empty-paragraph guard，安全
- `_insert_cost_table()` (lines 653/658) 使用 `doc.add_table()` 建立的 cell，python-docx 保證至少有一個 paragraph，安全
- server.log 中的 IndexError 來自舊版程式碼，當前版本已無此問題

### ✅ 審核待辦修復 — 帳號管理入口 + DRAFT 狀態 — 完成 (2026-03-02)

#### 問題描述
1. 「審核待辦」Rich Menu 直接顯示案件列表，沒有帳號管理功能入口
2. 案件資訊全顯示 0（completeness_pct=0, photo_count=0, 所有欄位為空）

#### 根因分析
- 照片上傳步驟呼叫 `_ensure_draft_case()` → `create_case()` 建立草稿案件
- 案件預設 `review_status=pending_review`，若使用者中途放棄（全域命令攔截器 reset session），空草稿留在磁碟
- 這些空草稿出現在管理者的「審核待辦」列表，所有欄位皆為 0

#### 修復方案
- **新增 `ReviewStatus.DRAFT`** — 草稿不再以 `pending_review` 存在
- **修改檔案**：
  - `app/models/case.py` — 新增 `DRAFT = "draft"` enum，預設改為 `DRAFT`
  - `app/services/case_manager.py` — 新增 `DRAFT→PENDING_REVIEW` 轉換，`create_case()` 加入 `calculate_completeness()`
  - `app/services/line_flow.py` — `_handle_management()` 新增子選單（案件審核/人員管理），含 approve/reject user 功能
  - `tests/test_case_manager.py` — 新增 `_submit_case()` helper，所有審核相關測試走 `DRAFT→PENDING_REVIEW` 生命週期
  - `storage/cases/case_20260228_0001/case.json` — 修正 `pending_review` → `draft`
  - `storage/cases/case_20260301_0002/case.json` — 修正 `pending_review` → `draft`

#### 案件生命週期（更新後）
```
DRAFT → PENDING_REVIEW → IN_PROGRESS → CLOSED
                       ↘ RETURNED → PENDING_REVIEW
```

#### 驗證結果
- LSP diagnostics: 0 errors（所有修改檔案）
- 測試：266/266 全數通過
- 102 個相關測試全數通過

### ✅ 權限閘門 + 個人資訊編輯/再次申請 — 完成 (2026-03-02)

#### 功能需求（使用者原文）
> "加上權限檢查, 然後在 個人資訊 功能 加上 再次申請的功能 與 更改資訊的功能, 再次申請 或 更改個人資訊 都需要 審核人員 再做確認, 開通後 即可 開放所有權限"

#### 問題描述
- 原本系統**無權限檢查** — rejected/pending/suspended 使用者可以使用所有 Bot 功能
- `handle_event()` 只檢查 `user is None`（從未註冊），不檢查 `user.is_active`
- `FlowType.PROFILE` 已存在於 enum 但從未實作對應的 `_handle_profile()` 方法

#### 實作方案

**1. 權限閘門（Permission Gate）** — `line_flow.py` 主 `handle_event()` (~L135-159)
- 非 active 使用者只允許使用「個人資訊」和「操作說明」
- 允許的 postback actions: `profile`, `help`, `edit_profile`, `reapply`, `edit_real_name`, `edit_role`, `edit_district`, `confirm_edit_profile`, `confirm_reapply`
- 非允許命令/流程：自動 reset session + 回覆狀態特定訊息（待審核/已退件/已停用）
- LINE API 無法踢除群組使用者，採用應用層級封鎖

**2. User.reapply() 方法** — `user.py` (~L81)
- 設定 `status = PENDING`，清除 `approved_at` 和 `approved_by`

**3. UserStore 新方法** — `user_store.py` (after L142)
- `reapply(line_id)`: 呼叫 `user.reapply()`，儲存
- `update_profile(line_id, **fields)`: 更新 real_name/role/district_id/district_name，自動呼叫 `user.reapply()` 設為待審核

**4. ProfileStep enum** — `line_state.py` (after L34)
- MENU, EDIT_REAL_NAME, EDIT_ROLE, EDIT_DISTRICT, CONFIRM_EDIT, CONFIRM_REAPPLY

**5. FlexBuilder.profile_flex() 增強** — `flex_builders.py` (~L959)
- 新增 `show_actions` 參數（預設 True）
- 所有狀態都顯示「✏️ 更改資訊」按鈕
- rejected/suspended 額外顯示「🔄 再次申請」按鈕

**6. _handle_profile() 完整流程** — `line_flow.py` (~L1384-1553)
```
edit_profile → MENU（選擇欄位）→ EDIT_REAL_NAME/EDIT_ROLE/EDIT_DISTRICT → CONFIRM_EDIT → update_profile() + 通知管理者
reapply → CONFIRM_REAPPLY → reapply() + 通知管理者
```

#### 修改檔案
- `app/models/user.py` (89行) — 新增 `reapply()` 方法
- `app/models/line_state.py` (192行) — 新增 `ProfileStep` enum
- `app/services/user_store.py` (253行) — 新增 `reapply()` 和 `update_profile()` 方法
- `app/services/flex_builders.py` (~2466行) — 重寫 `profile_flex()` 含 footer action buttons
- `app/services/line_flow.py` (~2412行) — 權限閘門 + profile 流程 + bug 修復
- `tests/test_line_flow.py` (1087行) — 13 個新測試 + 1 個 assertion 更新
- `tests/test_user_store.py` (~240行) — 6 個新測試
- `tests/test_e2e_reporting.py` (399行) — 1 個 assertion 更新

#### Bug 修復
1. **line_flow.py L179**: 重複的 `_handle_management()` 呼叫覆蓋 `_handle_profile()` 結果（copy-paste artifact）→ 刪除
2. **line_flow.py L25**: `_postback_data` 未 import → 加入 import

#### 新增測試（19 個）
- `test_line_flow.py`: 7 個權限閘門測試 + 6 個 profile/reapply 測試 = 13 個
- `test_user_store.py`: 6 個測試（reapply, reapply_nonexistent, reapply_from_suspended, update_profile, update_profile_partial, update_profile_nonexistent）
- 2 個既有測試 assertion 更新（權限閘門訊息變更）

#### 驗證結果
- LSP diagnostics: 0 errors（所有 7 個修改檔案）
- 測試：266/266 全數通過
### ✅ Web 人員管理頁面 (Admin Panel) — 完成 (2026-03-02)

#### 功能需求（使用者原文）
> "那目前所有人員的管理 你會建議我可以在哪裡 做管理 然後 只有 決策者 權限的人可以"
> 選擇：Web 管理頁面 + URL token 驗證 + 全部 5 項操作 + LINE Bot 連結按鈕

#### 認證機制
- URL token 驗證（HMAC-SHA256 + 1 小時過期）
- LINE Bot 產生 tokenized URL，點擊後直接開啟 admin 頁面
- 無登入表單，僅限決策人員 (manager) 存取
- Token 格式：`base64url(json({uid, exp}))` + `.` + `hmac_sha256(secret, payload)`

#### 5 項操作
1. 核准/退件待審核 (approve/reject pending users)
2. 停用/恢復帳號 (suspend/restore accounts)
3. 修改角色 (change role: user ↔ manager)
4. 修改工務段 (change district)
5. 刪除帳號 (delete user — irreversible)

#### 已實作檔案

**`app/core/security.py` — 新增 token 函式**
- `generate_admin_token(user_id, secret, expires_in=3600)` — 產生 HMAC-SHA256 籤名 token
- `verify_admin_token(token, secret)` — 驗證 token + 檢查過期

**`app/models/user.py` — 新增 `suspend()` 方法**
- 設定狀態為 `UserStatus.SUSPENDED`

**`app/services/user_store.py` — 5 個新方法**
- `suspend(line_id)`: 停用帳號
- `delete_user(line_id)`: 永久刪除使用者檔案
- `update_role(line_id, new_role)`: 變更角色 (user/manager)
- `update_district(line_id, district_id, district_name)`: 變更工務段
- `restore(line_id)`: 恢復停用帳號為 ACTIVE

**`app/routers/users.py` (243 lines) — 新建 API 路由**
- `GET /api/users` — 列出使用者（可篩選 status/district）
- `POST /api/users/action` — 執行 approve/reject/suspend/restore
- `PATCH /api/users` — 更新 role 和/或 district
- `DELETE /api/users` — 永久刪除使用者
- `GET /api/users/districts` — 回傳工務段列表
- 所有端點均需 `?token=...` 參數 + manager 角色檢查

**`app/main.py` — 路由註冊**
- `app.include_router(users_router, prefix="/api/users", tags=["Users"])`

**`app/services/line_flow.py` — LINE Bot 整合**
- 新增 `from app.core.security import generate_admin_token` import
- 審核待辦子選單新增「📋 完整管理」 URI 按鈕，產生 HMAC token URL 開啟 admin.html

**`webgis/admin.html` (767 lines) — 完整管理頁面**
- Token 驗證（從 URL query parameter 讀取）
- 狀態摘要卡片（可點擊篩選）
- 篩選欄：狀態下拉、工務段下拉、搜尋輸入
- 桌面表格 + 手機卡片視圖（響應式 640px 斷點）
- 上下文動作按鈕（依使用者狀態顯示不同操作）
- Modal 對話框（角色變更、工務段變更、刪除確認）
- Toast 通知
- Loading/空資料/錯誤狀態
- CSS 完全比照 stats.html 設計語言

**`tests/test_users_api.py` (~440 lines) — 44 個新測試**
- 11 個 token 測試（產生/驗證/過期/篤改）
- 12 個 store method 測試（suspend/delete/update_role/update_district/restore）
- 2 個 model 測試（User.suspend()）
- 19 個 API 整合測試（所有端點 + 權限檢查 + 錯誤處理）
- 自建最小化 FastAPI app fixture（跳過地質/LRS 服務）

#### 驗證結果
- LSP diagnostics: 0 errors（所有修改檔案）
- 測試：310/310 全數通過（44 個新測試）
- Uvicorn 已重啟（PID 55600）

---

## 🟢 當前狀態：Phase 1 全部完成 + 桌面版選單系統（Premium Menu + Quick Action + 常駐提示）完成，330/330 測試全數通過

### 照片標註系統設計記錄

#### 標註方法論
- 方法名稱：**Image-level Annotation (圖像級標註) / Multi-label Classification Labeling**
- 不圈繪，純文字多選標籤
- Phase 1 人工點選 → Phase 2 AI 半自動化（Vision LLM + fine-tuned classifier）
- 可用 CAM/Grad-CAM 做弱監督定位

#### Phase 2 最終目標（已與用戶確認）
```
照片上傳 → AI自動標註(人審核) → 災害描述自動生成(人修改)
→ 尺寸確定 → 整治設施(人給) → 經費概估(規則引擎) → 報告自動產出(人簽核)
```

表單自動化程度預估：
- （一）現況及災損概估：90% 自動
- （二）位置圖/現場照：95% 自動
- （三）破壞模式與致災原因：70% 自動（AI建議人確認）
- （四）復建計畫：60% 自動（工法需人決策）
- （七）工址環境調查：85% 自動

#### 目標 UI 流程（完整版）
```
上傳照片 → 入口卡片 →
  📷 逐項可見標籤（自動推進+進度顯示） →
  📷 完成 → [📸 補拍] / [🧠 判斷] / [⏭ 跳過] →
  (可選補拍 → 差異標記) →
  🧠 逐項判斷標籤（橘色卡片） →
  照片集完成摘要 → 下一集
```

---

## 關鍵資訊

### LINE 設定
- Channel ID: 2009266912
- Channel Secret: 89c4d7b306c42a00a56297c8b06080fc
- Channel Access Token: Q/hz4JBa/oEGsmXPdb+1FwYLKn8M5tW/FnCe7fyhAOWXI9xKPQ17XO2JTJnhSvW8tz9Reskhf2NhoPh3HHaqIZOC6jBMJY+UrQcuLodaPeblqQr9Sv4hkuRkJLhX6vhAlibV6wv2D4IO0RhA74x4awdB04t89/1O/w1cDnyilFU=
- LINE OA ID: @540rtauz
- LINE OA Name: System_Service
- User LINE ID: U64fa245a3b8e9b38ca0b716a889d71ae

### 基礎設施
- ngrok URL: https://unmurmurously-uncarted-nahla.ngrok-free.dev
- ngrok authtoken: 3AIeINlIT1slDLGqxUBPaR7BkkG_yE8y8k8kS5F2WugYGXXJ
- ngrok inspector: http://127.0.0.1:4040
- uvicorn port: 8000
- 統計儀表板: /webgis/stats.html
- 統計 API: /api/statistics
- 人員管理頁面: /webgis/admin.html?token=...
- 人員管理 API: /api/users (需 token 參數)

### 設計約束
- Phase 1 only: 不實作 AI/LLM，保留欄位供 Phase 2
- 繁體中文
- 角色：使用者人員(user) / 決策人員(manager)
- 初估經費：選填
- 照片標註方法：Image-level Annotation (multi-label classification)
- 照片標註：按災害類型區分（擋土牆/護岸、道路邊坡、橋梁）
- P2、P4 為必填標註照片
- File-based JSON storage（無資料庫）
- Bootstrap admin 透過 .env 設定
- 取消流程草稿資料：保留不刪除，狀態為 DRAFT（不顯示於審核待辦列表）
- 過程有問題的LOG都要記錄
- 選項儘量用點選方式，內容要夠豐富也要夠方便
- 要輔助第二階段AI辨識
- 要強調一張照片有哪些狀況才選
- 要有補照片再填寫的機制
- 統計顯示：LINE 摘要 + Web 詳細（方案 C 混合式）

### 六個工務段
| 工務段 | ID | 管轄路線 |
|--------|-----|---------|
| 景美工務段 | jingmei | 台2(部分), 台3, 台5, 台9, 台9乙 |
| 中和工務段 | zhonghe | 台3(都會), 台9(都會), 台9甲, 台15(部分), 台64, 台65 |
| 中壢工務段 | zhongli | 台1, 台4, 台15(桃園), 台31, 台66, 台61(部分) |
| 新竹工務段 | hsinchu | 台1(新竹), 台3(部分), 台13, 台15(濱海), 台31(部分), 台61(部分), 台68 |
| 復興工務段 | fuxing | 台7, 台7甲, 台7乙, 台118(部分), 台4(東段), 台3(北端山區) |
| 基隆工務段 | keelung | 台2, 台2甲(北段), 台5(基隆-汐止), 台9(瑞芳短段), 台62, 台62甲, 台102 |

### NLSC 國土測繪圖資 — 關鍵API端點
| Service | URL | Purpose |
|---------|-----|---------|
| WFS | https://wfs.nlsc.gov.tw/WFS | 向量圖徵查詢 |
| 門牌API | https://api.nlsc.gov.tw/idc/TextQueryMap/ | 地址地理編碼 |
| 地籍圖API | https://api.nlsc.gov.tw/dmaps/CadasMapPointQuery/ | 地籍查詢 |
| 國土利用API | https://api.nlsc.gov.tw/other/LandUsePointQuery/ | 土地利用分類 |
| 行政區API | https://api.nlsc.gov.tw/other/TownVillagePointQuery/ | 座標→行政區 |
| 圖臺API | https://maps.nlsc.gov.tw/go/{lon}/{lat}/{zoom}/{basemap}/ | 官方地圖連結 |

### API 資料格式 (/api/statistics)
```json
{
    "total_cases": int, "today_new": int,
    "by_status": {"draft": int, "pending_review": int, "in_progress": int, "closed": int, "returned": int},
    "by_district": {"jingmei": int, ...},
    "budget": {"total_estimated": float, "closed_estimated": float, "pending_estimated": float, "unfilled_count": int},
    "photo_completeness": {"total_cases": int, "cases_complete": int, "overall_pct": float, "by_photo_type": {"P1": int, "P2": int, "P3": int, "P4": int}},
    "route_frequency": [{"road": str, "count": int, "mileposts": [float]}],
    "time_trend": [{"date": "YYYY-MM-DD", "count": int}],
    "damage_types": {"by_category": {str: int}, "by_name": {str: int}},
    "processing_time": {"avg_hours": float, "total_closed": int, "by_district": {str: float}}
}
```

---

## 檔案結構（更新後）

```
app/
├── main.py (~168)
├── core/: config.py(97), logging_config.py(45), security.py(~100)
├── models/: case.py(243), evidence.py(183), user.py(~95), line_state.py(192), vendor.py(101)
├── routers/: line_webhook.py(141), cases.py(86), vendor_api.py(193), health.py(16), statistics.py(14), users.py(243)
├── services/: audit_logger.py(111), user_store.py(~300), case_store.py(~275),
│   evidence_store.py(313), case_manager.py(~467), lrs_service.py(498),
│   image_processor.py(431), pdf_parser.py(340), line_session.py(97),
│   flex_builders.py(~2711), line_flow.py(~2437), notification_service.py(164),
│   geology_service.py(428)
├── data/: districts.json, photo_tags.json(~2290), damage_modes.json, site_survey.json, lrs_milepost.csv
webgis/index.html (1054), stats.html (710), admin.html (767), layers.json (153)
tests/: 12 files, 330 tests (330 pass, 0 failures)
  test_e2e_reporting.py(9), test_line_flow.py(60+), test_flex_builders.py(35+),
  test_case_manager.py(273), test_word_generator.py, test_audit_logger.py, test_case_store.py,
  test_evidence_store.py, test_geology_service.py, test_image_processor.py,
  test_lrs_service.py, test_statistics.py, test_user_store.py (~240),
  test_users_api.py (~440, 44 tests) (103+ combined)
docs/plans/2026-03-01-statistics-display.md (951)
generate_planning_doc.py (964)
start_server.py — 一鍵 FastAPI + ngrok 啟動器
create_rich_menus.py — Rich Menu 上傳壓縮腳本
rich_menu_ids.json — Rich Menu IDs
```

---

## 待完成工作（優先順序）

### 🟡 接續
1. ~~整合 NLSC 國土測繪圖資至 WebGIS~~ ✅ 已完成
2. ~~完整端對端流程測試（照片標註新 UI 流程）~~ ✅ API 模擬測試完成（9 tests）
3. ~~Rich Menu 替換正式圖片~~ ✅ 已完成（Manager + User 各 6 按鍵）
4. ~~審核待辦 帳號管理功能 + 案件資訊全零修復~~ ✅ DRAFT 狀態 + 子選單完成
5. ~~權限閘門 + 個人資訊編輯/再次申請~~ ✅ 完成（19 個新測試）
6. ~~Web 人員管理頁面 (Admin Panel)~~ ✅ 完成（44 個新測試，admin.html 767 行）
7. ~~修復 `test_generate_date_fill_iso` / `test_generate_date_fill_minguo` mojibake~~ ✅ 已修復
8. **使用者手動 LINE 驗證** — 按照 8 大測試、29 步驟手動測試清單在實機 LINE 上驗證
9. **Web 人員管理頁面瀏覽器實測** — 確認 admin.html 在瀏覽器中正確顯示與操作

### 🟢 之後
4. 安全性：測試完成後輪換憑證
5. Phase 2 AI/LLM 模組（暫不實作）

---

## 已完成的 Agent Sessions

| Agent | Description | Session ID |
|-------|-------------|------------|
| Junior | 重構 photo_tags.json — 完整三層 annotation schema (1864 lines) | ses_358b99eaaffeiU3EhFk6lF7zDa |
| Junior | Rework line_flow.py — hierarchical photo_tags access | ses_358a13052ffeSbj6zRTu8tAaAq |
| Junior | GeologyService integration | ses_35abe5694ffe98T2bXtMgbbt0Q |
| Junior | 照片引導上傳流程重設計 | ses_35b377950ffei9Z9nQWe0oiK2s |
| Junior[deep] | Task 1: Expand get_statistics() + load_all_cases() | ses_358709be4ffe76o5L4lqNFTYdA |
| Junior[quick] | Task 3: Redesign FlexBuilder.statistics_flex() | ses_3586adfe9ffeNdE00pT8woXh4K |
| librarian | LINE API 研究 | ses_35c726e69ffejBiUcs5QOIG75O |
| librarian | PDF parsing 研究 | ses_35c725027ffem1zb3XAHiE7jzC |
| librarian | FastAPI patterns | ses_35c7230c3ffeKq7kuwWJa0H7dB |
| explore | 座標查找分析 | ses_35c720183ffeYL8sIhyn1I8KGr |
| oracle | 架構設計 | ses_35c6b2773ffe3mEaS2UJ57AJbw |
| librarian | 災害照片標註分類 | ses_35c090158ffeyMwQCZPw25xY5 |
| librarian | LINE Flex 多選模式 | ses_35c08c787ffezULlXYEAwfkhq0 |
| explore | NLSC 相關程式碼搜索 | ses_3585ffec9ffeIfmBQmko9yIV1t |
| librarian | NLSC WMTS 研究 + Leaflet 整合方式 | ses_3585fd7b9ffemBX91nFg27axEF |
| explore | LINE bot 對話流程狀態映射 | ses_35856d5c3ffeiSEXburT9s6WjA |
| explore | 測試檔案/模式搜索，識別測試缺口 | ses_35856bfaaffezuZsBrGQvB6ViK |
| Junior[deep] | test_line_flow.py — 34 E2E LINE flow tests | ses_358519108ffeum3QD7RJwXzL0Z |
| Junior[deep] | test_flex_builders.py — 28 Flex builder tests | ses_3585108d7ffeFpd11R5LBuegA2 |
| Junior[deep] | test_e2e_reporting.py — 9 E2E reporting flow tests | ses_3582e3653ffezDt6a8S0BACFU0 |
| explore | 權限閘門 — Explore user model, store, registration flow | ses_353977c39ffe5ZBUzptjYBfNjy |
| explore | 權限閘門 — Explore Rich Menu and LINE webhook routing | ses_353976197ffenJ1GtN6cJ2vG4U |
| librarian | LINE API: can bot kick/remove user from group? | ses_352e9edb0ffenM6iBl39NuU0ck |
| librarian | LINE Quick Reply postback format | ses_352b863b6ffeK7wLb2sxg8w5gP |
| explore | User management — user model, store, registration | ses_353977c39ffe5ZBUzptjYBfNjy |
| explore | User management — Rich Menu and webhook routing | ses_353976197ffenJ1GtN6cJ2vG4U |
| librarian | LINE 桌面版 rich menu 限制研究 | ses_35263486dffeXUlSuEsfjRfiep |
| librarian | LINE Messaging API persistent menu 研究 | ses_35241f77effeeqK9Upt7lGRjVY |
| Junior[deep] | 照片重構/里程格式/方案A（取消——主代理即接入執行） | ses_3524f0cd9ffeAXYSWyH2PnsHza |

---

## 使用者明確約束（原文）

- "請你以領導的腳色請subagent執行, 若subagent狀況不佳你再接入執行"
- "成果跟階段性記憶存在此資料夾"
- Phase 1 only: "暫不實作" Stage 2 AI/LLM
- "同一筆紀錄須能處理至少5張、最多10張照片上傳且做格式驗證"
- "必須於指定LINE聊天室完成消息處理模組操作流程"
- "若轉換不確定（confidence較低），回覆時標註「估值」"
- "腳色部分不用承辦人只要分為決策人員使用者人員這兩類就好"
- "初估經費可以先變成是選填"
- "聯絡資訊應該是不用因為是給公務機關內部使用的"
- "過程有問題的LOG都要記錄"
- 取消草稿資料："不用，先留著"（不刪除）
- "rich menu圖 我稍晚提供 我們先做其他的測試"
- "P2 P4一定要標註"
- 標註方法已確認為 Image-level Annotation (不圈繪，純文字標籤)
- "每一個環節做完請都 更新記憶"
- 地質資訊："做為自動查詢輔助, 最後資訊還是人為確認或更改"
- 地質顯示："背景帶入不顯示"
- "選項上 儘量 可以用點選的方式 所以選取內容要夠豐富 也要夠方便"
- "關於要輔助第二階段AI辨識部分 我認為也要納入"
- "要強調一張照片有哪些狀況才選, 然後要有可以補照片再填寫的機制"
- "然後最後再 幫我把Line上要點選的UI UX再設計精美一點, 然後再來討論統計顯示功能部分"
- 統計顯示功能：方案C（LINE摘要 + Web詳細）
- 統計Web增加：經費相關、照片完整度、特定路線災害頻率
- "加上權限檢查, 然後在 個人資訊 功能 加上 再次申請的功能 與 更改資訊的功能, 再次申請 或 更改個人資訊 都需要 審核人員 再做確認, 開通後 即可 開放所有權限"
- "用相似的標註能夠帶到相關對應的表格選項是最佳的方案, 儘量不要多填"


- "那目前所有人員的管理 你會建議我可以在哪裡 做管理 然後 只有 決策者 權限的人可以"
- 選擇：Web 管理頁面 + URL token 驗證 + 全部 5 項操作 + LINE Bot 連結按鈕
- "選了全區 就等於 全部的省道都能選取 權限就跟系統開發者一樣"
