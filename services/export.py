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


# ---------- shared document helpers (the required 7-section SOP layout) ----------
DOC_TITLE = "STANDARD OPERATING PROCEDURE (SOP)"


def _conf_pct(sop: SOP) -> int:
    return round(sop.overall_confidence * 100)


def _conf_label(pct: int) -> str:
    return "High" if pct >= 80 else "Moderate" if pct >= 60 else "Low"


def _conf_sentence(sop: SOP) -> str:
    pct = _conf_pct(sop)
    return (f"{pct}% — {_conf_label(pct)} confidence in the reconstructed workflow "
            f"(across {len(sop.steps)} step(s)).")


def _meta_block(sop: SOP) -> str:
    return (f"Version: {sop.version} | State: {sop.state.value} | "
            f"Models: {', '.join(sop.provenance.models) or 'n/a'}")


def _markdown(sop: SOP, image_loader: ImageLoader | None = None) -> str:
    L = [f"# {DOC_TITLE}", "", f"**Process:** {sop.title}", "", f"_{_meta_block(sop)}_", ""]
    L += [f"## 1. OBJECTIVE\n\n{sop.objective or '_Not specified._'}", ""]

    L += ["## 2. PRE-REQUISITES", ""]
    L += [f"- {p}" for p in sop.prerequisites] or ["- None"]

    L += ["", "## 3. STEP-BY-STEP PROCEDURE"]
    for s in sop.steps:  # each step: its description paragraph, then its screenshot, then the next
        flag = " ⚠️ needs review" if s.flags else ""
        L += ["", f"### Step {s.no}: {s.action}{flag}", "", s.description or ""]
        img = _step_image(s, image_loader)
        if img:
            b64 = base64.b64encode(img).decode()
            L += ["", f"![Step {s.no}](data:image/png;base64,{b64})"]

    L += ["", "## 4. EXCEPTION HANDLING", ""]
    L += [f"- {e}" for e in sop.exceptions] or ["- None documented."]

    L += ["", "## 5. VALIDATION & CHECKS", ""]
    L += [f"- {v}" for v in sop.validation] or ["- None documented."]

    L += ["", f"## 6. OUTPUT\n\n{sop.output or '_Not specified._'}", ""]
    L += ["## 7. CONFIDENCE SCORE", "", f"**{_conf_sentence(sop)}**"]
    return "\n".join(L)


