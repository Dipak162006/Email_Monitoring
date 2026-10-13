import React, { useRef, useState } from "react";
import { UploadCloud, FileText, Download, CheckCircle2, AlertTriangle, X, Loader2 } from "lucide-react";
import type { CampaignRecipientImportResponse } from "../../../types/campaign";

const MAX_CSV_SIZE = 5 * 1024 * 1024; // 5MB

interface RecipientCsvImportProps {
  onImport: (file: File) => Promise<CampaignRecipientImportResponse | null>;
  isLoading?: boolean;
  disabled?: boolean;
}

export const RecipientCsvImport: React.FC<RecipientCsvImportProps> = ({
  onImport,
  isLoading = false,
  disabled = false,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<CampaignRecipientImportResponse | null>(null);
  const [showInvalidDetails, setShowInvalidDetails] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith(".csv")) {
      setFileError("Only CSV files (.csv) are supported.");
      setSelectedFile(null);
      return;
    }

    if (file.size > MAX_CSV_SIZE) {
      setFileError("CSV file size exceeds the 5MB limit.");
      setSelectedFile(null);
      return;
    }

    setFileError(null);
    setImportResult(null);
    setSelectedFile(file);
  };

  const handleUpload = async () => {
    if (!selectedFile || disabled || isLoading) return;
    const result = await onImport(selectedFile);
    if (result) {
      setImportResult(result);
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleClearFile = () => {
    setSelectedFile(null);
    setFileError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleDownloadSample = () => {
    const sampleHeaders = "email,first_name,last_name\n";
    const sampleRows = "sarah.jenkins@acme.corp,Sarah,Jenkins\nmichael.chang@cloudscale.io,Michael,Chang\n";
    const blob = new Blob([sampleHeaders + sampleRows], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", "pulsemail_audience_sample.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="w-full space-y-4">
      {/* Upload Box */}
      <div className="w-full rounded-xl bg-slate-50/70 border-2 border-dashed border-slate-200 p-6 md:p-8 flex flex-col items-center justify-center text-center transition-colors">
        <div className="w-12 h-12 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center mb-3">
          <UploadCloud className="h-6 w-6" />
        </div>
        <h3 className="text-sm font-semibold text-slate-900">Upload Audience CSV File</h3>
        <p className="text-xs text-slate-500 mt-1 max-w-md">
          Supports UTF-8 CSV with <code className="px-1.5 py-0.5 rounded bg-slate-200/80 font-mono text-indigo-600 font-medium">email</code> header, plus optional <code className="px-1.5 py-0.5 rounded bg-slate-200/80 font-mono text-indigo-600 font-medium">first_name</code> and <code className="px-1.5 py-0.5 rounded bg-slate-200/80 font-mono text-indigo-600 font-medium">last_name</code>. Max 5MB.
        </p>

        {/* File Actions */}
        <div className="flex flex-wrap items-center justify-center gap-3 mt-4">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            onChange={handleFileChange}
            disabled={disabled || isLoading}
            className="hidden"
            id="csv-file-input"
          />
          <label
            htmlFor="csv-file-input"
            className={`cursor-pointer inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 transition-colors shadow-2xs ${
              disabled || isLoading ? "opacity-50 pointer-events-none" : ""
            }`}
          >
            <FileText className="h-4 w-4" />
            <span>Select CSV File</span>
          </label>
          <button
            type="button"
            onClick={handleDownloadSample}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white border border-slate-200 text-slate-700 text-xs font-medium hover:bg-slate-50 transition-colors shadow-2xs"
          >
            <Download className="h-4 w-4 text-slate-500" />
            <span>Download Sample CSV</span>
          </button>
        </div>

        {/* Selected File Badge */}
        {selectedFile && (
          <div className="mt-4 flex items-center gap-3 bg-white border border-slate-200 px-3.5 py-2 rounded-lg shadow-2xs max-w-md w-full justify-between animate-in fade-in">
            <div className="flex items-center gap-2 min-w-0">
              <FileText className="h-4 w-4 text-indigo-600 shrink-0" />
              <div className="text-left truncate">
                <p className="text-xs font-semibold text-slate-900 truncate">{selectedFile.name}</p>
                <p className="text-[11px] text-slate-500">
                  {(selectedFile.size / 1024).toFixed(1)} KB
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <button
                type="button"
                onClick={handleUpload}
                disabled={isLoading}
                className="px-3 py-1 rounded bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1 transition-colors disabled:opacity-50"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="h-3 w-3 animate-spin" />
                    <span>Uploading...</span>
                  </>
                ) : (
                  <span>Upload & Import</span>
                )}
              </button>
              <button
                type="button"
                onClick={handleClearFile}
                disabled={isLoading}
                className="p-1 rounded text-slate-400 hover:text-slate-600 transition-colors"
                title="Cancel file selection"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}

        {/* Error Notice */}
        {fileError && (
          <p className="text-xs text-rose-500 font-medium mt-3 flex items-center gap-1">
            <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
            <span>{fileError}</span>
          </p>
        )}
      </div>

      {/* Import Result Notification */}
      {importResult && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs space-y-3 animate-in fade-in">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
                <CheckCircle2 className="h-4 w-4" />
              </div>
              <div>
                <h4 className="text-xs font-bold text-slate-900">CSV Import Completed</h4>
                <p className="text-xs text-slate-600">
                  Total rows processed: <span className="font-semibold">{importResult.total_rows}</span>
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setImportResult(null)}
              className="text-slate-400 hover:text-slate-600 p-1"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="grid grid-cols-3 gap-2 text-center text-xs pt-1">
            <div className="bg-emerald-50 text-emerald-800 p-2 rounded-lg border border-emerald-100">
              <span className="block text-base font-bold">{importResult.inserted_count}</span>
              <span className="text-[11px]">Inserted</span>
            </div>
            <div className="bg-slate-50 text-slate-700 p-2 rounded-lg border border-slate-200">
              <span className="block text-base font-bold">{importResult.skipped_duplicates_count}</span>
              <span className="text-[11px]">Duplicates Skipped</span>
            </div>
            <div className="bg-rose-50 text-rose-700 p-2 rounded-lg border border-rose-100">
              <span className="block text-base font-bold">{importResult.invalid_rows_count}</span>
              <span className="text-[11px]">Invalid Rows</span>
            </div>
          </div>

          {importResult.invalid_rows_count > 0 && (
            <div className="pt-1">
              <button
                type="button"
                onClick={() => setShowInvalidDetails((prev) => !prev)}
                className="text-xs text-indigo-600 hover:text-indigo-700 font-medium underline"
              >
                {showInvalidDetails ? "Hide invalid rows details" : `View ${importResult.invalid_rows_count} invalid row error(s)`}
              </button>
              {showInvalidDetails && (
                <div className="mt-2 max-h-36 overflow-y-auto rounded bg-slate-50 p-2 border border-slate-200 text-xs space-y-1 font-mono">
                  {importResult.invalid_rows.map((row, idx) => (
                    <div key={idx} className="text-slate-700 flex items-start gap-2">
                      <span className="font-semibold text-rose-600">Row {row.row}:</span>
                      <span>{row.email || "(empty)"} — {row.reason}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
