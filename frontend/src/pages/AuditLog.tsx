import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getLogs, exportLogs } from "@/api/audit";
import type { AuditLogEntry, PaginatedResponse } from "@/types";

export default function AuditLog() {
  const [page, setPage] = useState(1);
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const { data, isLoading } = useQuery<PaginatedResponse<AuditLogEntry>>({
    queryKey: [
      "audit-logs",
      { page, actor, action, resourceType, startDate, endDate },
    ],
    queryFn: () =>
      getLogs({
        page,
        page_size: 50,
        actor: actor || undefined,
        action: action || undefined,
        resource_type: resourceType || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
      }),
  });

  const logs = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;
  const total = data?.total ?? 0;

  async function handleExport() {
    setExporting(true);
    try {
      const blob = await exportLogs({
        actor: actor || undefined,
        action: action || undefined,
        resource_type: resourceType || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "audit-log.csv";
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  function renderDiff(before?: Record<string, unknown>, after?: Record<string, unknown>) {
    if (!before && !after) return null;
    const allKeys = new Set([
      ...Object.keys(before ?? {}),
      ...Object.keys(after ?? {}),
    ]);
    const changes: { key: string; old: string; new_val: string }[] = [];
    allKeys.forEach((key) => {
      const oldVal = JSON.stringify((before ?? {})[key] ?? null);
      const newVal = JSON.stringify((after ?? {})[key] ?? null);
      if (oldVal !== newVal) {
        changes.push({ key, old: oldVal, new_val: newVal });
      }
    });
    if (changes.length === 0) return <p className="text-xs text-slate-400">No changes detected.</p>;
    return (
      <div className="space-y-1">
        {changes.map((c) => (
          <div key={c.key} className="text-xs font-mono">
            <span className="text-slate-500">{c.key}: </span>
            <span className="text-red-500 line-through">{c.old}</span>
            <span className="text-slate-400"> -&gt; </span>
            <span className="text-green-600">{c.new_val}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Audit Log</h1>
          <p className="text-sm text-slate-500 mt-1">
            View a chronological record of all platform actions and events.
          </p>
        </div>
        <button
          onClick={handleExport}
          disabled={exporting}
          className="px-4 py-2 text-sm font-medium text-slate-700 border border-slate-300 rounded-md hover:bg-slate-50 disabled:opacity-50 cursor-pointer"
        >
          {exporting ? "Exporting..." : "Export CSV"}
        </button>
      </div>

      {/* Filters */}
      <div className="flex items-end gap-3 flex-wrap">
        <div>
          <label className="block text-xs text-slate-500 mb-1">Actor</label>
          <input
            type="text"
            value={actor}
            onChange={(e) => {
              setActor(e.target.value);
              setPage(1);
            }}
            placeholder="Username..."
            className="px-3 py-2 border border-slate-300 rounded-md text-sm w-40 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
          />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">Action</label>
          <select
            value={action}
            onChange={(e) => {
              setAction(e.target.value);
              setPage(1);
            }}
            className="px-3 py-2 border border-slate-300 rounded-md text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500"
          >
            <option value="">All Actions</option>
            <option value="create">Create</option>
            <option value="update">Update</option>
            <option value="delete">Delete</option>
            <option value="login">Login</option>
            <option value="start">Start</option>
            <option value="pause">Pause</option>
            <option value="complete">Complete</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">
            Resource Type
          </label>
          <select
            value={resourceType}
            onChange={(e) => {
              setResourceType(e.target.value);
              setPage(1);
            }}
            className="px-3 py-2 border border-slate-300 rounded-md text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500"
          >
            <option value="">All Types</option>
            <option value="campaign">Campaign</option>
            <option value="template">Template</option>
            <option value="address_book">Address Book</option>
            <option value="landing_page">Landing Page</option>
            <option value="smtp_profile">SMTP Profile</option>
            <option value="user">User</option>
            <option value="api_key">API Key</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">
            Start Date
          </label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => {
              setStartDate(e.target.value);
              setPage(1);
            }}
            className="px-3 py-2 border border-slate-300 rounded-md text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500"
          />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">End Date</label>
          <input
            type="date"
            value={endDate}
            onChange={(e) => {
              setEndDate(e.target.value);
              setPage(1);
            }}
            className="px-3 py-2 border border-slate-300 rounded-md text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-sky-500"
          />
        </div>
        {(actor || action || resourceType || startDate || endDate) && (
          <button
            onClick={() => {
              setActor("");
              setAction("");
              setResourceType("");
              setStartDate("");
              setEndDate("");
              setPage(1);
            }}
            className="px-3 py-2 text-xs text-slate-500 hover:text-slate-700 cursor-pointer"
          >
            Clear Filters
          </button>
        )}
      </div>

      {/* Table */}
      <div className="bg-white rounded-lg border border-slate-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="px-5 py-3 font-medium w-8"></th>
              <th className="px-5 py-3 font-medium">Timestamp</th>
              <th className="px-5 py-3 font-medium">Actor</th>
              <th className="px-5 py-3 font-medium">Action</th>
              <th className="px-5 py-3 font-medium">Resource</th>
              <th className="px-5 py-3 font-medium">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading ? (
              <tr>
                <td className="px-5 py-12 text-center text-slate-400" colSpan={6}>
                  Loading audit log...
                </td>
              </tr>
            ) : logs.length === 0 ? (
              <tr>
                <td className="px-5 py-12 text-center text-slate-400" colSpan={6}>
                  No audit log entries found.
                </td>
              </tr>
            ) : (
              logs.map((entry) => (
                <>
                  <tr
                    key={entry.id}
                    onClick={() =>
                      setExpandedId(expandedId === entry.id ? null : entry.id)
                    }
                    className="hover:bg-slate-50 cursor-pointer"
                  >
                    <td className="px-5 py-3 text-slate-400 text-xs">
                      {expandedId === entry.id ? "\u25BC" : "\u25B6"}
                    </td>
                    <td className="px-5 py-3 text-slate-600 text-xs font-mono">
                      {new Date(entry.created_at).toLocaleString()}
                    </td>
                    <td className="px-5 py-3 font-medium text-slate-900">
                      {entry.username}
                    </td>
                    <td className="px-5 py-3">
                      <span
                        className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                          entry.action === "delete"
                            ? "bg-red-100 text-red-700"
                            : entry.action === "create"
                              ? "bg-green-100 text-green-700"
                              : "bg-blue-100 text-blue-700"
                        }`}
                      >
                        {entry.action}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-slate-600">
                      <span className="text-xs">
                        {entry.resource_type}
                        {entry.resource_id && (
                          <span className="text-slate-400 ml-1">
                            #{entry.resource_id.slice(0, 8)}
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-slate-500 text-xs truncate max-w-xs">
                      {Object.keys(entry.details).length > 0
                        ? JSON.stringify(entry.details).slice(0, 80)
                        : "--"}
                    </td>
                  </tr>
                  {expandedId === entry.id && (
                    <tr key={`${entry.id}-detail`}>
                      <td colSpan={6} className="px-10 py-4 bg-slate-50">
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <p className="text-xs font-medium text-slate-700 mb-1">
                              IP Address
                            </p>
                            <p className="text-xs text-slate-600 font-mono">
                              {entry.ip_address}
                            </p>
                          </div>
                          <div>
                            <p className="text-xs font-medium text-slate-700 mb-1">
                              Full Details
                            </p>
                            <pre className="text-xs text-slate-600 bg-white border border-slate-200 rounded p-2 overflow-auto max-h-32">
                              {JSON.stringify(entry.details, null, 2)}
                            </pre>
                          </div>
                          {(entry.before_state || entry.after_state) && (
                            <div className="col-span-2">
                              <p className="text-xs font-medium text-slate-700 mb-1">
                                State Diff
                              </p>
                              {renderDiff(entry.before_state, entry.after_state)}
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              ))
            )}
          </tbody>
        </table>

        {/* Pagination */}
        <div className="px-5 py-3 border-t border-slate-200 flex items-center justify-between">
          <p className="text-xs text-slate-500">
            {total > 0
              ? `Showing ${(page - 1) * 50 + 1}-${Math.min(page * 50, total)} of ${total}`
              : "No entries"}
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="px-3 py-1 text-xs border border-slate-300 rounded-md hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              Previous
            </button>
            <span className="text-xs text-slate-500">
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="px-3 py-1 text-xs border border-slate-300 rounded-md hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
