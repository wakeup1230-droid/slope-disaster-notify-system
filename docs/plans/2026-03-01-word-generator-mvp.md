# Word Generator MVP Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build `app/services/word_generator.py` that reads the Word template and fills it with Case model data, producing a complete 公路災害工程內容概述表.

**Architecture:** Read-only service that takes a Case + EvidenceManifest + cases_dir and produces a filled Word document (bytes). Uses python-docx to manipulate paragraphs and tables in the template. Does NOT modify any stored files—returns new bytes.

**Tech Stack:** python-docx, Pillow (for map image), pathlib, io.BytesIO

---

## Word Template Structure Reference

Template: `Input/公路災害工程內容概述表_20250808152309.docx`

### Paragraphs (key ones that need data)

| Para | Current Text | Data Source | Fill Strategy |
|------|-------------|-------------|---------------|
| P1 | `     年度  ` | `case.reporting_year` | Replace runs: insert year before "年度" |
| P2 | `一般災害  專案災害 () 災後 搶修 復建 經費明細表` | `case.disaster_type` + `case.processing_type` | Add checkbox marks ☑/☐ before selected options |
| P4 | `工程名稱：` | `case.project_name` | Append text after colon |
| P5 | `災害發生日期：    年    月      日` | `case.disaster_date` | Parse date, fill year/month/day in blank runs |
| P6 | `地點：    鄉（鎮、市）  村（里）` | `case.town_name` + `case.village_name` | Fill blank runs before 鄉/村 labels |
| P7 | `（所在或鄰近之河溪、道路或顯著目標）` | `case.nearby_landmark` | Replace blank runs with value |
| P8 | `是否屬重複致災地點：否　　是　     年興建` | `case.repeat_disaster` + `case.repeat_disaster_year` | Mark ☑ on 是/否, fill year |
| P12 | `1.災損說明(如：...)。` | `case.description` | Append new paragraph after P12 with description text |
| P14 | `2.原設計保護型式及災害前狀況說明(...)` | `case.original_protection` | Append new paragraph after P14 |
| P24 | `（三）破壞模式與可能致災原因分析與檢討` | `case.analysis_review` | Append new paragraph after P24 (or P25) |
| P27 | `1.工程內容、數量及單價：` | `case.cost_breakdown` | Append cost table after P27 |
| P29 | `2.初估總經費(仟元)：` | `case.estimated_cost` | Modify P30: insert total before "仟元" |
| P34 | `4.其他補充事項：` | `case.other_supplement` | Append text after P34 |
| P69 | `提報機關：` | `case.reporting_agency` | Append text after colon |

### Tables

| Table | Size | Purpose | Fill Strategy |
|-------|------|---------|---------------|
| Table 0 | 2x1 | 衛星定位點 (coordinates) | Fill X/Y blank runs in row 1 |
| Table 1 | 29x4 | 破壞模式/致災原因 (read-only reference) | **NO CHANGES** |
| Table 2 | 9x4 | 工址環境危害辨識 (site survey/hazard) | Mark checked items with ✓, fill notes in 備註 column |
| Table 3 | 2x2 | 承辦人/段長 signatures | Fill 承辦人 name |

### Section Logic (水土保持 P37-P43, 國家公園 P45-P53)

**水土保持 (soil_conservation):**
- `"需要已核定"` → P38 mark "是" with ☑
- `"需要未核定"` → P38 mark "是" with ☑ (same as above, different status)
- `"不需要"` → P39 mark "否" with ☑, then check which sub-reason applies:
  - Sub-items P40-P43 need secondary logic (for now, check P40 as default for disaster repair)

**國家公園 (national_park):**
- Non-empty string → P46 mark "是" with ☑
  - P47(1) 國家公園法申請: mark "是" (default for MVP)
  - P50(2) 生態檢核: mark "是" (default for MVP)
- Empty string → P53 mark "否" with ☑

---

## Task 1: Core WordGenerator class + paragraph fill (B1)

**Files:**
- Create: `app/services/word_generator.py`

**Step 1: Create the service module with core structure**

