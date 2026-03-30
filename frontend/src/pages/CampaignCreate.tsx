import { useState, useCallback, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { createCampaign } from "@/api/campaigns";
import { listAddressBooks } from "@/api/addressbooks";
import { listTemplates, listPretexts } from "@/api/templates";
import {
  listLandingPages,
  listBuiltinTemplates,
  createFromEditor,
} from "@/api/landing_pages";
import { listSmtpProfiles, testSmtpProfile } from "@/api/settings";
import type {
  AddressBook,
  EmailTemplate,
  PretextTemplate,
  LandingPage,
  BuiltinLandingPage,
  SmtpProfile,
} from "@/types";
import LandingPageEditor, {
  type LandingPageEditorHandle,
} from "@/components/LandingPageEditor";
import LandingPagePreview from "@/components/LandingPagePreview";

interface WizardData {
  name: string;
  description: string;
  training_url: string;
  training_redirect_delay: number;
  address_book_id: string;
  template_id: string;
  landing_page_id: string;
  smtp_profile_id: string;
  send_window_start: string;
  send_window_end: string;
  throttle_rate: number;
}

const steps = [
  { id: 1, label: "Details" },
  { id: 2, label: "Recipients" },
  { id: 3, label: "Email Template" },
  { id: 4, label: "Landing Page" },
  { id: 5, label: "SMTP Profile" },
  { id: 6, label: "Schedule" },
];

const INITIAL_DATA: WizardData = {
  name: "",
  description: "",
  training_url: "",
  training_redirect_delay: 5,
  address_book_id: "",
  template_id: "",
  landing_page_id: "",
  smtp_profile_id: "",
  send_window_start: "",
  send_window_end: "",
  throttle_rate: 10,
};

function StepIndicator({
  currentStep,
  onStepClick,
}: {
  currentStep: number;
  onStepClick: (step: number) => void;
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {steps.map((step, idx) => (
        <div key={step.id} className="flex items-center">
          <button
            onClick={() => onStepClick(step.id)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-colors cursor-pointer ${
              currentStep === step.id
                ? "bg-sky-600 text-white"
                : currentStep > step.id
                  ? "bg-sky-100 text-sky-700"
                  : "bg-slate-100 text-slate-500"
            }`}
          >
            <span className="w-5 h-5 rounded-full bg-white/20 flex items-center justify-center text-xs">
              {currentStep > step.id ? "\u2713" : step.id}
            </span>
            {step.label}
          </button>
          {idx < steps.length - 1 && (
            <div className="w-8 h-px bg-slate-300 mx-1" />
          )}
        </div>
      ))}
    </div>
  );
}

export default function CampaignCreate() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const editorRef = useRef<LandingPageEditorHandle>(null);
  const [currentStep, setCurrentStep] = useState(1);
  const [data, setData] = useState<WizardData>(INITIAL_DATA);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [testEmailAddr, setTestEmailAddr] = useState("");
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [showInlineEditor, setShowInlineEditor] = useState(false);
  const [inlineEditorName, setInlineEditorName] = useState("");
  const [landingPreviewHtml, setLandingPreviewHtml] = useState<string | null>(null);

  const update = useCallback(
    (field: keyof WizardData, value: string | number) => {
      setData((prev) => ({ ...prev, [field]: value }));
      setErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    },
    []
  );

  // Queries
  const addressBooksQuery = useQuery({
    queryKey: ["addressbooks-list"],
    queryFn: () => listAddressBooks({ page: 1, page_size: 100 }),
    enabled: currentStep === 2,
  });

  const templatesQuery = useQuery({
    queryKey: ["templates-list"],
    queryFn: () => listTemplates({ page: 1, page_size: 100 }),
    enabled: currentStep === 3,
  });

  const pretextsQuery = useQuery<PretextTemplate[]>({
    queryKey: ["pretexts"],
    queryFn: listPretexts,
    enabled: currentStep === 3,
  });

  const landingPagesQuery = useQuery({
    queryKey: ["landing-pages-list"],
    queryFn: () => listLandingPages({ page: 1, page_size: 100 }),
    enabled: currentStep === 4,
  });

  const builtinLandingQuery = useQuery<BuiltinLandingPage[]>({
    queryKey: ["builtin-landing"],
    queryFn: listBuiltinTemplates,
    enabled: currentStep === 4,
  });

  const smtpQuery = useQuery<SmtpProfile[]>({
    queryKey: ["smtp-profiles"],
    queryFn: listSmtpProfiles,
    enabled: currentStep === 5,
  });

  const launchMutation = useMutation({
    mutationFn: () =>
      createCampaign({
        name: data.name,
        description: data.description,
        template_id: data.template_id,
        landing_page_id: data.landing_page_id || undefined,
        address_book_id: data.address_book_id,
        smtp_profile_id: data.smtp_profile_id,
      }),
    onSuccess: (campaign) => {
      navigate(`/campaigns/${campaign.id}`);
    },
  });

  const testMutation = useMutation({
    mutationFn: () => testSmtpProfile(data.smtp_profile_id, testEmailAddr),
    onSuccess: (result) => setTestResult(result),
    onError: () => setTestResult({ success: false, message: "Connection test failed." }),
  });

  const inlineCreateMutation = useMutation({
    mutationFn: (editorData: { name: string; html: string; css: string }) =>
      createFromEditor(editorData),
    onSuccess: (newPage) => {
      queryClient.invalidateQueries({ queryKey: ["landing-pages-list"] });
      update("landing_page_id", newPage.id);
      setShowInlineEditor(false);
      setInlineEditorName("");
    },
  });

  function validate(): boolean {
    const errs: Record<string, string> = {};
    if (currentStep === 1) {
      if (!data.name.trim()) errs.name = "Campaign name is required.";
    }
    if (currentStep === 2) {
      if (!data.address_book_id && !uploadFile)
        errs.address_book_id = "Select an address book or upload a file.";
    }
    if (currentStep === 3) {
      if (!data.template_id)
        errs.template_id = "Select an email template.";
    }
    if (currentStep === 5) {
      if (!data.smtp_profile_id)
        errs.smtp_profile_id = "Select an SMTP profile.";
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }

  function goNext() {
    if (validate()) {
      setCurrentStep((s) => Math.min(steps.length, s + 1));
    }
  }

  function goPrev() {
    setCurrentStep((s) => Math.max(1, s - 1));
  }

  const addressBooks = (addressBooksQuery.data?.items ?? []) as AddressBook[];
  const templates = (templatesQuery.data?.items ?? []) as EmailTemplate[];
  const pretexts = pretextsQuery.data ?? [];
  const landingPages = (landingPagesQuery.data?.items ?? []) as LandingPage[];
  const builtinLanding = builtinLandingQuery.data ?? [];
  const smtpProfiles = smtpQuery.data ?? [];

  const selectedAddressBook = addressBooks.find(
    (ab) => ab.id === data.address_book_id
  );
  const selectedTemplate = templates.find((t) => t.id === data.template_id);
  const selectedSmtp = smtpProfiles.find((s) => s.id === data.smtp_profile_id);

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-sm text-slate-500 mb-2">
          <Link to="/campaigns" className="hover:text-slate-700">
            Campaigns
          </Link>
          <span>/</span>
          <span className="text-slate-900">New Campaign</span>
        </div>
        <h1 className="text-2xl font-bold text-slate-900">Create Campaign</h1>
      </div>

      {/* Step indicator */}
      <div className="bg-white rounded-lg border border-slate-200 p-5">
        <StepIndicator
          currentStep={currentStep}
          onStepClick={(s) => {
            if (s < currentStep) setCurrentStep(s);
          }}
        />
      </div>

      {/* Step content */}
      <div className="bg-white rounded-lg border border-slate-200 p-6">
        {/* Step 1: Details */}
        {currentStep === 1 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-slate-900">
              Campaign Details
            </h2>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Campaign Name *
              </label>
              <input
                type="text"
                value={data.name}
                onChange={(e) => update("name", e.target.value)}
                placeholder="e.g., Q1 Security Awareness Test"
                className={`w-full px-3 py-2 border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500 ${
                  errors.name ? "border-red-300" : "border-slate-300"
                }`}
              />
              {errors.name && (
                <p className="text-xs text-red-500 mt-1">{errors.name}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Description
              </label>
              <textarea
                rows={3}
                value={data.description}
                onChange={(e) => update("description", e.target.value)}
                placeholder="Brief description of this campaign's purpose..."
                className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Training Redirect URL
              </label>
              <input
                type="url"
                value={data.training_url}
                onChange={(e) => update("training_url", e.target.value)}
                placeholder="https://training.example.com/awareness"
                className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
              />
              <p className="text-xs text-slate-400 mt-1">
                Users who interact with the phishing page will be redirected to this training URL.
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Redirect Delay (seconds)
              </label>
              <input
                type="number"
                min={0}
                max={60}
                value={data.training_redirect_delay}
                onChange={(e) =>
                  update("training_redirect_delay", parseInt(e.target.value) || 0)
                }
                className="w-32 px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
              />
            </div>
          </div>
        )}

        {/* Step 2: Recipients */}
        {currentStep === 2 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-slate-900">
              Recipients
            </h2>
            <p className="text-sm text-slate-500">
              Select an existing address book or upload a new Excel/CSV file.
            </p>

            {errors.address_book_id && (
              <p className="text-xs text-red-500">{errors.address_book_id}</p>
            )}

            {addressBooksQuery.isLoading ? (
              <p className="text-sm text-slate-400">Loading address books...</p>
            ) : addressBooks.length > 0 ? (
              <div className="space-y-2">
                <label className="block text-sm font-medium text-slate-700">
                  Select Address Book
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {addressBooks.map((ab) => (
                    <button
                      key={ab.id}
                      onClick={() => update("address_book_id", ab.id)}
                      className={`text-left p-4 rounded-lg border-2 transition-colors cursor-pointer ${
                        data.address_book_id === ab.id
                          ? "border-sky-500 bg-sky-50"
                          : "border-slate-200 hover:border-slate-300"
                      }`}
                    >
                      <p className="text-sm font-medium text-slate-900">
                        {ab.name}
                      </p>
                      <p className="text-xs text-slate-500 mt-1">
                        {ab.contact_count} contacts
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            <div className="border-t border-slate-200 pt-4">
              <label className="block text-sm font-medium text-slate-700 mb-2">
                Or Upload New File
              </label>
              <div className="border-2 border-dashed border-slate-300 rounded-lg p-6 text-center">
                <input
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  onChange={(e) =>
                    setUploadFile(e.target.files?.[0] ?? null)
                  }
                  className="text-sm text-slate-600"
                />
                <p className="text-xs text-slate-400 mt-2">
                  Supported formats: CSV, XLSX, XLS
                </p>
                {uploadFile && (
                  <p className="text-sm text-sky-600 mt-2 font-medium">
                    Selected: {uploadFile.name}
                  </p>
                )}
              </div>
            </div>

            {selectedAddressBook && (
              <div className="bg-sky-50 rounded-md p-4">
                <p className="text-sm text-sky-800 font-medium">
                  Selected: {selectedAddressBook.name}
                </p>
                <p className="text-xs text-sky-600 mt-1">
                  {selectedAddressBook.contact_count} recipients will receive this campaign.
                </p>
              </div>
            )}
          </div>
        )}

        {/* Step 3: Email Template */}
        {currentStep === 3 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-slate-900">
              Email Template
            </h2>
            <p className="text-sm text-slate-500">
              Select a pretext from the built-in library or choose a custom template.
            </p>

            {errors.template_id && (
              <p className="text-xs text-red-500">{errors.template_id}</p>
            )}

            {/* Pretext Library */}
            {pretexts.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-slate-700 mb-2">
                  Pretext Library
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {pretexts.map((pt) => (
                    <div
                      key={pt.id}
                      className={`p-4 rounded-lg border-2 transition-colors ${
                        data.template_id === pt.id
                          ? "border-sky-500 bg-sky-50"
                          : "border-slate-200 hover:border-slate-300"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                          {pt.category}
                        </span>
                        <span className="text-xs text-slate-400">
                          {"*".repeat(pt.difficulty)}{"*".repeat(0)}
                          <span className="text-slate-200">
                            {"*".repeat(5 - pt.difficulty)}
                          </span>
                        </span>
                      </div>
                      <p className="text-sm font-medium text-slate-900">
                        {pt.name}
                      </p>
                      <p className="text-xs text-slate-500 mt-1 line-clamp-2">
                        {pt.description}
                      </p>
                      <div className="flex gap-2 mt-3">
                        <button
                          onClick={() => update("template_id", pt.id)}
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
            {templates.length > 0 && (
              <div className="border-t border-slate-200 pt-4">
                <h3 className="text-sm font-medium text-slate-700 mb-2">
                  Custom Templates
                </h3>
                <div className="space-y-2">
                  {templates.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => update("template_id", t.id)}
                      className={`w-full text-left p-3 rounded-lg border-2 transition-colors cursor-pointer ${
                        data.template_id === t.id
                          ? "border-sky-500 bg-sky-50"
                          : "border-slate-200 hover:border-slate-300"
                      }`}
                    >
                      <p className="text-sm font-medium text-slate-900">
                        {t.name}
                      </p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Subject: {t.subject}
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {templates.length === 0 && pretexts.length === 0 && !templatesQuery.isLoading && (
              <div className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center text-slate-400">
                No templates available. Create one on the Templates page first.
              </div>
            )}

            {/* Preview modal */}
            {previewHtml && (
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
        )}

        {/* Step 4: Landing Page */}
        {currentStep === 4 && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">
                  Landing Page
                </h2>
                <p className="text-sm text-slate-500">
                  Select a landing page template for credential capture. This
                  step is optional.
                </p>
              </div>
              <button
                onClick={() => setShowInlineEditor(true)}
                className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 cursor-pointer"
              >
                Create New in Editor
              </button>
            </div>

            {/* Inline editor */}
            {showInlineEditor && (
              <div className="border border-slate-200 rounded-lg overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 bg-slate-50 border-b border-slate-200">
                  <div className="flex items-center gap-3">
                    <label className="text-sm font-medium text-slate-700">
                      Page Name:
                    </label>
                    <input
                      type="text"
                      value={inlineEditorName}
                      onChange={(e) => setInlineEditorName(e.target.value)}
                      placeholder="My Landing Page"
                      className="px-3 py-1.5 border border-slate-300 rounded-md text-sm w-56 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    {inlineCreateMutation.isError && (
                      <span className="text-xs text-red-500">
                        Failed to save
                      </span>
                    )}
                    {inlineCreateMutation.isPending && (
                      <span className="text-xs text-slate-400">Saving...</span>
                    )}
                    <button
                      onClick={() => {
                        setShowInlineEditor(false);
                        setInlineEditorName("");
                      }}
                      className="px-3 py-1.5 text-xs font-medium text-slate-600 border border-slate-300 rounded hover:bg-slate-50 cursor-pointer"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
                <div style={{ height: 500 }}>
                  <LandingPageEditor
                    ref={editorRef}
                    onSave={(editorData) => {
                      if (!inlineEditorName.trim()) return;
                      inlineCreateMutation.mutate({
                        name: inlineEditorName,
                        html: editorData.fullPage,
                        css: editorData.css,
                      });
                    }}
                  />
                </div>
              </div>
            )}

            {/* Built-in templates */}
            {builtinLanding.length > 0 && (
              <div>
                <h3 className="text-sm font-medium text-slate-700 mb-2">
                  Template Gallery
                </h3>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                  {builtinLanding.map((bp) => (
                    <div
                      key={bp.id}
                      className={`rounded-lg border-2 overflow-hidden transition-colors ${
                        data.landing_page_id === bp.id
                          ? "border-sky-500"
                          : "border-slate-200 hover:border-slate-300"
                      }`}
                    >
                      <div
                        className="aspect-video bg-slate-100 flex items-center justify-center text-xs text-slate-400 cursor-pointer"
                        onClick={() => update("landing_page_id", bp.id)}
                      >
                        {bp.thumbnail_url ? (
                          <img
                            src={bp.thumbnail_url}
                            alt={bp.name}
                            className="w-full h-full object-cover"
                          />
                        ) : (
                          bp.category
                        )}
                      </div>
                      <div className="p-2">
                        <p className="text-xs font-medium text-slate-900 truncate">
                          {bp.name}
                        </p>
                        <div className="flex items-center justify-between mt-1">
                          <span className="text-[10px] text-slate-500">
                            {bp.category}
                          </span>
                          <button
                            onClick={() =>
                              setLandingPreviewHtml(
                                `<div style="padding:32px;text-align:center;color:#94a3b8;">Preview: ${bp.name}</div>`
                              )
                            }
                            className="text-[10px] text-sky-600 hover:text-sky-700 cursor-pointer"
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

            {/* Custom landing pages */}
            {landingPages.length > 0 && (
              <div className="border-t border-slate-200 pt-4">
                <h3 className="text-sm font-medium text-slate-700 mb-2">
                  Custom Pages
                </h3>
                <div className="space-y-2">
                  {landingPages.map((lp) => (
                    <div
                      key={lp.id}
                      className={`flex items-center justify-between p-3 rounded-lg border-2 transition-colors ${
                        data.landing_page_id === lp.id
                          ? "border-sky-500 bg-sky-50"
                          : "border-slate-200 hover:border-slate-300"
                      }`}
                    >
                      <button
                        onClick={() => update("landing_page_id", lp.id)}
                        className="flex-1 text-left cursor-pointer"
                      >
                        <p className="text-sm font-medium text-slate-900">
                          {lp.name}
                        </p>
                        <p className="text-xs text-slate-500 mt-0.5">
                          {lp.description}
                        </p>
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setLandingPreviewHtml(lp.html_content);
                        }}
                        className="ml-3 px-2 py-1 text-xs text-sky-600 hover:text-sky-700 cursor-pointer shrink-0"
                      >
                        Preview
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {data.landing_page_id && (
              <button
                onClick={() => update("landing_page_id", "")}
                className="text-xs text-slate-500 hover:text-slate-700 cursor-pointer"
              >
                Clear selection (no landing page)
              </button>
            )}

            {/* Landing page preview modal */}
            {landingPreviewHtml && (
              <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
                <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] flex flex-col">
                  <div className="flex items-center justify-between px-5 py-3 border-b border-slate-200">
                    <h3 className="font-semibold text-slate-900">
                      Landing Page Preview
                    </h3>
                    <button
                      onClick={() => setLandingPreviewHtml(null)}
                      className="text-slate-400 hover:text-slate-600 cursor-pointer"
                    >
                      Close
                    </button>
                  </div>
                  <div className="flex-1 overflow-auto p-5">
                    <LandingPagePreview html={landingPreviewHtml} height={450} />
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Step 5: SMTP Profile */}
        {currentStep === 5 && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold text-slate-900">
              SMTP Profile
            </h2>
            <p className="text-sm text-slate-500">
              Select the sending profile for this campaign.
            </p>

            {errors.smtp_profile_id && (
              <p className="text-xs text-red-500">{errors.smtp_profile_id}</p>
            )}

            {smtpQuery.isLoading ? (
              <p className="text-sm text-slate-400">Loading profiles...</p>
            ) : smtpProfiles.length > 0 ? (
              <div className="space-y-2">
                {smtpProfiles.map((sp) => (
                  <button
                    key={sp.id}
                    onClick={() => update("smtp_profile_id", sp.id)}
                    className={`w-full text-left p-4 rounded-lg border-2 transition-colors cursor-pointer ${
                      data.smtp_profile_id === sp.id
                        ? "border-sky-500 bg-sky-50"
                        : "border-slate-200 hover:border-slate-300"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium text-slate-900">
                        {sp.name}
                      </p>
                      {sp.smtp_type && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                          {sp.smtp_type}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500 mt-1">
                      {sp.from_address} via {sp.host}:{sp.port}
                    </p>
                  </button>
                ))}
              </div>
            ) : (
              <div className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center text-slate-400">
                No SMTP profiles configured.{" "}
                <Link to="/settings" className="text-sky-600 hover:text-sky-700">
                  Add one in Settings
                </Link>
                .
              </div>
            )}

            {data.smtp_profile_id && (
              <div className="border-t border-slate-200 pt-4">
                <h3 className="text-sm font-medium text-slate-700 mb-2">
                  Test Send
                </h3>
                <div className="flex items-center gap-2">
                  <input
                    type="email"
                    value={testEmailAddr}
                    onChange={(e) => setTestEmailAddr(e.target.value)}
                    placeholder="test@example.com"
                    className="px-3 py-2 border border-slate-300 rounded-md text-sm w-64 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                  />
                  <button
                    onClick={() => testMutation.mutate()}
                    disabled={!testEmailAddr || testMutation.isPending}
                    className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                  >
                    {testMutation.isPending ? "Sending..." : "Test Send"}
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
          </div>
        )}

        {/* Step 6: Schedule & Review */}
        {currentStep === 6 && (
          <div className="space-y-6">
            <h2 className="text-lg font-semibold text-slate-900">
              Schedule and Review
            </h2>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Send Window Start
                </label>
                <input
                  type="datetime-local"
                  value={data.send_window_start}
                  onChange={(e) => update("send_window_start", e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Send Window End
                </label>
                <input
                  type="datetime-local"
                  value={data.send_window_end}
                  onChange={(e) => update("send_window_end", e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Throttle Rate (emails per minute)
              </label>
              <input
                type="number"
                min={1}
                max={1000}
                value={data.throttle_rate}
                onChange={(e) =>
                  update("throttle_rate", parseInt(e.target.value) || 1)
                }
                className="w-32 px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
              />
            </div>

            {/* Campaign Summary */}
            <div className="bg-slate-50 rounded-lg p-5 space-y-3">
              <h3 className="text-sm font-semibold text-slate-900">
                Campaign Summary
              </h3>
              <dl className="grid grid-cols-2 gap-x-8 gap-y-2 text-sm">
                <div>
                  <dt className="text-slate-500">Name</dt>
                  <dd className="text-slate-900 font-medium mt-0.5">
                    {data.name || "(not set)"}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Recipients</dt>
                  <dd className="text-slate-900 font-medium mt-0.5">
                    {selectedAddressBook
                      ? `${selectedAddressBook.name} (${selectedAddressBook.contact_count})`
                      : "(not set)"}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Email Template</dt>
                  <dd className="text-slate-900 font-medium mt-0.5">
                    {selectedTemplate?.name || data.template_id || "(not set)"}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Landing Page</dt>
                  <dd className="text-slate-900 font-medium mt-0.5">
                    {data.landing_page_id || "None (optional)"}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">SMTP Profile</dt>
                  <dd className="text-slate-900 font-medium mt-0.5">
                    {selectedSmtp?.name || "(not set)"}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Throttle Rate</dt>
                  <dd className="text-slate-900 font-medium mt-0.5">
                    {data.throttle_rate} emails/min
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Training URL</dt>
                  <dd className="text-slate-900 font-medium mt-0.5 truncate">
                    {data.training_url || "Not configured"}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Schedule</dt>
                  <dd className="text-slate-900 font-medium mt-0.5">
                    {data.send_window_start
                      ? `${data.send_window_start} to ${data.send_window_end || "open"}`
                      : "Immediate"}
                  </dd>
                </div>
              </dl>
            </div>

            {launchMutation.isError && (
              <p className="text-sm text-red-500">
                Failed to create campaign. Please check your configuration and try again.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between">
        <button
          onClick={goPrev}
          disabled={currentStep === 1}
          className="px-4 py-2 text-sm font-medium text-slate-700 border border-slate-300 rounded-md hover:bg-slate-50 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          Previous
        </button>
        <div className="flex gap-3">
          <Link
            to="/campaigns"
            className="px-4 py-2 text-sm font-medium text-slate-700 border border-slate-300 rounded-md hover:bg-slate-50"
          >
            Cancel
          </Link>
          {currentStep < steps.length ? (
            <button
              onClick={goNext}
              className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 cursor-pointer"
            >
              Next
            </button>
          ) : (
            <button
              onClick={() => launchMutation.mutate()}
              disabled={launchMutation.isPending}
              className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 disabled:opacity-50 cursor-pointer"
            >
              {launchMutation.isPending ? "Creating..." : "Launch Campaign"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
