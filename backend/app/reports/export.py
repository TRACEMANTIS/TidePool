"""Export utilities for TidePool reports (CSV, JSON, PDF)."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from fastapi.responses import StreamingResponse


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

async def export_csv(data: list[dict], filename: str) -> StreamingResponse:
    """Generate a CSV streaming response from a list of dictionaries."""
    if not data:
        buf = io.StringIO()
        buf.write("")
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(data[0].keys()))
    writer.writeheader()
    for row in data:
        writer.writerow(row)
    buf.seek(0)

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------

async def export_json(data: dict, filename: str) -> StreamingResponse:
    """Generate a JSON streaming response with metadata header."""
    output = {
        "_metadata": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "filename": filename,
            "format": "json",
        },
        "data": data,
    }
    content = json.dumps(output, indent=2, default=str)

    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

_PDF_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: A4;
    margin: 2cm;
    @top-right {{ content: "CONFIDENTIAL"; font-size: 9pt; color: #999; }}
    @bottom-center {{ content: "Page " counter(page) " of " counter(pages); font-size: 9pt; color: #999; }}
  }}
  body {{
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.5;
    color: #333;
  }}
  h1 {{ font-size: 24pt; color: #1a1a2e; margin-bottom: 0.2em; }}
  h2 {{ font-size: 16pt; color: #16213e; border-bottom: 2px solid #0f3460; padding-bottom: 0.2em; margin-top: 1.5em; }}
  h3 {{ font-size: 13pt; color: #0f3460; }}
  .cover {{
    text-align: center;
    padding-top: 8cm;
    page-break-after: always;
  }}
  .cover h1 {{ font-size: 32pt; color: #1a1a2e; }}
  .cover .subtitle {{ font-size: 14pt; color: #555; margin-top: 1em; }}
  .cover .date {{ font-size: 12pt; color: #777; margin-top: 2em; }}
  .cover .confidential {{
    margin-top: 4cm;
    font-size: 14pt;
    font-weight: bold;
    color: #c0392b;
    border: 2px solid #c0392b;
    display: inline-block;
    padding: 0.3em 1.5em;
  }}
  .toc {{ page-break-after: always; }}
  .toc ul {{ list-style: none; padding-left: 0; }}
  .toc li {{ padding: 0.3em 0; border-bottom: 1px dotted #ccc; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 1em 0;
    font-size: 10pt;
  }}
  th {{
    background: #0f3460;
    color: #fff;
    text-align: left;
    padding: 8px 10px;
  }}
  td {{
    padding: 6px 10px;
    border-bottom: 1px solid #ddd;
  }}
  tr:nth-child(even) td {{ background: #f8f9fa; }}
  .metric-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 1em;
    margin: 1em 0;
  }}
  .metric-card {{
    border: 1px solid #ddd;
    border-radius: 6px;
    padding: 1em;
    text-align: center;
  }}
  .metric-card .value {{ font-size: 20pt; font-weight: bold; color: #0f3460; }}
  .metric-card .label {{ font-size: 9pt; color: #777; text-transform: uppercase; }}
  .bar-chart {{ margin: 1em 0; }}
  .risk-badge {{
    display: inline-block;
    padding: 0.2em 0.8em;
    border-radius: 4px;
    font-weight: bold;
    color: #fff;
  }}
  .risk-low {{ background: #27ae60; }}
  .risk-moderate {{ background: #f39c12; }}
  .risk-high {{ background: #e67e22; }}
  .risk-critical {{ background: #e74c3c; }}
  .risk-severe {{ background: #8e44ad; }}
  .findings li, .recommendations li {{ margin-bottom: 0.5em; }}
</style>
</head>
<body>

<!-- Cover Page -->
<div class="cover">
  <h1>{report_title}</h1>
  <div class="subtitle">{campaign_name}</div>
  <div class="date">Generated: {generated_date}</div>
  <div class="confidential">CONFIDENTIAL</div>
</div>

<!-- Table of Contents -->
<div class="toc">
  <h2>Table of Contents</h2>
  <ul>
    <li>1. Executive Summary</li>
    <li>2. Campaign Metrics</li>
    <li>3. Department Breakdown</li>
    <li>4. Risk Assessment</li>
    <li>5. Key Findings</li>
    <li>6. Recommendations</li>
    <li>Appendix A: Event Timeline</li>
  </ul>
</div>

<!-- Executive Summary -->
<h2>1. Executive Summary</h2>
<p>
  Campaign <strong>{campaign_name}</strong> targeted <strong>{total_recipients}</strong> recipients.
  Of those, <strong>{delivered}</strong> emails were delivered, <strong>{clicked}</strong> recipients
  clicked the phishing link ({click_rate}%), and <strong>{submitted}</strong> submitted credentials
  ({submit_rate}%). The organisation risk level is
  <span class="risk-badge risk-{risk_level_lower}">{risk_level}</span>.
</p>

<!-- Campaign Metrics -->
<h2>2. Campaign Metrics</h2>
<div class="metric-grid">
  <div class="metric-card"><div class="value">{sent}</div><div class="label">Sent</div></div>
  <div class="metric-card"><div class="value">{delivered}</div><div class="label">Delivered</div></div>
  <div class="metric-card"><div class="value">{opened}</div><div class="label">Opened</div></div>
  <div class="metric-card"><div class="value">{clicked}</div><div class="label">Clicked</div></div>
  <div class="metric-card"><div class="value">{submitted}</div><div class="label">Submitted</div></div>
  <div class="metric-card"><div class="value">{reported}</div><div class="label">Reported</div></div>
</div>

<h3>Rates</h3>
<table>
  <tr><th>Metric</th><th>Value</th></tr>
  <tr><td>Open Rate</td><td>{open_rate}%</td></tr>
  <tr><td>Click Rate</td><td>{click_rate}%</td></tr>
  <tr><td>Submit Rate</td><td>{submit_rate}%</td></tr>
  <tr><td>Report Rate</td><td>{report_rate}%</td></tr>
</table>

{bar_chart_svg}

<!-- Department Breakdown -->
<h2>3. Department Breakdown</h2>
{department_table}

<!-- Risk Assessment -->
<h2>4. Risk Assessment</h2>
<p>
  Organisation Risk Score: <strong>{org_risk_score}</strong>
  <span class="risk-badge risk-{risk_level_lower}">{risk_level}</span>
</p>

<!-- Key Findings -->
<h2>5. Key Findings</h2>
<ul class="findings">
{findings_html}
</ul>

<!-- Recommendations -->
<h2>6. Recommendations</h2>
<ul class="recommendations">
{recommendations_html}
</ul>

<!-- Appendix -->
<h2>Appendix A: Event Timeline</h2>
{timeline_table}

</body>
</html>
"""


