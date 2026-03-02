# Word 勾選欄位照片標註勾稽對照表（草案）

此版本僅使用照片標註 `annotations.tags` 作為勾稽來源，不使用 EXIF。

## 1) 破壞模式與可能致災原因分析與檢討（Table 1）

| Word 欄位 | 勾選條件（照片標註） | 來源 | 備註 |
|---|---|---|---|
| 道路上方邊坡滑動 | `slope_location` 含 `cut_slope` 或 `both` | P2 / slope_location | OR 規則 |
| 道路下方邊坡滑動 | `slope_location` 含 `fill_slope` 或 `both` | P2 / slope_location | OR 規則 |
| 整體性破壞 | `slope_location` 含 `both` | P2 / slope_location | |
| 土質鬆軟 | `geology_risk` 含 `soft_soil` | P7 / geology_risk | |
| 坡度過大 | `slope_gradient` 含 `moderate/steep/very_steep/cliff`，或 `geology_risk` 含 `steep_slope` | P4 / slope_gradient、P7 / geology_risk | OR 規則 |

## 2) 工址環境調查及危害辨識（Table 2）

| Row | Word 勾選項 | 勾選條件（照片標註） | 來源 |
|---|---|---|---|
| 1 | 物體倒塌/崩塌 | `site_risks` 含 `upslope_rockfall` | P1 / site_risks |
| 1 | 物體飛落危害 | `visible_damage` 含 `hanging_rock` 或 `isolated_rock_pile` | P2 / visible_damage |
| 2 | 物體倒塌/崩塌 | `visible_damage` 含 `debris_avalanche/rock_mass_slide/debris_flow`，或 `site_risks` 含 `collapse_sign/debris_flow_sign` | P2 / visible_damage、P1 / site_risks |
| 2 | 物體飛落危害 | Row2 已命中且 `visible_damage` 含 `slope_debris_deposit` | P2 / visible_damage |
| 3 | 路基缺口 | `site_risks` 含 `subgrade_gap` | P1 / site_risks |
| 3 | 路基下陷 | `site_risks` 含 `subsidence` | P1 / site_risks |
| 3 | 墜落、滾落危害 | Row3 任一命中（路基缺口/下陷） | 由 Row3 觸發 |
| 3 | 衝撞、被撞危害 | Row3 任一命中（路基缺口/下陷） | 由 Row3 觸發 |
| 4 | 結構物鋼筋裸露 | `site_risks` 含 `rebar_exposed` | P1 / site_risks |
| 4 | 危木倒塌 | `site_risks` 含 `hazard_tree` | P1 / site_risks |
| 4 | 護欄損壞 | `site_risks` 含 `guardrail_damage` | P1 / site_risks |
| 4 | 路面坑洞 | `site_risks` 含 `pothole` | P1 / site_risks |
| 4 | 路側電桿倒塌 | `site_risks` 含 `utility_pole_tilt` | P1 / site_risks |
| 5 | 臨河作業 | `site_risks` 含 `riverside_work` | P1 / site_risks |
| 5 | 曲流攻擊面 | `site_risks` 含 `meander_attack` | P1 / site_risks |
| 5 | 墜落危害 | Row5 任一命中（臨河作業/曲流攻擊面） | 由 Row5 觸發 |
| 5 | 溺斃危害 | Row5 任一命中（臨河作業/曲流攻擊面） | 由 Row5 觸發 |

## 3) 勾稽邏輯草案（供確認）

1. 先按 `photo_type + category + tag_id` 聚合標註（多張照片採聯集）。
2. 依上表逐條判斷，命中即勾選（OR）。
3. 同列多項可同時勾（如 Row4、Row5）。
4. 未命中不自動猜測、不補 EXIF。
5. 勾選來源僅限照片標註；若要納入其他來源（例如 site_survey）需另外加開關。

## 4) 待你確認的決策點

1. Table 2 的 Row6/Row7（天候、降雪）是否也要改成照片標註自動勾選。
2. Table 1 是否要擴充更多「致災原因」項目（例如排水不良、地質弱面）對應更多 tag。
3. 是否要在 Word 末段加「勾稽來源摘要」（列出命中的 `photo_type/tag_id`）做稽核追溯。
