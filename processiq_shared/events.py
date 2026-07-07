"""Domain events published on the bus (design Section 12.2).

Consumers must be idempotent. Every event carries a tenant_id and a correlation/job id.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

# Subjects / topics
SUBJECT_JOB_SUBMITTED = "jobs.submitted"
SUBJECT_JOB_PREPROCESSED = "jobs.preprocessed"
SUBJECT_JOB_STAGE = "jobs.stage"
SUBJECT_JOB_COMPLETED = "jobs.completed"
SUBJECT_JOB_FAILED = "jobs.failed"
SUBJECT_SOP_PUBLISHED = "sop.published"


class Event(BaseModel):
    subject: str
    tenant_id: str
    job_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    event_id: int = 0
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StageProgress(BaseModel):
    job_id: str
    stage: str
    progress: int
    message: str = ""