def _html(sop: SOP, image_loader: ImageLoader | None = None) -> str:
    steps_html = []
    for s in sop.steps:  # each step: heading + description paragraph, then its screenshot
        badge = (" <span style='background:#e0a92b;color:#000;padding:0 6px;border-radius:9px;"
                 "font-size:11px'>needs review</span>") if s.flags else ""
        img = _step_image(s, image_loader)
        img_html = ""
        if img:
            b64 = base64.b64encode(img).decode()
            img_html = (f"<img src='data:image/png;base64,{b64}' "
                        f"style='max-width:100%;border:1px solid #ddd;border-radius:8px;margin-top:8px'/>")
        steps_html.append(
            f"<div style='margin:0 0 26px'>"
            f"<h3 style='margin:0 0 6px'>Step {s.no}: {escape(s.action)}{badge}</h3>"
            f"<p style='margin:0'>{escape(s.description).replace(chr(10), '<br>')}</p>"
            f"{img_html}</div>")

    def ul(items: list[str], empty: str) -> str:
        return "<ul>" + ("".join(f"<li>{escape(x)}</li>" for x in items) or f"<li>{empty}</li>") + "</ul>"

    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{escape(sop.title)}</title>"
            f"<style>body{{font-family:Segoe UI,system-ui,sans-serif;max-width:860px;margin:24px auto;"
            f"padding:0 18px;color:#111}}h1{{margin-bottom:2px;font-size:22px}}h2{{margin-top:28px;"
            f"border-bottom:1px solid #eee;padding-bottom:4px}}h3{{margin-bottom:4px}}"
            f"</style></head><body>"
            f"<h1>{DOC_TITLE}</h1><p style='font-size:16px'><b>Process:</b> {escape(sop.title)}</p>"
            f"<p style='color:#6b7280;font-size:13px'><em>{escape(_meta_block(sop))}</em></p>"
            f"<h2>1. Objective</h2><p>{escape(sop.objective) or '<em>Not specified.</em>'}</p>"
            f"<h2>2. Pre-requisites</h2>{ul(sop.prerequisites, 'None')}"
            f"<h2>3. Step-by-Step Procedure</h2>{''.join(steps_html)}"
            f"<h2>4. Exception Handling</h2>{ul(sop.exceptions, 'None documented.')}"
            f"<h2>5. Validation &amp; Checks</h2>{ul(sop.validation, 'None documented.')}"
            f"<h2>6. Output</h2><p>{escape(sop.output) or '<em>Not specified.</em>'}</p>"
            f"<h2>7. Confidence Score</h2><p><b>{escape(_conf_sentence(sop))}</b></p>"
            f"</body></html>")


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
    doc.add_heading(DOC_TITLE, level=0)
    doc.add_heading(f"Process: {sop.title}", level=1)
    doc.add_paragraph(_meta_block(sop)).italic = True

    doc.add_heading("1. Objective", level=1)
    doc.add_paragraph(sop.objective or "Not specified.")

    doc.add_heading("2. Pre-requisites", level=1)
    for p in sop.prerequisites or ["None"]:
        doc.add_paragraph(p, style="List Bullet")

    doc.add_heading("3. Step-by-Step Procedure", level=1)
    for s in sop.steps:  # each step: heading + description paragraph, then its screenshot
        flag = "  (needs review)" if s.flags else ""
        doc.add_heading(f"Step {s.no}: {s.action}{flag}", level=2)
        doc.add_paragraph(s.description or "")
        img = _step_image(s, image_loader)
        if img:
            doc.add_picture(io.BytesIO(img), width=Inches(6.0))

    doc.add_heading("4. Exception Handling", level=1)
    for e in sop.exceptions or ["None documented."]:
        doc.add_paragraph(e, style="List Bullet")

    doc.add_heading("5. Validation & Checks", level=1)
    for v in sop.validation or ["None documented."]:
        doc.add_paragraph(v, style="List Bullet")

    doc.add_heading("6. Output", level=1)
    doc.add_paragraph(sop.output or "Not specified.")

    doc.add_heading("7. Confidence Score", level=1)
    doc.add_paragraph(_conf_sentence(sop)).bold = True

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pdf(sop: SOP, image_loader: ImageLoader | None = None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (
        Image,
        ListFlowable,
        ListItem,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    st = getSampleStyleSheet()
    cell = st["BodyText"]
    max_w = A4[0] - 72  # page width minus margins

    def bullets(items: list[str], empty: str) -> ListFlowable:
        items = items or [empty]
        return ListFlowable([ListItem(Paragraph(escape(x), cell)) for x in items],
                            bulletType="bullet", leftIndent=14)

    flow = [Paragraph(DOC_TITLE, st["Title"]),
            Paragraph(f"<b>Process:</b> {escape(sop.title)}", st["Heading2"]),
            Paragraph(escape(_meta_block(sop)), st["Italic"]), Spacer(1, 10),
            Paragraph("1. Objective", st["Heading2"]),
            Paragraph(escape(sop.objective) or "<i>Not specified.</i>", cell), Spacer(1, 6),
            Paragraph("2. Pre-requisites", st["Heading2"]), bullets(sop.prerequisites, "None"),
            Spacer(1, 6), Paragraph("3. Step-by-Step Procedure", st["Heading2"]), Spacer(1, 4)]

    for s in sop.steps:  # each step: heading + description paragraph, then its screenshot
        flag = " <i>(needs review)</i>" if s.flags else ""
        flow += [Paragraph(f"<b>Step {s.no}: {escape(s.action)}</b>{flag}", st["Heading3"]),
                 Paragraph(escape(s.description).replace("\n", "<br/>"), cell)]
        img = _step_image(s, image_loader)
        if img:
            iw, ih = ImageReader(io.BytesIO(img)).getSize()
            w = min(max_w, iw)
            flow += [Spacer(1, 4), Image(io.BytesIO(img), width=w, height=ih * w / iw)]
        flow.append(Spacer(1, 10))

    flow += [Spacer(1, 8), Paragraph("4. Exception Handling", st["Heading2"]),
             bullets(sop.exceptions, "None documented."), Spacer(1, 6),
             Paragraph("5. Validation & Checks", st["Heading2"]),
             bullets(sop.validation, "None documented."), Spacer(1, 6),
             Paragraph("6. Output", st["Heading2"]),
             Paragraph(escape(sop.output) or "<i>Not specified.</i>", cell), Spacer(1, 6),
             Paragraph("7. Confidence Score", st["Heading2"]),
             Paragraph(f"<b>{escape(_conf_sentence(sop))}</b>", cell)]
    doc.build(flow)
    return buf.getvalue()