```python
"""
Word document generator service.

Reads the 公路災害工程內容概述表 template and fills it with Case data,
producing a complete Word document as bytes.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from docx import Document
from docx.shared import Pt, Cm, Emu
from docx.oxml.ns import qn

from app.core.logging_config import get_logger
from app.models.case import Case, CostBreakdownItem
from app.models.evidence import EvidenceManifest, EvidenceMetadata

logger = get_logger(__name__)

# Default template path (relative to project root)
DEFAULT_TEMPLATE = Path("Input/公路災害工程內容概述表_20250808160309.docx")


class WordGenerator:
    """
    Generates filled Word documents from Case data.
    
    Usage:
        gen = WordGenerator(template_path, cases_dir)
        doc_bytes = gen.generate(case, manifest)
    """

    def __init__(
        self,
        template_path: Path,
        cases_dir: Path,
    ) -> None:
        self._template_path = template_path
        self._cases_dir = cases_dir
        if not self._template_path.exists():
            raise FileNotFoundError(f"Template not found: {self._template_path}")

    def generate(self, case: Case, manifest: Optional[EvidenceManifest] = None) -> bytes:
        """Generate a filled Word document and return as bytes."""
        doc = Document(str(self._template_path))
        
        self._fill_header(doc, case)          # P0-P2: title, year, disaster/processing type
        self._fill_basic_info(doc, case)       # P4-P8: name, date, location, repeat
        self._fill_coordinates(doc, case)      # Table 0: X/Y coordinates
        self._fill_description(doc, case)      # P10-P15: description + original protection
        self._fill_location_map(doc, case)     # P16: location map image
        self._fill_photos(doc, case, manifest) # P21: evidence photos
        self._fill_analysis(doc, case)         # P24: analysis & review
        self._fill_cost(doc, case)             # P27-P30: cost breakdown + total
        self._fill_other_supplement(doc, case) # P34: other supplement
        self._fill_soil_conservation(doc, case)    # P37-P44: soil conservation
        self._fill_national_park(doc, case)        # P45-P53: national park
        self._fill_hazard_table(doc, case)         # Table 2: site survey/hazard
        self._fill_signatures(doc, case)           # Table 3 + P69: signatures + agency
        
        # Serialize to bytes
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()
```

**Step 2: Implement helper methods**

Key helper: `_set_run_font()` to match existing font (微軟正黑體, 14pt = 177800 EMU)

```python
    @staticmethod
    def _set_run_font(run, font_name: str = "微軟正黑體", size_pt: int = 14) -> None:
        """Set font for a run to match template style."""
        run.font.name = font_name
        run.font.size = Pt(size_pt)
        rpr = run._element.get_or_add_rPr()
        rFonts = rpr.find(qn("w:rFonts"))
        if rFonts is None:
            rFonts = OxmlElement("w:rFonts")
            rpr.insert(0, rFonts)
        rFonts.set(qn("w:eastAsia"), font_name)
    
    @staticmethod
    def _append_text_to_paragraph(paragraph, text: str, font_name: str = "微軟正黑體", size_pt: int = 14) -> None:
        """Append text as a new run at end of paragraph."""
        run = paragraph.add_run(text)
        WordGenerator._set_run_font(run, font_name, size_pt)
    
    @staticmethod
    def _insert_paragraph_after(paragraph, text: str, font_name: str = "微軟正黑體", size_pt: int = 14):
        """Insert a new paragraph after the given paragraph."""
        from docx.oxml import OxmlElement
        new_p = OxmlElement("w:p")
        paragraph._element.addnext(new_p)
        # Create a run inside the new paragraph
        new_r = OxmlElement("w:r")
        new_p.append(new_r)
        new_t = OxmlElement("w:t")
        new_t.text = text
        new_t.set(qn("xml:space"), "preserve")
        new_r.append(new_t)
        # Apply font
        rpr = OxmlElement("w:rPr")
        rFonts = OxmlElement("w:rFonts")
        rFonts.set(qn("w:ascii"), font_name)
        rFonts.set(qn("w:eastAsia"), font_name)
        rFonts.set(qn("w:hAnsi"), font_name)
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), str(size_pt * 2))  # half-points
        szCs = OxmlElement("w:szCs")
        szCs.set(qn("w:val"), str(size_pt * 2))
        rpr.append(rFonts)
        rpr.append(sz)
        rpr.append(szCs)
        new_r.insert(0, rpr)
        return new_p
```

