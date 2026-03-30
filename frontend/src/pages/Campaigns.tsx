import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listCampaigns } from "@/api/campaigns";
import type { Campaign, CampaignStatus, PaginatedResponse } from "@/types";
import apiClient from "@/api/client";

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

export default function CampaignList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<PaginatedResponse<Campaign>>({
    queryKey: ["campaigns", { page, status: statusFilter, search }],
    queryFn: () =>
      listCampaigns({
        page,
        page_size: 20,
        status: statusFilter || undefined,
        search: search || undefined,
      }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/campaigns/${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    },
  });

  const campaigns = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;

  function handleDelete(e: React.MouseEvent, id: string, name: string) {
    e.stopPropagation();
    if (window.confirm(`Delete campaign "${name}"? This cannot be undone.`)) {
      deleteMutation.mutate(id);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Campaigns</h1>
          <p className="text-sm text-slate-500 mt-1">
            Manage and monitor your phishing simulation campaigns.
          </p>
        </div>
        <Link
          to="/campaigns/new"
          className="inline-flex items-center px-4 py-2 bg-sky-600 text-white text-sm font-medium rounded-md hover:bg-sky-700 transition-colors"
        >
          New Campaign
        </Link>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3">
        <input
          type="text"
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(1);
          }}
          placeholder="Search campaigns..."
          className="px-3 py-2 border border-slate-300 rounded-md text-sm w-64 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
        />
        <select
          value={statusFilter}
          onChange={(e) => {
            setStatusFilter(e.target.value);
            setPage(1);
          }}
          className="px-3 py-2 border border-slate-300 rounded-md text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500"
        >
          <option value="">All Statuses</option>
          <option value="draft">Draft</option>
          <option value="scheduled">Scheduled</option>
          <option value="running">Running</option>
          <option value="paused">Paused</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
        </select>
      </div>

      {/* Table */}
      <div className="bg-white rounded-lg border border-slate-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="px-5 py-3 font-medium">Name</th>
              <th className="px-5 py-3 font-medium">Status</th>
              <th className="px-5 py-3 font-medium">Recipients</th>
              <th className="px-5 py-3 font-medium">Progress</th>
              <th className="px-5 py-3 font-medium">Send Rate</th>
              <th className="px-5 py-3 font-medium">Created</th>
              <th className="px-5 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading ? (
              <tr>
                <td className="px-5 py-12 text-center text-slate-400" colSpan={7}>
                  Loading campaigns...
                </td>
              </tr>
            ) : campaigns.length === 0 ? (
              <tr>
                <td className="px-5 py-12 text-center text-slate-400" colSpan={7}>
                  No campaigns found. Click "New Campaign" to create one.
                </td>
              </tr>
            ) : (
              campaigns.map((c) => {
                const progress =
                  c.stats.total_recipients > 0
                    ? Math.round(
                        (c.stats.emails_sent / c.stats.total_recipients) * 100
                      )
                    : 0;
                return (
                  <tr
                    key={c.id}
                    onClick={() => navigate(`/campaigns/${c.id}`)}
                    className="hover:bg-slate-50 cursor-pointer"
                  >
                    <td className="px-5 py-3 font-medium text-slate-900">
                      {c.name}
                    </td>
                    <td className="px-5 py-3">
                      <StatusBadge status={c.status} />
                    </td>
                    <td className="px-5 py-3 text-slate-600">
                      {c.stats.total_recipients}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2 w-32">
                        <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-sky-500 rounded-full"
                            style={{ width: `${progress}%` }}
                          />
                        </div>
                        <span className="text-xs text-slate-500">{progress}%</span>
                      </div>
                    </td>
                    <td className="px-5 py-3 text-slate-600">
                      {c.send_rate ? `${c.send_rate}/min` : "--"}
                    </td>
                    <td className="px-5 py-3 text-slate-500">
                      {new Date(c.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <Link
                          to={`/campaigns/${c.id}`}
                          onClick={(e) => e.stopPropagation()}
                          className="text-sky-600 hover:text-sky-700 text-xs font-medium"
                        >
                          View
                        </Link>
                        {c.status === "draft" && (
                          <>
                            <Link
                              to={`/campaigns/${c.id}`}
                              onClick={(e) => e.stopPropagation()}
                              className="text-slate-500 hover:text-slate-700 text-xs font-medium"
                            >
                              Edit
                            </Link>
                            <button
                              onClick={(e) => handleDelete(e, c.id, c.name)}
                              className="text-red-500 hover:text-red-700 text-xs font-medium cursor-pointer"
                            >
                              Delete
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="px-5 py-3 border-t border-slate-200 flex items-center justify-between">
            <p className="text-xs text-slate-500">
              Page {page} of {totalPages} ({data?.total ?? 0} total)
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="px-3 py-1 text-xs border border-slate-300 rounded-md hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                Previous
              </button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="px-3 py-1 text-xs border border-slate-300 rounded-md hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
