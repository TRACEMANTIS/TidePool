import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listAddressBooks,
  uploadAddressBook,
  deleteAddressBook,
  getContacts,
  detectColumns,
  mapColumns,
} from "@/api/addressbooks";
import type {
  AddressBook,
  Contact,
  DetectedColumn,
  ColumnMapping,
  PaginatedResponse,
} from "@/types";

const TIDEPOOL_FIELDS = [
  { value: "", label: "-- Skip --" },
  { value: "email", label: "Email" },
  { value: "first_name", label: "First Name" },
  { value: "last_name", label: "Last Name" },
  { value: "position", label: "Position / Title" },
  { value: "department", label: "Department" },
  { value: "custom", label: "Custom Field" },
];

export default function AddressBookList() {
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [uploadName, setUploadName] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);

  // Column mapping state
  const [mappingBookId, setMappingBookId] = useState<string | null>(null);
  const [detectedCols, setDetectedCols] = useState<DetectedColumn[]>([]);
  const [colMappings, setColMappings] = useState<Record<string, string>>({});
  const [mappingProgress, setMappingProgress] = useState<number | null>(null);

  const { data, isLoading } = useQuery<PaginatedResponse<AddressBook>>({
    queryKey: ["addressbooks"],
    queryFn: () => listAddressBooks({ page: 1, page_size: 100 }),
  });

  const contactsQuery = useQuery<PaginatedResponse<Contact>>({
    queryKey: ["addressbook-contacts", expandedId],
    queryFn: () => getContacts(expandedId!, { page: 1, page_size: 20 }),
    enabled: !!expandedId,
  });

  const uploadMutation = useMutation({
    mutationFn: () => uploadAddressBook(uploadFile!, uploadName),
    onSuccess: (newBook) => {
      queryClient.invalidateQueries({ queryKey: ["addressbooks"] });
      setShowUpload(false);
      setUploadFile(null);
      setUploadName("");
      // Start column detection
      startColumnMapping(newBook.id);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteAddressBook,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["addressbooks"] });
    },
  });

  const mapMutation = useMutation({
    mutationFn: (params: { id: string; mappings: ColumnMapping[] }) =>
      mapColumns(params.id, params.mappings),
    onSuccess: () => {
      setMappingProgress(100);
      setTimeout(() => {
        setMappingBookId(null);
        setMappingProgress(null);
        queryClient.invalidateQueries({ queryKey: ["addressbooks"] });
      }, 1500);
    },
  });

  const startColumnMapping = useCallback(async (bookId: string) => {
    setMappingBookId(bookId);
    setMappingProgress(null);
    try {
      const cols = await detectColumns(bookId);
      setDetectedCols(cols);
      const autoMap: Record<string, string> = {};
      cols.forEach((col) => {
        if (col.suggested_mapping) {
          autoMap[col.source_column] = col.suggested_mapping;
        }
      });
      setColMappings(autoMap);
    } catch {
      setDetectedCols([]);
    }
  }, []);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) {
      setUploadFile(file);
      if (!uploadName) setUploadName(file.name.replace(/\.[^.]+$/, ""));
      setShowUpload(true);
    }
  }

  function submitMapping() {
    if (!mappingBookId) return;
    const mappings: ColumnMapping[] = Object.entries(colMappings)
      .filter(([, v]) => v)
      .map(([source, target]) => ({ source_column: source, target_field: target }));
    setMappingProgress(50);
    mapMutation.mutate({ id: mappingBookId, mappings });
  }

  const addressBooks = data?.items ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Address Books</h1>
          <p className="text-sm text-slate-500 mt-1">
            Manage contact lists for your phishing campaigns.
          </p>
        </div>
        <button
          onClick={() => setShowUpload(true)}
          className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 cursor-pointer"
        >
          Upload Address Book
        </button>
      </div>

      {/* Upload / Drag-and-Drop Zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          dragOver
            ? "border-sky-400 bg-sky-50"
            : "border-slate-300 bg-white"
        }`}
      >
        <div className="text-slate-500">
          <p className="text-sm font-medium">
            Drag and drop a file here, or{" "}
            <label className="text-sky-600 hover:text-sky-700 cursor-pointer">
              browse
              <input
                type="file"
                accept=".csv,.xlsx,.xls"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) {
                    setUploadFile(f);
                    if (!uploadName) setUploadName(f.name.replace(/\.[^.]+$/, ""));
                    setShowUpload(true);
                  }
                }}
              />
            </label>
          </p>
          <p className="text-xs text-slate-400 mt-1">
            Supported formats: CSV, XLSX, XLS
          </p>
        </div>
      </div>

      {/* Upload modal */}
      {showUpload && uploadFile && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6 space-y-4">
            <h3 className="text-lg font-semibold text-slate-900">
              Upload Address Book
            </h3>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Name
              </label>
              <input
                type="text"
                value={uploadName}
                onChange={(e) => setUploadName(e.target.value)}
                className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500"
              />
            </div>
            <p className="text-sm text-slate-500">
              File: {uploadFile.name} ({(uploadFile.size / 1024).toFixed(1)} KB)
            </p>
            {uploadMutation.isError && (
              <p className="text-xs text-red-500">Upload failed. Please try again.</p>
            )}
            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowUpload(false);
                  setUploadFile(null);
                  setUploadName("");
                }}
                className="px-4 py-2 text-sm font-medium text-slate-700 border border-slate-300 rounded-md hover:bg-slate-50 cursor-pointer"
              >
                Cancel
              </button>
              <button
                onClick={() => uploadMutation.mutate()}
                disabled={!uploadName.trim() || uploadMutation.isPending}
                className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 disabled:opacity-50 cursor-pointer"
              >
                {uploadMutation.isPending ? "Uploading..." : "Upload"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Column mapping modal */}
      {mappingBookId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4 p-6 space-y-4 max-h-[80vh] overflow-auto">
            <h3 className="text-lg font-semibold text-slate-900">
              Map Columns
            </h3>
            <p className="text-sm text-slate-500">
              Match the detected columns to TidePool fields. Auto-detected suggestions are pre-selected.
            </p>

            {detectedCols.length === 0 ? (
              <p className="text-sm text-slate-400">Detecting columns...</p>
            ) : (
              <div className="space-y-3">
                {detectedCols.map((col) => (
                  <div
                    key={col.source_column}
                    className="flex items-center gap-4 p-3 bg-slate-50 rounded-md"
                  >
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-slate-900">
                        {col.source_column}
                        {col.suggested_mapping && (
                          <span className="ml-2 text-xs text-sky-600 font-normal">
                            (auto-detected)
                          </span>
                        )}
                      </p>
                      <p className="text-xs text-slate-400 mt-0.5 truncate">
                        Sample: {col.sample_values.slice(0, 3).join(", ")}
                      </p>
                    </div>
                    <select
                      value={colMappings[col.source_column] ?? ""}
                      onChange={(e) =>
                        setColMappings((prev) => ({
                          ...prev,
                          [col.source_column]: e.target.value,
                        }))
                      }
                      className="px-3 py-1.5 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-sky-500"
                    >
                      {TIDEPOOL_FIELDS.map((f) => (
                        <option key={f.value} value={f.value}>
                          {f.label}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            )}

            {mappingProgress !== null && (
              <div className="space-y-1">
                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-sky-500 rounded-full transition-all"
                    style={{ width: `${mappingProgress}%` }}
                  />
                </div>
                <p className="text-xs text-slate-500">
                  {mappingProgress === 100 ? "Import complete" : "Processing..."}
                </p>
              </div>
            )}

            <div className="flex justify-end gap-3">
              <button
                onClick={() => {
                  setMappingBookId(null);
                  setDetectedCols([]);
                }}
                className="px-4 py-2 text-sm font-medium text-slate-700 border border-slate-300 rounded-md hover:bg-slate-50 cursor-pointer"
              >
                Skip
              </button>
              <button
                onClick={submitMapping}
                disabled={mapMutation.isPending}
                className="px-4 py-2 text-sm font-medium text-white bg-sky-600 rounded-md hover:bg-sky-700 disabled:opacity-50 cursor-pointer"
              >
                {mapMutation.isPending ? "Importing..." : "Import"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Address book list */}
      <div className="bg-white rounded-lg border border-slate-200">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500 border-b border-slate-200">
              <th className="px-5 py-3 font-medium">Name</th>
              <th className="px-5 py-3 font-medium">Contacts</th>
              <th className="px-5 py-3 font-medium">Source File</th>
              <th className="px-5 py-3 font-medium">Imported</th>
              <th className="px-5 py-3 font-medium">Status</th>
              <th className="px-5 py-3 font-medium"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading ? (
              <tr>
                <td className="px-5 py-12 text-center text-slate-400" colSpan={6}>
                  Loading address books...
                </td>
              </tr>
            ) : addressBooks.length === 0 ? (
              <tr>
                <td className="px-5 py-12 text-center text-slate-400" colSpan={6}>
                  No address books yet. Upload a CSV or Excel file to get started.
                </td>
              </tr>
            ) : (
              addressBooks.map((ab) => (
                <>
                  <tr
                    key={ab.id}
                    onClick={() =>
                      setExpandedId(expandedId === ab.id ? null : ab.id)
                    }
                    className="hover:bg-slate-50 cursor-pointer"
                  >
                    <td className="px-5 py-3 font-medium text-slate-900">
                      {ab.name}
                    </td>
                    <td className="px-5 py-3 text-slate-600">
                      {ab.contact_count}
                    </td>
                    <td className="px-5 py-3 text-slate-500 text-xs truncate max-w-xs">
                      {ab.source_file || "--"}
                    </td>
                    <td className="px-5 py-3 text-slate-500">
                      {new Date(ab.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-5 py-3">
                      <span
                        className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${
                          ab.status === "ready"
                            ? "bg-green-100 text-green-700"
                            : ab.status === "processing"
                              ? "bg-yellow-100 text-yellow-700"
                              : "bg-red-100 text-red-700"
                        }`}
                      >
                        {ab.status}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          if (
                            window.confirm(
                              `Delete address book "${ab.name}"?`
                            )
                          ) {
                            deleteMutation.mutate(ab.id);
                          }
                        }}
                        className="text-xs text-red-500 hover:text-red-700 cursor-pointer"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                  {expandedId === ab.id && (
                    <tr key={`${ab.id}-expand`}>
                      <td colSpan={6} className="px-5 py-3 bg-slate-50">
                        <p className="text-xs font-medium text-slate-600 mb-2">
                          Contact Preview (first 20)
                        </p>
                        {contactsQuery.isLoading ? (
                          <p className="text-xs text-slate-400">Loading...</p>
                        ) : (contactsQuery.data?.items ?? []).length === 0 ? (
                          <p className="text-xs text-slate-400">
                            No contacts in this address book.
                          </p>
                        ) : (
                          <table className="w-full text-xs">
                            <thead>
                              <tr className="text-slate-500">
                                <th className="text-left pb-1 font-medium">
                                  Email
                                </th>
                                <th className="text-left pb-1 font-medium">
                                  First Name
                                </th>
                                <th className="text-left pb-1 font-medium">
                                  Last Name
                                </th>
                                <th className="text-left pb-1 font-medium">
                                  Department
                                </th>
                                <th className="text-left pb-1 font-medium">
                                  Position
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {(contactsQuery.data?.items ?? []).map((c) => (
                                <tr key={c.id}>
                                  <td className="py-0.5 text-slate-700">
                                    {c.email}
                                  </td>
                                  <td className="py-0.5 text-slate-600">
                                    {c.first_name}
                                  </td>
                                  <td className="py-0.5 text-slate-600">
                                    {c.last_name}
                                  </td>
                                  <td className="py-0.5 text-slate-600">
                                    {c.department}
                                  </td>
                                  <td className="py-0.5 text-slate-600">
                                    {c.position}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