**Step 3: Implement `_fill_header` (P0-P2)**

```python
    def _fill_header(self, doc: Document, case: Case) -> None:
        """Fill P1 (year) and P2 (disaster type / processing type)."""
        # P1: 年度 — runs: ['     ', '年度  ']
        p1 = doc.paragraphs[1]
        if case.reporting_year and len(p1.runs) >= 1:
            p1.runs[0].text = f"  {case.reporting_year}  "
        
        # P2: 一般/專案 + 搶修/復建
        # runs: ['一般災害  ', '專案災害 (', ') 災後 ', '搶修 ', '復建 經費明細表']
        p2 = doc.paragraphs[2]
        if len(p2.runs) >= 5:
            if case.disaster_type == "一般":
                p2.runs[0].text = "☑一般災害  "
                p2.runs[1].text = "☐專案災害 ("
            elif case.disaster_type == "專案":
                p2.runs[0].text = "☐一般災害  "
                p2.runs[1].text = "☑專案災害 ("
            
            if case.processing_type == "搶修":
                p2.runs[3].text = "☑搶修 "
                p2.runs[4].text = "☐復建 經費明細表"
            elif case.processing_type == "復建":
                p2.runs[3].text = "☐搶修 "
                p2.runs[4].text = "☑復建 經費明細表"
```

**Step 4: Implement `_fill_basic_info` (P4-P8)**

```python
    def _fill_basic_info(self, doc: Document, case: Case) -> None:
        """Fill P4 (project name), P5 (date), P6 (location), P7 (landmark), P8 (repeat disaster)."""
        # P4: 工程名稱：
        p4 = doc.paragraphs[4]
        if case.project_name:
            p4.runs[0].text = f"工程名稱：{case.project_name}"
        
        # P5: 災害發生日期 — parse date and fill year/month/day
        p5 = doc.paragraphs[5]
        if case.disaster_date:
            self._fill_date(p5, case.disaster_date)
        
        # P6: 地點：    鄉（鎮、市）  村（里）
        # runs: ['地點：', '  ', '  ', '鄉（鎮、市）', '  ', '村（里）']
        p6 = doc.paragraphs[6]
        if len(p6.runs) >= 6:
            if case.town_name:
                p6.runs[1].text = case.town_name
                p6.runs[2].text = ""
            if case.village_name:
                p6.runs[4].text = case.village_name
        
        # P7: （所在或鄰近之河溪、道路或顯著目標）
        # runs: [' ', '  ', '（所在或鄰近...）']
        p7 = doc.paragraphs[7]
        if case.nearby_landmark and len(p7.runs) >= 1:
            p7.runs[0].text = f"  {case.nearby_landmark}"
            if len(p7.runs) > 1:
                p7.runs[1].text = ""
            if len(p7.runs) > 2:
                p7.runs[2].text = ""
        
        # P8: 是否屬重複致災地點：否　　是　     年興建
        # runs: ['是否屬重複致災地點：', '否　　', '是　', '     ', '年興建']
        p8 = doc.paragraphs[8]
        if len(p8.runs) >= 5:
            if case.repeat_disaster == "否":
                p8.runs[1].text = "☑否　　"
                p8.runs[2].text = "☐是　"
            elif case.repeat_disaster == "是":
                p8.runs[1].text = "☐否　　"
                p8.runs[2].text = "☑是　"
                if case.repeat_disaster_year:
                    p8.runs[3].text = f" {case.repeat_disaster_year} "
    
    def _fill_date(self, paragraph, date_str: str) -> None:
        """Fill date paragraph. Supports YYYY-MM-DD or 民國年月日 formats."""
        year, month, day = "", "", ""
        if "-" in date_str:
            # ISO format: 2024-08-15
            parts = date_str.split("-")
            if len(parts) == 3:
                try:
                    ad_year = int(parts[0])
                    year = str(ad_year - 1911)  # Convert to 民國年
                    month = parts[1].lstrip("0") or parts[1]
                    day = parts[2].lstrip("0") or parts[2]
                except ValueError:
                    pass
        else:
            # Try to extract digits for 民國 format
            # e.g., "113年8月15日"
            import re
            m = re.match(r"(\d+)\s*年\s*(\d+)\s*月\s*(\d+)\s*日", date_str)
            if m:
                year, month, day = m.group(1), m.group(2), m.group(3)
        
        # P5 runs: ['災害發生日期：', '  ', '  ', '年', '  ', ' ', ' 月 ', '  ', '  ', ' 日']
        runs = paragraph.runs
        if len(runs) >= 10 and year:
            runs[1].text = year
            runs[2].text = ""
            runs[4].text = month
            runs[5].text = ""
            runs[7].text = day
            runs[8].text = ""
```

