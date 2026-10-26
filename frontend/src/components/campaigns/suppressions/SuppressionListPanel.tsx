import React, { useState, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Search,
  Filter,
  Plus,
  Trash2,
  RefreshCw,
  ShieldCheck,
  Inbox,
  AlertCircle,
  Copy,
  Check,
} from "lucide-react";

import { useWorkspace } from "../../../hooks/useWorkspace";
import { usePermissions } from "../../../hooks/usePermissions";
import { suppressionsApi } from "../../../services/api";
import type { SuppressionEntry } from "../../../types/campaign";

import { SuppressionReasonBadge } from "./SuppressionReasonBadge";
import { AddSuppressionModal } from "./AddSuppressionModal";
import { DeleteSuppressionModal } from "./DeleteSuppressionModal";
import { Button } from "../../ui/Button";

interface SuppressionListPanelProps {
  onShowToast?: (text: string, type?: "success" | "error" | "info") => void;
}

export const SuppressionListPanel: React.FC<SuppressionListPanelProps> = ({
  onShowToast,
}) => {
  const queryClient = useQueryClient();
  const { currentCompanyId, currentRole } = useWorkspace();
  const { isAdminOrOwner: permissionsIsAdminOrOwner } = usePermissions();
  const isAdminOrOwner =
    currentRole !== "MEMBER" &&
    (currentRole === "OWNER" ||
      currentRole === "ADMIN" ||
      Boolean(permissionsIsAdminOrOwner));

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState("");
  const [reasonFilter, setReasonFilter] = useState<string>("ALL");
  const [copiedEmail, setCopiedEmail] = useState<string | null>(null);

  // Modals state
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [deleteModalState, setDeleteModalState] = useState<{
    isOpen: boolean;
    entry: SuppressionEntry | null;
  }>({
    isOpen: false,
    entry: null,
  });

  // Query: load company suppression list
  const {
    data: suppressions = [],
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery<SuppressionEntry[], Error>({
    queryKey: [
      "suppressions",
      currentCompanyId,
      reasonFilter !== "ALL" ? reasonFilter : undefined,
      searchQuery.trim() || undefined,
    ],
    queryFn: () => {
      if (!currentCompanyId) return Promise.resolve([]);
      return suppressionsApi.listSuppressions(currentCompanyId, {
        reason: reasonFilter !== "ALL" ? reasonFilter : undefined,
        search: searchQuery.trim() || undefined,
        limit: 100,
        offset: 0,
      });
    },
    enabled: Boolean(currentCompanyId),
  });

  // Filter in memory as additional safety / responsive filtering
  const filteredSuppressions = useMemo(() => {
    return suppressions.filter((entry) => {
      if (reasonFilter !== "ALL" && entry.reason !== reasonFilter) {
        return false;
      }
      if (searchQuery.trim().length > 0) {
        const q = searchQuery.toLowerCase();
        if (!entry.email.toLowerCase().includes(q)) {
          return false;
        }
      }
      return true;
    });
  }, [suppressions, reasonFilter, searchQuery]);

  const handleCopyEmail = (email: string) => {
    navigator.clipboard?.writeText(email);
    setCopiedEmail(email);
    setTimeout(() => {
      setCopiedEmail(null);
    }, 2000);
  };

  const handleAddSuccess = (msg: string) => {
    queryClient.invalidateQueries({ queryKey: ["suppressions", currentCompanyId] });
    onShowToast?.(msg, "success");
  };

  const handleDeleteSuccess = (email: string) => {
    queryClient.invalidateQueries({ queryKey: ["suppressions", currentCompanyId] });
    onShowToast?.(`Successfully unsuppressed ${email}.`, "success");
  };

  const formatDate = (isoString: string) => {
    try {
      return new Date(isoString).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return isoString;
    }
  };

  const hasActiveFilters = searchQuery.trim().length > 0 || reasonFilter !== "ALL";

  return (
    <div className="flex flex-col gap-5 w-full min-w-0">
      {/* Information Banner */}
      <div className="bg-indigo-50/60 border border-indigo-100 rounded-xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs text-indigo-900">
        <div className="flex items-start sm:items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-indigo-100/80 text-indigo-700 flex items-center justify-center shrink-0">
            <ShieldCheck className="h-4 w-4" />
          </div>
          <div>
            <span className="font-semibold block text-slate-900">
              Workspace Suppression Protection
            </span>
            <span className="text-slate-600">
              Addresses on this list are permanently blocked from campaign outreach across this
              workspace to safeguard your sender reputation.
            </span>
          </div>
        </div>
        <div className="text-slate-500 font-medium shrink-0 self-end sm:self-auto">
          {filteredSuppressions.length} suppressed address
          {filteredSuppressions.length === 1 ? "" : "es"}
        </div>
      </div>

      {/* Toolbar: Search, Reason Filter, Actions */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-white p-3.5 rounded-xl border border-slate-200/80 shadow-2xs">
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 flex-1 min-w-0">
          {/* Search Box */}
          <div className="relative flex-1 min-w-[200px] max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
            <input
              type="text"
              aria-label="Search suppressed email"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search suppressed email..."
              className="w-full pl-9 pr-3 py-1.5 text-xs rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition bg-slate-50/50 focus:bg-white"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 text-xs"
                title="Clear search"
              >
                ✕
              </button>
            )}
          </div>

          {/* Reason Filter Dropdown */}
          <div className="flex items-center gap-2">
            <Filter className="h-3.5 w-3.5 text-slate-400 shrink-0 hidden sm:block" />
            <select
              aria-label="Filter by suppression reason"
              value={reasonFilter}
              onChange={(e) => setReasonFilter(e.target.value)}
              className="text-xs py-1.5 px-3 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white text-slate-700 font-medium shadow-2xs cursor-pointer"
            >
              <option value="ALL">All Reasons</option>
              <option value="BOUNCE">Bounced</option>
              <option value="UNSUBSCRIBE">Unsubscribed</option>
              <option value="MANUAL">Manual</option>
              <option value="COMPLAINT">Complaint</option>
            </select>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2 shrink-0">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            className="h-8 px-2.5 text-xs text-slate-600 hover:text-slate-900"
            title="Refresh suppression list"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>

          {isAdminOrOwner && (
            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={() => setIsAddModalOpen(true)}
              className="h-8 px-3 text-xs flex items-center gap-1.5 shadow-sm"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>Add Suppressed Email</span>
            </Button>
          )}
        </div>
      </div>

      {/* Main Content: Table / Skeletons / Empty States */}
      {isLoading ? (
        <div className="bg-white rounded-xl border border-slate-200/80 p-8 flex flex-col items-center justify-center gap-3">
          <RefreshCw className="h-6 w-6 text-indigo-500 animate-spin" />
          <p className="text-xs text-slate-500 font-medium">Loading suppression records...</p>
        </div>
      ) : isError ? (
        <div className="bg-white rounded-xl border border-rose-200 p-8 flex flex-col items-center justify-center text-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-rose-50 border border-rose-200 text-rose-600 flex items-center justify-center">
            <AlertCircle className="h-5 w-5" />
          </div>
          <div>
            <h4 className="text-sm font-bold text-slate-900">Failed to load suppression list</h4>
            <p className="text-xs text-slate-500 mt-1 max-w-md">
              {error?.message || "An unexpected error occurred while communicating with the server."}
            </p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      ) : suppressions.length === 0 && !hasActiveFilters ? (
        // Empty State: No suppressions at all
        <div className="bg-white rounded-xl border border-slate-200/80 p-12 flex flex-col items-center justify-center text-center">
          <div className="w-12 h-12 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center mb-3">
            <Inbox className="h-6 w-6" />
          </div>
          <h4 className="text-sm font-bold text-slate-900">No suppressed email addresses</h4>
          <p className="text-xs text-slate-500 mt-1 max-w-md leading-relaxed">
            Hard bounces and unsubscribed recipients are automatically added here. You can also
            manually add addresses to safeguard your domain reputation.
          </p>
          {isAdminOrOwner && (
            <div className="mt-4">
              <Button
                type="button"
                variant="primary"
                size="sm"
                onClick={() => setIsAddModalOpen(true)}
                className="flex items-center gap-1.5"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>Add Suppressed Email</span>
              </Button>
            </div>
          )}
        </div>
      ) : filteredSuppressions.length === 0 ? (
        // Search / Filter Empty State
        <div className="bg-white rounded-xl border border-slate-200/80 p-10 flex flex-col items-center justify-center text-center">
          <div className="w-10 h-10 rounded-xl bg-slate-100 text-slate-500 flex items-center justify-center mb-3">
            <Search className="h-5 w-5" />
          </div>
          <h4 className="text-sm font-bold text-slate-900">No matching suppression records</h4>
          <p className="text-xs text-slate-500 mt-1 max-w-sm">
            No suppressed addresses found matching your active filter criteria.
          </p>
          <div className="mt-4">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                setSearchQuery("");
                setReasonFilter("ALL");
              }}
            >
              Clear Filters
            </Button>
          </div>
        </div>
      ) : (
        <div className="w-full min-w-0 flex flex-col rounded-xl border border-slate-200/80 bg-white shadow-2xs overflow-hidden">
          {/* Desktop Table View */}
          <div className="hidden sm:block overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-200/80 bg-slate-50/75 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                  <th className="py-3 px-4">Email Address</th>
                  <th className="py-3 px-4">Reason</th>
                  <th className="py-3 px-4">Date Suppressed</th>
                  {isAdminOrOwner && (
                    <th className="py-3 px-4 text-right">Actions</th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-xs">
                {filteredSuppressions.map((entry) => (
                  <tr
                    key={entry.id}
                    data-testid={`suppression-row-${entry.id}`}
                    className="hover:bg-slate-50/50 transition-colors group"
                  >
                    {/* Email Column */}
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-medium text-slate-900 select-all">
                          {entry.email}
                        </span>
                        <button
                          type="button"
                          onClick={() => handleCopyEmail(entry.email)}
                          className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-slate-600 transition-opacity p-0.5 rounded"
                          title="Copy email address"
                        >
                          {copiedEmail === entry.email ? (
                            <Check className="h-3.5 w-3.5 text-emerald-600" />
                          ) : (
                            <Copy className="h-3.5 w-3.5" />
                          )}
                        </button>
                      </div>
                    </td>

                    {/* Reason Column */}
                    <td className="py-3 px-4">
                      <SuppressionReasonBadge reason={entry.reason} />
                    </td>

                    {/* Date Column */}
                    <td className="py-3 px-4 text-slate-500 whitespace-nowrap">
                      {formatDate(entry.created_at)}
                    </td>

                    {/* Actions Column */}
                    {isAdminOrOwner && (
                      <td className="py-3 px-4 text-right">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            setDeleteModalState({
                              isOpen: true,
                              entry,
                            })
                          }
                          aria-label={`Unsuppress ${entry.email}`}
                          className="h-7 px-2 text-rose-600 hover:text-rose-700 hover:bg-rose-50 text-xs gap-1 font-medium"
                          title="Remove from suppression list"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                          <span>Unsuppress</span>
                        </Button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile Cards View */}
          <div className="sm:hidden divide-y divide-slate-100">
            {filteredSuppressions.map((entry) => (
              <div
                key={entry.id}
                data-testid={`suppression-card-${entry.id}`}
                className="p-4 flex flex-col gap-2.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="font-mono font-semibold text-xs text-slate-900 break-all">
                    {entry.email}
                  </span>
                  <SuppressionReasonBadge reason={entry.reason} />
                </div>
                <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1">
                  <span>Suppressed {formatDate(entry.created_at)}</span>
                  {isAdminOrOwner && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() =>
                        setDeleteModalState({
                          isOpen: true,
                          entry,
                        })
                      }
                      className="h-7 px-2 text-rose-600 hover:text-rose-700 hover:bg-rose-50 text-xs"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      <span>Unsuppress</span>
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Add Modal */}
      {currentCompanyId && (
        <AddSuppressionModal
          isOpen={isAddModalOpen}
          companyId={currentCompanyId}
          onClose={() => setIsAddModalOpen(false)}
          onSuccess={handleAddSuccess}
        />
      )}

      {/* Delete / Unsuppress Modal */}
      {currentCompanyId && (
        <DeleteSuppressionModal
          isOpen={deleteModalState.isOpen}
          entry={deleteModalState.entry}
          companyId={currentCompanyId}
          onClose={() => setDeleteModalState({ isOpen: false, entry: null })}
          onSuccess={handleDeleteSuccess}
        />
      )}
    </div>
  );
};
