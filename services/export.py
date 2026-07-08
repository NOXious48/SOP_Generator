"""Export service (design Section 5.7, TDD-14). Owner: Ankur2.

Renders an SOP into many formats. Machine-readable formats (JSON/XML/BPMN/testcases/rpa) are
generated from the process structure; document formats (md/html/docx/pdf) are human-facing.
"""
from __future__ import annotations

import base64
import io
import json
from collections.abc import Callable
from xml.sax.saxutils import escape

from processiq_shared.models import SOP, SopStep

SUPPORTED = {"md", "markdown", "html", "json", "xml", "bpmn", "testcases", "rpa", "docx", "pdf"}

# image_loader(artifact_id) -> raw image bytes (or None). Provided by the API so document exports
# can embed each step's screenshot with the click-target box drawn on it.
ImageLoader = Callable[[str], "bytes | None"]


def export(sop: SOP, fmt: str, image_loader: ImageLoader | None = None) -> tuple[bytes, str]:
    """Return (bytes, content_type). Document formats embed annotated screenshots when a loader
    is supplied; without one they render text-only (used by tests)."""
    fmt = fmt.lower()
    if fmt in {"md", "markdown"}:
        return _markdown(sop, image_loader).encode(), "text/markdown"
    if fmt == "html":
        return _html(sop, image_loader).encode(), "text/html"
    if fmt == "json":
        return sop.model_dump_json(indent=2).encode(), "application/json"
    if fmt == "xml":
        return _xml(sop).encode(), "application/xml"
    if fmt == "bpmn":
        return _bpmn(sop).encode(), "application/xml"
    if fmt == "testcases":
        return _testcases(sop).encode(), "application/json"
    if fmt == "rpa":
        return _rpa(sop).encode(), "text/x-python"
    if fmt == "docx":
        return _docx(sop, image_loader), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if fmt == "pdf":
        return _pdf(sop, image_loader), "application/pdf"
    raise ValueError(f"unsupported format: {fmt}")