**Step 5: Implement `_fill_coordinates` (Table 0)**

```python
    def _fill_coordinates(self, doc: Document, case: Case) -> None:
        """Fill Table 0 with X/Y coordinates."""
        if not case.primary_coordinate:
            return
        table = doc.tables[0]
        cell = table.rows[1].cells[0]
        # runs: ['衛星定位點：', '（Χ座標', '  ', '  ', 'Ｙ座標', '  ', '  ', '）']
        runs = cell.paragraphs[0].runs
        if len(runs) >= 7:
            lon_str = f"{case.primary_coordinate.lon:.6f}"
            lat_str = f"{case.primary_coordinate.lat:.6f}"
            runs[2].text = lon_str
            runs[3].text = " "
            runs[5].text = lat_str
            runs[6].text = " "
```

**Step 6: Implement `_fill_description` (P10-P15)**

```python
    def _fill_description(self, doc: Document, case: Case) -> None:
        """Fill description (after P12) and original protection (after P14)."""
        # Insert description after P12
        if case.description:
            self._insert_paragraph_after(doc.paragraphs[12], case.description)
        
        # Insert original protection after P14  
        if case.original_protection:
            # P14 index may shift if we inserted above, so find by text
            for i, p in enumerate(doc.paragraphs):
                if "原設計保護型式" in p.text:
                    self._insert_paragraph_after(p, case.original_protection)
                    break
```

**Step 7: Implement remaining fill methods as stubs (to be expanded in later tasks)**

