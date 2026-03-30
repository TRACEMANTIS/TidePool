import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getDashboardStats, getActiveCampaigns, getEventFeed } from "@/api/monitor";
import type { DashboardStats, LiveCampaignStats, EventFeedItem } from "@/types";

function TrendArrow({ value }: { value: number }) {
  if (value === 0) return <span className="text-slate-400 text-xs">--</span>;
  const isUp = value > 0;
  return (
    <span className={`inline-flex items-center text-xs font-medium ${isUp ? "text-green-600" : "text-red-500"}`}>
      <span className="mr-0.5">{isUp ? "\u2191" : "\u2193"}</span>
      {Math.abs(value).toFixed(1)}%
    </span>
  );
}

function StatCard({
  label,
  value,
  change,
  color,
}: {
  label: string;
  value: string | number;
  change?: number;
  color: "blue" | "green" | "purple" | "red" | "orange" | "emerald";
}) {
  const borderColors: Record<string, string> = {
    blue: "border-l-blue-500",
    green: "border-l-green-500",
    purple: "border-l-purple-500",
    red: "border-l-red-500",
    orange: "border-l-orange-500",
    emerald: "border-l-emerald-500",
  };
  return (
    <div className={`bg-white rounded-lg border border-slate-200 border-l-4 ${borderColors[color]} p-5`}>
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <div className="flex items-end justify-between mt-1">
        <p className="text-3xl font-bold text-slate-900">{value}</p>
        {change !== undefined && <TrendArrow value={change} />}
      </div>
    </div>
  );
}

function riskColor(level: string): "red" | "orange" | "emerald" {
  if (level === "critical" || level === "high") return "red";
  if (level === "medium") return "orange";
  return "emerald";
}

function ProgressBar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.round((value / max) * 100) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
        <div
          className="h-full bg-sky-500 rounded-full transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-slate-500 w-10 text-right">{pct}%</span>
    </div>
  );
}

function eventIcon(type: string): string {
  const icons: Record<string, string> = {
    sent: "\u25B8",
    delivered: "\u2713",
    opened: "\u25C9",
    clicked: "\u25CF",
    submitted: "\u25A0",
    reported: "\u25B2",
    error: "\u2717",
    campaign_started: "\u25B6",
    campaign_completed: "\u25A3",
  };
  return icons[type] || "\u25CB";
}

