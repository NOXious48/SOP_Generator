"""Pipeline orchestrator (design Sections 5.3, 7, 8).

A deterministic, ordered agent state machine. This scaffold uses a simple sequential runner with the
same node contract LangGraph will use; swap in LangGraph without changing agent code. Each stage
emits progress via an optional callback so the API can stream it.
"""
from __future__ import annotations

from collections.abc import Callable

from agents.base import Agent
from agents.generation import ConfidenceAgent, SopGenerationAgent, ValidationAgent
from agents.perception import GuiUnderstandingAgent, LayoutAgent, OcrAgent, VisionAgent
from agents.reasoning import KnowledgeGraphAgent, ReasoningAgent, WorkflowAgent
from agents.sop_vlm import VlmSopGenerationAgent
from processiq_shared.enums import PipelineStage
from processiq_shared.state import AgentState

ProgressCb = Callable[[str, int, str], None]

# Ordered pipeline: (stage, agent)
PIPELINE: list[tuple[PipelineStage, Agent]] = [
    (PipelineStage.VISION, VisionAgent()),
    (PipelineStage.OCR, OcrAgent()),
    (PipelineStage.LAYOUT, LayoutAgent()),
    (PipelineStage.GUI, GuiUnderstandingAgent()),
    (PipelineStage.WORKFLOW, WorkflowAgent()),
    (PipelineStage.REASONING, ReasoningAgent()),
    (PipelineStage.KNOWLEDGE_GRAPH, KnowledgeGraphAgent()),
    (PipelineStage.GENERATION, SopGenerationAgent()),
    (PipelineStage.VALIDATION, ValidationAgent()),
    (PipelineStage.CONFIDENCE, ConfidenceAgent()),
]

# VLM path: the multimodal model reads the screenshots directly + the user's instruction, so the
# heavy CV perception stages are skipped. Validation/Confidence still gate grounding + flags.
VLM_PIPELINE: list[tuple[PipelineStage, Agent]] = [
    (PipelineStage.GENERATION, VlmSopGenerationAgent()),
    (PipelineStage.VALIDATION, ValidationAgent()),
    (PipelineStage.CONFIDENCE, ConfidenceAgent()),
]


def _run(pipeline, state: AgentState, on_progress: ProgressCb | None) -> AgentState:
    total = len(pipeline)
    for idx, (stage, agent) in enumerate(pipeline, start=1):
        state = agent.run(state)
        if on_progress:
            on_progress(stage.value, int(idx / total * 100), f"{stage.value} complete")
    if on_progress:
        on_progress(PipelineStage.DONE.value, 100, "pipeline complete")
    return state


def run_pipeline(state: AgentState, on_progress: ProgressCb | None = None) -> AgentState:
    return _run(PIPELINE, state, on_progress)


def run_vlm_pipeline(state: AgentState, on_progress: ProgressCb | None = None) -> AgentState:
    return _run(VLM_PIPELINE, state, on_progress)
