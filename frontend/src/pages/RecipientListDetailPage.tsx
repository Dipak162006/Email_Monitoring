import React, { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ChevronRight,
  ArrowLeft,
  Users,
  Plus,
  UploadCloud,
  Search,
  X,
  ChevronLeft,
  CheckCircle2,
} from "lucide-react";

import { useWorkspace } from "../hooks/useWorkspace";
import { recipientListsApi } from "../services/api";
import type {
  RecipientListMember,
  RecipientListMemberCreatePayload,
  RecipientListMemberUpdatePayload,
} from "../types/recipientList";

import { Button } from "../components/ui/Button";
import { RecipientMembersTable } from "../components/recipientLists/RecipientMembersTable";
import {
  RecipientMemberSkeleton,
  RecipientMemberEmptyState,
  RecipientMemberSearchEmptyState,
  RecipientMemberErrorState,
} from "../components/recipientLists/RecipientMemberStates";
import { AddRecipientMemberModal } from "../components/recipientLists/AddRecipientMemberModal";
import { EditRecipientMemberModal } from "../components/recipientLists/EditRecipientMemberModal";
import { DeleteRecipientMemberModal } from "../components/recipientLists/DeleteRecipientMemberModal";
import { ImportRecipientCsvModal } from "../components/recipientLists/ImportRecipientCsvModal";