function formatRelativeTime(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export default function Dashboard() {
  const statsQuery = useQuery<DashboardStats>({
    queryKey: ["dashboard-stats"],
    queryFn: getDashboardStats,
    refetchInterval: 30000,
  });

  const activeCampaignsQuery = useQuery<LiveCampaignStats[]>({
    queryKey: ["active-campaigns"],
    queryFn: getActiveCampaigns,
    refetchInterval: 10000,
  });

  const eventFeedQuery = useQuery<EventFeedItem[]>({
    queryKey: ["event-feed", { limit: 10 }],
    queryFn: () => getEventFeed({ limit: 10 }),
    refetchInterval: 15000,
  });

  const stats = statsQuery.data;
  const activeCampaigns = activeCampaignsQuery.data ?? [];
  const events = eventFeedQuery.data ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-sm text-slate-500 mt-1">
          Overview of your phishing simulation activity.
        </p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Active Campaigns"
          value={stats?.active_campaigns ?? "--"}
          change={stats?.active_campaigns_change}
          color="blue"
        />
        <StatCard
          label="Total Contacts"
          value={stats?.total_contacts ?? "--"}
          change={stats?.total_contacts_change}
          color="green"
        />
        <StatCard
          label="Emails Sent This Month"
          value={stats?.emails_sent_month ?? "--"}
          change={stats?.emails_sent_change}
          color="purple"
        />
        <StatCard
          label="Org Risk Score"
          value={stats?.org_risk ? `${stats.org_risk.score}/100` : "--"}
          change={stats?.org_risk?.trend}
          color={stats?.org_risk ? riskColor(stats.org_risk.level) : "emerald"}
        />
      </div>

      {/* Active Campaigns */}
      <div className="bg-white rounded-lg border border-slate-200">
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">
            Active Campaigns
          </h2>
          <Link
            to="/campaigns"
            className="text-sm text-sky-600 hover:text-sky-700 font-medium"
          >
            View all
          </Link>
        </div>
        <div className="p-5">
          {activeCampaignsQuery.isLoading ? (
            <div className="py-8 text-center text-slate-400 text-sm">Loading...</div>
          ) : activeCampaigns.length === 0 ? (
            <div className="py-8 text-center text-slate-400 text-sm">
              No campaigns currently running.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-100">
                  <th className="pb-2 font-medium">Name</th>
                  <th className="pb-2 font-medium w-48">Progress</th>
                  <th className="pb-2 font-medium">Send Rate</th>
                  <th className="pb-2 font-medium">Started</th>
                  <th className="pb-2 font-medium">ETA</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {activeCampaigns.map((c) => (
                  <tr key={c.campaign_id} className="hover:bg-slate-50">
                    <td className="py-3">
                      <Link
                        to={`/campaigns/${c.campaign_id}`}
                        className="text-sky-600 hover:text-sky-700 font-medium"
                      >
                        {c.campaign_name}
                      </Link>
                    </td>
                    <td className="py-3">
                      <ProgressBar
                        value={c.stats.emails_sent}
                        max={c.stats.total_recipients}
                      />
                    </td>
                    <td className="py-3 text-slate-700">
                      {c.send_rate}/min
                    </td>
                    <td className="py-3 text-slate-500">
                      {c.started_at ? new Date(c.started_at).toLocaleDateString() : "--"}
                    </td>
                    <td className="py-3 text-slate-500">
                      {c.eta ? new Date(c.eta).toLocaleString() : "--"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Recent Activity */}
      <div className="bg-white rounded-lg border border-slate-200">
        <div className="px-5 py-4 border-b border-slate-200">
          <h2 className="text-lg font-semibold text-slate-900">
            Recent Activity
          </h2>
        </div>
        <div className="divide-y divide-slate-100">
          {eventFeedQuery.isLoading ? (
            <div className="p-5 text-center text-slate-400 text-sm">Loading...</div>
          ) : events.length === 0 ? (
            <div className="p-5 text-center text-slate-400 text-sm">
              No activity yet. Start a campaign to see events here.
            </div>
          ) : (
            events.map((event) => (
              <div key={event.id} className="px-5 py-3 flex items-center gap-3">
                <span className="w-6 h-6 rounded-full bg-slate-100 flex items-center justify-center text-xs text-slate-600 shrink-0">
                  {eventIcon(event.event_type)}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-slate-700 truncate">
                    {event.description}
                  </p>
                  <p className="text-xs text-slate-400">
                    {event.campaign_name}
                  </p>
                </div>
                <span className="text-xs text-slate-400 shrink-0">
                  {formatRelativeTime(event.timestamp)}
                </span>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="bg-white rounded-lg border border-slate-200 p-5">
        <h2 className="text-lg font-semibold text-slate-900 mb-4">
          Quick Actions
        </h2>
        <div className="flex flex-wrap gap-3">
          <Link
            to="/campaigns/new"
            className="inline-flex items-center px-4 py-2 bg-sky-600 text-white text-sm font-medium rounded-md hover:bg-sky-700 transition-colors"
          >
            New Campaign
          </Link>
          <Link
            to="/addressbooks"
            className="inline-flex items-center px-4 py-2 bg-white text-slate-700 text-sm font-medium rounded-md border border-slate-300 hover:bg-slate-50 transition-colors"
          >
            Upload Address Book
          </Link>
          <Link
            to="/reports"
            className="inline-flex items-center px-4 py-2 bg-white text-slate-700 text-sm font-medium rounded-md border border-slate-300 hover:bg-slate-50 transition-colors"
          >
            View Reports
          </Link>
        </div>
      </div>
    </div>
  );
}
