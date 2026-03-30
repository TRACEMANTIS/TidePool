import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getCampaign, startCampaign, pauseCampaign } from "@/api/campaigns";
import { getCampaignMetrics } from "@/api/reports";
import { getEventFeed } from "@/api/monitor";
import type {
  Campaign,
  CampaignStatus,
  CampaignMetrics,
  EventFeedItem,
  CampaignRecipient,
  DepartmentMetrics,
} from "@/types";
import apiClient from "@/api/client";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const tabs = ["Overview", "Recipients", "Results", "Timeline"];

const STATUS_STYLES: Record<CampaignStatus, string> = {
  draft: "bg-slate-100 text-slate-600",
  scheduled: "bg-blue-100 text-blue-700",
  running: "bg-green-100 text-green-700",
  paused: "bg-yellow-100 text-yellow-700",
  completed: "bg-indigo-100 text-indigo-700",
  cancelled: "bg-red-100 text-red-700",
};

function StatusBadge({ status }: { status: CampaignStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium uppercase tracking-wide ${STATUS_STYLES[status]}`}
    >
      {status === "running" && (
        <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
      )}
      {status}
    </span>
  );
}

function MetricCard({
  label,
  value,
  rate,
  color,
}: {
  label: string;
  value: number;
  rate?: number;
  color: string;
}) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <p className="text-xs font-medium text-slate-500 uppercase tracking-wide">
        {label}
      </p>
      <p className={`text-2xl font-bold mt-1 ${color}`}>{value}</p>
      {rate !== undefined && (
        <p className="text-xs text-slate-400 mt-0.5">{rate.toFixed(1)}%</p>
      )}
    </div>
  );
}

function FunnelBar({
  label,
  value,
  total,
  color,
}: {
  label: string;
  value: number;
  total: number;
  color: string;
}) {
  const pct = total > 0 ? (value / total) * 100 : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-slate-500 w-20 text-right">{label}</span>
      <div className="flex-1 h-6 bg-slate-100 rounded overflow-hidden">
        <div
          className={`h-full rounded ${color} transition-all`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-slate-600 w-16">
        {value} ({pct.toFixed(1)}%)
      </span>
    </div>
  );
}

export default function CampaignDetail() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState("Overview");
  const [recipientSearch, setRecipientSearch] = useState("");
  const [timelineFilter, setTimelineFilter] = useState("");

  const campaignQuery = useQuery<Campaign>({
    queryKey: ["campaign", id],
    queryFn: () => getCampaign(id!),
    enabled: !!id,
    refetchInterval: 10000,
  });

  const metricsQuery = useQuery<CampaignMetrics>({
    queryKey: ["campaign-metrics", id],
    queryFn: () => getCampaignMetrics(id!),
    enabled: !!id && activeTab !== "Timeline",
  });

  const recipientsQuery = useQuery<{ items: CampaignRecipient[] }>({
    queryKey: ["campaign-recipients", id, recipientSearch],
    queryFn: () =>
      apiClient
        .get(`/campaigns/${id}/recipients`, {
          params: { search: recipientSearch || undefined },
        })
        .then((r) => r.data),
    enabled: !!id && activeTab === "Recipients",
  });

  const departmentQuery = useQuery<DepartmentMetrics[]>({
    queryKey: ["campaign-departments", id],
    queryFn: () =>
      apiClient
        .get(`/reports/departments`, { params: { campaign_id: id } })
        .then((r) => r.data),
    enabled: !!id && activeTab === "Results",
  });

  const timelineQuery = useQuery<EventFeedItem[]>({
    queryKey: ["campaign-timeline", id, timelineFilter],
    queryFn: () =>
      getEventFeed({
        campaign_id: id,
        event_type: timelineFilter || undefined,
        limit: 100,
      }),
    enabled: !!id && activeTab === "Timeline",
    refetchInterval:
      campaignQuery.data?.status === "running" ? 5000 : false,
  });

  const startMutation = useMutation({
    mutationFn: () => startCampaign(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["campaign", id] }),
  });

  const pauseMutation = useMutation({
    mutationFn: () => pauseCampaign(id!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["campaign", id] }),
  });

  const resumeMutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/campaigns/${id}/resume`).then((r) => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["campaign", id] }),
  });

  const completeMutation = useMutation({
    mutationFn: () =>
      apiClient.post(`/campaigns/${id}/complete`).then((r) => r.data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["campaign", id] }),
  });

  const campaign = campaignQuery.data;
  const metrics = metricsQuery.data;
  const recipients = recipientsQuery.data?.items ?? [];
  const departments = departmentQuery.data ?? [];
  const timeline = timelineQuery.data ?? [];
  const stats = campaign?.stats;

  function actionButtons() {
    if (!campaign) return null;
    const s = campaign.status;
    return (
      <div className="flex gap-2">
        {(s === "draft" || s === "scheduled") && (
          <button
            onClick={() => startMutation.mutate()}
            disabled={startMutation.isPending}
            className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700 cursor-pointer disabled:opacity-50"
          >
            Start
          </button>
        )}
        {s === "running" && (
          <button
            onClick={() => pauseMutation.mutate()}
            disabled={pauseMutation.isPending}
            className="px-4 py-2 text-sm font-medium text-slate-700 border border-slate-300 rounded-md hover:bg-slate-50 cursor-pointer disabled:opacity-50"
          >
            Pause
          </button>
        )}
        {s === "paused" && (
          <>
            <button
              onClick={() => resumeMutation.mutate()}
              disabled={resumeMutation.isPending}
              className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700 cursor-pointer disabled:opacity-50"
            >
              Resume
            </button>
            <button
              onClick={() => completeMutation.mutate()}
              disabled={completeMutation.isPending}
              className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 cursor-pointer disabled:opacity-50"
            >
              Complete
            </button>
          </>
        )}
        {s === "running" && (
          <button
            onClick={() => completeMutation.mutate()}
            disabled={completeMutation.isPending}
            className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 cursor-pointer disabled:opacity-50"
          >
            Complete
          </button>
        )}
      </div>
    );
  }

  if (campaignQuery.isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-400">
        Loading campaign...
      </div>
    );
  }

  if (!campaign) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-400">
        Campaign not found.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-sm text-slate-500 mb-2">
          <Link to="/campaigns" className="hover:text-slate-700">
            Campaigns
          </Link>
          <span>/</span>
          <span className="text-slate-900">{campaign.name}</span>
        </div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-slate-900">
              {campaign.name}
            </h1>
            <StatusBadge status={campaign.status} />
          </div>
          {actionButtons()}
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-slate-200">
        <div className="flex gap-0">
          {tabs.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors cursor-pointer ${
                activeTab === tab
                  ? "border-sky-600 text-sky-600"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      {activeTab === "Overview" && (
        <div className="space-y-6">
          {/* Metric cards */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            <MetricCard
              label="Sent"
              value={stats?.emails_sent ?? 0}
              rate={
                stats && stats.total_recipients > 0
                  ? (stats.emails_sent / stats.total_recipients) * 100
                  : undefined
              }
              color="text-slate-900"
            />
            <MetricCard
              label="Opened"
              value={stats?.emails_opened ?? 0}
              rate={metrics?.open_rate}
              color="text-blue-600"
            />
            <MetricCard
              label="Clicked"
              value={stats?.links_clicked ?? 0}
              rate={metrics?.click_rate}
              color="text-amber-600"
            />
            <MetricCard
              label="Submitted"
              value={stats?.credentials_submitted ?? 0}
              rate={metrics?.submit_rate}
              color="text-red-600"
            />
            <MetricCard
              label="Reported"
              value={stats?.reported ?? 0}
              rate={metrics?.report_rate}
              color="text-green-600"
            />
          </div>

          {/* Funnel */}
          <div className="bg-white rounded-lg border border-slate-200 p-5">
            <h3 className="text-sm font-semibold text-slate-900 mb-4">
              Engagement Funnel
            </h3>
            <div className="space-y-3">
              <FunnelBar
                label="Sent"
                value={stats?.emails_sent ?? 0}
                total={stats?.total_recipients ?? 1}
                color="bg-slate-400"
              />
              <FunnelBar
                label="Opened"
                value={stats?.emails_opened ?? 0}
                total={stats?.total_recipients ?? 1}
                color="bg-blue-400"
              />
              <FunnelBar
                label="Clicked"
                value={stats?.links_clicked ?? 0}
                total={stats?.total_recipients ?? 1}
                color="bg-amber-400"
              />
              <FunnelBar
                label="Submitted"
                value={stats?.credentials_submitted ?? 0}
                total={stats?.total_recipients ?? 1}
                color="bg-red-400"
              />
            </div>
          </div>

          {/* Time-to-click distribution */}
          {metrics?.time_to_click_distribution &&
            metrics.time_to_click_distribution.length > 0 && (
              <div className="bg-white rounded-lg border border-slate-200 p-5">
                <h3 className="text-sm font-semibold text-slate-900 mb-4">
                  Time-to-Click Distribution
                </h3>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={metrics.time_to_click_distribution}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis dataKey="bucket" tick={{ fontSize: 12 }} />
                    <YAxis tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
        </div>
      )}

      {activeTab === "Recipients" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <input
              type="text"
              value={recipientSearch}
              onChange={(e) => setRecipientSearch(e.target.value)}
              placeholder="Search recipients..."
              className="px-3 py-2 border border-slate-300 rounded-md text-sm w-64 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
            />
            <button
              onClick={() => {
                window.open(
                  `/api/v1/campaigns/${id}/recipients/export`,
                  "_blank"
                );
              }}
              className="px-3 py-2 text-sm font-medium text-slate-700 border border-slate-300 rounded-md hover:bg-slate-50 cursor-pointer"
            >
              Export Selected
            </button>
          </div>

          <div className="bg-white rounded-lg border border-slate-200">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="px-5 py-3 font-medium">Name</th>
                  <th className="px-5 py-3 font-medium">Email</th>
                  <th className="px-5 py-3 font-medium">Department</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Events</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {recipientsQuery.isLoading ? (
                  <tr>
                    <td className="px-5 py-12 text-center text-slate-400" colSpan={5}>
                      Loading recipients...
                    </td>
                  </tr>
                ) : recipients.length === 0 ? (
                  <tr>
                    <td className="px-5 py-12 text-center text-slate-400" colSpan={5}>
                      No recipients found.
                    </td>
                  </tr>
                ) : (
                  recipients.map((r) => {
                    const statusColors: Record<string, string> = {
                      pending: "bg-slate-100 text-slate-600",
                      sent: "bg-blue-100 text-blue-700",
                      opened: "bg-sky-100 text-sky-700",
                      clicked: "bg-amber-100 text-amber-700",
                      submitted: "bg-red-100 text-red-700",
                      reported: "bg-green-100 text-green-700",
                    };
                    return (
                      <tr key={r.id} className="hover:bg-slate-50">
                        <td className="px-5 py-3 font-medium text-slate-900">
                          {r.first_name} {r.last_name}
                        </td>
                        <td className="px-5 py-3 text-slate-600">{r.email}</td>
                        <td className="px-5 py-3 text-slate-600">
                          {r.department}
                        </td>
                        <td className="px-5 py-3">
                          <span
                            className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                              statusColors[r.status] || statusColors.pending
                            }`}
                          >
                            {r.status}
                          </span>
                        </td>
                        <td className="px-5 py-3 text-xs text-slate-500">
                          {r.events.length} events
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === "Results" && (
        <div className="space-y-6">
          {/* Department breakdown */}
          <div className="bg-white rounded-lg border border-slate-200 p-5">
            <h3 className="text-sm font-semibold text-slate-900 mb-4">
              Department Breakdown
            </h3>
            {departments.length === 0 ? (
              <p className="text-sm text-slate-400">No department data available yet.</p>
            ) : (
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-slate-500 border-b border-slate-100">
                    <th className="pb-2 font-medium">Department</th>
                    <th className="pb-2 font-medium">Sent</th>
                    <th className="pb-2 font-medium">Opened</th>
                    <th className="pb-2 font-medium">Clicked</th>
                    <th className="pb-2 font-medium">Submitted</th>
                    <th className="pb-2 font-medium">Risk Score</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-50">
                  {departments.map((d) => {
                    const riskColor =
                      d.risk_score >= 75
                        ? "text-red-600 bg-red-50"
                        : d.risk_score >= 50
                          ? "text-orange-600 bg-orange-50"
                          : d.risk_score >= 25
                            ? "text-yellow-600 bg-yellow-50"
                            : "text-green-600 bg-green-50";
                    return (
                      <tr key={d.department}>
                        <td className="py-2 font-medium text-slate-900">
                          {d.department}
                        </td>
                        <td className="py-2 text-slate-600">{d.emails_sent}</td>
                        <td className="py-2 text-slate-600">
                          {d.opened} ({d.open_rate.toFixed(1)}%)
                        </td>
                        <td className="py-2 text-slate-600">
                          {d.clicked} ({d.click_rate.toFixed(1)}%)
                        </td>
                        <td className="py-2 text-slate-600">
                          {d.submitted} ({d.submit_rate.toFixed(1)}%)
                        </td>
                        <td className="py-2">
                          <span
                            className={`inline-flex px-2 py-0.5 rounded-full text-xs font-bold ${riskColor}`}
                          >
                            {d.risk_score}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* Click rate by hour */}
          {metrics?.click_rate_by_hour &&
            metrics.click_rate_by_hour.length > 0 && (
              <div className="bg-white rounded-lg border border-slate-200 p-5">
                <h3 className="text-sm font-semibold text-slate-900 mb-4">
                  Click Rate by Hour
                </h3>
                <ResponsiveContainer width="100%" height={250}>
                  <LineChart data={metrics.click_rate_by_hour}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                    <XAxis
                      dataKey="hour"
                      tick={{ fontSize: 12 }}
                      tickFormatter={(h) => `${h}:00`}
                    />
                    <YAxis
                      tick={{ fontSize: 12 }}
                      tickFormatter={(v) => `${v}%`}
                    />
                    <Tooltip formatter={(v: number) => `${v.toFixed(1)}%`} />
                    <Line
                      type="monotone"
                      dataKey="rate"
                      stroke="#0ea5e9"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}

          {/* Top clicked links */}
          {metrics?.top_clicked_links &&
            metrics.top_clicked_links.length > 0 && (
              <div className="bg-white rounded-lg border border-slate-200 p-5">
                <h3 className="text-sm font-semibold text-slate-900 mb-4">
                  Top 10 Most Clicked Links
                </h3>
                <div className="space-y-2">
                  {metrics.top_clicked_links.slice(0, 10).map((link, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between text-sm"
                    >
                      <span className="text-slate-600 truncate max-w-lg">
                        {link.url}
                      </span>
                      <span className="text-slate-900 font-medium ml-4">
                        {link.clicks} clicks
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
        </div>
      )}

      {activeTab === "Timeline" && (
        <div className="space-y-4">
          <div className="flex items-center gap-3">
            <select
              value={timelineFilter}
              onChange={(e) => setTimelineFilter(e.target.value)}
              className="px-3 py-2 border border-slate-300 rounded-md text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500"
            >
              <option value="">All Events</option>
              <option value="sent">Sent</option>
              <option value="opened">Opened</option>
              <option value="clicked">Clicked</option>
              <option value="submitted">Submitted</option>
              <option value="reported">Reported</option>
              <option value="error">Error</option>
            </select>
            {campaign.status === "running" && (
              <span className="text-xs text-green-600 font-medium flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                Auto-refreshing
              </span>
            )}
          </div>

          <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
            {timelineQuery.isLoading ? (
              <div className="p-5 text-center text-slate-400 text-sm">
                Loading timeline...
              </div>
            ) : timeline.length === 0 ? (
              <div className="p-5 text-center text-slate-400 text-sm">
                No events recorded yet.
              </div>
            ) : (
              timeline.map((event) => {
                const typeColors: Record<string, string> = {
                  sent: "bg-slate-100 text-slate-600",
                  delivered: "bg-blue-100 text-blue-600",
                  opened: "bg-sky-100 text-sky-600",
                  clicked: "bg-amber-100 text-amber-600",
                  submitted: "bg-red-100 text-red-600",
                  reported: "bg-green-100 text-green-600",
                  error: "bg-red-100 text-red-600",
                };
                return (
                  <div key={event.id} className="px-5 py-3 flex items-center gap-3">
                    <span
                      className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium shrink-0 ${
                        typeColors[event.event_type] || typeColors.sent
                      }`}
                    >
                      {event.event_type.charAt(0).toUpperCase()}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-slate-700">
                        {event.description}
                      </p>
                      {event.contact_name && (
                        <p className="text-xs text-slate-400">
                          {event.contact_name}
                        </p>
                      )}
                    </div>
                    <span className="text-xs text-slate-400 shrink-0">
                      {new Date(event.timestamp).toLocaleString()}
                    </span>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
