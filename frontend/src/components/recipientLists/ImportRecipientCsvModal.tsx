import React, { useRef, useState, useEffect } from "react";
import {
  UploadCloud,
  FileText,
  Download,
  CheckCircle2,
  AlertTriangle,
  X,
  Loader2,
  Table as TableIcon,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { Button } from "../ui/Button";
import type { RecipientListMemberImportResponse } from "../../types/recipientList";

const MAX_CSV_SIZE = 5 * 1024 * 1024; // 5MB

interface PreviewRow {
  rowNum: number;
  email: string;
  firstName: string;
  lastName: string;
  isValid: boolean;
  error?: string;
}

interface ImportRecipientCsvModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImport: (file: File) => Promise<RecipientListMemberImportResponse | null>;
  isLoading?: boolean;
}

export const ImportRecipientCsvModal: React.FC<ImportRecipientCsvModalProps> = ({
  isOpen,
  onClose,
  onImport,
  isLoading = false,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [previewRows, setPreviewRows] = useState<PreviewRow[]>([]);
  const [totalParsedRows, setTotalParsedRows] = useState(0);
  const [importResult, setImportResult] = useState<RecipientListMemberImportResponse | null>(null);
  const [showInvalidDetails, setShowInvalidDetails] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setSelectedFile(null);
      setFileError(null);
      setPreviewRows([]);
      setTotalParsedRows(0);
      setImportResult(null);
      setShowInvalidDetails(false);
      setIsDragging(false);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isLoading) {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isLoading, onClose]);

  if (!isOpen) return null;

  const parseCsvPreview = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      if (!text) {
        setFileError("File is empty.");
        setPreviewRows([]);
        return;
      }

      const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0);
      if (lines.length === 0) {
        setFileError("File is empty.");
        setPreviewRows([]);
        return;
      }

      const headerLine = lines[0];
      const headers = headerLine.split(",").map((h) => h.trim().toLowerCase().replace(/^["']|["']$/g, ""));
      const emailIdx = headers.indexOf("email");

      if (emailIdx === -1) {
        setFileError("CSV must contain an 'email' column header.");
        setPreviewRows([]);
        return;
      }

      const fnIdx = headers.findIndex((h) => ["first_name", "firstname", "first name"].includes(h));
      const lnIdx = headers.findIndex((h) => ["last_name", "lastname", "last name"].includes(h));

      const rows: PreviewRow[] = [];
      const seenEmailsInPreview = new Set<string>();
      const emailRegex = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

      const dataLines = lines.slice(1);
      setTotalParsedRows(dataLines.length);

      for (let i = 0; i < Math.min(dataLines.length, 5); i++) {
        const rawRow = dataLines[i];
        // simple CSV column split
        const cols = rawRow.split(",").map((c) => c.trim().replace(/^["']|["']$/g, ""));
        const rawEmail = cols[emailIdx] || "";
        const fn = fnIdx !== -1 && cols[fnIdx] ? cols[fnIdx] : "";
        const ln = lnIdx !== -1 && cols[lnIdx] ? cols[lnIdx] : "";

        let isValid = true;
        let error: string | undefined;

        if (!rawEmail) {
          isValid = false;
          error = "Missing email";
        } else if (!emailRegex.test(rawEmail)) {
          isValid = false;
          error = "Invalid format";
        } else if (seenEmailsInPreview.has(rawEmail.toLowerCase())) {
          isValid = false;
          error = "Duplicate in file";
        } else {
          seenEmailsInPreview.add(rawEmail.toLowerCase());
        }

        rows.push({
          rowNum: i + 2,
          email: rawEmail,
          firstName: fn,
          lastName: ln,
          isValid,
          error,
        });
      }

      setPreviewRows(rows);
    };
    reader.onerror = () => {
      setFileError("Failed to read file.");
    };
    reader.readAsText(file, "utf-8");
  };

  const handleProcessFile = (file: File) => {
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setFileError("Only CSV files (.csv) are supported.");
      setSelectedFile(null);
      setPreviewRows([]);
      return;
    }

    if (file.size > MAX_CSV_SIZE) {
      setFileError("CSV file size exceeds the 5MB limit.");
      setSelectedFile(null);
      setPreviewRows([]);
      return;
    }

    setFileError(null);
    setImportResult(null);
    setSelectedFile(file);
    parseCsvPreview(file);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    handleProcessFile(file);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) {
      handleProcessFile(file);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile || isLoading) return;
    try {
      const result = await onImport(selectedFile);
      if (result) {
        setImportResult(result);
        setSelectedFile(null);
        setPreviewRows([]);
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
      }
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.message || "Failed to import CSV file.";
      setFileError(msg);
    }
  };

  const handleClearFile = () => {
    setSelectedFile(null);
    setFileError(null);
    setPreviewRows([]);
    setTotalParsedRows(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleDownloadSample = () => {
    const sampleHeaders = "email,first_name,last_name\n";
    const sampleRows =
      "sarah.jenkins@acme.corp,Sarah,Jenkins\nmichael.chang@cloudscale.io,Michael,Chang\neva.rostova@nexus.tech,Eva,Rostova\n";
    const blob = new Blob([sampleHeaders + sampleRows], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", "pulsemail_contacts_sample.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="import-recipient-csv-title"
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150"
    >
      <div
        className="bg-white rounded-2xl shadow-2xl border border-slate-200 p-6 text-left animate-in zoom-in-95 duration-150 max-h-[92vh] overflow-y-auto"
        style={{ width: "min(calc(100vw - 32px), 620px)" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
              <UploadCloud className="h-5 w-5" />
            </div>
            <div>
              <h3 id="import-recipient-csv-title" className="text-base font-bold text-slate-900">
                Import Contacts from CSV
              </h3>
              <p className="text-xs text-slate-500">
                Bulk-import contacts with Email, First Name and Last Name.
              </p>
            </div>
          </div>
          <button
            type="button"
            disabled={isLoading}
            onClick={onClose}
            className="p-1 rounded text-slate-400 hover:text-slate-600 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Import Results View (when import finished) */}
        {importResult ? (
          <div className="mt-5 space-y-4 animate-in fade-in">
            <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 flex items-start gap-3">
              <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0 mt-0.5" />
              <div>
                <h4 className="text-sm font-bold text-emerald-900">CSV Import Completed</h4>
                <p className="text-xs text-emerald-700 mt-0.5">
                  Your contacts have been processed and updated in this recipient list.
                </p>
              </div>
            </div>

            {/* 5-Metric Breakdown */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-center text-xs">
              <div className="bg-slate-50 border border-slate-200 p-2.5 rounded-xl">
                <span className="block text-lg font-bold text-slate-900">{importResult.total_rows}</span>
                <span className="text-[11px] text-slate-500">Total Rows</span>
              </div>
              <div className="bg-emerald-50 border border-emerald-200 p-2.5 rounded-xl">
                <span className="block text-lg font-bold text-emerald-700">{importResult.imported_count}</span>
                <span className="text-[11px] text-emerald-700 font-medium">Successfully Imported</span>
              </div>
              <div className="bg-amber-50 border border-amber-200 p-2.5 rounded-xl">
                <span className="block text-lg font-bold text-amber-700">{importResult.file_duplicates_count}</span>
                <span className="text-[11px] text-amber-700 font-medium">In-File Duplicates</span>
              </div>
              <div className="bg-slate-50 border border-slate-200 p-2.5 rounded-xl">
                <span className="block text-lg font-bold text-slate-700">{importResult.existing_duplicates_count}</span>
                <span className="text-[11px] text-slate-500">Already in List</span>
              </div>
              <div className="bg-rose-50 border border-rose-200 p-2.5 rounded-xl col-span-2 sm:col-span-2">
                <span className="block text-lg font-bold text-rose-700">{importResult.invalid_rows_count}</span>
                <span className="text-[11px] text-rose-700 font-medium">Invalid Rows</span>
              </div>
            </div>

            {/* Invalid rows details */}
            {importResult.invalid_rows_count > 0 && (
              <div className="border border-slate-200 rounded-xl p-3 bg-slate-50/50 space-y-2">
                <button
                  type="button"
                  onClick={() => setShowInvalidDetails((p) => !p)}
                  className="w-full flex items-center justify-between text-xs font-semibold text-rose-700 hover:text-rose-800"
                >
                  <span>Review {importResult.invalid_rows_count} invalid row error(s)</span>
                  {showInvalidDetails ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </button>
                {showInvalidDetails && (
                  <div className="max-h-40 overflow-y-auto space-y-1 pt-1 font-mono text-[11px]">
                    {importResult.invalid_rows.map((r, idx) => (
                      <div key={idx} className="p-1.5 rounded bg-white border border-rose-100 text-slate-700 flex items-start gap-2">
                        <span className="font-semibold text-rose-600 shrink-0">Row {r.row}:</span>
                        <span className="truncate">{r.email || "(empty)"}</span>
                        <span className="text-slate-400">—</span>
                        <span className="text-rose-600">{r.reason}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="pt-2 flex justify-end">
              <Button
                type="button"
                onClick={onClose}
                className="px-5 py-2 text-xs font-semibold rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm"
              >
                Done
              </Button>
            </div>
          </div>
        ) : (
          /* File Upload & Preview Form */
          <div className="mt-5 space-y-5">
            {/* Drag and Drop Zone */}
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`rounded-2xl border-2 border-dashed p-6 text-center transition-all ${
                isDragging
                  ? "border-indigo-500 bg-indigo-50/50"
                  : "border-slate-200 bg-slate-50/60 hover:bg-slate-50"
              }`}
            >
              <div className="w-12 h-12 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto mb-3">
                <UploadCloud className="h-6 w-6" />
              </div>
              <p className="text-sm font-semibold text-slate-800">
                Drag and drop your CSV file here, or browse
              </p>
              <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                File must include an <code className="px-1 py-0.5 rounded bg-slate-200/80 font-mono text-indigo-600 font-semibold">email</code> header. Optional headers: <code className="px-1 py-0.5 rounded bg-slate-200/80 font-mono text-indigo-600 font-semibold">first_name</code>, <code className="px-1 py-0.5 rounded bg-slate-200/80 font-mono text-indigo-600 font-semibold">last_name</code>. Max 5MB.
              </p>

              <div className="flex flex-wrap items-center justify-center gap-2.5 mt-4">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".csv,text/csv"
                  onChange={handleFileChange}
                  disabled={isLoading}
                  className="hidden"
                  id="recipient-csv-file-picker"
                />
                <label
                  htmlFor="recipient-csv-file-picker"
                  className={`cursor-pointer inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 transition-colors shadow-sm ${
                    isLoading ? "opacity-50 pointer-events-none" : ""
                  }`}
                >
                  <FileText className="h-4 w-4" />
                  <span>Choose CSV File</span>
                </label>
                <button
                  type="button"
                  onClick={handleDownloadSample}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-white border border-slate-200 text-slate-700 text-xs font-medium hover:bg-slate-50 transition-colors shadow-2xs"
                >
                  <Download className="h-4 w-4 text-slate-500" />
                  <span>Download Sample</span>
                </button>
              </div>
            </div>

            {/* Error Message */}
            {fileError && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl flex items-center gap-2.5 text-xs text-rose-700">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                <span className="font-medium">{fileError}</span>
              </div>
            )}

            {/* Selected File Details & Preview */}
            {selectedFile && (
              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 rounded-xl bg-slate-50 border border-slate-200">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <FileText className="h-5 w-5 text-indigo-600 shrink-0" />
                    <div className="min-w-0 text-left">
                      <p className="text-xs font-semibold text-slate-900 truncate">{selectedFile.name}</p>
                      <p className="text-[11px] text-slate-500">
                        {(selectedFile.size / 1024).toFixed(1)} KB • approx. {totalParsedRows} data rows
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={handleClearFile}
                    disabled={isLoading}
                    className="p-1 text-slate-400 hover:text-slate-600 rounded"
                    title="Remove selected file"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                {/* CSV Preview Table */}
                {previewRows.length > 0 && (
                  <div className="border border-slate-200 rounded-xl overflow-hidden text-xs">
                    <div className="bg-slate-100 px-3 py-2 font-semibold text-slate-700 flex items-center gap-1.5">
                      <TableIcon className="h-3.5 w-3.5 text-slate-500" />
                      <span>Data Preview (first {previewRows.length} rows)</span>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full divide-y divide-slate-200 text-left">
                        <thead className="bg-slate-50 text-[11px] font-semibold text-slate-600">
                          <tr>
                            <th className="px-3 py-1.5">Row</th>
                            <th className="px-3 py-1.5">Email</th>
                            <th className="px-3 py-1.5">First Name</th>
                            <th className="px-3 py-1.5">Last Name</th>
                            <th className="px-3 py-1.5">Preview Check</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 bg-white">
                          {previewRows.map((r) => (
                            <tr key={r.rowNum} className="hover:bg-slate-50/50">
                              <td className="px-3 py-2 text-slate-400 font-mono text-[11px]">{r.rowNum}</td>
                              <td className="px-3 py-2 font-medium text-slate-900 font-mono text-[11px]">{r.email}</td>
                              <td className="px-3 py-2 text-slate-600">{r.firstName || "—"}</td>
                              <td className="px-3 py-2 text-slate-600">{r.lastName || "—"}</td>
                              <td className="px-3 py-2">
                                {r.isValid ? (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-semibold border border-emerald-100">
                                    <span className="w-1 h-1 rounded-full bg-emerald-500"></span>
                                    Valid
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 text-[10px] font-semibold border border-rose-100">
                                    <span className="w-1 h-1 rounded-full bg-rose-500"></span>
                                    {r.error}
                                  </span>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Footer Actions */}
            <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2.5">
              <Button
                type="button"
                variant="outline"
                disabled={isLoading}
                onClick={onClose}
                className="px-4 py-2 text-xs font-medium rounded-xl"
              >
                Cancel
              </Button>
              <Button
                type="button"
                disabled={!selectedFile || isLoading}
                onClick={handleUpload}
                className="px-5 py-2 text-xs font-semibold rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white flex items-center gap-1.5 shadow-sm disabled:opacity-50"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>Importing...</span>
                  </>
                ) : (
                  <span>Confirm & Import</span>
                )}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