def _build_bar_chart_svg(metrics: dict) -> str:
    """Build an inline SVG horizontal bar chart for the key rates."""
    bars = [
        ("Open Rate", metrics.get("open_rate", 0), "#3498db"),
        ("Click Rate", metrics.get("click_rate", 0), "#e67e22"),
        ("Submit Rate", metrics.get("submit_rate", 0), "#e74c3c"),
        ("Report Rate", metrics.get("report_rate", 0), "#27ae60"),
    ]
    bar_height = 30
    gap = 10
    label_width = 100
    chart_width = 500
    total_height = len(bars) * (bar_height + gap) + gap

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{label_width + chart_width + 60}" height="{total_height}" '
        f'class="bar-chart">',
    ]
    for i, (label, value, colour) in enumerate(bars):
        y = gap + i * (bar_height + gap)
        bar_w = max(1, value / 100 * chart_width)
        lines.append(
            f'  <text x="0" y="{y + bar_height * 0.7}" '
            f'font-size="10" fill="#333">{label}</text>'
        )
        lines.append(
            f'  <rect x="{label_width}" y="{y}" width="{bar_w}" '
            f'height="{bar_height}" fill="{colour}" rx="3"/>'
        )
        lines.append(
            f'  <text x="{label_width + bar_w + 5}" y="{y + bar_height * 0.7}" '
            f'font-size="10" fill="#333">{value}%</text>'
        )
    lines.append("</svg>")
    return "\n".join(lines)


