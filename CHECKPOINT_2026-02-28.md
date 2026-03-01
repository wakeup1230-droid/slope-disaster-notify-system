# 邊坡災害通報與資訊整合管理系統 — 階段性記憶檢查點
# 時間：2026-02-28 → 更新 2026-03-01 01:30（照片標註 UI/UX + 實作完成）

## 專案狀態：Phase 1 開發完成，照片標註三層架構已實作，統計顯示功能待討論

---

## 已完成工作

### ✅ 開發（Phase 1 核心）
1. 全部 57+ 原始碼檔案實作完成（LSP clean, compile clean）
2. Git commits:
   - `46fe2b2` — 完整實作（42 files, 8,662 lines）
   - `ff06a8b` — DOCX 規劃文件修正
   - 後續修正尚未 commit（照片標註系統重建、HEIC修正、logging、地質服務等）
3. **94/94 測試全數通過**（8 test files, pytest 4.83s）
4. LRS CSV 資料已載入（29,384 markers, 101 roads）
5. DOCX 規劃文件已產生並驗證可開啟

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

### ✅ Rich Menu — API 已建立（圖片為 placeholder）
- Manager menu: `richmenu-9b3567d26abfa6ad073607a6256eaff6`
- User menu: `richmenu-1f1b24deb3c2b1c24db1fcd38843a603`

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

**`app/data/photo_tags.json` (1864 lines) — ✅ 完成且驗證**
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

**`app/services/flex_builders.py` (1178 lines) — ✅ 完成且驗證**
- 新增常數：`JUDGMENT_COLOR = "#E8A317"`, `EXCLUSION_COLOR = "#CCCCCC"`
- 新增模組級 `_resolve_photo_tags()` 輔助函式
- 更新 `get_photo_tag_definition()` 接受 `disaster_type` 參數
- 新增 8 個 `@staticmethod` 方法：
  - `photo_set_entry_card()` — 照片集入口卡片
  - `tag_single_select_quick_reply()` — 單選 Quick Reply
  - `tag_multi_select_flex()` — 多選 Flex Bubble（雙欄佈局）
  - `photo_complete_card()` — 照片完成卡片（補拍/判斷/跳過）
  - `differential_tag_flex()` — 差異標記 Flex
  - `photo_set_summary_flex()` — 照片集完成摘要
  - `annotation_progress_carousel()` — 標註進度 Carousel
  - `judgment_category_flex()` — 🧠 判斷類別 Flex
- LSP: 僅 2 個 hints（未使用參數，保留給未來用途），無 errors

**`app/services/line_flow.py` (1447 lines) — ✅ 完成且驗證**
- 新增 `_resolve_photo_def()` — 從層級 photo_tags.json 解析定義（common → 災害類型 → 回退掃描）
- 新增 `_photo_type_prompt()` — 各照片類型的靜態提示文字
- 修正 `_current_tag_categories()` — 使用 `photo_tags` 而非舊的 `tag_categories`
- 20 處呼叫點全部使用新方法
- 0 處舊式 `self._photo_tags.get(photo_type)` 平面存取
- 0 處 `description` 欄位存取
- LSP: 0 errors, 0 warnings

---

## 🔶 當前狀態：實作完成，待 git commit 後討論統計顯示功能

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
- 取消流程草稿資料：保留不刪除
- 過程有問題的LOG都要記錄
- 選項儘量用點選方式，內容要夠豐富也要夠方便
- 要輔助第二階段AI辨識
- 要強調一張照片有哪些狀況才選
- 要有補照片再填寫的機制

### 六個工務段
| 工務段 | ID | 管轄路線 |
|--------|-----|---------|
| 景美工務段 | jingmei | 台2(部分), 台3, 台5, 台9, 台9甲, 台9乙 |
| 中和工務段 | zhonghe | 台3(都會), 台9(都會), 台15(部分), 台64, 台65 |
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

---

## 檔案結構（更新後）

```
app/
├── main.py (~140)
├── core/: config.py(97), logging_config.py(45), security.py(67)
├── models/: case.py(201), evidence.py(183), user.py(83), line_state.py(167), vendor.py(101)
├── routers/: line_webhook.py(141), cases.py(86), vendor_api.py(193), health.py(16)
├── services/: audit_logger.py(111), user_store.py(214), case_store.py(267),
│   evidence_store.py(313), case_manager.py(298), lrs_service.py(498),
│   image_processor.py(431), pdf_parser.py(340), line_session.py(97),
│   flex_builders.py(1178), line_flow.py(1447), notification_service.py(164),
│   geology_service.py(428)
├── data/: districts.json, photo_tags.json(1864), damage_modes.json, site_survey.json, lrs_milepost.csv
webgis/index.html (779)
tests/: 8 files, 94 tests
generate_planning_doc.py (964)
```

---

## 待完成工作（優先順序）

### 🔴 立即
1. **Git commit 所有變更**（photo_tags.json, evidence.py, line_state.py, flex_builders.py, line_flow.py）

### 🟡 接續
2. **討論統計顯示功能**（使用者明確要求：「再來討論統計顯示功能部分」）
3. 實作統計顯示功能

### 🟢 之後
4. 整合 NLSC 國土測繪圖資至 WebGIS
5. 完整端對端流程測試（照片標註新 UI 流程）
6. Rich Menu 替換正式圖片（使用者稍後提供）
7. 安全性：測試完成後輪換憑證

---

## 已完成的 Agent Sessions

| Agent | Description | Session ID |
|-------|-------------|------------|
| Junior | 重構 photo_tags.json — 完整三層 annotation schema (1864 lines) | ses_358b99eaaffeiU3EhFk6lF7zDa |
| Junior | Rework line_flow.py — hierarchical photo_tags access | ses_358a13052ffeSbj6zRTu8tAaAq |
| Junior | GeologyService integration | ses_35abe5694ffe98T2bXtMgbbt0Q |
| Junior | 照片引導上傳流程重設計 | ses_35b377950ffei9Z9nQWe0oiK2s |
| librarian | LINE API 研究 | ses_35c726e69ffejBiUcs5QOIG75O |
| librarian | PDF parsing 研究 | ses_35c725027ffem1zb3XAHiE7jzC |
| librarian | FastAPI patterns | ses_35c7230c3ffeKq7kuwWJa0H7dB |
| explore | 座標查找分析 | ses_35c720183ffeYL8sIhyn1I8KGr |
| oracle | 架構設計 | ses_35c6b2773ffe3mEaS2UJ57AJbw |
| librarian | 災害照片標註分類 | ses_35c090158ffeyMwQCZPw25xY5 |
| librarian | LINE Flex 多選模式 | ses_35c08c787ffezULlXYEAwfkhq0 |

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
- "聯絡資訊應該是不用因為是給公務人員內部使用的"
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
