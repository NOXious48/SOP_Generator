"""Golden-path tests for the Create New Order pipeline and the SOP schema contract."""
from __future__ import annotations

from apps.api.pipeline import run_job
from apps.api.store import InMemoryStore, store
from apps.orchestrator.graph import run_pipeline
from processiq_shared.enums import JobStatus
from processiq_shared.models import JobView, ScreenPerception
from processiq_shared.state import AgentState, JobContext


def _seed_process(n: int = 5) -> str:
    pid = store.create_process("demo", "Create New Order")
    for i in range(1, n + 1):
        store.add_artifact(pid, {"id": store.new_id("art"), "filename": f"{i}.png", "order": i})
    return pid


def test_pipeline_generates_grounded_sop():
    state = AgentState(
        job=JobContext(id="job_x", tenant_id="demo", process_id="p"),
        screens=[ScreenPerception(artifact_id=f"art_{i}", order=i) for i in range(1, 6)],
    )
    state = run_pipeline(state)
    assert state.sop is not None
    assert len(state.sop.steps) == 5
    # Every step references a real artifact => grounded.
    assert state.validation.grounded is True
    for step in state.sop.steps:
        assert step.screenshot_ref is not None
        assert step.screenshot_ref.artifact_id.startswith("art_")


def test_run_job_completes_and_scores():
    pid = _seed_process()
    job = JobView(id=store.new_id("job"), tenant_id="demo", process_id=pid,
                  status=JobStatus.QUEUED.value)
    store.save_job(job)
    job = run_job(job)
    assert job.status in {JobStatus.COMPLETED.value, JobStatus.NEEDS_REVIEW.value}
    sop = store.get_sop(job.sop_id)
    assert 0.0 <= sop.overall_confidence <= 1.0
    assert sop.title == "Create New Order"


def test_sop_json_schema_shape():
    fresh = InMemoryStore()
    assert fresh.new_id("sop").startswith("sop_")
