import {
  useEffect,
  useRef,
  useImperativeHandle,
  forwardRef,
  useState,
  useCallback,
} from "react";
import grapesjs, { type Editor } from "grapesjs";
import "grapesjs/dist/css/grapes.min.css";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface LandingPageEditorProps {
  initialHtml?: string;
  onChange?: (data: { html: string; css: string }) => void;
  onSave?: (data: { html: string; css: string; fullPage: string }) => void;
}

export interface LandingPageEditorHandle {
  getHtml: () => string;
  getCss: () => string;
  getFullPage: () => string;
}

/* ------------------------------------------------------------------ */
/*  Phishing-specific block definitions                                */
/* ------------------------------------------------------------------ */

const LOGIN_FORM_HTML = `
<div style="max-width:400px;margin:40px auto;padding:32px;border:1px solid #e2e8f0;border-radius:8px;background:#ffffff;font-family:system-ui,-apple-system,sans-serif;">
  <h2 style="margin:0 0 24px;font-size:20px;font-weight:600;color:#1e293b;text-align:center;">Sign In</h2>
  <form action="{{submit_url}}" method="POST">
    <input type="hidden" name="token" value="{{recipient_token}}" />
    <div style="margin-bottom:16px;">
      <label style="display:block;margin-bottom:4px;font-size:14px;color:#475569;">Email</label>
      <input type="email" name="email" placeholder="you@company.com"
        style="width:100%;padding:10px 12px;border:1px solid #cbd5e1;border-radius:6px;font-size:14px;box-sizing:border-box;" />
    </div>
    <div style="margin-bottom:24px;">
      <label style="display:block;margin-bottom:4px;font-size:14px;color:#475569;">Password</label>
      <input type="password" name="password" placeholder="Enter your password"
        style="width:100%;padding:10px 12px;border:1px solid #cbd5e1;border-radius:6px;font-size:14px;box-sizing:border-box;" />
    </div>
    <button type="submit"
      style="width:100%;padding:12px;background:#0369a1;color:#ffffff;border:none;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;">
      Sign In
    </button>
  </form>
</div>`;

const COMPANY_HEADER_HTML = `
<div style="background:#1e293b;padding:16px 32px;display:flex;align-items:center;gap:12px;font-family:system-ui,-apple-system,sans-serif;">
  <div style="width:36px;height:36px;background:#38bdf8;border-radius:6px;display:flex;align-items:center;justify-content:center;color:#ffffff;font-weight:700;font-size:16px;">C</div>
  <span style="color:#ffffff;font-size:18px;font-weight:600;">Company Name</span>
</div>`;

const ALERT_BANNER_HTML = `
<div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:16px 24px;margin:16px 0;font-family:system-ui,-apple-system,sans-serif;">
  <p style="margin:0;color:#92400e;font-size:14px;font-weight:600;">Action Required</p>
  <p style="margin:4px 0 0;color:#92400e;font-size:13px;">Your account requires immediate attention. Please verify your credentials to continue.</p>
</div>`;

const FOOTER_HTML = `
<div style="background:#f8fafc;border-top:1px solid #e2e8f0;padding:24px 32px;text-align:center;font-family:system-ui,-apple-system,sans-serif;">
  <p style="margin:0 0 8px;font-size:12px;color:#94a3b8;">2026 Company Name. All rights reserved.</p>
  <div style="display:flex;justify-content:center;gap:16px;">
    <a href="#" style="font-size:12px;color:#64748b;text-decoration:none;">Privacy Policy</a>
    <a href="#" style="font-size:12px;color:#64748b;text-decoration:none;">Terms of Service</a>
    <a href="#" style="font-size:12px;color:#64748b;text-decoration:none;">Contact Support</a>
  </div>
</div>`;

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

const LandingPageEditor = forwardRef<
  LandingPageEditorHandle,
  LandingPageEditorProps
