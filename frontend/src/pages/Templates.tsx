import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listTemplates,
  listPretexts,
  createTemplate,
  deleteTemplate,
} from "@/api/templates";
import type {
  EmailTemplate,
  PretextTemplate,
  PaginatedResponse,
} from "@/types";

const CATEGORY_COLORS: Record<string, string> = {
  IT: "bg-blue-100 text-blue-700",
  HR: "bg-purple-100 text-purple-700",
  Finance: "bg-green-100 text-green-700",
  Executive: "bg-amber-100 text-amber-700",
  Vendor: "bg-slate-100 text-slate-700",
};

const VARIABLES = [
  "{{first_name}}",
  "{{last_name}}",
  "{{email}}",
  "{{position}}",
  "{{department}}",
  "{{company}}",
];

export default function TemplateList() {
  const queryClient = useQueryClient();
  const [showEditor, setShowEditor] = useState(false);
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [showHtmlPreview, setShowHtmlPreview] = useState(false);

  // Editor state
  const [editorName, setEditorName] = useState("");
  const [editorSubject, setEditorSubject] = useState("");
  const [editorBody, setEditorBody] = useState("");
  const [editorCategory, setEditorCategory] = useState("");

  const templatesQuery = useQuery<PaginatedResponse<EmailTemplate>>({
    queryKey: ["templates"],
    queryFn: () => listTemplates({ page: 1, page_size: 100 }),
  });

  const pretextsQuery = useQuery<PretextTemplate[]>({
    queryKey: ["pretexts"],
    queryFn: listPretexts,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createTemplate({
        name: editorName,
        subject: editorSubject,
        body_html: editorBody,
        category: editorCategory,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      resetEditor();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteTemplate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates"] });
    },
  });

  function resetEditor() {
    setShowEditor(false);
    setEditorName("");
    setEditorSubject("");
    setEditorBody("");
    setEditorCategory("");
  }

  function insertVariable(v: string) {
    setEditorBody((prev) => prev + v);
  }

  const templates = templatesQuery.data?.items ?? [];
  const pretexts = pretextsQuery.data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Email Templates
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Create and manage phishing email templates with variable substitution.
          </p>
        </div>
        <button
          onClick={() => setShowEditor(true)}
          className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 cursor-pointer"
        >
          New Template
        </button>
      </div>

      {/* Pretext Library */}
      {pretexts.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-slate-900 mb-3">
            Pretext Library
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {pretexts.map((pt) => (
              <div
                key={pt.id}
                className="bg-white rounded-lg border border-slate-200 p-4 flex flex-col"
              >
                <div className="flex items-center justify-between mb-2">
                  <span
                    className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                      CATEGORY_COLORS[pt.category] ?? CATEGORY_COLORS.Vendor
                    }`}
                  >
                    {pt.category}
                  </span>
                  <span className="flex gap-0.5">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <span
                        key={i}
                        className={`w-2 h-2 rounded-full ${
                          i < pt.difficulty
                            ? "bg-amber-400"
                            : "bg-slate-200"
                        }`}
                      />
                    ))}
                  </span>
                </div>
                <h3 className="text-sm font-semibold text-slate-900">
                  {pt.name}
                </h3>
                <p className="text-xs text-slate-500 mt-1 flex-1 line-clamp-2">
                  {pt.description}
                </p>
                <div className="flex gap-3 mt-3 pt-3 border-t border-slate-100">
                  <button
                    onClick={() => {
                      setEditorName(pt.name);
                      setEditorSubject(pt.subject);
                      setEditorBody(pt.body_html);
                      setEditorCategory(pt.category);
                      setShowEditor(true);
                    }}
                    className="text-xs font-medium text-sky-600 hover:text-sky-700 cursor-pointer"
                  >
                    Use Template
                  </button>
                  <button
                    onClick={() => setPreviewHtml(pt.body_html)}
                    className="text-xs font-medium text-slate-500 hover:text-slate-700 cursor-pointer"
                  >
                    Preview
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Custom Templates */}
      <div>
        <h2 className="text-lg font-semibold text-slate-900 mb-3">
          Custom Templates
        </h2>
        <div className="bg-white rounded-lg border border-slate-200">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200">
                <th className="px-5 py-3 font-medium">Name</th>
                <th className="px-5 py-3 font-medium">Subject</th>
                <th className="px-5 py-3 font-medium">Category</th>
                <th className="px-5 py-3 font-medium">Last Modified</th>
                <th className="px-5 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {templatesQuery.isLoading ? (
                <tr>
                  <td className="px-5 py-12 text-center text-slate-400" colSpan={5}>
                    Loading templates...
                  </td>
                </tr>
              ) : templates.length === 0 ? (
                <tr>
                  <td className="px-5 py-12 text-center text-slate-400" colSpan={5}>
                    No custom templates yet.
                  </td>
                </tr>
              ) : (
                templates.map((t) => (
                  <tr key={t.id} className="hover:bg-slate-50">
                    <td className="px-5 py-3 font-medium text-slate-900">
                      {t.name}
                    </td>
                    <td className="px-5 py-3 text-slate-600 truncate max-w-xs">
                      {t.subject}
                    </td>
                    <td className="px-5 py-3">
                      {t.category && (
                        <span
                          className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                            CATEGORY_COLORS[t.category] ?? "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {t.category}
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-slate-500">
                      {new Date(t.updated_at).toLocaleDateString()}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => setPreviewHtml(t.body_html)}
                          className="text-xs text-sky-600 hover:text-sky-700 cursor-pointer"
                        >
                          Preview
                        </button>
                        <button
                          onClick={() => {
                            if (window.confirm(`Delete template "${t.name}"?`)) {
                              deleteMutation.mutate(t.id);
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
      </div>

      {/* Template Editor Modal */}
      {showEditor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl mx-4 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
              <h3 className="text-lg font-semibold text-slate-900">
                {editorName ? "Edit Template" : "New Template"}
              </h3>
              <button
                onClick={resetEditor}
                className="text-slate-400 hover:text-slate-600 cursor-pointer"
              >
                Close
              </button>
            </div>
            <div className="flex-1 overflow-auto p-6 space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Template Name
                  </label>
                  <input
                    type="text"
                    value={editorName}
                    onChange={(e) => setEditorName(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">
                    Category
                  </label>
                  <select
                    value={editorCategory}
                    onChange={(e) => setEditorCategory(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                  >
                    <option value="">None</option>
                    <option value="IT">IT</option>
                    <option value="HR">HR</option>
                    <option value="Finance">Finance</option>
                    <option value="Executive">Executive</option>
                    <option value="Vendor">Vendor</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Subject Line
                </label>
                <input
                  type="text"
                  value={editorSubject}
                  onChange={(e) => setEditorSubject(e.target.value)}
                  placeholder="e.g., Action Required: Verify Your Account"
                  className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                />
              </div>

              {/* Variable insertion */}
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Insert Variable
                </label>
                <div className="flex flex-wrap gap-2">
                  {VARIABLES.map((v) => (
                    <button
                      key={v}
                      onClick={() => insertVariable(v)}
                      className="px-2 py-1 text-xs font-mono bg-slate-100 text-slate-600 rounded hover:bg-slate-200 cursor-pointer"
                    >
                      {v}
                    </button>
                  ))}
                </div>
              </div>

              {/* Body editor with preview toggle */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-sm font-medium text-slate-700">
                    Email Body (HTML)
                  </label>
                  <button
                    onClick={() => setShowHtmlPreview(!showHtmlPreview)}
                    className="text-xs text-sky-600 hover:text-sky-700 cursor-pointer"
                  >
                    {showHtmlPreview ? "Edit" : "Preview"}
                  </button>
                </div>
                {showHtmlPreview ? (
                  <div className="border border-slate-300 rounded-md p-4 min-h-[200px] bg-white">
                    <div
                      className="prose prose-sm max-w-none"
                      dangerouslySetInnerHTML={{ __html: editorBody }}
                    />
                  </div>
                ) : (
                  <textarea
                    rows={12}
                    value={editorBody}
                    onChange={(e) => setEditorBody(e.target.value)}
                    placeholder="<html>...</html>"
                    className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                  />
                )}
              </div>

              {createMutation.isError && (
                <p className="text-xs text-red-500">Failed to save template.</p>
              )}
            </div>
            <div className="flex justify-end gap-3 px-6 py-4 border-t border-slate-200">
              <button
                onClick={resetEditor}
                className="px-4 py-2 text-sm font-medium text-slate-700 border border-slate-300 rounded-md hover:bg-slate-50 cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={() => createMutation.mutate()}
                disabled={
                  !editorName.trim() ||
                  !editorSubject.trim() ||
                  createMutation.isPending
                }
                className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 disabled:opacity-50 cursor-pointer"
              >
                {createMutation.isPending ? "Saving..." : "Save Template"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Preview modal */}
      {previewHtml && !showEditor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200">
              <h3 className="font-semibold text-slate-900">Email Preview</h3>
              <button
                onClick={() => setPreviewHtml(null)}
                className="text-slate-400 hover:text-slate-600 cursor-pointer"
              >
                Close
              </button>
            </div>
            <div className="p-5 overflow-auto flex-1">
              <div
                className="prose prose-sm max-w-none"
                dangerouslySetInnerHTML={{ __html: previewHtml }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
