"""Core domain models: perception, process graph, SOP, and API DTOs.

These implement the contracts in design Sections 7.3 (agent state) and 16 Appendix D (SOP schema).
Bounding boxes are normalized [x, y, w, h] with values in [0, 1].
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .enums import ElementType, ScreenRole, SopState, StepFlag

BBox = list[float]  # [x, y, w, h], normalized 0..1


def _now() -> datetime:
    return datetime.now(UTC)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:24]}"


# ---------- Perception ----------
class Element(BaseModel):
    id: str = Field(default_factory=lambda: _id("el"))
    type: ElementType = ElementType.UNKNOWN
    bbox: BBox
    confidence: float = 0.0
    text: str | None = None


class TextRegion(BaseModel):
    text: str
    bbox: BBox
    confidence: float = 0.0
    lang: str = "en"
    element_id: str | None = None


class ScreenSemantics(BaseModel):
    role: ScreenRole = ScreenRole.UNKNOWN
    primary_action: str | None = None  # element id
    actionable_elements: list[str] = Field(default_factory=list)
    summary: str = ""


class ScreenPerception(BaseModel):
    artifact_id: str
    order: int
    elements: list[Element] = Field(default_factory=list)
    text: list[TextRegion] = Field(default_factory=list)
    layout: dict[str, Any] = Field(default_factory=dict)
    semantics: ScreenSemantics = Field(default_factory=ScreenSemantics)
    screen_hash: str | None = None


# ---------- Process graph ----------
class Transition(BaseModel):
    from_order: int
    to_order: int
    action_element_id: str | None = None
    action_label: str | None = None
    state_change: str | None = None


class ProcessGraph(BaseModel):
    intent: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)
    branches: list[dict[str, Any]] = Field(default_factory=list)


# ---------- SOP (design Section 16, Appendix D) ----------
class ScreenshotRef(BaseModel):
    artifact_id: str
    bbox: BBox


class SopStep(BaseModel):
    no: int
    action: str
    description: str
    screenshot_ref: ScreenshotRef | None = None
    confidence: float = 0.0
    flags: list[StepFlag] = Field(default_factory=list)


class Provenance(BaseModel):
    models: list[str] = Field(default_factory=list)
    prompt_versions: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_now)


class SOP(BaseModel):
    id: str = Field(default_factory=lambda: _id("sop"))
    tenant_id: str
    process_id: str
    title: str
    version: int = 1
    state: SopState = SopState.DRAFT
    objective: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    steps: list[SopStep] = Field(default_factory=list)
    exceptions: list[str] = Field(default_factory=list)
    validation: list[str] = Field(default_factory=list)
    output: str = ""
    overall_confidence: float = 0.0
    provenance: Provenance = Field(default_factory=Provenance)
    created_at: datetime = Field(default_factory=_now)


class ValidationReport(BaseModel):
    grounded: bool = True
    flags: list[dict[str, Any]] = Field(default_factory=list)
    explanations: list[str] = Field(default_factory=list)


# ---------- API DTOs ----------
class CreateProcessRequest(BaseModel):
    name: str
    tenant_id: str | None = None


class CreateJobRequest(BaseModel):
    process_id: str
    options: dict[str, Any] = Field(default_factory=dict)


class JobView(BaseModel):
    id: str
    tenant_id: str
    process_id: str
    status: str
    stage: str | None = None
    progress: int = 0
    sop_id: str | None = None
    error: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=_now)


class ProblemDetail(BaseModel):
    """RFC 9457 problem details (design Section 10.2)."""
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    request_id: str | None = None
