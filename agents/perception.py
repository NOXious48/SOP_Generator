"""Perception agents: Vision, OCR, Layout, GUI understanding.

Vision + OCR call the inference gateway (OmniParser v2 / PaddleOCR under the active MODEL_PROFILE)
when the job carries real artifact paths (`state.job.plan["artifact_paths"]`). Without paths — or
when the gateway returns no usable result (mock profile, model failure) — they fall back to the
demo synthesizer so the pipeline always completes.

Owner (Divya): GUI understanding still heuristic; replace with UI-VLM per design Section 6.3.
"""
from __future__ import annotations

from processiq_shared.enums import ElementType, ScreenRole
from processiq_shared.models import BBox, Element, ScreenSemantics, TextRegion
from processiq_shared.state import AgentState

from .base import Agent

# Mock knowledge for the "Create New Order" demo, keyed by screen order.
_DEMO_SCREENS = {
    1: (ScreenRole.LOGIN, "Login", ElementType.BUTTON, [0.42, 0.61, 0.16, 0.06]),
    2: (ScreenRole.DASHBOARD, "Dashboard", ElementType.LINK, [0.05, 0.18, 0.20, 0.05]),
    3: (ScreenRole.FORM, "Create New Order", ElementType.BUTTON, [0.10, 0.20, 0.30, 0.08]),
    4: (ScreenRole.CONFIRMATION, "Save Order", ElementType.BUTTON, [0.60, 0.80, 0.18, 0.06]),
    5: (ScreenRole.LIST, "Orders List", ElementType.TABLE, [0.05, 0.30, 0.90, 0.50]),
}


def _artifact_path(state: AgentState, artifact_id: str) -> str | None:
    return state.job.plan.get("artifact_paths", {}).get(artifact_id)


def _contains(outer: BBox, cx: float, cy: float) -> bool:
    x, y, w, h = outer
    return x <= cx <= x + w and y <= cy <= y + h


def _owning_element(elements: list[Element], bbox: BBox) -> Element | None:
    """Smallest detected element containing the text region's center (FR-041 association)."""
    cx, cy = bbox[0] + bbox[2] / 2, bbox[1] + bbox[3] / 2
    candidates = [el for el in elements if _contains(el.bbox, cx, cy)]
    if not candidates:
        return None
    return min(candidates, key=lambda el: el.bbox[2] * el.bbox[3])


class VisionAgent(Agent):
    name = "vision"
    model = "mock-vision"

    def _run(self, state: AgentState) -> AgentState:
        for screen in state.screens:
            detected = self._detect(_artifact_path(state, screen.artifact_id))
            if detected is None:
                self._mock_screen(screen)
                continue
            for d in detected:
                screen.elements.append(Element(
                    type=ElementType.UNKNOWN,
                    bbox=d["bbox"],
                    confidence=d["confidence"],
                    text=d.get("caption"),
                ))
            primary = max(screen.elements, key=lambda el: el.confidence, default=None)
            screen.semantics = ScreenSemantics(
                role=ScreenRole.UNKNOWN,
                primary_action=primary.id if primary else None,
                summary=f"{len(screen.elements)} interactable elements detected",
            )
        return state

    def _detect(self, path: str | None) -> list[dict] | None:
        if not path:
            return None
        try:
            from apps.inference_gateway.gateway import gateway

            out = gateway.infer("detection", {"image_path": path})
            elements = out.get("elements")
            if elements is not None:
                self.model = out.get("model", self.model)
            return elements  # None on mock profile (echo payload has no elements)
        except Exception:
            return None  # real model unavailable -> demo synth keeps the pipeline alive

    @staticmethod
    def _mock_screen(screen) -> None:
        role, label, etype, bbox = _DEMO_SCREENS.get(
            screen.order, (ScreenRole.UNKNOWN, "Action", ElementType.BUTTON, [0.4, 0.6, 0.2, 0.08])
        )
        el = Element(type=etype, bbox=bbox, confidence=0.94, text=label)
        screen.elements.append(el)
        screen.semantics = ScreenSemantics(role=role, primary_action=el.id, summary=f"{role.value} screen")


class OcrAgent(Agent):
    name = "ocr"
    model = "mock-ocr"

    def _run(self, state: AgentState) -> AgentState:
        for screen in state.screens:
            regions = self._ocr(_artifact_path(state, screen.artifact_id))
            if regions is None:
                for el in screen.elements:
                    if el.text:
                        screen.text.append(
                            TextRegion(text=el.text, bbox=el.bbox, confidence=0.97, element_id=el.id)
                        )
                continue
            for r in regions:
                owner = _owning_element(screen.elements, r["bbox"])
                screen.text.append(TextRegion(
                    text=r["text"], bbox=r["bbox"], confidence=r["confidence"],
                    element_id=owner.id if owner else None,
                ))
            self._label_elements(screen)
        return state

    def _ocr(self, path: str | None) -> list[dict] | None:
        if not path:
            return None
        try:
            from apps.inference_gateway.gateway import gateway

            out = gateway.infer("ocr", {"image_path": path})
            regions = out.get("regions")
            if regions is not None:
                self.model = out.get("model", self.model)
            return regions
        except Exception:
            return None

    @staticmethod
    def _label_elements(screen) -> None:
        """OCR text is authoritative for element labels (better than VLM captions)."""
        by_element: dict[str, list[TextRegion]] = {}
        for tr in screen.text:
            if tr.element_id:
                by_element.setdefault(tr.element_id, []).append(tr)
        for el in screen.elements:
            regions = by_element.get(el.id)
            if regions:
                regions.sort(key=lambda t: (t.bbox[1], t.bbox[0]))  # reading order
                el.text = " ".join(t.text for t in regions)


class LayoutAgent(Agent):
    name = "layout"
    model = "geometric-heuristics"

    def _run(self, state: AgentState) -> AgentState:
        for screen in state.screens:
            ordered = sorted(screen.elements, key=lambda e: (e.bbox[1], e.bbox[0]))
            screen.layout = {"reading_order": [e.id for e in ordered]}
        return state


class GuiUnderstandingAgent(Agent):
    name = "gui_understanding"
    model = "heuristic"

    def _run(self, state: AgentState) -> AgentState:
        for screen in state.screens:
            labeled = [e.id for e in screen.elements if e.text]
            screen.semantics.actionable_elements = (
                labeled or ([screen.semantics.primary_action] if screen.semantics.primary_action else [])
            )
        return state
