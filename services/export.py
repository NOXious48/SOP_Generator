"""Export service (design Section 5.7, TDD-14). Owner: Ankur2.

Renders an SOP into many formats. Machine-readable formats (JSON/XML/BPMN/testcases/rpa) are
generated from the process structure; document formats (md/html/docx/pdf) are human-facing.
"""
from __future__ import annotations

import io
import json
from xml.sax.saxutils import escape

from processiq_shared.models import SOP

SUPPORTED = {"md", "markdown", "html", "json", "xml", "bpmn", "testcases", "rpa", "docx", "pdf"}


def export(sop: SOP, fmt: str) -> tuple[bytes, str]:
    """Return (bytes, content_type)."""
    fmt = fmt.lower()
    if fmt in {"md", "markdown"}:
        return _markdown(sop).encode(), "text/markdown"
    if fmt == "html":
        return _html(sop).encode(), "text/html"
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
        return _docx(sop), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if fmt == "pdf":
        return _pdf(sop), "application/pdf"
    raise ValueError(f"unsupported format: {fmt}")


def _meta_block(sop: SOP) -> str:
    return (f"Confidence: {sop.overall_confidence} | Version: {sop.version} | "
            f"State: {sop.state.value} | Models: {', '.join(sop.provenance.models)}")


def _markdown(sop: SOP) -> str:
    lines = [f"# {sop.title}", "", f"> {_meta_block(sop)}", "",
             f"## Objective\n{sop.objective}", "",
             "## Prerequisites"]
    lines += [f"- {p}" for p in sop.prerequisites] or ["- None"]
    lines += ["", "## Steps", "", "| # | Action | Description | Confidence | Screenshot |",
              "|---|--------|-------------|-----------|-----------|"]
    for s in sop.steps:
        ref = s.screenshot_ref.artifact_id if s.screenshot_ref else "-"
        flag = " ⚠️" if s.flags else ""
        lines.append(f"| {s.no} | {s.action}{flag} | {s.description} | {s.confidence} | {ref} |")
    lines += ["", "## Exceptions"] + [f"- {e}" for e in sop.exceptions]
    lines += ["", "## Validation & Checks"] + [f"- {v}" for v in sop.validation]
    lines += ["", f"## Output\n{sop.output}"]
    return "\n".join(lines)


def _html(sop: SOP) -> str:
    rows = "".join(
        f"<tr><td>{s.no}</td><td>{escape(s.action)}</td><td>{escape(s.description)}</td>"
        f"<td>{s.confidence}</td></tr>" for s in sop.steps
    )
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{escape(sop.title)}</title>"
            f"</head><body><h1>{escape(sop.title)}</h1><p><em>{escape(_meta_block(sop))}</em></p>"
            f"<h2>Objective</h2><p>{escape(sop.objective)}</p>"
            f"<h2>Steps</h2><table border='1' cellspacing='0' cellpadding='4'>"
            f"<tr><th>#</th><th>Action</th><th>Description</th><th>Conf</th></tr>{rows}</table>"
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


def _docx(sop: SOP) -> bytes:
    from docx import Document

    doc = Document()
    doc.add_heading(sop.title, level=0)
    doc.add_paragraph(_meta_block(sop))
    doc.add_heading("Objective", level=1)
    doc.add_paragraph(sop.objective)
    doc.add_heading("Prerequisites", level=1)
    for p in sop.prerequisites:
        doc.add_paragraph(p, style="List Bullet")
    doc.add_heading("Steps", level=1)
    table = doc.add_table(rows=1, cols=4)
    hdr = table.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text, hdr[3].text = "#", "Action", "Description", "Conf"
    for s in sop.steps:
        row = table.add_row().cells
        row[0].text, row[1].text = str(s.no), s.action
        row[2].text, row[3].text = s.description, str(s.confidence)
    doc.add_heading("Output", level=1)
    doc.add_paragraph(sop.output)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pdf(sop: SOP) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    flow = [Paragraph(sop.title, styles["Title"]),
            Paragraph(_meta_block(sop), styles["Italic"]), Spacer(1, 12),
            Paragraph("Objective", styles["Heading2"]),
            Paragraph(sop.objective, styles["Normal"]), Spacer(1, 8),
            Paragraph("Steps", styles["Heading2"])]
    for s in sop.steps:
        flag = " (needs review)" if s.flags else ""
        flow.append(Paragraph(f"<b>{s.no}. {escape(s.action)}</b>{flag} — {escape(s.description)} "
                              f"[conf {s.confidence}]", styles["Normal"]))
        flow.append(Spacer(1, 4))
    flow += [Spacer(1, 8), Paragraph("Output", styles["Heading2"]),
             Paragraph(sop.output, styles["Normal"])]
    doc.build(flow)
    return buf.getvalue()
