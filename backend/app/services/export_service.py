"""Report exports: PDF (ReportLab) and CSV."""

import csv
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.utils.urls import PLATFORM_LABELS


def _p(text, style) -> Paragraph:
    return Paragraph(escape(str(text if text is not None else "")).replace("\n", "<br/>"), style)


def report_to_csv(company, report: dict, report_id: str) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "company_name", "website", "report_id", "finding_type", "classification", "title", "description",
            "confidence", "evidence_urls", "evidence_excerpts", "generated_at",
        ]
    )  # fmt: skip
    for f in report.get("findings", []):
        ev = f.get("evidence", [])
        w.writerow(
            [
                company.name,
                company.website_url,
                report_id,
                f["finding_type"],
                f["classification"],
                f["title"],
                f["description"],
                f["confidence"],
                " | ".join(e["source_url"] for e in ev),
                " | ".join(e["excerpt"] for e in ev),
                report.get("generated_at", ""),
            ]
        )
    if not report.get("findings"):
        w.writerow([company.name, company.website_url, report_id, "", "", "", "No findings were generated", "", "", "", report.get("generated_at", "")])
    return buf.getvalue().encode("utf-8-sig")


def companies_to_csv(companies) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "company_name", "website", "domain", "industry", "linkedin_url", "instagram_url", "youtube_url",
            "facebook_url", "x_url", "research_status", "last_researched_at", "created_at",
        ]
    )  # fmt: skip
    for c in companies:
        w.writerow(
            [
                c.name, c.website_url, c.normalized_domain, c.industry or "", c.linkedin_url or "", c.instagram_url or "",
                c.youtube_url or "", c.facebook_url or "", c.x_url or "", c.latest_status or "pending",
                c.last_researched_at.isoformat() if c.last_researched_at else "", c.created_at.isoformat(),
            ]
        )  # fmt: skip
    return buf.getvalue().encode("utf-8-sig")


def report_to_pdf(company, report: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"{company.name} - Company Intelligence Report", author="LeadPilotAI",
    )  # fmt: skip
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=16, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11, spaceBefore=10, spaceAfter=4)
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=9, leading=12)
    small = ParagraphStyle("small", parent=body, fontSize=7.5, leading=10, textColor=colors.HexColor("#555555"))
    story = [_p(company.name, h1), _p(f"{company.website_url}  |  Generated {report.get('generated_at', '')[:19]} UTC", small)]

    ov = report.get("overview", {})
    story.append(_p("Overview", h2))
    rows = [
        ["Industry", ov.get("industry") or "unknown"],
        ["Business model", ov.get("business_model", "unknown")],
        ["Description", ov.get("description", "unknown")],
        ["Target audience", ", ".join(ov.get("target_audience", [])) or "unknown"],
        ["Products", "; ".join(p["name"] for p in ov.get("products", [])) or "unknown"],
        ["Services", "; ".join(p["name"] for p in ov.get("services", [])) or "unknown"],
        ["Positioning", ov.get("market_positioning", "unknown")],
    ]
    t = Table([[_p(a, small), _p(b, body)] for a, b in rows], colWidths=[32 * mm, 138 * mm])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(t)

    story.append(_p("Research coverage", h2))
    cov = [["Source", "Status", "Verification", "Last checked"]] + [
        [PLATFORM_LABELS[c["platform"]], c["status"].replace("_", " "), c.get("verification_status") or "-", (c.get("last_checked_at") or "-")[:19]]
        for c in report.get("research_coverage", [])
    ]
    ct = Table([[_p(x, small if i == 0 else body) for x in r] for i, r in enumerate(cov)], colWidths=[35 * mm, 40 * mm, 40 * mm, 55 * mm])
    ct.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.lightgrey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6"))]))
    story.append(ct)

    story.append(_p("Findings", h2))
    findings = report.get("findings", [])
    if not findings:
        story.append(_p("No evidence-backed findings were generated.", body))
    for f in findings:
        story.append(_p(f"{f['title']}  [{f['classification'].replace('_', ' ')} | confidence: {f['confidence']}]", ParagraphStyle("ft", parent=body, fontName="Helvetica-Bold")))
        story.append(_p(f["description"], body))
        for e in f.get("evidence", []):
            story.append(_p(f"Evidence: \"{e['excerpt']}\" - {e['source_url']}", small))
        story.append(Spacer(1, 4))

    sp = report.get("sales_preparation", {})
    story.append(_p("Sales preparation", h2))
    for title, key in (("Talking points", "talking_points"), ("Questions to ask", "prospect_questions")):
        items = sp.get(key, [])
        if items:
            story.append(_p(title, ParagraphStyle("b", parent=body, fontName="Helvetica-Bold")))
            for it in items:
                story.append(_p(f"- {it['text']}", body))
    for title, key in (("Potential value proposition", "value_proposition"), ("Suggested next action", "suggested_next_action")):
        it = sp.get(key)
        if it:
            story.append(_p(title, ParagraphStyle("b2", parent=body, fontName="Helvetica-Bold")))
            story.append(_p(it["text"], body))
    if not any(sp.get(k) for k in ("talking_points", "prospect_questions", "value_proposition", "suggested_next_action")):
        story.append(_p("No grounded sales preparation was generated.", body))

    story.append(_p("Limitations", h2))
    for n in report.get("limitations", []) or ["None recorded."]:
        story.append(_p(f"- {n}", body))

    story.append(_p("Sources", h2))
    for s in report.get("sources", [])[:60]:
        story.append(_p(f"{s['url']}  ({s['platform']}, {s['document_type']}, collected {s['collected_at'][:19]} UTC)", small))
    story.append(Spacer(1, 6))
    story.append(_p(f"Model: {report.get('model_id') or 'n/a'} | Prompt v{report.get('prompt_version')} | Pipeline v{report.get('pipeline_version')}", small))
    doc.build(story)
    return buf.getvalue()
