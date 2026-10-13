import React, { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  RefreshCw,
  UserPlus,
  UploadCloud,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

import { useWorkspace } from "../hooks/useWorkspace";
import { campaignsApi, RequestError } from "../services/api";
import type {
  CampaignRecipient,
  CampaignRecipientCreatePayload,
  CampaignRecipientUpdatePayload,
  CampaignRecipientImportResponse,
} from "../types/campaign";

import { CampaignStatusBadge } from "../components/campaigns/CampaignStatusBadge";
import { RecipientSummaryCards } from "../components/campaigns/recipients/RecipientSummaryCards";
import { RecipientManualForm } from "../components/campaigns/recipients/RecipientManualForm";
import { RecipientCsvImport } from "../components/campaigns/recipients/RecipientCsvImport";
import { RecipientToolbar } from "../components/campaigns/recipients/RecipientToolbar";
import { RecipientTable } from "../components/campaigns/recipients/RecipientTable";
import { RecipientMobileCard } from "../components/campaigns/recipients/RecipientMobileCard";
import { RecipientDeleteModal } from "../components/campaigns/recipients/RecipientDeleteModal";
import { RecipientEditModal } from "../components/campaigns/recipients/RecipientEditModal";
import {
  RecipientSkeleton,
  RecipientEmptyAudience,
  RecipientSearchEmpty,
  RecipientErrorState,
} from "../components/campaigns/recipients/RecipientStates";

export const CampaignRecipientsPage: React.FC = () => {
  const { campaignId } = useParams<{ campaignId: string }>();
  const campaignIdNum = Number(campaignId);
  const queryClient = useQueryClient();
  const { currentCompanyId, currentRole } = useWorkspace();

  // Toast feedback state
  const [toastMessage, setToastMessage] = useState<{
    text: string;
    type: "success" | "error" | "info";
  } | null>(null);

  const showToast = (
    text: string,
    type: "success" | "error" | "info" = "success"
  ) => {
    setToastMessage({ text, type });
    setTimeout(() => {
      setToastMessage(null);
    }, 3500);
  };

  const isAdminOrOwner = currentRole === "OWNER" || currentRole === "ADMIN";

  // Navigation & Tabs state
  const [activeTab, setActiveTab] = useState<"manual" | "csv">("manual");

  // Filtering & Pagination state
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  // Modals state
  const [deleteModal, setDeleteModal] = useState<{
    isOpen: boolean;
    recipient: CampaignRecipient | null;
  }>({ isOpen: false, recipient: null });

  const [editModal, setEditModal] = useState<{
    isOpen: boolean;
    recipient: CampaignRecipient | null;
  }>({ isOpen: false, recipient: null });

  // 1. Fetch Campaign Details
  const {
    data: campaign,
    isLoading: isCampaignLoading,
    refetch: refetchCampaign,
  } = useQuery({
    queryKey: ["campaigns", currentCompanyId, "detail", campaignIdNum],
    queryFn: () => {
      if (!currentCompanyId || !campaignIdNum) throw new Error("Missing parameters");
      return campaignsApi.getCampaign(currentCompanyId, campaignIdNum);
    },
    enabled: Boolean(currentCompanyId && campaignIdNum),
    staleTime: 30000,
  });

  // 2. Fetch Recipients List
  const {
    data: loadedRecipients = [],
    isLoading: isRecipientsLoading,
    isError: isRecipientsError,
    error: recipientsError,
    refetch: refetchRecipients,
    isFetching: isRecipientsFetching,
  } = useQuery({
    queryKey: [
      "campaigns",
      currentCompanyId,
      campaignIdNum,
      "recipients",
      { statusFilter, searchQuery, currentPage, pageSize },
    ],
    queryFn: () => {
      if (!currentCompanyId || !campaignIdNum) throw new Error("Missing parameters");
      return campaignsApi.listRecipients(currentCompanyId, campaignIdNum, {
        status: statusFilter !== "ALL" ? statusFilter : undefined,
        search: searchQuery.trim() || undefined,
        limit: pageSize,
        offset: (currentPage - 1) * pageSize,
      });
    },
    enabled: Boolean(currentCompanyId && campaignIdNum),
  });

  const isDraft = campaign?.status === "DRAFT";
  const isEditable = Boolean(isDraft && isAdminOrOwner);

  // Invalidation helper
  const invalidateRecipientQueries = () => {
    queryClient.invalidateQueries({
      queryKey: ["campaigns", currentCompanyId, campaignIdNum, "recipients"],
    });
    queryClient.invalidateQueries({
      queryKey: ["campaigns", currentCompanyId, "detail", campaignIdNum],
    });
    queryClient.invalidateQueries({
      queryKey: ["campaigns", currentCompanyId],
    });
  };

  // 3. Add Single Recipient Mutation
  const createMutation = useMutation({
    mutationFn: (payload: CampaignRecipientCreatePayload) => {
      if (!currentCompanyId || !campaignIdNum) throw new Error("Missing parameters");
      return campaignsApi.createRecipient(currentCompanyId, campaignIdNum, payload);
    },
    onSuccess: (newRecipient) => {
      invalidateRecipientQueries();
      showToast(`Added ${newRecipient.email} to campaign audience.`);
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Failed to add recipient.";
      showToast(msg, "error");
    },
  });

  // 4. Update Recipient Mutation
  const updateMutation = useMutation({
    mutationFn: ({
      recipientId,
      payload,
    }: {
      recipientId: number;
      payload: CampaignRecipientUpdatePayload;
    }) => {
      if (!currentCompanyId || !campaignIdNum) throw new Error("Missing parameters");
      return campaignsApi.updateRecipient(
        currentCompanyId,
        campaignIdNum,
        recipientId,
        payload
      );
    },
    onSuccess: (updated) => {
      invalidateRecipientQueries();
      setEditModal({ isOpen: false, recipient: null });
      showToast(`Updated recipient "${updated.email}".`);
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Failed to update recipient.";
      showToast(msg, "error");
    },
  });

  // 5. Delete Recipient Mutation
  const deleteMutation = useMutation({
    mutationFn: (recipientId: number) => {
      if (!currentCompanyId || !campaignIdNum) throw new Error("Missing parameters");
      return campaignsApi.deleteRecipient(currentCompanyId, campaignIdNum, recipientId);
    },
    onSuccess: () => {
      invalidateRecipientQueries();
      const removedEmail = deleteModal.recipient?.email;
      setDeleteModal({ isOpen: false, recipient: null });
      showToast(
        removedEmail
          ? `Removed ${removedEmail} from audience.`
          : "Recipient removed from audience."
      );
    },
    onError: (err: unknown) => {
      setDeleteModal({ isOpen: false, recipient: null });
      const msg =
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Failed to remove recipient.";
      showToast(msg, "error");
    },
  });

  // 6. CSV Import Handler
  const handleCsvImport = async (file: File): Promise<CampaignRecipientImportResponse | null> => {
    if (!currentCompanyId || !campaignIdNum) return null;
    try {
      const res = await campaignsApi.importRecipientsCsv(
        currentCompanyId,
        campaignIdNum,
        file
      );
      invalidateRecipientQueries();
      showToast(
        `Import complete: ${res.inserted_count} added, ${res.skipped_duplicates_count} skipped.`
      );
      return res;
    } catch (err: unknown) {
      const msg =
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Failed to import CSV.";
      showToast(msg, "error");
      return null;
    }
  };

  const handleRefresh = () => {
    refetchCampaign();
    refetchRecipients();
    showToast("Audience records refreshed.", "info");
  };

  const handleCopyEmail = (emailText: string) => {
    navigator.clipboard?.writeText(emailText).then(() => {
      showToast(`Copied ${emailText} to clipboard.`, "info");
    });
  };

  const handleClearFilters = () => {
    setSearchQuery("");
    setStatusFilter("ALL");
    setCurrentPage(1);
  };

  const totalLoaded = loadedRecipients.length;
  const hasActiveFilters = Boolean(searchQuery || statusFilter !== "ALL");

  return (
    <div className="w-full max-w-[1440px] mx-auto min-w-0 px-3 sm:px-4 md:px-6 lg:px-8 py-6 space-y-6 box-border">
      {/* 1. Header & Navigation */}
      <div className="flex flex-col gap-4">
        {/* Breadcrumb row */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <nav className="flex items-center gap-1.5 text-xs sm:text-sm text-slate-500 truncate">
            <Link
              to="/campaigns"
              className="hover:text-indigo-600 transition-colors flex items-center gap-1 text-slate-600"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Back to Campaigns</span>
            </Link>
            <span className="text-slate-300">/</span>
            <Link
              to={`/campaigns/${campaignIdNum}`}
              className="text-slate-600 hover:text-indigo-600 transition-colors font-medium truncate max-w-[200px] sm:max-w-xs"
            >
              {campaign?.name || `Campaign #${campaignIdNum}`}
            </Link>
            <span className="text-slate-300">/</span>
            <span className="text-slate-900 font-semibold">Audience Records</span>
          </nav>

          <div className="flex items-center gap-2 shrink-0">
            {campaign && <CampaignStatusBadge status={campaign.status} />}
            <button
              type="button"
              onClick={handleRefresh}
              disabled={isRecipientsFetching}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-medium transition-colors shadow-2xs disabled:opacity-50"
            >
              <RefreshCw
                className={`h-3.5 w-3.5 text-indigo-600 ${
                  isRecipientsFetching ? "animate-spin" : ""
                }`}
              />
              <span className="hidden sm:inline">Refresh List</span>
            </button>
            <Link
              to={campaignIdNum ? `/campaigns/${campaignIdNum}` : "/campaigns"}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-2xs transition-all shrink-0"
            >
              <span>Return to Details</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>

        {/* Main Headline */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
                Campaign Recipients
              </h1>
              <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200/60">
                {(campaign?.recipient_count ?? totalLoaded).toLocaleString()} target records
              </span>
            </div>
            <p className="text-xs sm:text-sm text-slate-500 mt-1 max-w-3xl leading-relaxed">
              Manage the audience and recipient list for this campaign. Audience records define the intended dispatch scope and are pre-screened for delivery safety.
            </p>
          </div>
        </div>
      </div>

      {/* 2. Recipient Metric Cards */}
      <RecipientSummaryCards
        campaign={campaign || null}
        recipients={loadedRecipients}
        isLoading={isCampaignLoading || isRecipientsLoading}
      />

      {/* 3. Ingestion Methods Box (Draft & Admin Only) */}
      <div className="bg-white rounded-xl border border-slate-200/80 shadow-2xs overflow-hidden min-w-0">
        {!isDraft ? (
          <div className="p-4 bg-slate-50/70 border-b border-slate-200 text-xs text-slate-600 flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-amber-600 shrink-0" />
            <span>
              Recipients cannot be modified when campaign is in{" "}
              <strong className="text-slate-800">{campaign?.status}</strong> status. Audience records can only be configured while in DRAFT.
            </span>
          </div>
        ) : !isAdminOrOwner ? (
          <div className="p-4 bg-slate-50/70 border-b border-slate-200 text-xs text-slate-600 flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-slate-500 shrink-0" />
            <span>
              Read-only view: Only workspace Admins and Owners can add, import, or remove recipients.
            </span>
          </div>
        ) : (
          <>
            {/* Tabs Header */}
            <div className="flex items-center px-4 sm:px-6 pt-3 gap-4 bg-slate-50/60 border-b border-slate-200">
              <button
                type="button"
                onClick={() => setActiveTab("manual")}
                className={`pb-3 px-1 text-xs sm:text-sm font-semibold transition-all flex items-center gap-2 border-b-2 ${
                  activeTab === "manual"
                    ? "text-indigo-600 border-indigo-600"
                    : "text-slate-500 border-transparent hover:text-slate-800"
                }`}
              >
                <UserPlus className="h-4 w-4" />
                <span>Add Manually</span>
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("csv")}
                className={`pb-3 px-1 text-xs sm:text-sm font-semibold transition-all flex items-center gap-2 border-b-2 ${
                  activeTab === "csv"
                    ? "text-indigo-600 border-indigo-600"
                    : "text-slate-500 border-transparent hover:text-slate-800"
                }`}
              >
                <UploadCloud className="h-4 w-4" />
                <span>Import CSV</span>
                <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-200 text-slate-700">
                  Batch
                </span>
              </button>
            </div>

            {/* Tab Contents */}
            <div className="p-4 sm:p-6">
              {activeTab === "manual" ? (
                <RecipientManualForm
                  onSubmit={async (payload) => {
                    await createMutation.mutateAsync(payload);
                  }}
                  isLoading={createMutation.isPending}
                  disabled={!isEditable}
                />
              ) : (
                <RecipientCsvImport
                  onImport={handleCsvImport}
                  disabled={!isEditable}
                />
              )}
            </div>
          </>
        )}
      </div>

      {/* 4. Search & Filter Toolbar */}
      <RecipientToolbar
        searchQuery={searchQuery}
        onSearchChange={(q) => {
          setSearchQuery(q);
          setCurrentPage(1);
        }}
        statusFilter={statusFilter}
        onStatusFilterChange={(s) => {
          setStatusFilter(s);
          setCurrentPage(1);
        }}
        totalFilteredCount={totalLoaded}
        totalLoadedCount={campaign?.recipient_count ?? totalLoaded}
        onClearFilters={handleClearFilters}
        hasActiveFilters={hasActiveFilters}
      />

      {/* 5. Audience Records Main Table / Cards View */}
      <div className="w-full min-w-0 bg-white rounded-xl border border-slate-200/80 shadow-2xs overflow-hidden">
        {isRecipientsLoading ? (
          <RecipientSkeleton />
        ) : isRecipientsError ? (
          <RecipientErrorState
            message={recipientsError instanceof Error ? recipientsError.message : undefined}
            onRetry={() => refetchRecipients()}
          />
        ) : totalLoaded === 0 && !hasActiveFilters ? (
          <RecipientEmptyAudience
            isEditable={isEditable}
            onSelectTab={(t) => setActiveTab(t)}
          />
        ) : totalLoaded === 0 && hasActiveFilters ? (
          <RecipientSearchEmpty onClearFilters={handleClearFilters} />
        ) : (
          <>
            {/* Desktop Table View */}
            <div className="hidden md:block w-full min-w-0">
              <RecipientTable
                recipients={loadedRecipients}
                isEditable={isEditable}
                onEdit={(r) => setEditModal({ isOpen: true, recipient: r })}
                onDelete={(r) => setDeleteModal({ isOpen: true, recipient: r })}
                onCopyEmail={handleCopyEmail}
              />
            </div>

            {/* Mobile Cards View */}
            <div className="block md:hidden w-full divide-y divide-slate-100 p-3 space-y-3">
              {loadedRecipients.map((recipient) => (
                <RecipientMobileCard
                  key={recipient.id}
                  recipient={recipient}
                  isEditable={isEditable}
                  onEdit={(r) => setEditModal({ isOpen: true, recipient: r })}
                  onDelete={(r) => setDeleteModal({ isOpen: true, recipient: r })}
                  onCopyEmail={handleCopyEmail}
                />
              ))}
            </div>

            {/* Bounded Pagination Footer */}
            <div className="px-4 sm:px-6 py-3 bg-slate-50/70 border-t border-slate-200 flex flex-col sm:flex-row items-center justify-between gap-3 text-slate-600 text-xs">
              <div className="flex items-center gap-2">
                <span>Rows per page:</span>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    setPageSize(Number(e.target.value));
                    setCurrentPage(1);
                  }}
                  className="bg-white border border-slate-200 rounded px-2 py-1 text-slate-800 text-xs focus:outline-none cursor-pointer"
                >
                  <option value={10}>10</option>
                  <option value={25}>25</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
              </div>

              <div className="flex items-center gap-3">
                <span>
                  Page {currentPage}
                </span>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage <= 1}
                    className="p-1 rounded bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    title="Previous page"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setCurrentPage((p) => p + 1)}
                    disabled={totalLoaded < pageSize}
                    className="p-1 rounded bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    title="Next page"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* 6. Informational Deliverability Safety Banner */}
      <div className="rounded-xl bg-slate-50/80 border border-slate-200 p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <ShieldCheck className="h-5 w-5 text-indigo-600 shrink-0" />
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-900 truncate">
              Strict RFC 5322 validation active
            </p>
            <p className="text-xs text-slate-500 truncate">
              Syntax validation and deduplication are enforced during recipient ingestion.
            </p>
          </div>
        </div>
      </div>

      {/* 7. Next Step / Return to Detail Callout */}
      <div className="rounded-xl bg-white border border-indigo-100 p-4.5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-2xs">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-9 h-9 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
            <CheckCircle2 className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <p className="text-xs sm:text-sm font-semibold text-slate-900 truncate">
              {isDraft ? "Audience configured in DRAFT status" : `Campaign status: ${campaign?.status}`}
            </p>
            <p className="text-xs text-slate-500 truncate">
              {isDraft
                ? "Recipients are staged. Return to the campaign detail page to run preflight validation and schedule or dispatch."
                : "Audience records are frozen for this lifecycle status."}
            </p>
          </div>
        </div>
        <Link
          to={campaignIdNum ? `/campaigns/${campaignIdNum}` : "/campaigns"}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs sm:text-sm font-semibold transition-all shadow-2xs shrink-0"
        >
          <span>Continue to Campaign Details</span>
          <ArrowRight className="h-4 w-4" />
        </Link>
      </div>

      {/* 8. Delete Confirmation Dialog */}
      <RecipientDeleteModal
        isOpen={deleteModal.isOpen}
        recipient={deleteModal.recipient}
        onClose={() => setDeleteModal({ isOpen: false, recipient: null })}
        onConfirm={() => {
          if (deleteModal.recipient) {
            deleteMutation.mutate(deleteModal.recipient.id);
          }
        }}
        isLoading={deleteMutation.isPending}
      />

      {/* 8. Edit Recipient Dialog */}
      <RecipientEditModal
        isOpen={editModal.isOpen}
        recipient={editModal.recipient}
        onClose={() => setEditModal({ isOpen: false, recipient: null })}
        onSave={(recipientId, payload) => {
          updateMutation.mutate({ recipientId, payload });
        }}
        isLoading={updateMutation.isPending}
      />

      {/* Toast Notification */}
      {toastMessage && (
        <div
          role="status"
          aria-live="polite"
          className={`fixed bottom-6 right-6 z-50 px-4 py-2.5 rounded-lg text-xs font-semibold shadow-xl border flex items-center gap-2 animate-in slide-in-from-bottom-2 ${
            toastMessage.type === "error"
              ? "bg-rose-900 border-rose-800 text-rose-100"
              : toastMessage.type === "info"
              ? "bg-slate-900 border-slate-800 text-slate-100"
              : "bg-slate-900 border-slate-800 text-slate-100"
          }`}
        >
          <span>{toastMessage.text}</span>
        </div>
      )}
    </div>
  );
};