```python
    def _fill_location_map(self, doc: Document, case: Case) -> None:
        """Fill P16 location map image. (Task 3)"""
        pass  # Implemented in Task 3

    def _fill_photos(self, doc: Document, case: Case, manifest: Optional[EvidenceManifest]) -> None:
        """Fill P21 evidence photos. (Task 2)"""
        pass  # Implemented in Task 2

    def _fill_analysis(self, doc: Document, case: Case) -> None:
        """Fill P24 analysis & review."""
        if not case.analysis_review:
            return
        for p in doc.paragraphs:
            if "破壞模式與可能致災原因分析與檢討" in p.text:
                self._insert_paragraph_after(p, case.analysis_review)
                break

    def _fill_cost(self, doc: Document, case: Case) -> None:
        """Fill P27-P30 cost breakdown + total."""
        # Find P27 (工程內容、數量及單價) and insert cost table after it
        if case.cost_breakdown:
            for p in doc.paragraphs:
                if "工程內容、數量及單價" in p.text:
                    self._insert_cost_table(doc, p, case.cost_breakdown)
                    break
        
        # Fill P30 total: runs ['合計', '仟元'] → insert total between
        if case.estimated_cost is not None:
            for p in doc.paragraphs:
                if p.text.strip().startswith("合計") and "仟元" in p.text:
                    if len(p.runs) >= 2:
                        total_str = f"{case.estimated_cost:,.0f}"
                        p.runs[0].text = f"合計 {total_str} "
                    break

    def _insert_cost_table(self, doc: Document, after_paragraph, items: list[CostBreakdownItem]) -> None:
        """Insert a cost breakdown table after the given paragraph."""
        from docx.oxml import OxmlElement
        
        # Build table data
        rows_data = []
        for item in items:
            if item.amount and item.amount > 0:
                rows_data.append([
                    item.item_name,
                    item.unit,
                    f"{item.unit_price:,.0f}" if item.unit_price else "-",
                    f"{item.quantity:,.0f}" if item.quantity else "-",
                    f"{item.amount:,.0f}",
                ])
        
        if not rows_data:
            return
        
        # Create table element
        tbl = OxmlElement("w:tbl")
        # Table properties
        tblPr = OxmlElement("w:tblPr")
        tblStyle = OxmlElement("w:tblStyle")
        tblStyle.set(qn("w:val"), "TableGrid")
        tblPr.append(tblStyle)
        tblW = OxmlElement("w:tblW")
        tblW.set(qn("w:w"), "0")
        tblW.set(qn("w:type"), "auto")
        tblPr.append(tblW)
        tbl.append(tblPr)
        
        # Header row
        headers = ["項目", "單位", "單價", "數量", "金額(仟元)"]
        self._add_table_row(tbl, headers, bold=True)
        
        # Data rows
        for row_data in rows_data:
            self._add_table_row(tbl, row_data)
        
        # Insert after paragraph
        after_paragraph._element.addnext(tbl)
    
    @staticmethod
    def _add_table_row(tbl_element, cells: list[str], bold: bool = False) -> None:
        """Add a row to a table XML element."""
        from docx.oxml import OxmlElement
        tr = OxmlElement("w:tr")
        for cell_text in cells:
            tc = OxmlElement("w:tc")
            p = OxmlElement("w:p")
            r = OxmlElement("w:r")
            # Font
            rpr = OxmlElement("w:rPr")
            rFonts = OxmlElement("w:rFonts")
            rFonts.set(qn("w:ascii"), "微軟正黑體")
            rFonts.set(qn("w:eastAsia"), "微軟正黑體")
            rFonts.set(qn("w:hAnsi"), "微軟正黑體")
            sz = OxmlElement("w:sz")
            sz.set(qn("w:val"), "22")  # 11pt
            szCs = OxmlElement("w:szCs")
            szCs.set(qn("w:val"), "22")
            rpr.append(rFonts)
            rpr.append(sz)
            rpr.append(szCs)
            if bold:
                b = OxmlElement("w:b")
                rpr.append(b)
            r.insert(0, rpr)
            t = OxmlElement("w:t")
            t.text = cell_text
            t.set(qn("xml:space"), "preserve")
            r.append(t)
            p.append(r)
            tc.append(p)
            tr.append(tc)
        tbl_element.append(tr)

    def _fill_other_supplement(self, doc: Document, case: Case) -> None:
        """Fill P34 其他補充事項."""
        if not case.other_supplement:
            return
        for p in doc.paragraphs:
            if "其他補充事項" in p.text:
                self._insert_paragraph_after(p, case.other_supplement)
                break
```

**Step 8: Implement `_fill_soil_conservation` (P37-P44)**

```python
    def _fill_soil_conservation(self, doc: Document, case: Case) -> None:
        """Fill soil conservation section P37-P44."""
        if not case.soil_conservation:
            return
        
        # Find P38 (是) and P39 (否) by text
        for p in doc.paragraphs:
            text = p.text.strip()
            # P38: "1、是。" → runs: ['1、', '是。']
            if text == "1、是。" and "水土保持" not in text:
                if case.soil_conservation.startswith("需要"):
                    if len(p.runs) >= 2:
                        p.runs[1].text = "☑是。"
                else:
                    if len(p.runs) >= 2:
                        p.runs[1].text = "☐是。"
            
            # P39: "2、否，..." → runs: ['2、', '否，...']
            if text.startswith("2、否，請依下列檢核事項勾選"):
                if case.soil_conservation == "不需要":
                    if len(p.runs) >= 2:
                        p.runs[1].text = "☑否，請依下列檢核事項勾選："
                    # Default: check P40 (必要之緊急搶通) for disaster repair
                    # Find the next paragraph with (1) and mark it
                else:
                    if len(p.runs) >= 2:
                        p.runs[1].text = "☐否，請依下列檢核事項勾選："
```

