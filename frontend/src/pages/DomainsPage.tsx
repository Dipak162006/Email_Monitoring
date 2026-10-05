import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Globe,
  Plus,
  RefreshCw,
  Search,
  Lock,
} from "lucide-react";
import { useWorkspace } from "../hooks/useWorkspace";
import { useNotification } from "../hooks/useNotification";
import { domainsApi } from "../services/api";
import type { Domain, DomainVerificationStatus } from "../types/domains";
import { DomainStatusBadge } from "../components/domains/DomainStatusBadge";
import { DomainDnsStatus } from "../components/domains/DomainDnsStatus";
import { DomainActionMenu } from "../components/domains/DomainActionMenu";
import { DomainDetailsDrawer } from "../components/domains/DomainDetailsDrawer";
import { AddDomainDialog } from "../components/domains/AddDomainDialog";
import { EditDkimDialog } from "../components/domains/EditDkimDialog";
import { DeleteDomainDialog } from "../components/domains/DeleteDomainDialog";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { ErrorState } from "../components/ui/ErrorState";
import { cn } from "../lib/utils";

type StatusFilter = "ALL" | DomainVerificationStatus;

export function DomainsPage() {
  const queryClient = useQueryClient();

  // Active workspace & permissions context
  const {
    currentCompany,
    currentCompanyId,
    currentRole,
    isLoading: isWorkspaceLoading,
    isError: isWorkspaceError,
  } = useWorkspace();

  const canManage = currentRole === "OWNER" || currentRole === "ADMIN";
  const isMember = currentRole === "MEMBER";

  // Global notification feedback
  const { showNotification } = useNotification();

  // Modal / Drawer states
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [selectedDomainForDrawer, setSelectedDomainForDrawer] = useState<Domain | null>(null);
  const [selectedDomainForEdit, setSelectedDomainForEdit] = useState<Domain | null>(null);
  const [selectedDomainForDelete, setSelectedDomainForDelete] = useState<Domain | null>(null);

  // Search and status filter
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");

  // Per-domain verification state
  const [verifyingDomainId, setVerifyingDomainId] = useState<number | null>(null);

  // Fetch domains for active company
  const {
    data: domains = [],
    isLoading: isDomainsLoading,
    isError: isDomainsError,
    error: domainsErrorObj,
    refetch: refetchDomains,
    isFetching: isRefetching,
  } = useQuery({
    queryKey: ["company-domains", currentCompanyId],
    queryFn: () => domainsApi.listDomains(currentCompanyId!),
    enabled: !!currentCompanyId,
    staleTime: 30000,
  });

  // Verify Domain Mutation
  const verifyMutation = useMutation({
    mutationFn: async ({
      companyId,
      domainId,
    }: {
      companyId: number;
      domainId: number;
    }) => {
      if (!canManage) {
        throw new Error("You do not have permission to verify domains in this workspace.");
      }
      setVerifyingDomainId(domainId);
      return domainsApi.verifyDomain(companyId, domainId);
    },
    onSuccess: (updatedDomain) => {
      setVerifyingDomainId(null);
      queryClient.invalidateQueries({ queryKey: ["company-domains", currentCompanyId] });
      // If the drawer is open for this domain, keep it in sync
      if (selectedDomainForDrawer && selectedDomainForDrawer.id === updatedDomain.id) {
        setSelectedDomainForDrawer(updatedDomain);
      }
      showNotification(`DNS verification complete for ${updatedDomain.domain_name}.`);
    },
    onError: (err: unknown) => {
      setVerifyingDomainId(null);
      const errorObj = err as { detail?: string; message?: string };
      showNotification(
        errorObj.detail || errorObj.message || "DNS verification failed. Please try again.",
        "error"
      );
    },
  });

  // Client-side filtering by search query and verification_status
  const filteredDomains = useMemo(() => {
    return domains.filter((dom) => {
      // Status filter
      if (statusFilter !== "ALL" && dom.verification_status !== statusFilter) {
        return false;
      }
      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase().trim();
        const matchesName = dom.domain_name.toLowerCase().includes(q);
        const matchesSelector = dom.dkim_selector
          ? dom.dkim_selector.toLowerCase().includes(q)
          : false;
        if (!matchesName && !matchesSelector) {
          return false;
        }
      }
      return true;
    });
  }, [domains, statusFilter, searchQuery]);

  const handleVerify = (domain: Domain) => {
    if (!currentCompanyId) return;
    verifyMutation.mutate({
      companyId: currentCompanyId,
      domainId: domain.id,
    });
  };

  const handleDrawerVerify = () => {
    if (selectedDomainForDrawer) {
      handleVerify(selectedDomainForDrawer);
    }
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "Never";
    try {
      const date = new Date(dateStr);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffMins = Math.floor(diffMs / (1000 * 60));
      const diffHours = Math.floor(diffMins / 60);
      const diffDays = Math.floor(diffHours / 24);

      if (diffMins < 1) return "Just now";
      if (diffMins < 60) return `${diffMins} min${diffMins === 1 ? "" : "s"} ago`;
      if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? "" : "s"} ago`;
      if (diffDays < 7) return `${diffDays} day${diffDays === 1 ? "" : "s"} ago`;

      return date.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return dateStr;
    }
  };

  // Workspace error state
  if (isWorkspaceError || (!isWorkspaceLoading && !currentCompany)) {
    return (
      <div className="py-8">
        <ErrorState
          title="Workspace Unavailable"
          message="Could not load your active workspace. Please check your company connection."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header Section */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-xl font-bold tracking-tight text-slate-900">
              Domains
            </h1>
            {!isDomainsLoading && (
              <span className="px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 text-xs font-semibold">
                {domains.length} {domains.length === 1 ? "Domain" : "Domains"} Configured
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Manage and verify DNS authentication for your company's email domains.
          </p>
        </div>

        {/* Action Button Group */}
        <div className="flex items-center gap-2.5 shrink-0">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => refetchDomains()}
            disabled={isRefetching || isDomainsLoading}
            className="gap-1.5 text-xs text-slate-700 bg-white border-slate-200 hover:bg-slate-50 cursor-pointer shadow-2xs"
            title="Refresh domain DNS data"
          >
            <RefreshCw
              className={cn("w-3.5 h-3.5 text-slate-500", (isRefetching || isDomainsLoading) && "animate-spin")}
            />
            <span>Refresh</span>
          </Button>

          {canManage && (
            <Button
              type="button"
              size="sm"
              onClick={() => setIsAddModalOpen(true)}
              className="gap-1.5 text-xs bg-indigo-600 hover:bg-indigo-700 text-white font-semibold cursor-pointer shadow-2xs"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>Add Domain</span>
            </Button>
          )}
        </div>
      </div>

      {/* Read-Only Member Banner */}
      {isMember && (
        <div
          className="rounded-xl bg-slate-100/80 border border-slate-200 px-4 py-2.5 flex items-center gap-2.5 text-slate-700 text-xs"
          role="note"
        >
          <Lock className="w-4 h-4 text-slate-500 shrink-0" />
          <span>
            <strong>Read-Only Access:</strong> You are currently signed in as a workspace Member. Domain additions, modifications, and deletions are disabled.
          </span>
        </div>
      )}

      {/* Filter & Search Toolbar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        {/* Search */}
        <div className="relative flex-1 max-w-md">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search domain name or selector..."
            className="w-full pl-9 pr-4 py-1.5 text-xs bg-white border border-slate-200 rounded-lg text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 shadow-2xs transition-all"
          />
        </div>

        {/* Status Filter Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          <span className="text-xs font-medium text-slate-500 shrink-0 mr-1">
            Status:
          </span>
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg">
            {(["ALL", "VERIFIED", "WARNING", "FAILED", "PENDING"] as StatusFilter[]).map((tab) => {
              const isActive = statusFilter === tab;
              const label =
                tab === "ALL"
                  ? "All"
                  : tab.charAt(0) + tab.slice(1).toLowerCase();

              return (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setStatusFilter(tab)}
                  className={cn(
                    "px-2.5 py-1 rounded-md text-xs font-medium transition-all cursor-pointer",
                    isActive
                      ? "bg-white text-slate-900 font-semibold shadow-2xs"
                      : "text-slate-600 hover:text-slate-900"
                  )}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      {isDomainsLoading ? (
        /* Polished Skeleton Loading State */
        <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-2xs space-y-3">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="h-4 w-32 bg-slate-100 animate-pulse rounded" />
            <div className="h-4 w-24 bg-slate-100 animate-pulse rounded" />
          </div>
          <div className="space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="h-14 w-full bg-slate-50 animate-pulse rounded-lg border border-slate-100"
              />
            ))}
          </div>
        </div>
      ) : isDomainsError ? (
        /* Error State */
        <ErrorState
          title="Failed to Load Domains"
          message={
            (domainsErrorObj as { detail?: string; message?: string })?.detail ||
            "Unable to retrieve registered domains for this company. Please try again."
          }
          onRetry={() => refetchDomains()}
        />
      ) : domains.length === 0 ? (
        /* Empty State */
        <EmptyState
          icon={<Globe className="w-6 h-6 text-slate-400" />}
          title="No domains configured"
          description="Add your first domain to verify its DNS authentication settings for email."
          actionLabel={canManage ? "+ Add Domain" : undefined}
          onAction={canManage ? () => setIsAddModalOpen(true) : undefined}
        />
      ) : filteredDomains.length === 0 ? (
        /* No Search / Filter Matches */
        <div className="bg-white rounded-xl border border-dashed border-slate-200 p-8 text-center">
          <Search className="w-8 h-8 text-slate-300 mx-auto mb-2" />
          <h4 className="text-xs font-semibold text-slate-800">No matching domains</h4>
          <p className="text-[11px] text-slate-500 mt-0.5">
            No domains matched your search query or filter.
          </p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setSearchQuery("");
              setStatusFilter("ALL");
            }}
            className="mt-3 text-xs"
          >
            Clear Filters
          </Button>
        </div>
      ) : (
        /* Loaded Table & Mobile Cards */
        <div className="space-y-4">
          {/* Desktop Table (>= 1024px) */}
          <div className="hidden lg:block bg-white rounded-xl border border-slate-200 shadow-2xs overflow-visible">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-50/80 border-b border-slate-200 text-slate-500 text-[11px] font-bold uppercase tracking-wider select-none">
                  <th scope="col" className="py-3 px-4">
                    Domain Name
                  </th>
                  <th scope="col" className="py-3 px-4">
                    Overall Status
                  </th>
                  <th scope="col" className="py-3 px-4">
                    DNS Diagnostics
                  </th>
                  <th scope="col" className="py-3 px-4">
                    Last Checked
                  </th>
                  <th scope="col" className="py-3 px-4 text-right">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-xs">
                {filteredDomains.map((domain, index) => {
                  const isVerifying = verifyingDomainId === domain.id;

                  return (
                    <tr
                      key={domain.id}
                      className="hover:bg-slate-50/60 transition-colors group"
                    >
                      {/* Domain Name */}
                      <td className="py-3.5 px-4">
                        <div
                          onClick={() => setSelectedDomainForDrawer(domain)}
                          className="flex items-center gap-2.5 cursor-pointer"
                        >
                          <div className="w-7 h-7 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 group-hover:bg-indigo-600 group-hover:text-white transition-colors shrink-0">
                            <Globe className="w-3.5 h-3.5" />
                          </div>
                          <div className="flex flex-col min-w-0">
                            <span className="font-mono text-xs font-bold text-slate-900 group-hover:text-indigo-600 transition-colors truncate">
                              {domain.domain_name}
                            </span>
                            <span className="text-[11px] text-slate-400">
                              Added {formatDate(domain.created_at)}
                            </span>
                          </div>
                        </div>
                      </td>

                      {/* Overall Status */}
                      <td className="py-3.5 px-4">
                        <DomainStatusBadge status={domain.verification_status} size="sm" />
                      </td>

                      {/* DNS Diagnostics Matrix */}
                      <td className="py-3.5 px-4">
                        <DomainDnsStatus
                          mxStatus={domain.mx_status}
                          spfStatus={domain.spf_status}
                          dkimStatus={domain.dkim_status}
                          dmarcStatus={domain.dmarc_status}
                          dkimSelector={domain.dkim_selector}
                        />
                      </td>

                      {/* Last Checked */}
                      <td className="py-3.5 px-4">
                        <span className="font-mono text-[11px] text-slate-500">
                          {formatDate(domain.last_checked_at)}
                        </span>
                      </td>

                      {/* Actions */}
                      <td className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {canManage && (
                            <button
                              type="button"
                              onClick={() => handleVerify(domain)}
                              disabled={isVerifying}
                              className="px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200/70 text-slate-700 text-xs font-medium transition-colors flex items-center gap-1 disabled:opacity-50 cursor-pointer"
                              title="Verify DNS authentication now"
                            >
                              <RefreshCw
                                className={cn("w-3 h-3 text-slate-500", isVerifying && "animate-spin")}
                              />
                              <span>{isVerifying ? "Verifying..." : "Verify"}</span>
                            </button>
                          )}

                          {/* 3-Dot Action Menu */}
                          <DomainActionMenu
                            domain={domain}
                            canManage={canManage}
                            isVerifying={isVerifying}
                            onViewDetails={(dom) => setSelectedDomainForDrawer(dom)}
                            onVerify={(dom) => handleVerify(dom)}
                            onEditDkim={(dom) => setSelectedDomainForEdit(dom)}
                            onDelete={(dom) => setSelectedDomainForDelete(dom)}
                            direction={index >= filteredDomains.length - 2 && filteredDomains.length > 2 ? "up" : "down"}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Mobile Responsive Card Stack (< 1024px) */}
          <div className="lg:hidden space-y-3">
            {filteredDomains.map((domain) => {
              const isVerifying = verifyingDomainId === domain.id;

              return (
                <div
                  key={domain.id}
                  className="bg-white rounded-xl border border-slate-200 p-4 shadow-2xs space-y-3"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div
                      onClick={() => setSelectedDomainForDrawer(domain)}
                      className="flex items-center gap-2.5 cursor-pointer min-w-0"
                    >
                      <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shrink-0">
                        <Globe className="w-4 h-4" />
                      </div>
                      <div className="min-w-0">
                        <span className="font-mono text-xs font-bold text-slate-900 block truncate">
                          {domain.domain_name}
                        </span>
                        <p className="text-[11px] text-slate-400">
                          Added {formatDate(domain.created_at)}
                        </p>
                      </div>
                    </div>
                    <DomainStatusBadge status={domain.verification_status} size="sm" />
                  </div>

                  {/* DNS Matrix */}
                  <div className="pt-1">
                    <DomainDnsStatus
                      mxStatus={domain.mx_status}
                      spfStatus={domain.spf_status}
                      dkimStatus={domain.dkim_status}
                      dmarcStatus={domain.dmarc_status}
                      dkimSelector={domain.dkim_selector}
                    />
                  </div>

                  {/* Card Footer */}
                  <div className="flex items-center justify-between pt-2.5 border-t border-slate-100 text-xs">
                    <span className="font-mono text-[11px] text-slate-400">
                      Checked {formatDate(domain.last_checked_at)}
                    </span>
                    <div className="flex items-center gap-2">
                      {canManage && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={isVerifying}
                          onClick={() => handleVerify(domain)}
                          className="h-7 px-2.5 text-xs text-slate-700 border-slate-200"
                        >
                          <RefreshCw
                            className={cn("w-3 h-3 mr-1", isVerifying && "animate-spin")}
                          />
                          <span>{isVerifying ? "Checking..." : "Verify"}</span>
                        </Button>
                      )}
                      <Button
                        type="button"
                        size="sm"
                        onClick={() => setSelectedDomainForDrawer(domain)}
                        className="h-7 px-2.5 text-xs bg-indigo-600 hover:bg-indigo-700 text-white"
                      >
                        Details
                      </Button>

                      {/* Mobile 3-dot overflow */}
                      <DomainActionMenu
                        domain={domain}
                        canManage={canManage}
                        isVerifying={isVerifying}
                        onViewDetails={(dom) => setSelectedDomainForDrawer(dom)}
                        onVerify={(dom) => handleVerify(dom)}
                        onEditDkim={(dom) => setSelectedDomainForEdit(dom)}
                        onDelete={(dom) => setSelectedDomainForDelete(dom)}
                        direction="up"
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Details Slide-Over Sheet */}
      <DomainDetailsDrawer
        isOpen={Boolean(selectedDomainForDrawer)}
        onClose={() => setSelectedDomainForDrawer(null)}
        domain={selectedDomainForDrawer}
        canManage={canManage}
        isVerifying={verifyingDomainId === selectedDomainForDrawer?.id}
        onVerify={handleDrawerVerify}
        onEditDkim={() => {
          setSelectedDomainForEdit(selectedDomainForDrawer);
          setSelectedDomainForDrawer(null);
        }}
        onDelete={() => {
          setSelectedDomainForDelete(selectedDomainForDrawer);
          setSelectedDomainForDrawer(null);
        }}
      />

      {/* Add Domain Dialog */}
      {currentCompanyId && (
        <AddDomainDialog
          isOpen={isAddModalOpen}
          onClose={() => setIsAddModalOpen(false)}
          companyId={currentCompanyId}
          onSuccess={(newDomain) => {
            setIsAddModalOpen(false);
            queryClient.invalidateQueries({ queryKey: ["company-domains", currentCompanyId] });
            showNotification(`Domain ${newDomain.domain_name} added successfully.`);
          }}
        />
      )}

      {/* Edit DKIM Dialog */}
      {currentCompanyId && selectedDomainForEdit && (
        <EditDkimDialog
          isOpen={Boolean(selectedDomainForEdit)}
          onClose={() => setSelectedDomainForEdit(null)}
          domain={selectedDomainForEdit}
          companyId={currentCompanyId}
          onSuccess={(updatedDomain) => {
            setSelectedDomainForEdit(null);
            queryClient.invalidateQueries({ queryKey: ["company-domains", currentCompanyId] });
            showNotification(`DKIM configuration updated for ${updatedDomain.domain_name}.`);
          }}
        />
      )}

      {/* Delete Domain Confirmation Dialog */}
      {currentCompanyId && selectedDomainForDelete && (
        <DeleteDomainDialog
          isOpen={Boolean(selectedDomainForDelete)}
          onClose={() => setSelectedDomainForDelete(null)}
          domain={selectedDomainForDelete}
          companyId={currentCompanyId}
          onSuccess={(deletedDomain) => {
            setSelectedDomainForDelete(null);
            if (selectedDomainForDrawer?.id === deletedDomain.id) {
              setSelectedDomainForDrawer(null);
            }
            queryClient.invalidateQueries({ queryKey: ["company-domains", currentCompanyId] });
            queryClient.invalidateQueries({ queryKey: ["company-email-accounts"] });
            showNotification(`Domain ${deletedDomain.domain_name} deleted.`);
          }}
        />
      )}
    </div>
  );
}
