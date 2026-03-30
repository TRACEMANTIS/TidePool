"""Tests for report generation and export endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


_AGGREGATOR_PATCH = "app.api.reports._aggregator"
_EXEC_GEN_PATCH = "app.api.reports._exec_gen"
_COMPLIANCE_GEN_PATCH = "app.api.reports._compliance_gen"


def _make_mock_metrics(campaign_id: int = 1):
    """Create a mock CampaignMetrics result."""
    m = MagicMock()
    m.campaign_id = campaign_id
    m.total_recipients = 100
    m.sent = 98
    m.delivered = 95
    m.opened = 60
    m.clicked = 25
    m.submitted = 10
    m.reported = 5
    m.open_rate = 0.63
    m.click_rate = 0.26
    m.submit_rate = 0.11
    m.report_rate = 0.05
    m.time_to_first_click_median = None
    m.time_to_first_click_p90 = None
    m.sends_by_hour = {9: 20, 10: 30, 11: 25, 12: 23}
    m.events_timeline = [
        {"timestamp": "2026-01-15T09:00:00Z", "type": "SENT", "count": 98},
        {"timestamp": "2026-01-15T10:00:00Z", "type": "OPENED", "count": 60},
    ]
    return m


def _make_mock_dept_metrics():
    """Create mock department metrics."""
    depts = []
    for name, risk in [("Engineering", 0.15), ("Sales", 0.45), ("HR", 0.30)]:
        d = MagicMock()
        d.name = name
        d.headcount = 30
        d.sent = 28
        d.opened = int(28 * (risk + 0.2))
        d.clicked = int(28 * risk)
        d.submitted = int(28 * risk * 0.5)
        d.reported = 2
        d.risk_score = risk
        depts.append(d)
    return depts


# ---------------------------------------------------------------------------
# Campaign metrics
# ---------------------------------------------------------------------------


class TestCampaignMetrics:
    """Tests for GET /api/v1/reports/campaigns/{id}/metrics."""

    @patch(_AGGREGATOR_PATCH)
    async def test_campaign_metrics(
        self,
        mock_aggregator,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Returns correct aggregate counts for a campaign."""
        mock_aggregator.get_campaign_metrics = AsyncMock(
            return_value=_make_mock_metrics(1)
        )

        resp = await client.get(
            "/api/v1/reports/campaigns/1/metrics",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        body = resp.json()
        assert body["campaign_id"] == 1
        assert body["total_recipients"] == 100
        assert body["sent"] == 98
        assert body["opened"] == 60
        assert body["clicked"] == 25
        assert body["submitted"] == 10
        assert body["reported"] == 5
        assert body["open_rate"] == pytest.approx(0.63, abs=0.01)
        assert body["click_rate"] == pytest.approx(0.26, abs=0.01)
        assert isinstance(body["sends_by_hour"], dict)
        assert isinstance(body["events_timeline"], list)


# ---------------------------------------------------------------------------
# Department metrics
# ---------------------------------------------------------------------------


class TestDepartmentMetrics:
    """Tests for GET /api/v1/reports/campaigns/{id}/departments."""

    @patch(_AGGREGATOR_PATCH)
    async def test_department_metrics(
        self,
        mock_aggregator,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Returns per-department breakdown sorted by risk score."""
        mock_aggregator.get_department_metrics = AsyncMock(
            return_value=_make_mock_dept_metrics()
        )

        resp = await client.get(
            "/api/v1/reports/campaigns/1/departments",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 3

        # Verify each department has the expected fields.
        for dept in body:
            assert "name" in dept
            assert "headcount" in dept
            assert "sent" in dept
            assert "opened" in dept
            assert "clicked" in dept
            assert "submitted" in dept
            assert "risk_score" in dept

        dept_names = [d["name"] for d in body]
        assert "Engineering" in dept_names
        assert "Sales" in dept_names


# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------


class TestRiskScoring:
    """Tests for risk score calculation consistency."""

    @patch(_AGGREGATOR_PATCH)
    async def test_risk_scoring(
        self,
        mock_aggregator,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Verify risk scores are numeric and within valid range."""
        mock_aggregator.get_department_metrics = AsyncMock(
            return_value=_make_mock_dept_metrics()
        )

        resp = await client.get(
            "/api/v1/reports/campaigns/1/departments",
            headers=auth_headers,
        )
        body = resp.json()

        for dept in body:
            score = dept["risk_score"]
            assert isinstance(score, (int, float))
            assert 0.0 <= score <= 1.0, (
                f"Risk score {score} for {dept['name']} is outside [0, 1]"
            )


# ---------------------------------------------------------------------------
# Executive report
# ---------------------------------------------------------------------------


class TestExecutiveReport:
    """Tests for GET /api/v1/reports/campaigns/{id}/executive."""

    @patch(_EXEC_GEN_PATCH)
    async def test_executive_report(
        self,
        mock_exec_gen,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Executive report generates a response with all expected sections."""
        mock_exec_gen.generate = AsyncMock(return_value={
            "campaign_id": 1,
            "campaign_name": "Q1 Assessment",
            "executive_summary": "Overall risk is moderate.",
            "total_recipients": 100,
            "open_rate": 0.63,
            "click_rate": 0.26,
            "submit_rate": 0.11,
            "recommendations": [
                "Increase phishing awareness training for Sales.",
                "Implement MFA across all departments.",
            ],
            "department_breakdown": [
                {"name": "Sales", "risk_score": 0.45},
                {"name": "HR", "risk_score": 0.30},
            ],
        })

        resp = await client.get(
            "/api/v1/reports/campaigns/1/executive",
            headers=auth_headers,
        )
        assert resp.status_code == 200

        body = resp.json()
        assert "campaign_id" in body
        assert "executive_summary" in body
        assert "recommendations" in body
        assert isinstance(body["recommendations"], list)
        assert "department_breakdown" in body


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


class TestCSVExport:
    """Tests for GET /api/v1/reports/campaigns/{id}/export/csv."""

    @patch(_AGGREGATOR_PATCH)
    async def test_csv_export(
        self,
        mock_aggregator,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """CSV export returns a valid streaming CSV response."""
        mock_aggregator.get_campaign_metrics = AsyncMock(
            return_value=_make_mock_metrics(1)
        )
        mock_aggregator.get_department_metrics = AsyncMock(
            return_value=_make_mock_dept_metrics()
        )

        # Patch the export_csv to return a StreamingResponse.
        with patch("app.api.reports.export_csv") as mock_csv:
            from starlette.responses import StreamingResponse

            csv_content = "department,headcount,sent,opened\nEngineering,30,28,10\n"

            async def fake_csv(rows, filename):
                return StreamingResponse(
                    iter([csv_content]),
                    media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'},
                )

            mock_csv.side_effect = fake_csv

            resp = await client.get(
                "/api/v1/reports/campaigns/1/export/csv",
                headers=auth_headers,
            )
            assert resp.status_code == 200
            assert "text/csv" in resp.headers.get("content-type", "")
            assert "department" in resp.text


# ---------------------------------------------------------------------------
# Compliance package
# ---------------------------------------------------------------------------


class TestCompliancePackage:
    """Tests for POST /api/v1/reports/campaigns/{id}/compliance-package."""

    @patch(_COMPLIANCE_GEN_PATCH)
    async def test_compliance_package(
        self,
        mock_compliance_gen,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Compliance package returns a ZIP file."""
        # Create a minimal valid ZIP.
        import zipfile
        import io

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("summary.json", '{"campaign_id": 1}')
            zf.writestr("metrics.csv", "department,risk_score\nSales,0.45\n")
            zf.writestr("timeline.json", "[]")
        zip_bytes = buf.getvalue()

        mock_compliance_gen.export_package = AsyncMock(return_value=zip_bytes)

        resp = await client.post(
            "/api/v1/reports/campaigns/1/compliance-package",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

        # Verify the response is a valid ZIP.
        result_buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(result_buf, "r") as zf:
            names = zf.namelist()
            assert "summary.json" in names
            assert "metrics.csv" in names
