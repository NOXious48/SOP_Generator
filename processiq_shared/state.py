"""Typed agent shared-state object (design Section 7.3).

The orchestrator threads this object through the LangGraph pipeline. Each agent reads its declared
inputs and writes typed outputs; nothing is exchanged as free-form chat.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from .models import SOP, ProcessGraph, ScreenPerception, Transition, ValidationReport


class TraceEvent(BaseModel):
    agent: str
    model: str | None = None
    version: str | None = None
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    status: str = "ok"


class JobContext(BaseModel):
    id: str
    tenant_id: str
    process_id: str
    plan: dict[str, Any] = Field(default_factory=dict)
    confidence_threshold: float = 0.75


class AgentState(BaseModel):
    """Shared state threaded through the pipeline."""
    job: JobContext
    screens: list[ScreenPerception] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)
    process_graph: ProcessGraph | None = None
    sop: SOP | None = None
    validation: ValidationReport | None = None
    trace: list[TraceEvent] = Field(default_factory=list)

    def add_trace(self, event: TraceEvent) -> None:
        self.trace.append(event)