**Step 9: Implement `_fill_national_park` (P45-P53)**

```python
    def _fill_national_park(self, doc: Document, case: Case) -> None:
        """Fill national park section P45-P53."""
        in_park = bool(case.national_park)
        
        for p in doc.paragraphs:
            text = p.text.strip()
            
            # P46: "1、是，請依下列檢核事項勾選："
            if text.startswith("1、是，請依下列檢核事項勾選"):
                if len(p.runs) >= 2:
                    p.runs[1].text = ("☑" if in_park else "☐") + "是，請依下列檢核事項勾選："
            
            # P48: 是 (國家公園法申請) and P49: 否
            # P51: 是 (生態檢核) and P52: 否
            # These are simple "是"/"否" paragraphs under sub-items
            # For MVP: if in_park, mark both P48 and P51 as ☑是
            
            # P53: "2、否。"
            if text == "2、否。":
                if len(p.runs) >= 2:
                    p.runs[1].text = ("☑" if not in_park else "☐") + "否。"
```

**Step 10: Implement `_fill_hazard_table` (Table 2) and `_fill_signatures` (Table 3 + P69)**

```python
    def _fill_hazard_table(self, doc: Document, case: Case) -> None:
        """
        Fill Table 2 (工址環境危害辨識表) from site_survey data.
        
        Table 2 layout (9 rows x 4 cols):
        Row 0: Headers (工址位置, 現地狀況, 工址風險, 備註)
        Row 1-2: 上邊坡
        Row 3: 下邊坡
        Row 4: 結構物、路側及路面
        Row 5: 橋梁、河道
        Row 6-7: 其他
        Row 8: (empty footer)
        
        The template already has default items filled.
        We mark checked items with ✓ in the 備註 column.
        """
        if not case.site_survey:
            return
        
        table = doc.tables[2]
        
        # Build lookup: item_id → checked status
        checked_items = {item.item_id: item for item in case.site_survey if item.checked}
        
        # Mapping: table row index → list of item_ids that correspond to that row
        ROW_ITEM_MAP = {
            1: ["upslope_rockfall"],
            2: ["upslope_collapse"],
            3: ["downslope_subgrade_gap", "downslope_settlement"],
            4: ["structure_rebar_exposed", "structure_dangerous_tree", "structure_guardrail", "structure_pothole", "structure_utility_pole"],
            5: ["bridge_river_adjacent", "bridge_river_meander_erosion"],
            6: ["other_weather"],
            7: ["other_snow"],
        }
        
        for row_idx, item_ids in ROW_ITEM_MAP.items():
            any_checked = any(iid in checked_items for iid in item_ids)
            if any_checked:
                # Write ✓ in 備註 column (col 3)
                cell = table.rows[row_idx].cells[3]
                notes = []
                for iid in item_ids:
                    if iid in checked_items:
                        item = checked_items[iid]
                        mark = f"✓ {item.item_name}"
                        if item.note:
                            mark += f"（{item.note}）"
                        notes.append(mark)
                cell.paragraphs[0].text = "\n".join(notes)
        
        # Also fill hazard_supplement in a note if available
        if case.hazard_supplement:
            # Add note to the last data row
            last_row = table.rows[min(7, len(table.rows) - 1)]
            note_cell = last_row.cells[3]
            existing = note_cell.text.strip()
            if existing:
                note_cell.paragraphs[0].text = f"{existing}\n補充：{case.hazard_supplement}"
            else:
                note_cell.paragraphs[0].text = f"補充：{case.hazard_supplement}"

    def _fill_signatures(self, doc: Document, case: Case) -> None:
        """Fill Table 3 (signatures) and P69 (reporting agency)."""
        # Table 3: [0,0]=承辦人, [0,1]=段長, [1,0]=(name), [1,1]=(name)
        table = doc.tables[3]
        if case.created_by and case.created_by.real_name:
            cell = table.rows[1].cells[0]
            if cell.paragraphs:
                self._append_text_to_paragraph(cell.paragraphs[0], case.created_by.real_name)
        
        # P69: 提報機關：
        for p in doc.paragraphs:
            if p.text.strip() == "提報機關：":
                p.runs[0].text = f"提報機關：{case.reporting_agency}"
                break
```

