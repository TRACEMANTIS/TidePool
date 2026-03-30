"""Reports router -- campaign metrics, executive summaries, exports, and compliance."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.reports.aggregator import MetricsAggregator
from app.reports.compliance import CompliancePackageGenerator
from app.reports.executive import ExecutiveReportGenerator
from app.reports.export import export_csv, export_json, export_pdf
from app.schemas.reports import (
    CampaignMetricsResponse,
    DepartmentMetricsResponse,
    OrgRiskResponse,
    TrendResponse,
)

router = APIRouter(prefix="/reports")

_aggregator = MetricsAggregator()
_exec_gen = ExecutiveReportGenerator()
_compliance_gen = CompliancePackageGenerator()


# ---------------------------------------------------------------------------
# Campaign metrics
# ---------------------------------------------------------------------------

@router.get("/campaigns/{campaign_id}/metrics", response_model=CampaignMetricsResponse)
async def campaign_metrics(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> CampaignMetricsResponse:
    """Return aggregate metrics for a single campaign."""
    m = await _aggregator.get_campaign_metrics(campaign_id, db)
    return CampaignMetricsResponse(
        campaign_id=m.campaign_id,
        total_recipients=m.total_recipients,
        sent=m.sent,
        delivered=m.delivered,
        opened=m.opened,
        clicked=m.clicked,
        submitted=m.submitted,
        reported=m.reported,
        open_rate=m.open_rate,
        click_rate=m.click_rate,
        submit_rate=m.submit_rate,
        report_rate=m.report_rate,
        time_to_first_click_median_seconds=(
            m.time_to_first_click_median.total_seconds()
            if m.time_to_first_click_median else None
        ),
        time_to_first_click_p90_seconds=(
            m.time_to_first_click_p90.total_seconds()
            if m.time_to_first_click_p90 else None
        ),
        sends_by_hour=m.sends_by_hour,
        events_timeline=m.events_timeline,
    )


# ---------------------------------------------------------------------------
# Department breakdown
# ---------------------------------------------------------------------------

@router.get(
    "/campaigns/{campaign_id}/departments",
    response_model=list[DepartmentMetricsResponse],
)
async def department_metrics(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[DepartmentMetricsResponse]:
    """Return per-department metrics for a campaign, sorted by risk score."""
    depts = await _aggregator.get_department_metrics(campaign_id, db)
    return [
        DepartmentMetricsResponse(
            name=d.name,
            headcount=d.headcount,
            sent=d.sent,
            opened=d.opened,
            clicked=d.clicked,
            submitted=d.submitted,
            reported=d.reported,
            risk_score=d.risk_score,
        )
        for d in depts
    ]


# ---------------------------------------------------------------------------
# Executive summary
# ---------------------------------------------------------------------------

@router.get("/campaigns/{campaign_id}/executive")
async def executive_summary(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict:
    """Return an executive-level summary report for a campaign."""
    return await _exec_gen.generate(campaign_id, db)


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

@router.get("/campaigns/{campaign_id}/export/pdf")
async def export_campaign_pdf(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    """Generate and download a PDF report for the campaign."""
    report_data = await _exec_gen.generate(campaign_id, db)

    # Attach timeline for the appendix
    metrics = await _aggregator.get_campaign_metrics(campaign_id, db)
    report_data["events_timeline"] = metrics.events_timeline

    pdf_bytes = await export_pdf(report_data, "executive")

    # Detect content type: WeasyPrint produces real PDF, fallback is HTML
    content_type = "application/pdf"
    filename = f"campaign_{campaign_id}_report.pdf"
    if pdf_bytes[:5] != b"%PDF-":
        content_type = "text/html"
        filename = f"campaign_{campaign_id}_report.html"

    return Response(
        content=pdf_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------

@router.get("/campaigns/{campaign_id}/export/csv")
async def export_campaign_csv(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Export campaign metrics as CSV."""
    m = await _aggregator.get_campaign_metrics(campaign_id, db)
    depts = await _aggregator.get_department_metrics(campaign_id, db)

    rows = [
        {
            "department": d.name,
            "headcount": d.headcount,
            "sent": d.sent,
            "opened": d.opened,
            "clicked": d.clicked,
            "submitted": d.submitted,
            "reported": d.reported,
            "risk_score": d.risk_score,
        }
        for d in depts
    ]

    # Add a summary row
    rows.append({
        "department": "TOTAL",
        "headcount": m.total_recipients,
        "sent": m.sent,
        "opened": m.opened,
        "clicked": m.clicked,
        "submitted": m.submitted,
        "reported": m.reported,
        "risk_score": "",
    })

    return await export_csv(rows, f"campaign_{campaign_id}_metrics.csv")


# ---------------------------------------------------------------------------
# Compliance package
# ---------------------------------------------------------------------------

@router.post("/campaigns/{campaign_id}/compliance-package")
async def generate_compliance_package(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> Response:
    """Generate and download a compliance evidence ZIP archive."""
    zip_bytes = await _compliance_gen.export_package(campaign_id, db)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="campaign_{campaign_id}_compliance.zip"'
            ),
        },
    )


# ---------------------------------------------------------------------------
# Trend analysis
# ---------------------------------------------------------------------------

@router.get("/trend", response_model=TrendResponse)
async def trend_analysis(
    campaign_ids: str = Query(..., description="Comma-separated campaign IDs"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> TrendResponse:
    """Return trend analysis across multiple campaigns."""
    ids = _parse_id_list(campaign_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="At least one campaign ID required.")

    trend = await _aggregator.get_trend_metrics(ids, db)
    return TrendResponse(
        campaigns=[
            {
                "campaign_id": c["campaign_id"],
                "name": c["name"],
                "date": c.get("date"),
                "open_rate": c["open_rate"],
                "click_rate": c["click_rate"],
                "submit_rate": c["submit_rate"],
            }
            for c in trend.campaigns
        ],
        trend_direction=trend.trend_direction,
    )


# ---------------------------------------------------------------------------
# Organisation risk score
# ---------------------------------------------------------------------------

@router.get("/org-risk", response_model=OrgRiskResponse)
async def org_risk_score(
    campaign_ids: str = Query(..., description="Comma-separated campaign IDs"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> OrgRiskResponse:
    """Return the organisation-wide risk score across specified campaigns."""
    ids = _parse_id_list(campaign_ids)
    if not ids:
        raise HTTPException(status_code=400, detail="At least one campaign ID required.")

    risk = await _aggregator.get_org_risk_score(ids, db)
    return OrgRiskResponse(
        org_risk_score=risk.org_risk_score,
        risk_level=risk.risk_level,
        department_rankings=[
            {
                "name": d["name"],
                "risk_score": d["risk_score"],
                "headcount": d["headcount"],
            }
            for d in risk.department_rankings
        ],
        improvement_delta=risk.improvement_delta,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_id_list(ids_str: str) -> list[int]:
    """Parse a comma-separated string of IDs into a list of ints."""
    result = []
    for part in ids_str.split(","):
        part = part.strip()
        if part.isdigit():
            result.append(int(part))
    return result