# ---------- annotated screenshots ----------
def _annotated_png(image_bytes: bytes, bbox: list[float] | None, max_w: int = 1000) -> bytes | None:
    """Draw the click-target box on the screenshot; downscale for embedding. None on failure."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return None
    if img.width > max_w:
        img = img.resize((max_w, round(img.height * max_w / img.width)))
    W, H = img.size
    if bbox and len(bbox) == 4:
        x, y, w, h = bbox
        if w > 0 and h > 0 and (w * h) < 0.9:  # skip empty sentinel / full-frame boxes
            box = [x * W, y * H, (x + w) * W, (y + h) * H]
            draw = ImageDraw.Draw(img)
            for off in range(3):  # thick, high-contrast rectangle
                draw.rectangle([box[0] - off, box[1] - off, box[2] + off, box[3] + off],
                               outline=(233, 69, 96))
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _step_image(step: SopStep, image_loader: ImageLoader | None) -> bytes | None:
    if image_loader is None or step.screenshot_ref is None:
        return None
    raw = image_loader(step.screenshot_ref.artifact_id)
    if not raw:
        return None
    return _annotated_png(raw, step.screenshot_ref.bbox)


def _meta_block(sop: SOP) -> str:
    return (f"Confidence: {sop.overall_confidence} | Version: {sop.version} | "
            f"State: {sop.state.value} | Models: {', '.join(sop.provenance.models)}")


def _markdown(sop: SOP, image_loader: ImageLoader | None = None) -> str:
    lines = [f"# {sop.title}", "", f"> {_meta_block(sop)}", "",
             f"## Objective\n{sop.objective}", "",
             "## Prerequisites"]
    lines += [f"- {p}" for p in sop.prerequisites] or ["- None"]
    lines += ["", "## Steps", ""]
    for s in sop.steps:
        flag = " ⚠️ needs review" if s.flags else ""
        lines.append(f"### Step {s.no}: {s.action}{flag}")
        lines.append("")
        lines.append(f"{s.description}")
        lines.append("")
        lines.append(f"*Confidence: {s.confidence}*")
        img = _step_image(s, image_loader)
        if img:
            b64 = base64.b64encode(img).decode()
            lines.append("")
            lines.append(f"![Step {s.no}](data:image/png;base64,{b64})")
        lines.append("")
    lines += ["## Exceptions"] + [f"- {e}" for e in sop.exceptions]
    lines += ["", "## Validation & Checks"] + [f"- {v}" for v in sop.validation]
    lines += ["", f"## Output\n{sop.output}"]
    return "\n".join(lines)


def _html(sop: SOP, image_loader: ImageLoader | None = None) -> str:
    cards = []
    for s in sop.steps:
        badge = ("<span style='background:#e0a92b;color:#000;padding:1px 7px;border-radius:10px;"
                 "font-size:12px'>needs review</span>") if s.flags else ""
        img = _step_image(s, image_loader)
        img_html = ""
        if img:
            b64 = base64.b64encode(img).decode()
            img_html = (f"<img src='data:image/png;base64,{b64}' "
                        f"style='max-width:100%;border:1px solid #ddd;border-radius:8px;margin-top:8px'/>")
        cards.append(
            f"<div style='margin:0 0 22px;padding:14px 16px;border:1px solid #e5e7eb;border-radius:12px'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center'>"
            f"<h3 style='margin:0'>Step {s.no}: {escape(s.action)}</h3>{badge}</div>"
            f"<p style='margin:6px 0'>{escape(s.description)}</p>"
            f"<p style='margin:0;color:#6b7280;font-size:13px'>Confidence: {s.confidence}</p>"
            f"{img_html}</div>")
    prereqs = "".join(f"<li>{escape(p)}</li>" for p in sop.prerequisites)
    excs = "".join(f"<li>{escape(e)}</li>" for e in sop.exceptions)
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{escape(sop.title)}</title>"
            f"<style>body{{font-family:Segoe UI,system-ui,sans-serif;max-width:820px;margin:24px auto;"
            f"padding:0 18px;color:#111}}h1{{margin-bottom:4px}}</style></head><body>"
            f"<h1>{escape(sop.title)}</h1><p><em>{escape(_meta_block(sop))}</em></p>"
            f"<h2>Objective</h2><p>{escape(sop.objective)}</p>"
            f"<h2>Prerequisites</h2><ul>{prereqs}</ul>"
            f"<h2>Steps</h2>{''.join(cards)}"
            f"<h2>Exceptions</h2><ul>{excs}</ul>"
            f"<h2>Output</h2><p>{escape(sop.output)}</p></body></html>")


def _xml(sop: SOP) -> str:
    steps = "".join(
        f"<step no='{s.no}' confidence='{s.confidence}'><action>{escape(s.action)}</action>"
        f"<description>{escape(s.description)}</description></step>" for s in sop.steps
    )
    return (f"<?xml version='1.0' encoding='UTF-8'?><sop title='{escape(sop.title)}' "
            f"version='{sop.version}' confidence='{sop.overall_confidence}'>"
            f"<objective>{escape(sop.objective)}</objective><steps>{steps}</steps></sop>")


def _bpmn(sop: SOP) -> str:
    """Minimal but valid-shaped BPMN 2.0 with a task per step in sequence."""
    ns = "http://www.omg.org/spec/BPMN/20100524/MODEL"
    tasks, flows = [], []
    prev = "StartEvent_1"
    for s in sop.steps:
        tid = f"Task_{s.no}"
        tasks.append(f"<task id='{tid}' name='{escape(s.action)}'/>")
        flows.append(f"<sequenceFlow id='Flow_{s.no}' sourceRef='{prev}' targetRef='{tid}'/>")
        prev = tid
    flows.append(f"<sequenceFlow id='Flow_end' sourceRef='{prev}' targetRef='EndEvent_1'/>")
    return (f"<?xml version='1.0' encoding='UTF-8'?>"
            f"<definitions xmlns='{ns}' id='Defs_{sop.id}' targetNamespace='http://processiq'>"
            f"<process id='Process_{sop.id}' name='{escape(sop.title)}' isExecutable='false'>"
            f"<startEvent id='StartEvent_1'/>{''.join(tasks)}"
            f"<endEvent id='EndEvent_1'/>{''.join(flows)}</process></definitions>")


def _testcases(sop: SOP) -> str:
    cases = [{
        "id": f"TC-{s.no:03d}", "title": f"Verify: {s.action}",
        "steps": [s.description],
        "expected": "Step completes without error and UI advances as described.",
        "priority": "P1" if not s.flags else "P0",
    } for s in sop.steps]
    return json.dumps({"process": sop.title, "cases": cases}, indent=2)


def _rpa(sop: SOP) -> str:
    """RPA automation-script SKELETON (artifact only — never auto-executed, design §14.6)."""
    body = [f"# Auto-generated RPA skeleton for: {sop.title}",
            "# NOTE: artifact only. Review before running in an RPA runtime.",
            "def run(bot):"]
    for s in sop.steps:
        ref = s.screenshot_ref.artifact_id if s.screenshot_ref else "n/a"
        body.append(f"    bot.step({s.no}, action={s.action!r})  # ref={ref}")
    body.append("    return 'completed'")
    return "\n".join(body)


def _docx(sop: SOP, image_loader: ImageLoader | None = None) -> bytes:
    from docx import Document
    from docx.shared import Inches

    doc = Document()
    doc.add_heading(sop.title, level=0)
    doc.add_paragraph(_meta_block(sop))
    doc.add_heading("Objective", level=1)
    doc.add_paragraph(sop.objective)
    doc.add_heading("Prerequisites", level=1)
    for p in sop.prerequisites:
        doc.add_paragraph(p, style="List Bullet")
    doc.add_heading("Steps", level=1)
    for s in sop.steps:
        flag = "  (needs review)" if s.flags else ""
        doc.add_heading(f"Step {s.no}: {s.action}{flag}", level=2)
        doc.add_paragraph(s.description)
        doc.add_paragraph(f"Confidence: {s.confidence}")
        img = _step_image(s, image_loader)
        if img:
            doc.add_picture(io.BytesIO(img), width=Inches(6.0))
    doc.add_heading("Output", level=1)
    doc.add_paragraph(sop.output)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pdf(sop: SOP, image_loader: ImageLoader | None = None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    max_w = A4[0] - 72  # page width minus margins
    flow = [Paragraph(escape(sop.title), styles["Title"]),
            Paragraph(escape(_meta_block(sop)), styles["Italic"]), Spacer(1, 12),
            Paragraph("Objective", styles["Heading2"]),
            Paragraph(escape(sop.objective), styles["Normal"]), Spacer(1, 8),
            Paragraph("Steps", styles["Heading2"])]
    for s in sop.steps:
        flag = " (needs review)" if s.flags else ""
        flow.append(Paragraph(f"<b>{s.no}. {escape(s.action)}</b>{flag}", styles["Heading3"]))
        flow.append(Paragraph(f"{escape(s.description)} [conf {s.confidence}]", styles["Normal"]))
        img = _step_image(s, image_loader)
        if img:
            iw, ih = ImageReader(io.BytesIO(img)).getSize()
            w = min(max_w, iw)
            flow.append(Spacer(1, 4))
            flow.append(Image(io.BytesIO(img), width=w, height=ih * w / iw))
        flow.append(Spacer(1, 10))
    flow += [Paragraph("Output", styles["Heading2"]), Paragraph(escape(sop.output), styles["Normal"])]
    doc.build(flow)
    return buf.getvalue()