export const RecipientListDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const listId = Number(id);
  const { currentCompanyId } = useWorkspace();
  const queryClient = useQueryClient();

  // Search & Pagination state
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 50;

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setCurrentPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Modal states
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [isImportOpen, setIsImportOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<RecipientListMember | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RecipientListMember | null>(null);

  // Toast feedback state
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 3500);
  };

  // 1. Query: List metadata
  const {
    data: list,
    isLoading: isListLoading,
  } = useQuery({
    queryKey: ["recipientList", currentCompanyId, listId],
    queryFn: () => {
      if (!currentCompanyId || isNaN(listId)) return null;
      return recipientListsApi.getRecipientList(currentCompanyId, listId);
    },
    enabled: Boolean(currentCompanyId && !isNaN(listId)),
  });

  // 2. Query: List members (with search & pagination)
  const offset = (currentPage - 1) * pageSize;
  const {
    data: membersData,
    isLoading: isMembersLoading,
    isError: isMembersError,
    error: membersError,
    refetch: refetchMembers,
  } = useQuery({
    queryKey: ["recipientListMembers", currentCompanyId, listId, debouncedSearch, currentPage],
    queryFn: () => {
      if (!currentCompanyId || isNaN(listId)) {
        return { items: [], total: 0, limit: pageSize, offset: 0 };
      }
      return recipientListsApi.listMembers(currentCompanyId, listId, {
        search: debouncedSearch || undefined,
        limit: pageSize,
        offset,
      });
    },
    enabled: Boolean(currentCompanyId && !isNaN(listId)),
  });

  // Invalidation helper
  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: ["recipientListMembers", currentCompanyId, listId] });
    queryClient.invalidateQueries({ queryKey: ["recipientList", currentCompanyId, listId] });
    queryClient.invalidateQueries({ queryKey: ["recipientLists"] });
  };

  // 3. Mutation: Add Member
  const addMutation = useMutation({
    mutationFn: (payload: RecipientListMemberCreatePayload) => {
      if (!currentCompanyId) throw new Error("No active workspace");
      return recipientListsApi.addMember(currentCompanyId, listId, payload);
    },
    onSuccess: (newMember) => {
      invalidateAll();
      showToast(`Contact "${newMember.email}" added to list.`);
    },
  });

  // 4. Mutation: Update Member
  const updateMutation = useMutation({
    mutationFn: ({
      memberId,
      payload,
    }: {
      memberId: number;
      payload: RecipientListMemberUpdatePayload;
    }) => {
      if (!currentCompanyId) throw new Error("No active workspace");
      return recipientListsApi.updateMember(currentCompanyId, listId, memberId, payload);
    },
    onSuccess: (updated) => {
      invalidateAll();
      showToast(`Contact "${updated.email}" updated.`);
      setEditTarget(null);
    },
  });

  // 5. Mutation: Remove Member
  const deleteMutation = useMutation({
    mutationFn: (memberId: number) => {
      if (!currentCompanyId) throw new Error("No active workspace");
      return recipientListsApi.removeMember(currentCompanyId, listId, memberId);
    },
    onSuccess: () => {
      invalidateAll();
      showToast("Contact removed from list.");
      setDeleteTarget(null);
    },
  });

  // CSV Import handler
  const handleCsvImport = async (file: File) => {
    if (!currentCompanyId) throw new Error("No active workspace");
    const result = await recipientListsApi.importMembersCsv(currentCompanyId, listId, file);
    invalidateAll();
    return result;
  };

  const totalMembers = membersData?.total ?? 0;
  const members = membersData?.items ?? [];
  const totalPages = Math.max(1, Math.ceil(totalMembers / pageSize));

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 bg-slate-900 text-white text-xs px-4 py-2.5 rounded-xl shadow-xl flex items-center gap-2 animate-in fade-in slide-in-from-bottom-2 duration-200">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Breadcrumb Navigation */}
      <nav className="flex items-center gap-2 text-xs text-slate-500">
        <Link
          to="/recipient-lists"
          className="hover:text-slate-800 transition-colors inline-flex items-center gap-1.5"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Recipient Lists
        </Link>
        <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
        <span className="font-semibold text-slate-900 truncate">
          {isListLoading ? "Loading list..." : list?.name || `List #${id}`}
        </span>
      </nav>

      {/* Header Banner */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-start sm:items-center gap-3.5">
          <div className="w-12 h-12 rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
            <Users className="w-6 h-6" />
          </div>
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-xl font-bold text-slate-900">
                {list?.name || (isListLoading ? "Loading List..." : `List #${id}`)}
              </h1>
              {list && (
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-semibold border border-indigo-100">
                  {list.recipient_count} {list.recipient_count === 1 ? "contact" : "contacts"}
                </span>
              )}
            </div>
            {list?.description ? (
              <p className="text-xs text-slate-500 mt-1 max-w-2xl">{list.description}</p>
            ) : (
              <p className="text-xs text-slate-400 mt-1 italic">No description provided</p>
            )}
          </div>
        </div>

        <Link to="/recipient-lists">
          <Button variant="outline" className="text-xs font-semibold px-4 py-2 rounded-xl">
            Back to Recipient Lists
          </Button>
        </Link>
      </div>

      {/* Action Toolbar */}
      <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-xs flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        {/* Search */}
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3.5 top-2.5 h-4 w-4 text-slate-400 pointer-events-none" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search contacts by email or name..."
            className="w-full pl-9 pr-8 py-2 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:bg-white focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
          />
          {searchInput && (
            <button
              type="button"
              onClick={() => setSearchInput("")}
              className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 p-0.5"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2.5">
          <Button
            type="button"
            variant="outline"
            onClick={() => setIsImportOpen(true)}
            className="px-4 py-2 text-xs font-semibold rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 flex items-center gap-1.5 shadow-2xs"
          >
            <UploadCloud className="h-4 w-4 text-slate-500" />
            <span>Import CSV</span>
          </Button>
          <Button
            type="button"
            onClick={() => setIsAddOpen(true)}
            className="px-4 py-2 text-xs font-semibold rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white flex items-center gap-1.5 shadow-sm"
          >
            <Plus className="h-4 w-4" />
            <span>Add Recipient</span>
          </Button>
        </div>
      </div>

      {/* Content Area */}
      {isMembersLoading ? (
        <RecipientMemberSkeleton />
      ) : isMembersError ? (
        <RecipientMemberErrorState
          error={(membersError as any)?.message}
          onRetry={() => refetchMembers()}
        />
      ) : members.length === 0 ? (
        debouncedSearch ? (
          <RecipientMemberSearchEmptyState
            searchTerm={debouncedSearch}
            onClearSearch={() => setSearchInput("")}
          />
        ) : (
          <RecipientMemberEmptyState
            onAddRecipient={() => setIsAddOpen(true)}
            onImportCsv={() => setIsImportOpen(true)}
          />
        )
      ) : (
        <div className="space-y-4">
          <RecipientMembersTable
            members={members}
            onEdit={(m) => setEditTarget(m)}
            onDelete={(m) => setDeleteTarget(m)}
          />

          {/* Pagination Controls */}
          {totalMembers > 0 && (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-500 px-1">
              <div>
                Showing <span className="font-semibold text-slate-900">{offset + 1}</span> to{" "}
                <span className="font-semibold text-slate-900">
                  {Math.min(offset + pageSize, totalMembers)}
                </span>{" "}
                of <span className="font-semibold text-slate-900">{totalMembers}</span> contacts
              </div>

              {totalPages > 1 && (
                <div className="flex items-center gap-1.5">
                  <Button
                    type="button"
                    variant="outline"
                    disabled={currentPage <= 1}
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    className="p-1.5 rounded-lg text-xs"
                    title="Previous page"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <span className="px-2 font-medium text-slate-700">
                    Page {currentPage} of {totalPages}
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={currentPage >= totalPages}
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    className="p-1.5 rounded-lg text-xs"
                    title="Next page"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Modals */}
      <AddRecipientMemberModal
        isOpen={isAddOpen}
        onClose={() => setIsAddOpen(false)}
        onAdd={async (payload) => {
          await addMutation.mutateAsync(payload);
        }}
        isLoading={addMutation.isPending}
      />

      <EditRecipientMemberModal
        isOpen={Boolean(editTarget)}
        member={editTarget}
        onClose={() => setEditTarget(null)}
        onSave={async (memberId, payload) => {
          await updateMutation.mutateAsync({ memberId, payload });
        }}
        isLoading={updateMutation.isPending}
      />

      <DeleteRecipientMemberModal
        isOpen={Boolean(deleteTarget)}
        member={deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={async () => {
          if (!deleteTarget) return;
          await deleteMutation.mutateAsync(deleteTarget.id);
        }}
        isLoading={deleteMutation.isPending}
      />

      <ImportRecipientCsvModal
        isOpen={isImportOpen}
        onClose={() => setIsImportOpen(false)}
        onImport={handleCsvImport}
      />
    </div>
  );
};
