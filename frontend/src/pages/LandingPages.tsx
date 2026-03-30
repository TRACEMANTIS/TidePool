import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listLandingPages,
  listBuiltinTemplates,
  deleteLandingPage,
  cloneFromUrl,
  createFromEditor,
  updateLandingPageHtml,
  previewLandingPage,
} from "@/api/landing_pages";
import type {
  LandingPage,
  BuiltinLandingPage,
  PaginatedResponse,
} from "@/types";
import LandingPageEditor, {
  type LandingPageEditorHandle,
} from "@/components/LandingPageEditor";
import LandingPagePreview from "@/components/LandingPagePreview";

const CATEGORY_COLORS: Record<string, string> = {
  O365: "bg-blue-100 text-blue-700",
  Google: "bg-red-100 text-red-700",
  Okta: "bg-indigo-100 text-indigo-700",
  VPN: "bg-green-100 text-green-700",
  Generic: "bg-slate-100 text-slate-700",
};

interface EditorState {
  mode: "create" | "edit" | "customize";
  pageId?: string;
  pageName?: string;
  initialHtml?: string;
}

export default function LandingPageList() {
  const queryClient = useQueryClient();
  const editorHandleRef = useRef<LandingPageEditorHandle>(null);
  const [cloneUrl, setCloneUrl] = useState("");
  const [cloneName, setCloneName] = useState("");
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [editorState, setEditorState] = useState<EditorState | null>(null);
  const [editorName, setEditorName] = useState("");

  const pagesQuery = useQuery<PaginatedResponse<LandingPage>>({
    queryKey: ["landing-pages"],
    queryFn: () => listLandingPages({ page: 1, page_size: 100 }),
  });

  const builtinQuery = useQuery<BuiltinLandingPage[]>({
    queryKey: ["builtin-landing-pages"],
    queryFn: listBuiltinTemplates,
  });

  const deleteMutation = useMutation({
    mutationFn: deleteLandingPage,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["landing-pages"] });
    },
  });

  const cloneMutation = useMutation({
    mutationFn: () => cloneFromUrl(cloneUrl, cloneName),
    onSuccess: (cloned) => {
      queryClient.invalidateQueries({ queryKey: ["landing-pages"] });
      setCloneUrl("");
      setCloneName("");
      // Open cloned page in editor for review
      setEditorState({
        mode: "edit",
        pageId: cloned.id,
        pageName: cloned.name,
        initialHtml: cloned.html_content,
      });
      setEditorName(cloned.name);
    },
  });

  const createFromEditorMutation = useMutation({
    mutationFn: (data: { name: string; html: string; css: string }) =>
      createFromEditor(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["landing-pages"] });
      setEditorState(null);
      setEditorName("");
    },
  });

  const updateHtmlMutation = useMutation({
    mutationFn: (data: { id: string; html: string; css?: string }) =>
      updateLandingPageHtml(data.id, { html: data.html, css: data.css }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["landing-pages"] });
      setEditorState(null);
      setEditorName("");
    },
  });

  const pages = pagesQuery.data?.items ?? [];
  const builtinPages = builtinQuery.data ?? [];

  /* -- Preview with sample data -- */
  const handlePreviewPage = async (pageId: string) => {
    try {
      const result = await previewLandingPage(pageId);
      setPreviewHtml(result.html);
    } catch {
      setPreviewHtml(
        '<div style="padding:32px;text-align:center;color:#94a3b8;">Failed to load preview.</div>'
      );
    }
  };

  /* -- Editor save handler -- */
  const handleEditorSave = (data: {
    html: string;
    css: string;
    fullPage: string;
  }) => {
    if (!editorState) return;

    if (editorState.mode === "edit" && editorState.pageId) {
      updateHtmlMutation.mutate({
        id: editorState.pageId,
        html: data.fullPage,
        css: data.css,
      });
    } else {
      // create or customize
      if (!editorName.trim()) return;
      createFromEditorMutation.mutate({
        name: editorName,
        html: data.fullPage,
        css: data.css,
      });
    }
  };

  /* -- Full-screen editor modal -- */
  if (editorState) {
    return (
      <div className="fixed inset-0 z-50 flex flex-col bg-white">
        {/* Editor header bar */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-white shrink-0">
          <div className="flex items-center gap-4">
            <button
              onClick={() => {
                setEditorState(null);
                setEditorName("");
              }}
              className="text-sm text-slate-500 hover:text-slate-700 cursor-pointer"
            >
              &larr; Back to Landing Pages
            </button>
            <div className="w-px h-5 bg-slate-200" />
            {editorState.mode === "edit" ? (
              <span className="text-sm font-medium text-slate-900">
                Editing: {editorState.pageName}
              </span>
            ) : (
              <div className="flex items-center gap-2">
                <label className="text-sm font-medium text-slate-700">
                  Page Name:
                </label>
                <input
                  type="text"
                  value={editorName}
                  onChange={(e) => setEditorName(e.target.value)}
                  placeholder="My Landing Page"
                  className="px-3 py-1.5 border border-slate-300 rounded-md text-sm w-64 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                />
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            {(createFromEditorMutation.isPending ||
              updateHtmlMutation.isPending) && (
              <span className="text-xs text-slate-400">Saving...</span>
            )}
            {createFromEditorMutation.isError && (
              <span className="text-xs text-red-500">Save failed</span>
            )}
            {updateHtmlMutation.isError && (
              <span className="text-xs text-red-500">Save failed</span>
            )}
          </div>
        </div>

        {/* Editor canvas */}
        <div className="flex-1 min-h-0">
          <LandingPageEditor
            ref={editorHandleRef}
            initialHtml={editorState.initialHtml ?? ""}
            onSave={handleEditorSave}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Landing Pages</h1>
          <p className="text-sm text-slate-500 mt-1">
            Design credential capture pages for your phishing campaigns.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setEditorState({ mode: "create" });
              setEditorName("");
            }}
            className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 cursor-pointer"
          >
            Create Custom Page
          </button>
        </div>
      </div>

      {/* Template Gallery */}
      {builtinPages.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-slate-900 mb-3">
            Template Gallery
          </h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
            {builtinPages.map((bp) => (
              <div
                key={bp.id}
                className="bg-white rounded-lg border border-slate-200 overflow-hidden group"
              >
                <div className="aspect-video bg-slate-100 flex items-center justify-center relative">
                  {bp.thumbnail_url ? (
                    <img
                      src={bp.thumbnail_url}
                      alt={bp.name}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <span className="text-sm text-slate-400">{bp.category}</span>
                  )}
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors" />
                </div>
                <div className="p-3">
                  <p className="text-sm font-medium text-slate-900">{bp.name}</p>
                  <span
                    className={`inline-flex mt-1 text-xs font-medium px-2 py-0.5 rounded-full ${
                      CATEGORY_COLORS[bp.category] ?? CATEGORY_COLORS.Generic
                    }`}
                  >
                    {bp.category}
                  </span>
                  <div className="flex gap-2 mt-2">
                    <button
                      onClick={() => {
                        setEditorState({
                          mode: "customize",
                          pageName: bp.name,
                          initialHtml: `<div class="p-4 text-center text-slate-500">Template: ${bp.name}</div>`,
                        });
                        setEditorName(`${bp.name} (Custom)`);
                      }}
                      className="text-xs font-medium text-sky-600 hover:text-sky-700 cursor-pointer"
                    >
                      Customize
                    </button>
                    <button
                      onClick={() => handlePreviewPage(bp.id)}
                      className="text-xs font-medium text-slate-500 hover:text-slate-700 cursor-pointer"
                    >
                      Preview
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Clone from URL */}
      <div className="bg-white rounded-lg border border-slate-200 p-5">
        <h2 className="text-sm font-semibold text-slate-900 mb-3">
          Clone from URL
        </h2>
        <p className="text-xs text-slate-500 mb-3">
          Clone an external page and open it in the editor for review and
          modification.
        </p>
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label className="block text-xs text-slate-500 mb-1">
              Source URL
            </label>
            <input
              type="url"
              value={cloneUrl}
              onChange={(e) => setCloneUrl(e.target.value)}
              placeholder="https://login.example.com"
              className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
            />
          </div>
          <div className="w-48">
            <label className="block text-xs text-slate-500 mb-1">
              Page Name
            </label>
            <input
              type="text"
              value={cloneName}
              onChange={(e) => setCloneName(e.target.value)}
              placeholder="My Cloned Page"
              className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
            />
          </div>
          <button
            onClick={() => cloneMutation.mutate()}
            disabled={!cloneUrl.trim() || !cloneName.trim() || cloneMutation.isPending}
            className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 disabled:opacity-50 cursor-pointer"
          >
            {cloneMutation.isPending ? "Cloning..." : "Clone & Edit"}
          </button>
        </div>
        {cloneMutation.isError && (
          <p className="text-xs text-red-500 mt-2">Failed to clone page. Check the URL and try again.</p>
        )}
      </div>

      {/* Custom Pages Table */}
      <div>
        <h2 className="text-lg font-semibold text-slate-900 mb-3">
          Custom Pages
        </h2>
        <div className="bg-white rounded-lg border border-slate-200">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 border-b border-slate-200">
                <th className="px-5 py-3 font-medium">Name</th>
                <th className="px-5 py-3 font-medium">Capture Credentials</th>
                <th className="px-5 py-3 font-medium">Redirect URL</th>
                <th className="px-5 py-3 font-medium">Last Modified</th>
                <th className="px-5 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {pagesQuery.isLoading ? (
                <tr>
                  <td className="px-5 py-12 text-center text-slate-400" colSpan={5}>
                    Loading landing pages...
                  </td>
                </tr>
              ) : pages.length === 0 ? (
                <tr>
                  <td className="px-5 py-12 text-center text-slate-400" colSpan={5}>
                    No custom landing pages yet. Click "Create Custom Page" to get started.
                  </td>
                </tr>
              ) : (
                pages.map((lp) => (
                  <tr key={lp.id} className="hover:bg-slate-50">
                    <td className="px-5 py-3 font-medium text-slate-900">
                      {lp.name}
                    </td>
                    <td className="px-5 py-3">
                      <span
                        className={`text-xs font-medium ${
                          lp.capture_credentials
                            ? "text-green-600"
                            : "text-slate-400"
                        }`}
                      >
                        {lp.capture_credentials ? "Yes" : "No"}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-slate-500 text-xs truncate max-w-xs">
                      {lp.redirect_url || "--"}
                    </td>
                    <td className="px-5 py-3 text-slate-500">
                      {new Date(lp.updated_at).toLocaleDateString()}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => {
                            setEditorState({
                              mode: "edit",
                              pageId: lp.id,
                              pageName: lp.name,
                              initialHtml: lp.html_content,
                            });
                            setEditorName(lp.name);
                          }}
                          className="text-xs text-sky-600 hover:text-sky-700 cursor-pointer"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => setPreviewHtml(lp.html_content)}
                          className="text-xs text-slate-500 hover:text-slate-700 cursor-pointer"
                        >
                          Preview
                        </button>
                        <button
                          onClick={() => {
                            if (
                              window.confirm(
                                `Delete landing page "${lp.name}"?`
                              )
                            ) {
                              deleteMutation.mutate(lp.id);
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

      {/* Preview modal */}
      {previewHtml && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200">
              <h3 className="font-semibold text-slate-900">Landing Page Preview</h3>
              <button
                onClick={() => setPreviewHtml(null)}
                className="text-slate-400 hover:text-slate-600 cursor-pointer"
              >
                Close
              </button>
            </div>
            <div className="flex-1 overflow-auto p-5">
              <LandingPagePreview html={previewHtml} height={500} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
