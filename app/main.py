from __future__ import annotations

import importlib
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.logging_config import get_logger, setup_logging
from app.routers.cases import router as cases_router
from app.routers.health import router as health_router
from app.routers.line_webhook import router as line_webhook_router
from app.routers.vendor_api import router as vendor_router
from app.routers.statistics import router as statistics_router
from app.services.audit_logger import AuditLogger
from app.services.case_manager import CaseManager
from app.services.case_store import CaseStore
from app.services.evidence_store import EvidenceStore
from app.services.image_processor import ImageProcessor
from app.services.geology_service import GeologyService
from app.services.lrs_service import LRSService
from app.services.user_store import UserStore

logger = get_logger(__name__)


def _load_symbol(module_path: str, symbol: str) -> Any:
    module = importlib.import_module(module_path)
    return getattr(module, symbol)


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = get_settings()
        setup_logging("DEBUG" if settings.app_env == "development" else "INFO")
        settings.ensure_directories()

        user_store = UserStore(settings.users_dir)
        case_store = CaseStore(settings.cases_dir, settings.locks_dir)
        audit_logger = AuditLogger(settings.cases_dir)
        evidence_store = EvidenceStore(settings.cases_dir)
        case_manager = CaseManager(case_store, audit_logger)
        image_processor = ImageProcessor(
            thumbnail_size=settings.thumbnail_size,
            max_size_mb=settings.max_image_size_mb,
            accepted_formats=settings.accepted_formats_list,
        )
        lrs_service = LRSService(
            settings.lrs_csv_path,
            max_distance_m=settings.lrs_max_distance_m,
            grid_size_deg=settings.lrs_grid_size_deg,
        )
        geology_service = None
        try:
            geology_service = GeologyService(
                shapefile_dir=Path("Input/17_易淹水計畫流域地質圖"),
            )
        except Exception as exc:
            logger.warning("Geology data not loaded: %s", exc)

        line_session_store_cls = _load_symbol("app.services.line_session", "LineSessionStore")
        notification_service_cls = _load_symbol(
            "app.services.notification_service", "NotificationService"
        )
        line_flow_controller_cls = _load_symbol("app.services.line_flow", "LineFlowController")

        line_session_store = line_session_store_cls(settings.sessions_dir)
        notification_service = notification_service_cls(settings.line_channel_access_token)
        line_flow = line_flow_controller_cls(
            line_session_store=line_session_store,
            user_store=user_store,
            case_manager=case_manager,
            evidence_store=evidence_store,
            image_processor=image_processor,
            lrs_service=lrs_service,
            geology_service=geology_service,
            notification_service=notification_service,
        )

        app.state.settings = settings
        app.state.user_store = user_store
        app.state.case_store = case_store
        app.state.case_manager = case_manager
        app.state.evidence_store = evidence_store
        app.state.image_processor = image_processor
        app.state.lrs_service = lrs_service
        app.state.geology_service = geology_service
        app.state.line_flow = line_flow
        app.state.notification_service = notification_service
        app.state.line_session_store = line_session_store

        if settings.bootstrap_admin_line_id:
            _ = user_store.ensure_bootstrap_admin(
                settings.bootstrap_admin_line_id,
                settings.bootstrap_admin_name,
            )

        try:
            load_data = getattr(lrs_service, "load_data", None)
            if callable(load_data):
                _ = load_data()
        except Exception as exc:
            logger.warning("LRS data not loaded: %s", exc)

        logger.info("Application started: env=%s", settings.app_env)
        yield
        logger.info("Application shutting down")

    app = FastAPI(
        title="邊坡災害通報與資訊整合管理系統",
        version="1.0.0-phase1",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router, tags=["Health"])
    app.include_router(line_webhook_router, prefix="/webhook", tags=["LINE Webhook"])
    app.include_router(cases_router, prefix="/api/cases", tags=["Cases"])
    app.include_router(vendor_router, prefix="/vendor", tags=["Vendor API"])
    app.include_router(statistics_router, prefix="/api/statistics", tags=["Statistics"])

    webgis_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "webgis")
    if os.path.isdir(webgis_path):
        app.mount("/webgis", StaticFiles(directory=webgis_path, html=True), name="webgis")

    return app


app = create_app()
