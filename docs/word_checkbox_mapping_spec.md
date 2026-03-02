# Word 勾稽邏輯規格（照片標註版）

更新日期：2026-03-02

## 範圍與原則

- 本規格適用 `WordGenerator` 輸出之 Table 1（破壞模式與可能致災原因分析與檢討）與 Table 2（工址環境調查及危害辨識）。
- 勾稽來源以照片標註為主（`EvidenceManifest -> annotations.tags`）。
- EXIF 不作為勾選依據。
- Table 1 採用「先勾破壞模式，再勾致災原因（gate）」原則。
- 未命中對應標註時不自動勾選。

---

## Table 1：破壞模式與可能致災原因分析與檢討

### A. 道路邊坡類（`damage_mode_category=road_slope`）

#### 破壞模式
- 道路上方邊坡滑動：`P2.slope_location` 包含 `cut_slope`
- 道路下方邊坡滑動：`P2.slope_location` 包含 `fill_slope`
- 整體性破壞：`P2.slope_location` 包含 `both`

#### 致災原因（需先命中上述任一破壞模式）
- 土質鬆軟：`P7.geology_risk` 包含 `soft_soil`
- 坡度過大：`P4.slope_gradient` 包含 `moderate|steep|very_steep|cliff`，或 `P7.geology_risk` 包含 `steep_slope`

### B. 護岸/擋土牆類（`damage_mode_category=revetment_retaining`）

#### 破壞模式
- 護岸、擋土牆崩坍：`P2.visible_damage` 命中 `collapse|displacement|tilt|scour|undermining|surface_erosion`
- 河道內結構物破壞：`P2.structure_location` 命中 `riverside` 且有可見損壞
- 道路上方邊坡擋土牆破壞：`P2.structure_location` 命中 `road_upslope` 且有可見損壞
- 道路下方邊坡擋土牆破壞：`P2.structure_location` 命中 `road_downslope` 且有可見損壞

#### 致災原因（需先命中本群任一破壞模式）
- 水路流速過大，使基腳掏空或沖毀。：`P2.visible_damage` 命中 `undermining|foundation_exposed|scour`
- 水路流速過大，護岸面被異物撞擊損毀。：`P2.visible_damage` 命中 `crack|spalling|displacement|tilt` 且 `P4.water_body` 命中 `river_high|river_turbid|bank_erosion`
- 水路流速過大，使護岸面被淘刷。：`P2.visible_damage` 命中 `scour|surface_erosion`
- 坡面無排水設施(自然邊坡)：`P4.drainage` 命中 `no_drainage` 或 `P4/P2.water_signs` 命中 `dry`
- 設計不足：`P4.disaster_cause` 命中 `design_inadequate`
- 坡面排水不良：`P4.disaster_cause` 命中 `poor_drainage|slope_poor_drain`
- 道路排水不良：`P4.disaster_cause` 命中 `road_poor_drain|subgrade_drain_poor`
- 存在介面：`P7.geology_risk` 命中 `interface_exist`
- 水路流量過大造成溢流，使臨水構造物損壞。：`P4.water_body` 命中 `overtopping|river_high`
- 路基缺口因道路設計排水不良：`P1.site_risks` 命中 `subgrade_gap` 且 `P4.drainage` 命中 `blocked|severe_blocked`
- 排水溝、集水井未定期清理所致：`P4.drainage` 命中 `blocked|severe_blocked|catch_basin`

### C. 橋梁類（`damage_mode_category=bridge`）

#### 破壞模式
- 整跨落橋：`P2.damaged_component` 命中 `deck|girder|pier`（至少兩者）且 `P2.visible_damage` 命中 `collapse|displacement` 且 `P2.severity` 命中 `critical`
- 橋墩基礎裸露：`P2.damaged_component` 命中 `pier|foundation` 且 `P2.visible_damage` 命中 `foundation_exposed` 或 `P2.foundation_exposure` 命中 `depth_100_200|depth_gt_200|full_exposure`
- 橋墩撞擊混凝土表面破裂：`P2.damaged_component` 命中 `pier` 且 `P2.visible_damage` 命中 `impact_damage` 且 `crack|spalling`
- 橋面傾斜：`P2.damaged_component` 命中 `deck` 且 `P2.visible_damage` 命中 `tilt|displacement`
- 橋台翼牆破壞：`P2.damaged_component` 命中 `abutment|wing_wall` 且有可見損壞
- 橋梁大梁撞傷混凝土破裂鋼筋裸露：`P2.damaged_component` 命中 `girder` 且 `P2.visible_damage` 命中 `impact_damage` 且 `crack|spalling|rebar_exposed`
- 橋梁大梁撞斷混凝土破裂鋼筋裸露：`P2.damaged_component` 命中 `girder` 且 `P2.visible_damage` 命中 `impact_damage` 且 `collapse|displacement`
- 橋面護欄破裂：`P2.damaged_component` 命中 `railing|parapet` 且 `P2.visible_damage` 命中 `crack|spalling`
- 橋面路燈損壞排水管阻塞：`P4.deck_overall` 命中 `drainage_blocked` 且 `P4.river_obstacles` 命中 `debris_pile|waste`

#### 致災原因（需先命中本群任一破壞模式）
- 洪水沖刷，橋墩傾斜：`P4.disaster_cause` 命中 `flood_scour` 或 `P4.river_condition` 命中 `flood`，且橋墩/傾斜跡象成立
- 洪水沖刷掏空：`P4.disaster_cause` 命中 `flood_scour` 或 `P4.pier_scour` 命中 `undermined` 或 `P2.visible_damage` 命中 `scour`
- 洪水夾雜石塊撞擊：`P4.disaster_cause` 命中 `debris_impact` 或 `P2.visible_damage` 命中 `impact_damage`
- 基礎部份掏空，橋墩位移：`P4.disaster_cause` 命中 `foundation_settlement` 或（`P4.pier_scour=undermined` 且 `P2.visible_damage=displacement`）
- 洪水沖刷基礎橋台背牆位移：`P4.disaster_cause=flood_scour` 且橋台/翼牆背牆損壞或位移跡象成立
- 翼牆與橋台旁防洪牆共構基礎遭洪水沖刷破壞：`P4.disaster_cause=flood_scour` 且 `P2.damaged_component` 命中 `wing_wall|abutment`
- 洪水夾雜石塊，樹幹撞擊大梁：`P4.disaster_cause=debris_impact` 且 `P2.damaged_component=girder` 且 `P2.visible_damage=impact_damage`
- 洪水淹沒橋面夾雜石塊撞擊：`P4.river_condition` 命中 `flood|high_water` 且 `P2.damaged_component=deck` 且 `P2.visible_damage=impact_damage`
- 洪水夾雜樹枝、垃圾阻塞，路燈被颱風吹斷：`P4.river_obstacles` 命中 `debris_pile|waste` 且 `P4.deck_overall=drainage_blocked`

### D. Table 1 保留人工項目

- 其他(請敘述)
- 致災原因需另辦理整體安全評估

---

## Table 2：工址環境調查及危害辨識

### 已自動勾稽
- Row1 ~ Row5：依 `P1.site_risks` 與 `P2.visible_damage` 勾選現地狀況與工址風險。

### 保留手動
- Row6（天氣炎熱 -> 熱危害）
- Row7（冬天易降雪 -> 低溫危害）

---

## 實作檔案

- `app/services/word_generator.py`
- `tests/test_word_generator.py`

## 驗證狀態

- `pytest tests/test_word_generator.py tests/test_line_flow.py` 通過（116 passed）。
