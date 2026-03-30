import { useState } from "react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface LandingPagePreviewProps {
  html: string;
  width?: number | string;
  height?: number;
}

type DeviceSize = "desktop" | "tablet" | "mobile";

const DEVICE_WIDTHS: Record<DeviceSize, string> = {
  desktop: "100%",
  tablet: "768px",
  mobile: "375px",
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function LandingPagePreview({
  html,
  width = "100%",
  height = 600,
}: LandingPagePreviewProps) {
  const [device, setDevice] = useState<DeviceSize>("desktop");

  const containerWidth =
    device === "desktop"
      ? typeof width === "number"
        ? `${width}px`
        : width
      : DEVICE_WIDTHS[device];

  return (
    <div className="flex flex-col items-center gap-4">
      {/* Device toggle */}
      <div className="flex items-center gap-1 bg-slate-100 rounded-lg p-1">
        {(["desktop", "tablet", "mobile"] as const).map((d) => (
          <button
            key={d}
            onClick={() => setDevice(d)}
            className={`px-3 py-1.5 text-xs font-medium rounded-md capitalize cursor-pointer transition-colors ${
              device === d
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {d}
          </button>
        ))}
      </div>

      {/* Browser chrome wrapper */}
      <div
        className="transition-all duration-200 ease-in-out"
        style={{ width: containerWidth, maxWidth: "100%" }}
      >
        {/* Title bar */}
        <div className="bg-slate-200 rounded-t-lg px-4 py-2 flex items-center gap-2">
          <div className="flex gap-1.5">
            <span className="w-3 h-3 rounded-full bg-red-400" />
            <span className="w-3 h-3 rounded-full bg-yellow-400" />
            <span className="w-3 h-3 rounded-full bg-green-400" />
          </div>
          <div className="flex-1 mx-4">
            <div className="bg-white rounded px-3 py-1 text-xs text-slate-400 text-center truncate">
              https://example.com/landing
            </div>
          </div>
        </div>

        {/* Iframe */}
        <div
          className="border border-t-0 border-slate-200 rounded-b-lg overflow-hidden bg-white shadow-lg"
          style={{ height }}
        >
          <iframe
            srcDoc={html}
            sandbox="allow-same-origin"
            title="Landing page preview"
            className="w-full h-full border-0"
          />
        </div>
      </div>
    </div>
  );
}