>(function LandingPageEditor({ initialHtml, onChange, onSave }, ref) {
  const editorContainerRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<Editor | null>(null);
  const [showCode, setShowCode] = useState(false);
  const [codeValue, setCodeValue] = useState("");
  const [importMode, setImportMode] = useState(false);
  const [importValue, setImportValue] = useState("");

  /* -- helpers exposed via ref -- */

  const getHtml = useCallback((): string => {
    if (!editorRef.current) return "";
    return editorRef.current.getHtml();
  }, []);

  const getCss = useCallback((): string => {
    if (!editorRef.current) return "";
    return editorRef.current.getCss() ?? "";
  }, []);

  const getFullPage = useCallback((): string => {
    const html = getHtml();
    const css = getCss();
    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<style>
body { margin: 0; padding: 0; }
${css}
</style>
</head>
<body>
<input type="hidden" name="token" value="{{recipient_token}}" />
${html}
</body>
</html>`;
  }, [getHtml, getCss]);

  useImperativeHandle(ref, () => ({ getHtml, getCss, getFullPage }), [
    getHtml,
    getCss,
    getFullPage,
  ]);

  /* -- GrapesJS initialization -- */

  useEffect(() => {
    if (!editorContainerRef.current) return;

    const editor = grapesjs.init({
      container: editorContainerRef.current,
      height: "100%",
      width: "auto",
      fromElement: false,
      components: initialHtml || "",
      storageManager: false,

      /* Canvas */
      canvas: {
        styles: [],
        scripts: [],
      },

      /* Block manager */
      blockManager: {
        appendTo: "#gjs-blocks",
        blocks: [
          {
            id: "text",
            label: "Text",
            category: "Basic",
            content: '<div data-gjs-type="text">Insert your text here</div>',
          },
          {
            id: "image",
            label: "Image",
            category: "Basic",
            content: { type: "image" },
          },
          {
            id: "link",
            label: "Link",
            category: "Basic",
            content: {
              type: "link",
              content: "Link text",
              style: { color: "#0369a1" },
            },
          },
          {
            id: "form",
            label: "Form",
            category: "Basic",
            content: `<form action="{{submit_url}}" method="POST"><input type="hidden" name="token" value="{{recipient_token}}" /></form>`,
          },
          {
            id: "input",
            label: "Input",
            category: "Basic",
            content: '<input type="text" placeholder="Enter value" style="padding:8px 12px;border:1px solid #cbd5e1;border-radius:4px;font-size:14px;" />',
          },
          {
            id: "button",
            label: "Button",
            category: "Basic",
            content:
              '<button type="button" style="padding:10px 24px;background:#0369a1;color:#fff;border:none;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;">Button</button>',
          },
          {
            id: "columns-2",
            label: "2 Columns",
            category: "Layout",
            content: `<div style="display:flex;gap:16px;padding:16px;">
              <div style="flex:1;min-height:60px;border:1px dashed #cbd5e1;padding:8px;">Column 1</div>
              <div style="flex:1;min-height:60px;border:1px dashed #cbd5e1;padding:8px;">Column 2</div>
            </div>`,
          },
          {
            id: "columns-3",
            label: "3 Columns",
            category: "Layout",
            content: `<div style="display:flex;gap:16px;padding:16px;">
              <div style="flex:1;min-height:60px;border:1px dashed #cbd5e1;padding:8px;">Column 1</div>
              <div style="flex:1;min-height:60px;border:1px dashed #cbd5e1;padding:8px;">Column 2</div>
              <div style="flex:1;min-height:60px;border:1px dashed #cbd5e1;padding:8px;">Column 3</div>
            </div>`,
          },
          {
            id: "section",
            label: "Section",
            category: "Layout",
            content:
              '<section style="padding:32px 24px;min-height:100px;"></section>',
          },
          {
            id: "divider",
            label: "Divider",
            category: "Layout",
            content:
              '<hr style="border:none;border-top:1px solid #e2e8f0;margin:16px 0;" />',
          },
          /* Phishing-specific blocks */
          {
            id: "login-form",
            label: "Login Form",
            category: "Phishing",
            content: LOGIN_FORM_HTML,
          },
          {
            id: "company-header",
            label: "Company Header",
            category: "Phishing",
            content: COMPANY_HEADER_HTML,
          },
          {
            id: "alert-banner",
            label: "Alert Banner",
            category: "Phishing",
            content: ALERT_BANNER_HTML,
          },
          {
            id: "footer",
            label: "Footer",
            category: "Phishing",
            content: FOOTER_HTML,
          },
        ],
      },

      /* Style manager */
      styleManager: {
        appendTo: "#gjs-styles",
        sectors: [
          {
            name: "General",
            open: true,
            properties: [
              "display",
              "float",
              "position",
              "top",
              "right",
              "bottom",
              "left",
              "overflow",
              "opacity",
            ],
          },
          {
            name: "Dimension",
            open: false,
            properties: [
              "width",
              "min-width",
              "max-width",
              "height",
              "min-height",
              "max-height",
              "margin",
              "padding",
            ],
          },
          {
            name: "Typography",
            open: false,
            properties: [
              "font-family",
              "font-size",
              "font-weight",
              "letter-spacing",
              "color",
              "line-height",
              "text-align",
              "text-decoration",
              "text-transform",
            ],
          },
          {
            name: "Decorations",
            open: false,
            properties: [
              "background-color",
              "background",
              "border",
              "border-radius",
              "box-shadow",
            ],
          },
        ],
      },

      /* Layer manager */
      layerManager: {
        appendTo: "#gjs-layers",
      },

      /* Device manager */
      deviceManager: {
        devices: [
          { name: "Desktop", width: "" },
          { name: "Tablet", width: "768px", widthMedia: "992px" },
          { name: "Mobile", width: "375px", widthMedia: "480px" },
        ],
      },

      /* Panels -- we provide our own toolbar, so disable defaults */
      panels: { defaults: [] },
    });

    /* Notify parent on changes */
    editor.on("component:update", () => {
      onChange?.({ html: editor.getHtml(), css: editor.getCss() ?? "" });
    });
    editor.on("component:add", () => {
      onChange?.({ html: editor.getHtml(), css: editor.getCss() ?? "" });
    });
    editor.on("component:remove", () => {
      onChange?.({ html: editor.getHtml(), css: editor.getCss() ?? "" });
    });

    editorRef.current = editor;

    return () => {
      editor.destroy();
      editorRef.current = null;
    };
    // initialHtml intentionally only applied on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* -- Toolbar actions -- */

  const handleSave = useCallback(() => {
    onSave?.({
      html: getHtml(),
      css: getCss(),
      fullPage: getFullPage(),
    });
  }, [onSave, getHtml, getCss, getFullPage]);

  const handlePreview = useCallback(() => {
    const fullPage = getFullPage();
    const win = window.open("", "_blank");
    if (win) {
      win.document.write(fullPage);
      win.document.close();
    }
  }, [getFullPage]);

  const handleUndo = useCallback(() => {
    editorRef.current?.UndoManager.undo();
  }, []);

  const handleRedo = useCallback(() => {
    editorRef.current?.UndoManager.redo();
  }, []);

  const handleClear = useCallback(() => {
    if (!editorRef.current) return;
    if (window.confirm("Clear all content? This cannot be undone.")) {
      editorRef.current.DomComponents.clear();
      editorRef.current.CssComposer.clear();
    }
  }, []);

  const handleToggleCode = useCallback(() => {
    if (!showCode) {
      setCodeValue(getHtml());
    }
    setShowCode((prev) => !prev);
  }, [showCode, getHtml]);

  const handleApplyCode = useCallback(() => {
    if (!editorRef.current) return;
    editorRef.current.DomComponents.clear();
    editorRef.current.setComponents(codeValue);
    setShowCode(false);
  }, [codeValue]);

  const handleImportHtml = useCallback(() => {
    if (!editorRef.current || !importValue.trim()) return;
    editorRef.current.DomComponents.clear();
    editorRef.current.setComponents(importValue);
    setImportMode(false);
    setImportValue("");
  }, [importValue]);

  const handleDeviceChange = useCallback((device: string) => {
    editorRef.current?.setDevice(device);
  }, []);

  /* -- Active sidebar tab -- */
  const [activePanel, setActivePanel] = useState<
    "blocks" | "styles" | "layers"
  >("blocks");

  return (
    <div className="flex flex-col h-full bg-slate-50">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-slate-200 shrink-0">
        <div className="flex items-center gap-1">
          <button
            onClick={handleSave}
            className="px-3 py-1.5 text-xs font-medium text-white bg-sky-600 rounded hover:bg-sky-700 cursor-pointer"
          >
            Save
          </button>
          <button
            onClick={handlePreview}
            className="px-3 py-1.5 text-xs font-medium text-slate-700 bg-slate-100 rounded hover:bg-slate-200 cursor-pointer"
          >
            Preview
          </button>
          <div className="w-px h-5 bg-slate-200 mx-1" />
          <button
            onClick={handleUndo}
            className="px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded cursor-pointer"
            title="Undo"
          >
            Undo
          </button>
          <button
            onClick={handleRedo}
            className="px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded cursor-pointer"
            title="Redo"
          >
            Redo
          </button>
          <div className="w-px h-5 bg-slate-200 mx-1" />
          <button
            onClick={handleClear}
            className="px-2 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50 rounded cursor-pointer"
          >
            Clear
          </button>
          <button
            onClick={() => setImportMode(true)}
            className="px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded cursor-pointer"
          >
            Import HTML
          </button>
          <button
            onClick={handleToggleCode}
            className={`px-2 py-1.5 text-xs font-medium rounded cursor-pointer ${
              showCode
                ? "bg-sky-100 text-sky-700"
                : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            {showCode ? "Close Code" : "Code View"}
          </button>
        </div>

        {/* Device switcher */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => handleDeviceChange("Desktop")}
            className="px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded cursor-pointer"
            title="Desktop"
          >
            Desktop
          </button>
          <button
            onClick={() => handleDeviceChange("Tablet")}
            className="px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded cursor-pointer"
            title="Tablet"
          >
            Tablet
          </button>
          <button
            onClick={() => handleDeviceChange("Mobile")}
            className="px-2 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 rounded cursor-pointer"
            title="Mobile"
          >
            Mobile
          </button>
        </div>
      </div>

      {/* Main area: sidebar + canvas */}
      <div className="flex flex-1 min-h-0">
        {/* Sidebar */}
        <div className="w-64 bg-white border-r border-slate-200 flex flex-col shrink-0">
          <div className="flex border-b border-slate-200">
            {(["blocks", "styles", "layers"] as const).map((panel) => (
              <button
                key={panel}
                onClick={() => setActivePanel(panel)}
                className={`flex-1 px-3 py-2 text-xs font-medium capitalize cursor-pointer ${
                  activePanel === panel
                    ? "text-sky-700 border-b-2 border-sky-600"
                    : "text-slate-500 hover:text-slate-700"
                }`}
              >
                {panel}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-y-auto">
            <div
              id="gjs-blocks"
              className={activePanel === "blocks" ? "" : "hidden"}
            />
            <div
              id="gjs-styles"
              className={activePanel === "styles" ? "" : "hidden"}
            />
            <div
              id="gjs-layers"
              className={activePanel === "layers" ? "" : "hidden"}
            />
          </div>
        </div>

        {/* Canvas */}
        <div className="flex-1 min-w-0 relative">
          <div ref={editorContainerRef} className="h-full" />

          {/* Code view overlay */}
          {showCode && (
            <div className="absolute inset-0 z-10 bg-white flex flex-col">
              <div className="flex items-center justify-between px-4 py-2 border-b border-slate-200">
                <span className="text-sm font-medium text-slate-700">
                  HTML Source
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={handleApplyCode}
                    className="px-3 py-1 text-xs font-medium text-white bg-sky-600 rounded hover:bg-sky-700 cursor-pointer"
                  >
                    Apply Changes
                  </button>
                  <button
                    onClick={() => setShowCode(false)}
                    className="px-3 py-1 text-xs font-medium text-slate-600 bg-slate-100 rounded hover:bg-slate-200 cursor-pointer"
                  >
                    Cancel
                  </button>
                </div>
              </div>
              <textarea
                value={codeValue}
                onChange={(e) => setCodeValue(e.target.value)}
                className="flex-1 p-4 font-mono text-sm text-slate-800 bg-slate-50 resize-none focus:outline-none"
                spellCheck={false}
              />
            </div>
          )}
        </div>
      </div>

      {/* Import HTML modal */}
      {importMode && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4 p-6 space-y-4">
            <h3 className="text-lg font-semibold text-slate-900">
              Import HTML
            </h3>
            <p className="text-sm text-slate-500">
              Paste HTML content below. This will replace the current editor
              content.
            </p>
            <textarea
              rows={14}
              value={importValue}
              onChange={(e) => setImportValue(e.target.value)}
              placeholder="Paste HTML here..."
              className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
              spellCheck={false}
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setImportMode(false);
                  setImportValue("");
                }}
                className="px-4 py-2 text-sm font-medium text-slate-700 border border-slate-300 rounded-md hover:bg-slate-50 cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={handleImportHtml}
                disabled={!importValue.trim()}
                className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 disabled:opacity-50 cursor-pointer"
              >
                Import
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
});

export default LandingPageEditor;
