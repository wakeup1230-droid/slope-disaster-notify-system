"""
LINE conversation state models.

Manages the multi-step conversation state machine for LINE Bot interactions.
Each user has a session stored as JSON, tracking their current flow position.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class FlowType(str, Enum):
    """Types of conversation flows."""
    IDLE = "idle"
    REGISTRATION = "registration"
    REPORTING = "reporting"
    QUERY = "query"
    MANAGEMENT = "management"
    PHOTO_ANNOTATION = "photo_annotation"
    PROFILE = "profile"


class RegistrationStep(str, Enum):
    """Steps in the registration flow."""
    ASK_REAL_NAME = "ask_real_name"
    ASK_ROLE = "ask_role"
    ASK_DISTRICT = "ask_district"
    CONFIRM = "confirm"
    DONE = "done"


class ReportingStep(str, Enum):
    """Steps in the 12-step disaster reporting flow."""
    SELECT_DISTRICT = "select_district"          # Step 1
    SELECT_ROAD = "select_road"                  # Step 2
    INPUT_COORDINATES = "input_coordinates"      # Step 3
    CONFIRM_MILEPOST = "confirm_milepost"        # Step 4
    SELECT_DAMAGE_MODE = "select_damage_mode"    # Step 5
    SELECT_DAMAGE_CAUSE = "select_damage_cause"  # Step 6
    INPUT_DESCRIPTION = "input_description"      # Step 7
    UPLOAD_PHOTOS = "upload_photos"              # Step 8
    ANNOTATE_PHOTOS = "annotate_photos"          # Step 9
    SITE_SURVEY = "site_survey"                  # Step 10
    ESTIMATED_COST = "estimated_cost"            # Step 11
    CONFIRM_SUBMIT = "confirm_submit"            # Step 12
    DONE = "done"


class AnnotationSubStep(str, Enum):
    """Sub-steps within photo annotation."""
    SELECT_PHOTO = "select_photo"
    SELECT_TYPE = "select_type"
    SELECT_TAGS = "select_tags"
    CUSTOM_INPUT = "custom_input"
    CONFIRM_ANNOTATION = "confirm_annotation"
    NEXT_PHOTO = "next_photo"


class GuidedPhotoSubStep(str, Enum):
    """Sub-steps for guided photo upload and inline annotation."""

    # --- Existing (backward compat) ---
    AWAITING_UPLOAD = "awaiting_upload"
    SELECT_TAGS = "select_tags"
    CUSTOM_INPUT = "custom_input"
    CONFIRM_ANNOTATION = "confirm_annotation"
    CHOOSE_OPTIONAL = "choose_optional"

    # --- New: Photo-set annotation flow ---
    PHOTO_VISIBLE_TAGS = "photo_visible_tags"
    SUPPLEMENT_PHOTO = "supplement_photo"
    JUDGMENT_TAGS = "judgment_tags"
    TEXT_INPUT = "text_input"
    SET_COMPLETE = "set_complete"

class LineSession(BaseModel):
    """
    Persistent conversation state for a LINE user.

    Stored as JSON in storage/sessions/{source_key}.json.
    The source_key is the LINE user_id.
    """
    # --- Session Identity ---
    source_key: str = Field(description="LINE user_id")
    user_id: str = Field(default="", description="Same as source_key for 1:1 chat")

    # --- Current Flow ---
    flow: FlowType = FlowType.IDLE
    step: str = ""  # Current step within the flow (enum value as string)
    sub_step: str = ""  # Sub-step for nested flows like photo annotation

    # --- Flow Data (accumulated during conversation) ---
    data: dict[str, Any] = Field(default_factory=dict)

    # --- Photo Annotation State ---
    current_photo_index: int = 0
    pending_tags: list[str] = Field(default_factory=list)
    annotation_accumulator: dict[str, Any] = Field(default_factory=dict)

    # --- Draft Case ID (for reporting flow) ---
    draft_case_id: Optional[str] = None

    # --- Timestamps ---
    started_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    last_message_at: Optional[str] = None

    # --- Deduplication ---
    last_event_id: Optional[str] = None

    def reset(self) -> None:
        """Reset session to idle state, clearing all flow data."""
        self.flow = FlowType.IDLE
        self.step = ""
        self.sub_step = ""
        self.data = {}
        self.current_photo_index = 0
        self.pending_tags = []
        self.annotation_accumulator = {}
        self.draft_case_id = None
        self.updated_at = datetime.now().isoformat()

    def start_flow(self, flow: FlowType, initial_step: str = "") -> None:
        """Start a new conversation flow."""
        self.flow = flow
        self.step = initial_step
        self.sub_step = ""
        self.data = {}
        self.started_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()

    def advance_step(self, next_step: str) -> None:
        """Move to the next step in the current flow."""
        self.step = next_step
        self.sub_step = ""
        self.updated_at = datetime.now().isoformat()

    def set_sub_step(self, sub_step: str) -> None:
        """Set sub-step for nested flows."""
        self.sub_step = sub_step
        self.updated_at = datetime.now().isoformat()

    def store_data(self, key: str, value: Any) -> None:
        """Store a piece of data collected during the flow."""
        self.data[key] = value
        self.updated_at = datetime.now().isoformat()

    def get_data(self, key: str, default: Any = None) -> Any:
        """Retrieve stored flow data."""
        return self.data.get(key, default)

    def is_duplicate_event(self, event_id: str) -> bool:
        """Check if this event was already processed (webhook retry dedup)."""
        if self.last_event_id == event_id:
            return True
        self.last_event_id = event_id
        return False

    def touch(self) -> None:
        """Update last_message_at timestamp."""
        self.last_message_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
