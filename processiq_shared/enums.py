"""Enumerations shared across ProcessIQ services."""
from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    PREPROCESS = "PREPROCESS"
    RUNNING = "RUNNING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PipelineStage(str, Enum):
    INGESTED = "ingested"
    PREPROCESS = "preprocess"
    VISION = "vision"
    OCR = "ocr"
    LAYOUT = "layout"
    GUI = "gui_understanding"
    WORKFLOW = "workflow"
    REASONING = "reasoning"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    GENERATION = "generation"
    VALIDATION = "validation"
    CONFIDENCE = "confidence"
    DONE = "done"


class SopState(str, Enum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class ElementType(str, Enum):
    BUTTON = "button"
    INPUT = "input"
    DROPDOWN = "dropdown"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    TABLE = "table"
    TAB = "tab"
    MENU = "menu"
    MODAL = "modal"
    TOAST = "toast"
    ICON = "icon"
    LINK = "link"
    CARD = "card"
    LABEL = "label"
    IMAGE = "image"
    UNKNOWN = "unknown"


class ScreenRole(str, Enum):
    LOGIN = "login"
    DASHBOARD = "dashboard"
    FORM = "form"
    LIST = "list"
    DETAIL = "detail"
    CONFIRMATION = "confirmation"
    ERROR = "error"
    UNKNOWN = "unknown"


class Role(str, Enum):
    ADMIN = "Admin"
    ANALYST = "Analyst"
    REVIEWER = "Reviewer"
    VIEWER = "Viewer"
    AUDITOR = "Auditor"


class StepFlag(str, Enum):
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    POSSIBLE_HALLUCINATION = "POSSIBLE_HALLUCINATION"
    MISSING_STEP = "MISSING_STEP"
    NEEDS_REVIEW = "NEEDS_REVIEW"