---

## Task 2: Photo insertion (B2)

**Files:**
- Modify: `app/services/word_generator.py` (the `_fill_photos` method)

**Implementation:**

```python
    def _fill_photos(self, doc: Document, case: Case, manifest: Optional[EvidenceManifest]) -> None:
        """Insert evidence photos after P21 (照片 section)."""
        if not manifest or not manifest.evidence:
            return
        
        # Find P21 by text
        target_p = None
        for p in doc.paragraphs:
            if "照片" in p.text and "建議擺放" in p.text:
                target_p = p
                break
        
        if target_p is None:
            return
        
        # Collect photo evidence (images only, sorted by photo_type)
        photos = [
            ev for ev in manifest.evidence
            if ev.content_type.startswith("image/") and ev.photo_type
        ]
        photos.sort(key=lambda e: e.photo_type or "Z")
        
        # Insert each photo
        current_p = target_p
        for ev in photos:
            # Read photo file
            photo_path = self._cases_dir / case.case_id / ev.evidence_path
            if not photo_path.exists():
                logger.warning("Photo file not found: %s", photo_path)
                continue
            
            # Insert caption paragraph
            caption = f"{ev.photo_type_name or ev.photo_type}"
            cap_p = self._insert_paragraph_after(current_p, caption, size_pt=12)
            
            # Insert image paragraph
            img_p_elem = self._insert_paragraph_after_elem(cap_p, "")
            # Wrap as Paragraph and add image
            from docx.text.paragraph import Paragraph
            img_paragraph = Paragraph(img_p_elem, doc)
            run = img_paragraph.add_run()
            run.add_picture(str(photo_path), width=Cm(14))
            
            current_p = img_p_elem
    
    @staticmethod
    def _insert_paragraph_after_elem(after_elem, text: str):
        """Insert an empty paragraph element after given element. Returns the new element."""
        from docx.oxml import OxmlElement
        new_p = OxmlElement("w:p")
        if text:
            r = OxmlElement("w:r")
            t = OxmlElement("w:t")
            t.text = text
            r.append(t)
            new_p.append(r)
        after_elem.addnext(new_p)
        return new_p
```

**Note:** Photo insertion is complex with python-docx when inserting after arbitrary paragraphs. An alternative approach is to use `doc.add_picture()` which appends to the end — we may need to restructure to add a "photos section" at the appropriate location. The exact approach should be refined during implementation based on what works best.

---

## Task 3: Location map (B3)

**Files:**
- Modify: `app/services/word_generator.py` (the `_fill_location_map` method)

**Approach:** Use a static map tile service (OpenStreetMap static map via `staticmap` library, or a simpler approach using `urllib` to fetch from a tile server). For MVP, generate a map image using the `staticmap` pip package.

**Implementation:**

```python
    def _fill_location_map(self, doc: Document, case: Case) -> None:
        """Generate and insert a location map after P16."""
        if not case.primary_coordinate:
            return
        
        lat = case.primary_coordinate.lat
        lon = case.primary_coordinate.lon
        
        # Generate static map image
        map_bytes = self._generate_static_map(lat, lon)
        if not map_bytes:
            return
        
        # Find P16 (位置簡圖)
        for p in doc.paragraphs:
            if "位置簡圖" in p.text:
                # Insert image after this paragraph
                img_stream = io.BytesIO(map_bytes)
                # Use _insert_paragraph_after to create new paragraph, then add image
                run = p.add_run()
                run.add_break()
                run.add_picture(img_stream, width=Cm(14))
                break
    
    @staticmethod
    def _generate_static_map(lat: float, lon: float, zoom: int = 15, width: int = 600, height: int = 400) -> Optional[bytes]:
        """Generate a static map image using staticmap library."""
        try:
            from staticmap import StaticMap, CircleMarker
            m = StaticMap(width, height)
            marker = CircleMarker((lon, lat), "red", 12)
            m.add_marker(marker)
            image = m.render(zoom=zoom)
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            buf.seek(0)
            return buf.getvalue()
        except ImportError:
            logger.warning("staticmap not installed, skipping location map")
            return None
        except Exception as e:
            logger.error("Failed to generate static map: %s", e)
            return None
```

