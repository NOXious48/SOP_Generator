"""End-to-end pipeline demo — no external services required.

Simulates uploading the 5 "Create New Order" screens, runs the full agent pipeline, and prints the
generated SOP with confidence + provenance.

    python -m scripts.demo_pipeline
"""
from __future__ import annotations

import json

from apps.api.pipeline import run_job
from apps.api.store import store
from processiq_shared.enums import JobStatus
from processiq_shared.models import JobView

DEMO_SCREENS = [
    "01_login.png",
    "02_dashboard.png",
    "03_create_order_form.png",
    "04_confirm_order.png",
    "05_orders_list.png",
]


def main() -> None:
    tenant = "demo"
    process_id = store.create_process(tenant, "Create New Order")
    for i, name in enumerate(DEMO_SCREENS, start=1):
        store.add_artifact(process_id, {"id": store.new_id("art"), "filename": name, "order": i})

    job = JobView(
        id=store.new_id("job"),
        tenant_id=tenant,
        process_id=process_id,
        status=JobStatus.QUEUED.value,
    )
    store.save_job(job)
    job = run_job(job)

    print(f"\nJob {job.id} -> status={job.status}, sop={job.sop_id}\n")
    sop = store.get_sop(job.sop_id)
    print("=" * 70)
    print(f"SOP: {sop.title}   (overall confidence {sop.overall_confidence})")
    print("=" * 70)
    print(f"Objective: {sop.objective}")
    print(f"Prerequisites: {', '.join(sop.prerequisites)}")
    print("\nSteps:")
    for s in sop.steps:
        flags = f"  [{', '.join(f.value for f in s.flags)}]" if s.flags else ""
        ref = s.screenshot_ref.artifact_id if s.screenshot_ref else "-"
        print(f"  {s.no}. {s.action} (conf {s.confidence}, ref {ref}){flags}")
        print(f"     {s.description}")
    print(f"\nExceptions: {sop.exceptions}")
    print(f"Validation: {sop.validation}")
    print(f"Output: {sop.output}")
    print(f"\nProvenance models: {sop.provenance.models}")
    print("\nGrounded:", store.states[job.id].validation.grounded)
    print("\nRaw SOP JSON (first 600 chars):")
    print(json.dumps(json.loads(sop.model_dump_json()), indent=2)[:600], "...")


if __name__ == "__main__":
    main()
