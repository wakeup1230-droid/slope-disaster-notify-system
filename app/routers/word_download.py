"""Word document download endpoint."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.core.logging_config import get_logger
from app.models.evidence import EvidenceManifest
from app.services.word_generator import DEFAULT_TEMPLATE, WordGenerator

router = APIRouter()
logger = get_logger(__name__)


@router.get("/{case_id}/word")
async def download_word(request: Request, case_id: str):
    """Generate and download Word report for a case."""
    case_store = request.app.state.case_store
    case = case_store.get(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")

    # 每次下載都即時由最新模板重產，避免舊版 run 結構導致內容錯位
    settings = request.app.state.settings
    manifest_path = settings.cases_dir / case_id / "evidence_manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="Manifest not found")

    manifest = EvidenceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    base_dir = getattr(settings, "base_dir", None)
    template_path = (base_dir / "Input" / "公路災害工程內容概述表_空白.docx") if base_dir else DEFAULT_TEMPLATE
    generator = WordGenerator(template_path=template_path, cases_dir=settings.cases_dir)

    file_bytes = generator.generate(case=case, manifest=manifest)
    # 檔名用西元年月日小時分 (YYYYMMDD_HHmm.docx) — 台灣時間
    tz_tw = timezone(timedelta(hours=8))
    now_tw = datetime.now(tz_tw)
    filename = f"{now_tw.strftime('%Y%m%d_%H%M')}.docx"
    ascii_fallback = filename
    encoded_name = quote(filename)
    content_disp = (
        f'attachment; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{encoded_name}"
    )
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": content_disp},
    )
