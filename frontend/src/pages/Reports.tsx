import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getExecutiveSummary,
  getTrend,
  exportPdf,
  exportCsv,
  generateCompliancePackage,
  getDepartmentMetrics,
} from "@/api/reports";
import { listCampaigns } from "@/api/campaigns";
import type {
  ExecutiveSummary,
  TrendData,
  DepartmentMetrics,
  Campaign,
  PaginatedResponse,
} from "@/types";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

function RiskGauge({ score, level }: { score: number; level: string }) {
  const colors: Record<string, string> = {
    low: "text-green-500",
    medium: "text-yellow-500",
    high: "text-orange-500",
    critical: "text-red-500",
  };
  const bgColors: Record<string, string> = {
    low: "bg-green-50 border-green-200",
    medium: "bg-yellow-50 border-yellow-200",
    high: "bg-orange-50 border-orange-200",
    critical: "bg-red-50 border-red-200",
  };
  return (
    <div
      className={`flex flex-col items-center justify-center p-6 rounded-lg border ${
        bgColors[level] ?? bgColors.low
      }`}
    >
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">
        Organization Risk Score
      </p>
      <p className={`text-5xl font-bold ${colors[level] ?? colors.low}`}>
        {score}
      </p>
      <p className="text-sm text-slate-600 mt-1 uppercase font-medium">
        {level}
      </p>
    </div>
  );
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function ReportList() {
  const [selectedCampaign, setSelectedCampaign] = useState<string>("");
  const [exporting, setExporting] = useState<string | null>(null);

  const campaignsQuery = useQuery<PaginatedResponse<Campaign>>({
    queryKey: ["campaigns-for-reports"],
    queryFn: () => listCampaigns({ page: 1, page_size: 100 }),
  });

  const summaryQuery = useQuery<ExecutiveSummary>({
    queryKey: ["executive-summary"],
    queryFn: getExecutiveSummary,
  });

  const trendQuery = useQuery<TrendData[]>({
    queryKey: ["trend"],
    queryFn: getTrend,
  });

  const departmentQuery = useQuery<DepartmentMetrics[]>({
    queryKey: ["department-metrics", selectedCampaign],
    queryFn: () => getDepartmentMetrics(selectedCampaign || undefined),
  });

  const campaigns = campaignsQuery.data?.items ?? [];
  const summary = summaryQuery.data;
  const trendData = trendQuery.data ?? [];
  const departments = departmentQuery.data ?? [];

  async function handleExportPdf() {
    if (!selectedCampaign) return;
    setExporting("pdf");
    try {
      const blob = await exportPdf(selectedCampaign);
      downloadBlob(blob, `report-${selectedCampaign}.pdf`);
    } finally {
      setExporting(null);
    }
  }

  async function handleExportCsv() {
    if (!selectedCampaign) return;
    setExporting("csv");
    try {
      const blob = await exportCsv(selectedCampaign);
      downloadBlob(blob, `report-${selectedCampaign}.csv`);
    } finally {
      setExporting(null);
    }
  }

  async function handleCompliancePackage() {
    if (!selectedCampaign) return;
    setExporting("compliance");
    try {
      const blob = await generateCompliancePackage(selectedCampaign);
      downloadBlob(blob, `compliance-${selectedCampaign}.zip`);
    } finally {
      setExporting(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Reports</h1>
          <p className="text-sm text-slate-500 mt-1">
            Generate and download campaign reports and analytics.
          </p>
        </div>
      </div>

      {/* Campaign selector and report types */}
      <div className="flex items-center gap-4 flex-wrap">
        <div>
          <label className="block text-xs text-slate-500 mb-1">
            Campaign
          </label>
          <select
            value={selectedCampaign}
            onChange={(e) => setSelectedCampaign(e.target.value)}
            className="px-3 py-2 border border-slate-300 rounded-md text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500 w-64"
          >
            <option value="">All Campaigns</option>
            {campaigns.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>

        {/* Report type badges */}
        <div className="flex gap-2 items-end pt-4">
          <span className="px-3 py-1.5 text-xs font-medium bg-sky-100 text-sky-700 rounded-full">
            Executive Summary
          </span>
          <span className="px-3 py-1.5 text-xs font-medium bg-purple-100 text-purple-700 rounded-full">
            Department Breakdown
          </span>
          <span className="px-3 py-1.5 text-xs font-medium bg-green-100 text-green-700 rounded-full">
            Trend Analysis
          </span>
          <span className="px-3 py-1.5 text-xs font-medium bg-amber-100 text-amber-700 rounded-full">
            Compliance Package
          </span>
        </div>
      </div>

      {/* Executive summary preview */}
      {summary && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <RiskGauge
            score={summary.org_risk.score}
            level={summary.org_risk.level}
          />
          <div className="lg:col-span-2 bg-white rounded-lg border border-slate-200 p-5">
            <h3 className="text-sm font-semibold text-slate-900 mb-3">
              Key Metrics
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div>
                <p className="text-xs text-slate-500">Total Campaigns</p>
                <p className="text-xl font-bold text-slate-900">
                  {summary.total_campaigns}
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Emails Sent</p>
                <p className="text-xl font-bold text-slate-900">
                  {summary.total_emails_sent.toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Avg Open Rate</p>
                <p className="text-xl font-bold text-blue-600">
                  {summary.avg_open_rate.toFixed(1)}%
                </p>
              </div>
              <div>
                <p className="text-xs text-slate-500">Avg Click Rate</p>
                <p className="text-xl font-bold text-amber-600">
                  {summary.avg_click_rate.toFixed(1)}%
                </p>
              </div>
            </div>

            {summary.org_risk.top_risk_departments.length > 0 && (
              <div className="mt-4 pt-4 border-t border-slate-100">
                <p className="text-xs font-medium text-slate-500 mb-2">
                  Top Risk Departments
                </p>
                <div className="flex flex-wrap gap-2">
                  {summary.org_risk.top_risk_departments.map((d) => (
                    <span
                      key={d.department}
                      className="px-2 py-1 text-xs bg-red-50 text-red-700 rounded-md"
                    >
                      {d.department}: {d.score}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Export buttons */}
      <div className="bg-white rounded-lg border border-slate-200 p-5">
        <h3 className="text-sm font-semibold text-slate-900 mb-3">
          Export Reports
        </h3>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={handleExportPdf}
            disabled={!selectedCampaign || exporting === "pdf"}
            className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 disabled:opacity-50 cursor-pointer"
          >
            {exporting === "pdf" ? "Generating..." : "Download PDF"}
          </button>
          <button
            onClick={handleExportCsv}
            disabled={!selectedCampaign || exporting === "csv"}
            className="px-4 py-2 text-sm font-medium text-slate-700 border border-slate-300 rounded-md hover:bg-slate-50 disabled:opacity-50 cursor-pointer"
          >
            {exporting === "csv" ? "Generating..." : "Download CSV"}
          </button>
          <button
            onClick={handleCompliancePackage}
            disabled={!selectedCampaign || exporting === "compliance"}
            className="px-4 py-2 text-sm font-medium text-slate-700 border border-slate-300 rounded-md hover:bg-slate-50 disabled:opacity-50 cursor-pointer"
          >
            {exporting === "compliance"
              ? "Generating..."
              : "Generate Compliance Package (ZIP)"}
          </button>
        </div>
        {!selectedCampaign && (
          <p className="text-xs text-slate-400 mt-2">
            Select a campaign above to enable exports.
          </p>
        )}
      </div>

      {/* Trend chart */}
      {trendData.length > 0 && (
        <div className="bg-white rounded-lg border border-slate-200 p-5">
          <h3 className="text-sm font-semibold text-slate-900 mb-4">
            Click Rate Trend Across Campaigns
          </h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="campaign_name" tick={{ fontSize: 11 }} angle={-20} textAnchor="end" height={60} />
              <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `${v}%`} />
              <Tooltip formatter={(v: number) => `${v.toFixed(1)}%`} />
              <Legend />
              <Line
                type="monotone"
                dataKey="click_rate"
                stroke="#f59e0b"
                strokeWidth={2}
                name="Click Rate"
                dot={{ r: 4 }}
              />
              <Line
                type="monotone"
                dataKey="open_rate"
                stroke="#3b82f6"
                strokeWidth={2}
                name="Open Rate"
                dot={{ r: 4 }}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Department risk heatmap */}
      {departments.length > 0 && (
        <div className="bg-white rounded-lg border border-slate-200 p-5">
          <h3 className="text-sm font-semibold text-slate-900 mb-4">
            Department Risk Heatmap
          </h3>
          <div className="space-y-2">
            {departments
              .sort((a, b) => b.risk_score - a.risk_score)
              .map((d) => {
                const bgColor =
                  d.risk_score >= 75
                    ? "bg-red-400"
                    : d.risk_score >= 50
                      ? "bg-orange-400"
                      : d.risk_score >= 25
                        ? "bg-yellow-400"
                        : "bg-green-400";
                return (
                  <div key={d.department} className="flex items-center gap-3">
                    <span className="text-sm text-slate-700 w-32 text-right truncate">
                      {d.department}
                    </span>
                    <div className="flex-1 h-7 bg-slate-100 rounded overflow-hidden relative">
                      <div
                        className={`h-full rounded ${bgColor} transition-all`}
                        style={{ width: `${d.risk_score}%` }}
                      />
                      <span className="absolute inset-0 flex items-center px-2 text-xs font-medium text-slate-900">
                        {d.risk_score} -- Open: {d.open_rate.toFixed(1)}% | Click:{" "}
                        {d.click_rate.toFixed(1)}% | Submit:{" "}
                        {d.submit_rate.toFixed(1)}%
                      </span>
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
}
