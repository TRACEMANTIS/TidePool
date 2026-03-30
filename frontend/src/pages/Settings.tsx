import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listSmtpProfiles,
  createSmtpProfile,
  deleteSmtpProfile,
  testSmtpProfile,
  listApiKeys,
  createApiKey,
  revokeApiKey,
  listUsers,
  createUser,
  getGeneralSettings,
  updateGeneralSettings,
} from "@/api/settings";
import type { SmtpProfile, ApiKey, User, GeneralSettings, PaginatedResponse } from "@/types";

const settingsTabs = ["SMTP Profiles", "API Keys", "User Management", "General"];

const SMTP_TYPES = ["SMTP", "SES", "Mailgun", "SendGrid", "Custom"];

export default function Settings() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState("SMTP Profiles");

  // SMTP state
  const [showSmtpModal, setShowSmtpModal] = useState(false);
  const [smtpForm, setSmtpForm] = useState({
    name: "", host: "", port: 587, username: "", password: "",
    use_tls: true, from_address: "", smtp_type: "SMTP",
  });
  const [testEmail, setTestEmail] = useState("");
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  // API Key state
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyExpiry, setNewKeyExpiry] = useState(90);
  const [generatedKey, setGeneratedKey] = useState<string | null>(null);
  const [keyCopied, setKeyCopied] = useState(false);

  // User state
  const [showUserModal, setShowUserModal] = useState(false);
  const [userForm, setUserForm] = useState({
    username: "", email: "", full_name: "", password: "",
    role: "operator" as "admin" | "operator" | "viewer",
  });

  // General state
  const [generalForm, setGeneralForm] = useState<GeneralSettings | null>(null);

  // Queries
  const smtpQuery = useQuery<SmtpProfile[]>({
    queryKey: ["smtp-profiles"],
    queryFn: listSmtpProfiles,
    enabled: activeTab === "SMTP Profiles",
  });

  const keysQuery = useQuery<ApiKey[]>({
    queryKey: ["api-keys"],
    queryFn: listApiKeys,
    enabled: activeTab === "API Keys",
  });

  const usersQuery = useQuery<PaginatedResponse<User>>({
    queryKey: ["users"],
    queryFn: listUsers,
    enabled: activeTab === "User Management",
  });

  const generalQuery = useQuery<GeneralSettings>({
    queryKey: ["general-settings"],
    queryFn: getGeneralSettings,
    enabled: activeTab === "General",
  });

  // Set general form when data loads
  if (generalQuery.data && !generalForm) {
    setGeneralForm(generalQuery.data);
  }

  // Mutations
  const createSmtpMutation = useMutation({
    mutationFn: () => createSmtpProfile(smtpForm),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["smtp-profiles"] });
      setShowSmtpModal(false);
      setSmtpForm({ name: "", host: "", port: 587, username: "", password: "", use_tls: true, from_address: "", smtp_type: "SMTP" });
    },
  });

  const deleteSmtpMutation = useMutation({
    mutationFn: deleteSmtpProfile,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["smtp-profiles"] }),
  });

  const testSmtpMutation = useMutation({
    mutationFn: ({ id, email }: { id: string; email: string }) => testSmtpProfile(id, email),
    onSuccess: (result) => setTestResult(result),
    onError: () => setTestResult({ success: false, message: "Test failed." }),
  });

  const createKeyMutation = useMutation({
    mutationFn: () => createApiKey({ name: newKeyName, expires_in_days: newKeyExpiry }),
    onSuccess: (key) => {
      queryClient.invalidateQueries({ queryKey: ["api-keys"] });
      setGeneratedKey(key.raw_key ?? null);
      setNewKeyName("");
    },
  });

  const revokeKeyMutation = useMutation({
    mutationFn: revokeApiKey,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["api-keys"] }),
  });

  const createUserMutation = useMutation({
    mutationFn: () => createUser(userForm),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setShowUserModal(false);
      setUserForm({ username: "", email: "", full_name: "", password: "", role: "operator" });
    },
  });

  const updateGeneralMutation = useMutation({
    mutationFn: () => updateGeneralSettings(generalForm!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["general-settings"] }),
  });

  const smtpProfiles = smtpQuery.data ?? [];
  const apiKeys = keysQuery.data ?? [];
  const users = usersQuery.data?.items ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Settings</h1>
        <p className="text-sm text-slate-500 mt-1">
          Configure SMTP profiles, API keys, manage users, and adjust platform settings.
        </p>
      </div>

      {/* Tabs */}
      <div className="border-b border-slate-200">
        <div className="flex gap-0">
          {settingsTabs.map((tab) => (
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

      {/* SMTP Profiles */}
      {activeTab === "SMTP Profiles" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-500">
              Configure SMTP servers for sending phishing emails.
            </p>
            <button
              onClick={() => setShowSmtpModal(true)}
              className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 cursor-pointer"
            >
              Add SMTP Profile
            </button>
          </div>

          <div className="bg-white rounded-lg border border-slate-200">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="px-5 py-3 font-medium">Name</th>
                  <th className="px-5 py-3 font-medium">Type</th>
                  <th className="px-5 py-3 font-medium">From Address</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {smtpQuery.isLoading ? (
                  <tr>
                    <td className="px-5 py-12 text-center text-slate-400" colSpan={5}>
                      Loading...
                    </td>
                  </tr>
                ) : smtpProfiles.length === 0 ? (
                  <tr>
                    <td className="px-5 py-12 text-center text-slate-400" colSpan={5}>
                      No SMTP profiles configured.
                    </td>
                  </tr>
                ) : (
                  smtpProfiles.map((sp) => (
                    <tr key={sp.id} className="hover:bg-slate-50">
                      <td className="px-5 py-3 font-medium text-slate-900">
                        {sp.name}
                      </td>
                      <td className="px-5 py-3">
                        <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                          {sp.smtp_type || "SMTP"}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-slate-600">
                        {sp.from_address}
                      </td>
                      <td className="px-5 py-3">
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                            sp.status === "active"
                              ? "bg-green-100 text-green-700"
                              : sp.status === "error"
                                ? "bg-red-100 text-red-700"
                                : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {sp.status || "active"}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => {
                              setTestingId(sp.id);
                              setTestResult(null);
                            }}
                            className="text-xs text-sky-600 hover:text-sky-700 cursor-pointer"
                          >
                            Test
                          </button>
                          <button
                            onClick={() => {
                              if (window.confirm(`Delete profile "${sp.name}"?`)) {
                                deleteSmtpMutation.mutate(sp.id);
                              }
                            }}
                            className="text-xs text-red-500 hover:text-red-700 cursor-pointer"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Test Connection inline */}
          {testingId && (
            <div className="bg-white rounded-lg border border-slate-200 p-4">
              <h3 className="text-sm font-medium text-slate-900 mb-2">
                Test Connection
              </h3>
              <div className="flex items-center gap-2">
                <input
                  type="email"
                  value={testEmail}
                  onChange={(e) => setTestEmail(e.target.value)}
                  placeholder="recipient@example.com"
                  className="px-3 py-2 border border-slate-300 rounded-md text-sm w-64 focus:outline-none focus:ring-2 focus:ring-sky-500"
                />
                <button
                  onClick={() =>
                    testSmtpMutation.mutate({ id: testingId, email: testEmail })
                  }
                  disabled={!testEmail || testSmtpMutation.isPending}
                  className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 disabled:opacity-50 cursor-pointer"
                >
                  {testSmtpMutation.isPending ? "Testing..." : "Test Connection"}
                </button>
                <button
                  onClick={() => {
                    setTestingId(null);
                    setTestResult(null);
                  }}
                  className="text-xs text-slate-500 hover:text-slate-700 cursor-pointer"
                >
                  Cancel
                </button>
              </div>
              {testResult && (
                <p
                  className={`text-xs mt-2 ${
                    testResult.success ? "text-green-600" : "text-red-500"
                  }`}
                >
                  {testResult.message}
                </p>
              )}
            </div>
          )}

          {/* Create SMTP Modal */}
          {showSmtpModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
              <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4 p-6 space-y-4">
                <h3 className="text-lg font-semibold text-slate-900">
                  Add SMTP Profile
                </h3>
                <div className="grid grid-cols-2 gap-4">
                  <div className="col-span-2">
                    <label className="block text-sm font-medium text-slate-700 mb-1">Name</label>
                    <input type="text" value={smtpForm.name} onChange={(e) => setSmtpForm({ ...smtpForm, name: e.target.value })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Type</label>
                    <select value={smtpForm.smtp_type} onChange={(e) => setSmtpForm({ ...smtpForm, smtp_type: e.target.value })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500">
                      {SMTP_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">From Address</label>
                    <input type="email" value={smtpForm.from_address} onChange={(e) => setSmtpForm({ ...smtpForm, from_address: e.target.value })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Host</label>
                    <input type="text" value={smtpForm.host} onChange={(e) => setSmtpForm({ ...smtpForm, host: e.target.value })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Port</label>
                    <input type="number" value={smtpForm.port} onChange={(e) => setSmtpForm({ ...smtpForm, port: parseInt(e.target.value) || 0 })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Username</label>
                    <input type="text" value={smtpForm.username} onChange={(e) => setSmtpForm({ ...smtpForm, username: e.target.value })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
                    <input type="password" value={smtpForm.password} onChange={(e) => setSmtpForm({ ...smtpForm, password: e.target.value })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
                  </div>
                  <div className="col-span-2">
                    <label className="flex items-center gap-2 text-sm text-slate-700">
                      <input type="checkbox" checked={smtpForm.use_tls}
                        onChange={(e) => setSmtpForm({ ...smtpForm, use_tls: e.target.checked })}
                        className="rounded border-slate-300" />
                      Use TLS
                    </label>
                  </div>
                </div>
                {createSmtpMutation.isError && (
                  <p className="text-xs text-red-500">Failed to create profile.</p>
                )}
                <div className="flex justify-end gap-3 pt-2">
                  <button onClick={() => setShowSmtpModal(false)}
                    className="px-4 py-2 text-sm font-medium text-slate-700 border border-slate-300 rounded-md hover:bg-slate-50 cursor-pointer">
                    Cancel
                  </button>
                  <button onClick={() => createSmtpMutation.mutate()}
                    disabled={!smtpForm.name || !smtpForm.host || createSmtpMutation.isPending}
                    className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 disabled:opacity-50 cursor-pointer">
                    {createSmtpMutation.isPending ? "Creating..." : "Create Profile"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* API Keys */}
      {activeTab === "API Keys" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-500">
              Manage API keys for programmatic access.
            </p>
            <button
              onClick={() => {
                setShowKeyModal(true);
                setGeneratedKey(null);
                setKeyCopied(false);
              }}
              className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 cursor-pointer"
            >
              Generate New Key
            </button>
          </div>

          <div className="bg-white rounded-lg border border-slate-200">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="px-5 py-3 font-medium">Name</th>
                  <th className="px-5 py-3 font-medium">Key Prefix</th>
                  <th className="px-5 py-3 font-medium">Created</th>
                  <th className="px-5 py-3 font-medium">Expires</th>
                  <th className="px-5 py-3 font-medium">Last Used</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {keysQuery.isLoading ? (
                  <tr>
                    <td className="px-5 py-12 text-center text-slate-400" colSpan={7}>
                      Loading...
                    </td>
                  </tr>
                ) : apiKeys.length === 0 ? (
                  <tr>
                    <td className="px-5 py-12 text-center text-slate-400" colSpan={7}>
                      No API keys generated.
                    </td>
                  </tr>
                ) : (
                  apiKeys.map((k) => (
                    <tr key={k.id} className="hover:bg-slate-50">
                      <td className="px-5 py-3 font-medium text-slate-900">
                        {k.name}
                      </td>
                      <td className="px-5 py-3 font-mono text-xs text-slate-600">
                        {k.key_prefix}...
                      </td>
                      <td className="px-5 py-3 text-slate-500">
                        {new Date(k.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-5 py-3 text-slate-500">
                        {k.expires_at
                          ? new Date(k.expires_at).toLocaleDateString()
                          : "Never"}
                      </td>
                      <td className="px-5 py-3 text-slate-500">
                        {k.last_used_at
                          ? new Date(k.last_used_at).toLocaleDateString()
                          : "Never"}
                      </td>
                      <td className="px-5 py-3">
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                            k.is_active
                              ? "bg-green-100 text-green-700"
                              : "bg-red-100 text-red-700"
                          }`}
                        >
                          {k.is_active ? "Active" : "Revoked"}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-right">
                        {k.is_active && (
                          <button
                            onClick={() => {
                              if (window.confirm(`Revoke API key "${k.name}"?`)) {
                                revokeKeyMutation.mutate(k.id);
                              }
                            }}
                            className="text-xs text-red-500 hover:text-red-700 cursor-pointer"
                          >
                            Revoke
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Generate Key Modal */}
          {showKeyModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
              <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6 space-y-4">
                {generatedKey ? (
                  <>
                    <h3 className="text-lg font-semibold text-slate-900">
                      API Key Generated
                    </h3>
                    <div className="bg-amber-50 border border-amber-200 rounded-md p-3">
                      <p className="text-xs text-amber-700 font-medium mb-2">
                        WARNING: This key will only be shown once. Copy it now and store it securely.
                      </p>
                      <div className="flex items-center gap-2">
                        <code className="flex-1 text-sm font-mono bg-white border border-slate-200 rounded px-3 py-2 break-all">
                          {generatedKey}
                        </code>
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(generatedKey);
                            setKeyCopied(true);
                          }}
                          className="px-3 py-2 text-xs font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 cursor-pointer shrink-0"
                        >
                          {keyCopied ? "Copied" : "Copy"}
                        </button>
                      </div>
                    </div>
                    <div className="flex justify-end">
                      <button
                        onClick={() => {
                          setShowKeyModal(false);
                          setGeneratedKey(null);
                        }}
                        className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 cursor-pointer"
                      >
                        Done
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <h3 className="text-lg font-semibold text-slate-900">
                      Generate API Key
                    </h3>
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Key Name</label>
                      <input type="text" value={newKeyName} onChange={(e) => setNewKeyName(e.target.value)}
                        placeholder="e.g., CI/CD Pipeline"
                        className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-700 mb-1">Expires In (days)</label>
                      <input type="number" min={1} max={365} value={newKeyExpiry}
                        onChange={(e) => setNewKeyExpiry(parseInt(e.target.value) || 90)}
                        className="w-32 px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
                    </div>
                    {createKeyMutation.isError && (
                      <p className="text-xs text-red-500">Failed to generate key.</p>
                    )}
                    <div className="flex justify-end gap-3">
                      <button onClick={() => setShowKeyModal(false)}
                        className="px-4 py-2 text-sm font-medium text-slate-700 border border-slate-300 rounded-md hover:bg-slate-50 cursor-pointer">
                        Cancel
                      </button>
                      <button onClick={() => createKeyMutation.mutate()}
                        disabled={!newKeyName.trim() || createKeyMutation.isPending}
                        className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 disabled:opacity-50 cursor-pointer">
                        {createKeyMutation.isPending ? "Generating..." : "Generate"}
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* User Management */}
      {activeTab === "User Management" && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm text-slate-500">
              Manage user accounts and role assignments.
            </p>
            <button
              onClick={() => setShowUserModal(true)}
              className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 cursor-pointer"
            >
              Add User
            </button>
          </div>

          <div className="bg-white rounded-lg border border-slate-200">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-500 border-b border-slate-200">
                  <th className="px-5 py-3 font-medium">Username</th>
                  <th className="px-5 py-3 font-medium">Email</th>
                  <th className="px-5 py-3 font-medium">Role</th>
                  <th className="px-5 py-3 font-medium">Status</th>
                  <th className="px-5 py-3 font-medium">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {usersQuery.isLoading ? (
                  <tr>
                    <td className="px-5 py-12 text-center text-slate-400" colSpan={5}>
                      Loading...
                    </td>
                  </tr>
                ) : users.length === 0 ? (
                  <tr>
                    <td className="px-5 py-12 text-center text-slate-400" colSpan={5}>
                      No additional users.
                    </td>
                  </tr>
                ) : (
                  users.map((u) => (
                    <tr key={u.id} className="hover:bg-slate-50">
                      <td className="px-5 py-3 font-medium text-slate-900">
                        {u.username}
                      </td>
                      <td className="px-5 py-3 text-slate-600">{u.email}</td>
                      <td className="px-5 py-3">
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                            u.role === "admin"
                              ? "bg-red-100 text-red-700"
                              : u.role === "operator"
                                ? "bg-blue-100 text-blue-700"
                                : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {u.role}
                        </span>
                      </td>
                      <td className="px-5 py-3">
                        <span
                          className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                            u.is_active
                              ? "bg-green-100 text-green-700"
                              : "bg-red-100 text-red-700"
                          }`}
                        >
                          {u.is_active ? "Active" : "Disabled"}
                        </span>
                      </td>
                      <td className="px-5 py-3 text-slate-500">
                        {new Date(u.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Create User Modal */}
          {showUserModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
              <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6 space-y-4">
                <h3 className="text-lg font-semibold text-slate-900">Add User</h3>
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Username</label>
                    <input type="text" value={userForm.username} onChange={(e) => setUserForm({ ...userForm, username: e.target.value })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Full Name</label>
                    <input type="text" value={userForm.full_name} onChange={(e) => setUserForm({ ...userForm, full_name: e.target.value })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
                    <input type="email" value={userForm.email} onChange={(e) => setUserForm({ ...userForm, email: e.target.value })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
                    <input type="password" value={userForm.password} onChange={(e) => setUserForm({ ...userForm, password: e.target.value })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-700 mb-1">Role</label>
                    <select value={userForm.role} onChange={(e) => setUserForm({ ...userForm, role: e.target.value as "admin" | "operator" | "viewer" })}
                      className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500">
                      <option value="viewer">Viewer</option>
                      <option value="operator">Operator</option>
                      <option value="admin">Admin</option>
                    </select>
                  </div>
                </div>
                {createUserMutation.isError && (
                  <p className="text-xs text-red-500">Failed to create user.</p>
                )}
                <div className="flex justify-end gap-3">
                  <button onClick={() => setShowUserModal(false)}
                    className="px-4 py-2 text-sm font-medium text-slate-700 border border-slate-300 rounded-md hover:bg-slate-50 cursor-pointer">
                    Cancel
                  </button>
                  <button onClick={() => createUserMutation.mutate()}
                    disabled={!userForm.username || !userForm.email || !userForm.password || createUserMutation.isPending}
                    className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 disabled:opacity-50 cursor-pointer">
                    {createUserMutation.isPending ? "Creating..." : "Create User"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* General */}
      {activeTab === "General" && (
        <div className="bg-white rounded-lg border border-slate-200 p-6 space-y-6">
          {generalQuery.isLoading ? (
            <p className="text-sm text-slate-400">Loading settings...</p>
          ) : generalForm ? (
            <>
              <div>
                <h3 className="text-sm font-medium text-slate-900 mb-1">
                  Application Name
                </h3>
                <input
                  type="text"
                  value={generalForm.app_name}
                  onChange={(e) =>
                    setGeneralForm({ ...generalForm, app_name: e.target.value })
                  }
                  className="px-3 py-2 border border-slate-300 rounded-md text-sm w-64 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                />
              </div>
              <div>
                <h3 className="text-sm font-medium text-slate-900 mb-1">
                  Default Throttle Rate (emails/min)
                </h3>
                <input
                  type="number"
                  min={1}
                  value={generalForm.default_throttle_rate}
                  onChange={(e) =>
                    setGeneralForm({
                      ...generalForm,
                      default_throttle_rate: parseInt(e.target.value) || 1,
                    })
                  }
                  className="px-3 py-2 border border-slate-300 rounded-md text-sm w-32 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                />
              </div>
              <div>
                <h3 className="text-sm font-medium text-slate-900 mb-1">
                  Upload Directory
                </h3>
                <input
                  type="text"
                  value={generalForm.upload_directory}
                  onChange={(e) =>
                    setGeneralForm({
                      ...generalForm,
                      upload_directory: e.target.value,
                    })
                  }
                  className="px-3 py-2 border border-slate-300 rounded-md text-sm w-96 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                />
              </div>
              <div>
                <h3 className="text-sm font-medium text-slate-900 mb-1">
                  Log Level
                </h3>
                <select
                  value={generalForm.log_level}
                  onChange={(e) =>
                    setGeneralForm({
                      ...generalForm,
                      log_level: e.target.value as GeneralSettings["log_level"],
                    })
                  }
                  className="px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                >
                  <option value="debug">Debug</option>
                  <option value="info">Info</option>
                  <option value="warning">Warning</option>
                  <option value="error">Error</option>
                </select>
              </div>
              <div>
                <button
                  onClick={() => updateGeneralMutation.mutate()}
                  disabled={updateGeneralMutation.isPending}
                  className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 disabled:opacity-50 cursor-pointer"
                >
                  {updateGeneralMutation.isPending
                    ? "Saving..."
                    : "Save Settings"}
                </button>
                {updateGeneralMutation.isSuccess && (
                  <span className="ml-3 text-xs text-green-600">Saved.</span>
                )}
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-400">
              Unable to load settings.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
