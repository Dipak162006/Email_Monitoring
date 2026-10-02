import { useState, useEffect, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Building2,
  Info,
  Check,
  CheckCheck,
  Copy,
  X,
  AlertCircle,
  CheckCircle2,
  Loader2,
} from "lucide-react";
import { useWorkspace } from "../hooks/useWorkspace";
import { companiesApi } from "../services/api";
import { cn } from "../lib/utils";

function formatCreatedDate(dateStr?: string): { formatted: string; relative: string } {
  if (!dateStr) return { formatted: "Unknown", relative: "" };
  try {
    const d = new Date(dateStr);
    const formatted = d.toLocaleDateString("en-US", {
      month: "long",
      day: "numeric",
      year: "numeric",
    });
    const now = new Date();
    const diffMs = now.getTime() - d.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    let relative = "";
    if (diffDays < 1) relative = "Today";
    else if (diffDays === 1) relative = "Yesterday";
    else if (diffDays < 30) relative = `${diffDays} days ago`;
    else if (diffDays < 365) {
      const months = Math.floor(diffDays / 30);
      relative = `${months} ${months === 1 ? "month" : "months"} ago`;
    } else {
      const years = Math.floor(diffDays / 365);
      relative = `${years} ${years === 1 ? "year" : "years"} ago`;
    }
    return { formatted, relative };
  } catch {
    return { formatted: dateStr, relative: "" };
  }
}