**Dependency:** `pip install staticmap` (pure Python, uses OSM tiles)

---

## Task 4: Hazard table fill (B4)

Already covered in Task 1 Step 10 (`_fill_hazard_table`). This task is about testing and refinement.

---

## Task 5: Soil conservation / National park checkbox mapping (B5)

Already covered in Task 1 Steps 8-9. This task is about testing and refinement.

For more detailed checkbox handling:

**Soil conservation sub-items (when "不需要"):**
- P40 `(1)` — 必要之緊急搶通或搶災工作 → most common for disaster repair → ☑ by default
- P41 `(2)` — 山坡地既有道路改善或維護 → check if road_slope damage mode
- P42 `(3)` — 非屬山坡地災害性質 → check if NOT road_slope
- P43 `(4)` — 其他適用法令 → rarely used

**National park sub-items (when in park):**
- P48 "是" / P49 "否，無需申請原因：" → Default: ☑是
- P51 "是" / P52 "否，無需辦理原因：" → Default: ☑是

---

## Task 6: Tests (B6)

**Files:**
- Create: `tests/test_word_generator.py`

**Test cases:**

1. `test_generate_basic_fields` — Create Case with basic fields, generate doc, verify paragraphs contain data
2. `test_generate_with_coordinates` — Verify Table 0 filled with X/Y
3. `test_generate_with_cost_breakdown` — Verify cost table inserted
4. `test_generate_with_soil_conservation_yes` — Verify P38 marked ☑
5. `test_generate_with_soil_conservation_no` — Verify P39 marked ☑
6. `test_generate_with_national_park` — Verify P46 marked ☑
7. `test_generate_without_national_park` — Verify P53 marked ☑
8. `test_generate_with_site_survey` — Verify Table 2 備註 column has ✓
9. `test_generate_with_photos` — Verify photos embedded (requires temp files)
10. `test_generate_with_location_map` — Mock staticmap, verify image embedded
11. `test_generate_returns_bytes` — Verify output is valid docx bytes
12. `test_template_not_found_raises` — Verify FileNotFoundError

**Test strategy:**
- Use real template file for integration tests
- Create minimal Case objects with specific fields
- Read generated docx bytes back with python-docx to verify content
- Mock staticmap for map tests
- Create temp evidence files for photo tests

---

## Execution Order

1. **Task 1** (B1): Core class + all paragraph fill methods + stubs
2. **Task 6 part 1**: Basic tests (fields 1-8) to verify Task 1
3. **Task 2** (B2): Photo insertion
4. **Task 3** (B3): Location map (+ pip install staticmap)
5. **Task 4** (B4): Hazard table refinement + tests
6. **Task 5** (B5): Soil/park checkbox refinement + tests
7. **Task 6 part 2**: Remaining tests (photos, map, integration)
8. **Final**: Run all tests, verify no regressions

---

## Key Design Decisions

1. **Read-only service**: WordGenerator does NOT modify stored files. It produces new bytes.
2. **Paragraph index stability**: Some fill methods find paragraphs by text search (not index) because inserting new paragraphs shifts indices.
3. **Font matching**: Template uses 微軟正黑體 14pt (177800 EMU). All inserted text must match.
4. **Checkbox convention**: Using ☑/☐ Unicode characters since Word doesn't have native checkbox support in paragraph text.
5. **Photo insertion**: Using python-docx's `add_picture()` on runs, with width constraint of 14cm to fit page.
6. **Static map**: Using `staticmap` library (pure Python, OSM tiles) for MVP. Can upgrade to Google Maps Static API later.
7. **Cost table**: Building table with OOXML because python-docx's `add_table()` only appends to end of document.
