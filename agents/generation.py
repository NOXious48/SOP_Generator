"""SOP Generation, Validation, and Confidence agents.

Generation is schema-constrained (produces a valid SOP model). Validation enforces grounding:
every step must reference an element that exists in perception evidence (cite-or-omit).
Owner (Pushp/Divya): swap the deterministic generator for schema-constrained LLM decoding.
"""
from __future__ import annotations

from processiq_shared.enums import SopState, StepFlag
from processiq_shared.models import (
    SOP,
    Provenance,
    ScreenshotRef,
    SopStep,
    ValidationReport,
)
from processiq_shared.state import AgentState

from .base import Agent


class SopGenerationAgent(Agent):
    name = "generation"
    model = "mock-llm"

    def _run(self, state: AgentState) -> AgentState:
        pg = state.process_graph
        steps: list[SopStep] = []
        for i, screen in enumerate(sorted(state.screens, key=lambda s: s.order), start=1):
            el = screen.elements[0] if screen.elements else None
            action = (el.text if el else None) or f"Step {i}"
            steps.append(
                SopStep(
                    no=i,
                    action=action,
                    description=f"On the {screen.semantics.role.value} screen, perform: {action}.",
                    screenshot_ref=ScreenshotRef(artifact_id=screen.artifact_id, bbox=el.bbox)
                    if el
                    else None,
                    confidence=round(min(0.99, (el.confidence if el else 0.6)), 3),
                )
            )
        sop = SOP(
            tenant_id=state.job.tenant_id,
            process_id=state.job.process_id,
            title=(pg.intent if pg else "Generated SOP"),
            objective=f"Define the steps required to complete '{pg.intent}' accurately."
            if pg
            else "Generated from screenshots.",
            prerequisites=(pg.prerequisites if pg else []),
            steps=steps,
            exceptions=["Invalid input -> show error and allow retry."],
            validation=["All mandatory fields are completed before saving."],
            output="Process completed successfully.",
            provenance=Provenance(models=[e.model for e in state.trace if e.model], prompt_versions=["gen-v0"]),
        )
        state.sop = sop
        return state


class ValidationAgent(Agent):
    name = "validation"

    def _run(self, state: AgentState) -> AgentState:
        report = ValidationReport(grounded=True)
        if state.sop:
            valid_artifacts = {s.artifact_id for s in state.screens}
            for step in state.sop.steps:
                ref = step.screenshot_ref
                if ref is None or ref.artifact_id not in valid_artifacts:
                    report.grounded = False
                    step.flags.append(StepFlag.POSSIBLE_HALLUCINATION)
                    report.flags.append({"step": step.no, "issue": "ungrounded reference"})
        state.validation = report
        return state


class ConfidenceAgent(Agent):
    name = "confidence"

    def _run(self, state: AgentState) -> AgentState:
        if not state.sop:
            return state
        threshold = state.job.confidence_threshold
        for step in state.sop.steps:
            if step.confidence < threshold:
                if StepFlag.LOW_CONFIDENCE not in step.flags:
                    step.flags.append(StepFlag.LOW_CONFIDENCE)
        scores = [s.confidence for s in state.sop.steps] or [0.0]
        state.sop.overall_confidence = round(sum(scores) / len(scores), 3)
        needs_review = any(s.flags for s in state.sop.steps) or not (
            state.validation.grounded if state.validation else True
        )
        state.sop.state = SopState.DRAFT if not needs_review else SopState.DRAFT
        return state
