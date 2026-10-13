import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, AlertCircle, Info } from "lucide-react";

import { useWorkspace } from "../hooks/useWorkspace";
import { usePermissions } from "../hooks/usePermissions";
import { campaignsApi, emailAccountsApi, RequestError } from "../services/api";
import type { Campaign, CampaignStatus } from "../types/campaign";

import { CampaignPageHeader } from "../components/campaigns/CampaignPageHeader";
import { CampaignSummaryCards } from "../components/campaigns/CampaignSummaryCards";
import { CampaignToolbar } from "../components/campaigns/CampaignToolbar";
import { CampaignTable } from "../components/campaigns/CampaignTable";
import { CampaignSkeleton } from "../components/campaigns/CampaignSkeleton";
import { CampaignEmptyState } from "../components/campaigns/CampaignEmptyState";
import { CampaignSearchEmptyState } from "../components/campaigns/CampaignSearchEmptyState";
import { CampaignErrorState } from "../components/campaigns/CampaignErrorState";
import {
  CancelCampaignModal,
  type CampaignModalMode,
} from "../components/campaigns/CancelCampaignModal";
import { CampaignPagination } from "../components/campaigns/CampaignPagination";

export function CampaignsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentCompanyId, currentRole } = useWorkspace();
  const { isAdminOrOwner: permissionsIsAdminOrOwner } = usePermissions();
  const isAdminOrOwner =
    currentRole !== "MEMBER" &&
    (currentRole === "OWNER" ||
      currentRole === "ADMIN" ||
      Boolean(permissionsIsAdminOrOwner));

  // Toolbar & filter state
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [senderFilter, setSenderFilter] = useState<string>("ALL");
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 10;

  // View Options: toggle KPI Summary Cards
  const [showSummaryCards, setShowSummaryCards] = useState(true);

  // Modal confirmation state (cancel vs delete)
  const [modalState, setModalState] = useState<{
    isOpen: boolean;
    campaign: Campaign | null;
    mode: CampaignModalMode;
  }>({
    isOpen: false,
    campaign: null,
    mode: "cancel",
  });

  // Toast feedback banner state
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

  // 1. Fetch authorized email accounts for sender filter and resolution
  const { data: emailAccounts = [] } = useQuery({
    queryKey: ["authorizedEmailAccounts"],
    queryFn: () => emailAccountsApi.getAuthorizedAccounts(),
    staleTime: 60000,
  });

  // 2. Fetch company campaigns using backend pagination & status filter
  const {
    data: loadedCampaigns = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery<Campaign[], Error>({
    queryKey: [
      "campaigns",
      currentCompanyId,
      statusFilter !== "ALL" ? statusFilter : undefined,
      currentPage,
      pageSize,
    ],
    queryFn: () => {
      if (!currentCompanyId) return Promise.resolve([]);
      return campaignsApi.listCampaigns(currentCompanyId, {
        status: statusFilter !== "ALL" ? (statusFilter as CampaignStatus) : undefined,
        limit: pageSize,
        offset: (currentPage - 1) * pageSize,
      });
    },
    enabled: Boolean(currentCompanyId),
  });

  // Client-side filtering of the currently loaded page by keyword and sender
  const filteredCampaigns = useMemo(() => {
    return loadedCampaigns.filter((campaign) => {
      // Sender filter
      if (senderFilter !== "ALL") {
        if (String(campaign.email_account_id) !== senderFilter) {
          return false;
        }
      }

      // Search keyword filter (campaign name or subject)
      if (searchQuery.trim().length > 0) {
        const query = searchQuery.toLowerCase();
        const matchesName = campaign.name.toLowerCase().includes(query);
        const matchesSubject = campaign.subject?.toLowerCase().includes(query) ?? false;
        if (!matchesName && !matchesSubject) {
          return false;
        }
      }

      return true;
    });
  }, [loadedCampaigns, senderFilter, searchQuery]);

  // Filter change handlers (reset to page 1)
  const handleSearchChange = (query: string) => {
    setSearchQuery(query);
    setCurrentPage(1);
  };

  const handleStatusFilterChange = (status: string) => {
    setStatusFilter(status);
    setCurrentPage(1);
  };

  const handleSenderFilterChange = (senderId: string) => {
    setSenderFilter(senderId);
    setCurrentPage(1);
  };

  const handleClearFilters = () => {
    setSearchQuery("");
    setStatusFilter("ALL");
    setSenderFilter("ALL");
    setCurrentPage(1);
    showToast("Filters reset to default view.");
  };

  const hasActiveFilters =
    searchQuery.trim().length > 0 || statusFilter !== "ALL" || senderFilter !== "ALL";

  // Mutations
  const invalidateCampaigns = () => {
    queryClient.invalidateQueries({ queryKey: ["campaigns", currentCompanyId] });
  };

  // 1. Pause Campaign
  const pauseMutation = useMutation({
    mutationFn: (campaign: Campaign) => {
      if (!currentCompanyId) throw new Error("No active company");
      return campaignsApi.pauseCampaign(currentCompanyId, campaign.id);
    },
    onSuccess: (updated) => {
      invalidateCampaigns();
      showToast(`Campaign "${updated.name}" was paused.`);
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Failed to pause campaign.";
      showToast(msg, "error");
    },
  });

  // 2. Resume Campaign
  const resumeMutation = useMutation({
    mutationFn: (campaign: Campaign) => {
      if (!currentCompanyId) throw new Error("No active company");
      return campaignsApi.resumeCampaign(currentCompanyId, campaign.id);
    },
    onSuccess: (updated) => {
      invalidateCampaigns();
      showToast(`Campaign "${updated.name}" was resumed.`);
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Failed to resume campaign.";
      showToast(msg, "error");
    },
  });

  // 3. Cancel Campaign
  const cancelMutation = useMutation({
    mutationFn: (campaign: Campaign) => {
      if (!currentCompanyId) throw new Error("No active company");
      return campaignsApi.cancelCampaign(currentCompanyId, campaign.id);
    },
    onSuccess: (updated) => {
      setModalState({ isOpen: false, campaign: null, mode: "cancel" });
      invalidateCampaigns();
      showToast(`Campaign "${updated.name}" was cancelled.`);
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Failed to cancel campaign.";
      showToast(msg, "error");
    },
  });

  // 5. Delete Campaign (draft or finished)
  const deleteMutation = useMutation({
    mutationFn: (campaign: Campaign) => {
      if (!currentCompanyId) throw new Error("No active company");
      return campaignsApi.deleteCampaign(currentCompanyId, campaign.id);
    },
    onSuccess: (_, campaign) => {
      setModalState({ isOpen: false, campaign: null, mode: "delete" });
      invalidateCampaigns();
      showToast(`Campaign "${campaign.name}" was permanently deleted.`);
    },
    onError: (err: unknown) => {
      setModalState({ isOpen: false, campaign: null, mode: "delete" });
      const msg =
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Failed to delete campaign.";
      showToast(msg, "error");
    },
  });

  // Action handlers
  const handleOpenCancelModal = (campaign: Campaign) => {
    setModalState({
      isOpen: true,
      campaign,
      mode: "cancel",
    });
  };

  const handleOpenDeleteModal = (campaign: Campaign) => {
    setModalState({
      isOpen: true,
      campaign,
      mode: "delete",
    });
  };

  const handleConfirmModalAction = () => {
    if (!modalState.campaign || cancelMutation.isPending || deleteMutation.isPending) return;
    if (modalState.mode === "cancel") {
      cancelMutation.mutate(modalState.campaign);
    } else {
      deleteMutation.mutate(modalState.campaign);
    }
  };

  const handleViewCampaign = (campaign: Campaign) => {
    navigate(`/campaigns/${campaign.id}`);
  };

  const handleEditCampaign = (campaign: Campaign) => {
    if (campaign.status?.toUpperCase() === "DRAFT") {
      navigate(`/campaigns/${campaign.id}/edit`);
    }
  };

  const handleManageRecipients = (campaign: Campaign) => {
    navigate(`/campaigns/${campaign.id}/recipients`);
  };

  const handleCreateCampaign = () => {
    navigate("/campaigns/new");
  };

  const handleSendNowCampaign = (campaign: Campaign) => {
    showToast(
      `Immediate dispatch is not supported for scheduled campaign "${campaign.name}".`,
      "info"
    );
  };

  const mutatingCampaignId =
    pauseMutation.isPending && pauseMutation.variables
      ? pauseMutation.variables.id
      : resumeMutation.isPending && resumeMutation.variables
      ? resumeMutation.variables.id
      : cancelMutation.isPending && cancelMutation.variables
      ? cancelMutation.variables.id
      : deleteMutation.isPending && deleteMutation.variables
      ? deleteMutation.variables.id
      : null;

  return (
    <div className="flex flex-col gap-6 w-full max-w-7xl mx-auto min-w-0">
      {/* 1. Page Header */}
      <CampaignPageHeader
        totalCount={loadedCampaigns.length}
        showViewOptions={showSummaryCards}
        onToggleViewOptions={() => setShowSummaryCards((prev) => !prev)}
        onCreateCampaign={handleCreateCampaign}
      />

      {/* 2. KPI / Summary Cards Area */}
      {showSummaryCards && (
        <CampaignSummaryCards campaigns={loadedCampaigns} isLoading={isLoading} />
      )}

      {/* 3. Toolbar (Search & Filters) */}
      <CampaignToolbar
        searchQuery={searchQuery}
        onSearchChange={handleSearchChange}
        statusFilter={statusFilter}
        onStatusFilterChange={handleStatusFilterChange}
        senderFilter={senderFilter}
        onSenderFilterChange={handleSenderFilterChange}
        emailAccounts={emailAccounts}
        onClearFilters={handleClearFilters}
        hasActiveFilters={hasActiveFilters}
      />

      {/* 4. Main Content Area */}
      {isLoading ? (
        <CampaignSkeleton />
      ) : isError ? (
        <CampaignErrorState
          message={error?.message || "Unable to reach the campaign dispatch cluster."}
          onRetry={() => refetch()}
        />
      ) : loadedCampaigns.length === 0 && !hasActiveFilters ? (
        <CampaignEmptyState onCreateCampaign={handleCreateCampaign} />
      ) : filteredCampaigns.length === 0 ? (
        <CampaignSearchEmptyState onClearFilters={handleClearFilters} />
      ) : (
        <div className="w-full min-w-0 flex flex-col rounded-xl border border-slate-200/80 bg-white shadow-2xs overflow-hidden">
          <CampaignTable
            campaigns={filteredCampaigns}
            emailAccounts={emailAccounts}
            onViewCampaign={handleViewCampaign}
            onEditCampaign={isAdminOrOwner ? handleEditCampaign : undefined}
            onManageRecipients={handleManageRecipients}
            onSendNowCampaign={isAdminOrOwner ? handleSendNowCampaign : undefined}
            onPauseCampaign={
              isAdminOrOwner ? (c) => pauseMutation.mutate(c) : undefined
            }
            onResumeCampaign={
              isAdminOrOwner ? (c) => resumeMutation.mutate(c) : undefined
            }
            onCancelCampaign={isAdminOrOwner ? handleOpenCancelModal : undefined}
            onDeleteCampaign={isAdminOrOwner ? handleOpenDeleteModal : undefined}
            mutatingCampaignId={mutatingCampaignId}
          />

          {/* Pagination Footer */}
          <CampaignPagination
            currentPage={currentPage}
            pageSize={pageSize}
            itemCountOnPage={filteredCampaigns.length}
            hasNextPage={loadedCampaigns.length === pageSize}
            totalItems={currentPage === 1 && loadedCampaigns.length < pageSize ? loadedCampaigns.length : undefined}
            onPageChange={(page) => setCurrentPage(page)}
          />
        </div>
      )}

      {/* 5. Cancel / Delete Confirmation Modal */}
      <CancelCampaignModal
        isOpen={modalState.isOpen}
        campaign={modalState.campaign}
        mode={modalState.mode}
        onClose={() => setModalState({ isOpen: false, campaign: null, mode: "cancel" })}
        onConfirm={handleConfirmModalAction}
        isLoading={cancelMutation.isPending || deleteMutation.isPending}
      />

      {/* 6. Toast Banner */}
      {toastMessage && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-6 right-6 z-50 bg-slate-900 text-white px-4 py-3 rounded-xl shadow-xl flex items-center gap-3 border border-slate-800 text-xs animate-in fade-in slide-in-from-bottom-2 duration-200"
        >
          {toastMessage.type === "success" ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
          ) : toastMessage.type === "info" ? (
            <Info className="h-4 w-4 text-sky-400 shrink-0" />
          ) : (
            <AlertCircle className="h-4 w-4 text-rose-400 shrink-0" />
          )}
          <span>{toastMessage.text}</span>
        </div>
      )}
    </div>
  );
}