export function SettingsPage() {
  const { currentCompany, currentCompanyId, currentRole, refreshWorkspaces } = useWorkspace();

  // Form input state initialized from active workspace
  const [nameInput, setNameInput] = useState(currentCompany?.name ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Copy ID clipboard feedback
  const [copied, setCopied] = useState(false);

  // Sync input value whenever active workspace loads or switches
  useEffect(() => {
    if (currentCompany?.name) {
      setNameInput(currentCompany.name);
      setValidationError(null);
      setSuccessMessage(null);
      setErrorMessage(null);
    }
  }, [currentCompany?.id, currentCompany?.name]);

  // Query actual member count for active workspace
  const { data: members = [], isLoading: isMembersLoading } = useQuery({
    queryKey: ["company-members", currentCompanyId],
    queryFn: () => (currentCompanyId ? companiesApi.getMembers(currentCompanyId) : Promise.resolve([])),
    enabled: !!currentCompanyId,
    staleTime: 30000,
  });

  const displayedWorkspaceId = currentCompany?.id ? `company-${currentCompany.id}` : "N/A";
  const createdDateInfo = formatCreatedDate(currentCompany?.created_at);

  const isDirty = nameInput.trim() !== (currentCompany?.name ?? "");
  const isValidLength = nameInput.trim().length > 0 && nameInput.length <= 255;
  const canSave = isDirty && isValidLength;

  const handleCopyId = async () => {
    if (!currentCompany?.id) return;
    try {
      await navigator.clipboard.writeText(displayedWorkspaceId);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore clipboard write failures in restricted environments
    }
  };

  const handleReset = () => {
    setNameInput(currentCompany?.name ?? "");
    setValidationError(null);
    setErrorMessage(null);
    setSuccessMessage(null);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = nameInput.trim();

    if (!trimmed) {
      setValidationError("Workspace name is required and cannot be empty.");
      return;
    }

    if (trimmed.length > 255) {
      setValidationError("Workspace name cannot exceed 255 characters.");
      return;
    }

    if (!currentCompanyId) {
      setErrorMessage("No active workspace selected.");
      return;
    }

    setIsSaving(true);
    setValidationError(null);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      await companiesApi.updateCompany(currentCompanyId, { name: trimmed });
      // Invalidate and refresh workspace state so switcher, document title, and context sync immediately
      await refreshWorkspaces();
      setSuccessMessage("Workspace name updated successfully.");
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail ||
        err?.message ||
        "Failed to update workspace name. Please try again.";
      setErrorMessage(typeof detail === "string" ? detail : JSON.stringify(detail));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="w-full bg-slate-50/50 min-h-screen py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-6xl mx-auto flex flex-col gap-6">
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2.5">
              <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
                Company Settings
              </h1>
              {currentRole && (
                <span className="px-2.5 py-0.5 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-700 text-xs font-semibold capitalize">
                  {currentRole.toLowerCase()}
                </span>
              )}
            </div>
            <p className="text-sm text-slate-500">
              Manage your workspace name and organization details.
            </p>
          </div>
        </div>

        {/* Two-Column Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Column 1: General Settings (lg:col-span-8) */}
          <div className="lg:col-span-8 flex flex-col gap-6">
            <div className="bg-white rounded-xl p-6 sm:p-7 shadow-xs border border-slate-200 flex flex-col gap-6">
              {/* Card Header */}
              <div className="flex items-start gap-3.5">
                <div className="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-100/80 flex items-center justify-center text-indigo-600 shrink-0">
                  <Building2 className="w-5 h-5 text-indigo-600" />
                </div>
                <div className="flex flex-col">
                  <h2 className="text-base font-semibold text-slate-900">General Settings</h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Update the name displayed across your workspace.
                  </p>
                </div>
              </div>

              {/* Notification Feedback Banners */}
              {successMessage && (
                <div className="p-3.5 rounded-lg bg-emerald-50 border border-emerald-200 flex items-center justify-between text-emerald-800">
                  <div className="flex items-center gap-2 text-xs sm:text-sm font-medium">
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                    <span>{successMessage}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSuccessMessage(null)}
                    className="text-emerald-500 hover:text-emerald-700 p-0.5 rounded-sm cursor-pointer"
                    aria-label="Dismiss notification"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              )}

              {errorMessage && (
                <div className="p-3.5 rounded-lg bg-rose-50 border border-rose-200 flex items-center justify-between text-rose-800">
                  <div className="flex items-center gap-2 text-xs sm:text-sm font-medium">
                    <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                    <span>{errorMessage}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setErrorMessage(null)}
                    className="text-rose-500 hover:text-rose-700 p-0.5 rounded-sm cursor-pointer"
                    aria-label="Dismiss notification"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              )}

              {/* Form */}
              <form onSubmit={handleSubmit} className="flex flex-col gap-5">
                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <label
                      htmlFor="ws-name-input"
                      className="text-xs font-semibold text-slate-700 flex items-center gap-1"
                    >
                      <span>Workspace Name</span>
                      <span className="text-rose-500">*</span>
                    </label>
                    <span
                      className={cn(
                        "text-xs transition-colors",
                        nameInput.length > 255 ? "text-rose-600 font-semibold" : "text-slate-400"
                      )}
                    >
                      {nameInput.length} / 255 characters
                    </span>
                  </div>

                  <div className="relative flex items-center rounded-lg">
                    <div className="absolute left-3.5 flex items-center pointer-events-none text-slate-400">
                      <Building2 className="w-4 h-4" />
                    </div>
                    <input
                      id="ws-name-input"
                      type="text"
                      maxLength={255}
                      value={nameInput}
                      onChange={(e) => {
                        setNameInput(e.target.value);
                        if (validationError) setValidationError(null);
                        if (successMessage) setSuccessMessage(null);
                        if (errorMessage) setErrorMessage(null);
                      }}
                      disabled={isSaving}
                      placeholder="e.g. ABC Technologies"
                      className={cn(
                        "w-full pl-10 pr-10 py-2.5 rounded-lg bg-slate-50 border text-slate-900 text-sm placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:bg-white transition-all",
                        validationError
                          ? "border-rose-300 focus:ring-rose-500"
                          : "border-slate-200 focus:ring-indigo-500 focus:border-indigo-500"
                      )}
                    />
                    {nameInput.length > 0 && !isSaving && (
                      <button
                        type="button"
                        onClick={() => {
                          setNameInput("");
                          document.getElementById("ws-name-input")?.focus();
                        }}
                        className="absolute right-3 p-1 text-slate-400 hover:text-slate-600 rounded-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer"
                        aria-label="Clear workspace name"
                        title="Clear workspace name"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    )}
                  </div>

                  {validationError && (
                    <span className="text-xs text-rose-600 font-medium flex items-center gap-1 pt-1">
                      <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                      <span>{validationError}</span>
                    </span>
                  )}
                </div>

                {/* Action Buttons Bar */}
                <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={handleReset}
                    disabled={!isDirty || isSaving}
                    className="px-4 py-2 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-xs font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                  >
                    Reset
                  </button>
                  <button
                    type="submit"
                    disabled={!canSave || isSaving}
                    className="px-5 py-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 text-xs font-semibold flex items-center gap-2 shadow-xs transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                  >
                    {isSaving ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Check className="w-4 h-4" />
                    )}
                    <span>{isSaving ? "Saving..." : "Save Changes"}</span>
                  </button>
                </div>
              </form>
            </div>
          </div>

          {/* Column 2: Workspace Details (lg:col-span-4) */}
          <div className="lg:col-span-4 flex flex-col gap-6">
            <div className="bg-white rounded-xl p-6 sm:p-7 shadow-xs border border-slate-200 flex flex-col gap-5">
              {/* Card Header */}
              <div className="flex items-start gap-3.5">
                <div className="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-100/80 flex items-center justify-center text-indigo-600 shrink-0">
                  <Info className="w-5 h-5 text-indigo-600" />
                </div>
                <div className="flex flex-col">
                  <h2 className="text-base font-semibold text-slate-900">Workspace Details</h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Read-only workspace configuration.
                  </p>
                </div>
              </div>

              {/* Metadata List */}
              <div className="flex flex-col divide-y divide-slate-100">
                {/* Workspace ID */}
                <div className="py-3.5 first:pt-0 flex flex-col gap-1.5">
                  <span className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">
                    Workspace ID
                  </span>
                  <div className="flex items-center justify-between gap-2">
                    <code className="font-mono text-xs text-slate-800 bg-slate-50 px-2.5 py-1 rounded-md border border-slate-200 select-all">
                      {displayedWorkspaceId}
                    </code>
                    <button
                      type="button"
                      onClick={handleCopyId}
                      className="p-1.5 rounded-md hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"
                      title="Copy Workspace ID"
                      aria-label="Copy Workspace ID"
                    >
                      {copied ? (
                        <CheckCheck className="w-4 h-4 text-emerald-600" />
                      ) : (
                        <Copy className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>

                {/* Created Date */}
                <div className="py-3.5 flex items-center justify-between">
                  <div className="flex flex-col">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">
                      Created Date
                    </span>
                    <span className="text-sm font-medium text-slate-800 mt-0.5">
                      {createdDateInfo.formatted}
                    </span>
                  </div>
                  {createdDateInfo.relative && (
                    <span className="text-xs text-slate-400">
                      {createdDateInfo.relative}
                    </span>
                  )}
                </div>

                {/* Workspace Status */}
                <div className="py-3.5 flex items-center justify-between">
                  <div className="flex flex-col">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">
                      Workspace Status
                    </span>
                  </div>
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-slate-50 border border-slate-200 text-xs font-medium text-slate-700">
                    <span
                      className={cn(
                        "w-2 h-2 rounded-full",
                        currentCompany?.is_active ? "bg-emerald-500" : "bg-slate-400"
                      )}
                    />
                    {currentCompany?.is_active ? "Active" : "Inactive"}
                  </span>
                </div>

                {/* Member Allocation */}
                <div className="py-3.5 last:pb-0 flex items-center justify-between">
                  <div className="flex flex-col">
                    <span className="text-[11px] uppercase tracking-wider text-slate-400 font-bold">
                      Member Allocation
                    </span>
                    <span className="text-sm font-medium text-slate-800 mt-0.5">
                      {isMembersLoading
                        ? "Loading members..."
                        : `${members.length} Active Member${members.length === 1 ? "" : "s"}`}
                    </span>
                  </div>
                  <span className="text-xs text-indigo-700 font-semibold bg-indigo-50 border border-indigo-100 px-2.5 py-0.5 rounded-full">
                    Standard
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