def _build_department_table(departments: list[dict]) -> str:
    """Build an HTML table for department breakdown."""
    if not departments:
        return "<p>No department data available.</p>"

    rows = []
    for d in departments:
        rows.append(
            f"  <tr><td>{d.get('name', '')}</td>"
            f"<td>{d.get('headcount', 0)}</td>"
            f"<td>{d.get('sent', 0)}</td>"
            f"<td>{d.get('clicked', 0)}</td>"
            f"<td>{d.get('submitted', 0)}</td>"
            f"<td>{d.get('risk_score', 0):.4f}</td></tr>"
        )

    return (
        "<table>\n"
        "  <tr><th>Department</th><th>Headcount</th><th>Sent</th>"
        "<th>Clicked</th><th>Submitted</th><th>Risk Score</th></tr>\n"
        + "\n".join(rows)
        + "\n</table>"
    )


def _build_timeline_table(timeline: list[dict]) -> str:
    """Build an HTML table for the events timeline."""
    if not timeline:
        return "<p>No timeline data available.</p>"

    rows = []
    for entry in timeline:
        rows.append(
            f"  <tr><td>{entry.get('timestamp', '')}</td>"
            f"<td>{entry.get('event_type', '')}</td>"
            f"<td>{entry.get('count', '')}</td></tr>"
        )

    return (
        "<table>\n"
        "  <tr><th>Timestamp</th><th>Event Type</th><th>Count</th></tr>\n"
        + "\n".join(rows)
        + "\n</table>"
    )


async def export_pdf(report_data: dict, report_type: str = "executive") -> bytes:
    """Generate a PDF from report data using WeasyPrint.

    Falls back to raw HTML bytes if WeasyPrint is not installed.
    """
    metrics = report_data.get("overall_metrics", {})
    summary = report_data.get("campaign_summary", {})
    risk = report_data.get("risk_assessment", {})
    departments = report_data.get("department_breakdown", [])
    findings = report_data.get("key_findings", [])
    recommendations = report_data.get("recommendations", [])
    timeline = report_data.get("events_timeline", [])

    risk_level_val = risk.get("risk_level", "Low")

    html = _PDF_TEMPLATE.format(
        report_title=f"Phishing Simulation {report_type.title()} Report",
        campaign_name=summary.get("name", "Unknown Campaign"),
        generated_date=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        total_recipients=summary.get("total_recipients", 0),
        sent=metrics.get("sent", 0),
        delivered=metrics.get("delivered", 0),
        opened=metrics.get("opened", 0),
        clicked=metrics.get("clicked", 0),
        submitted=metrics.get("submitted", 0),
        reported=metrics.get("reported", 0),
        open_rate=metrics.get("open_rate", 0),
        click_rate=metrics.get("click_rate", 0),
        submit_rate=metrics.get("submit_rate", 0),
        report_rate=metrics.get("report_rate", 0),
        risk_level=risk_level_val,
        risk_level_lower=risk_level_val.lower(),
        org_risk_score=risk.get("org_risk_score", 0),
        bar_chart_svg=_build_bar_chart_svg(metrics),
        department_table=_build_department_table(departments),
        findings_html="\n".join(f"  <li>{f}</li>" for f in findings),
        recommendations_html="\n".join(f"  <li>{r}</li>" for r in recommendations),
        timeline_table=_build_timeline_table(timeline),
    )

    try:
        from weasyprint import HTML as WeasyprintHTML
        pdf_bytes = WeasyprintHTML(string=html).write_pdf()
        return pdf_bytes
    except ImportError:
        # WeasyPrint not available; return HTML bytes as fallback.
        return html.encode("utf-8")
