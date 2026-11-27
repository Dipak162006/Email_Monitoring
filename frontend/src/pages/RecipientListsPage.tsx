import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, X, CheckCircle2, ChevronLeft, ChevronRight } from "lucide-react";

import { useWorkspace } from "../hooks/useWorkspace";
import { recipientListsApi, RequestError } from "../services/api";
import type {
  RecipientList,
  RecipientListCreatePayload,
  RecipientListUpdatePayload,
} from "../types/recipientList";

import { Button } from "../components/ui/Button";
import { RecipientListsTable } from "../components/recipientLists/RecipientListsTable";
import {
  RecipientListSkeleton,
  RecipientListEmptyState,
  RecipientListSearchEmptyState,
  RecipientListErrorState,
} from "../components/recipientLists/RecipientListsStates";
import { CreateRecipientListModal } from "../components/recipientLists/CreateRecipientListModal";
import { EditRecipientListModal } from "../components/recipientLists/EditRecipientListModal";
import { DeleteRecipientListModal } from "../components/recipientLists/DeleteRecipientListModal";

export const RecipientListsPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentCompanyId } = useWorkspace();

  // Search & Pagination state
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const pageSize = 50;

  // Debounce search input by 300ms
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setCurrentPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Modal states
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<RecipientList | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RecipientList | null>(null);

  // Toast feedback
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (msg: string) => {
    setToastMessage(msg);
    setTimeout(() => {
      setToastMessage(null);
    }, 3500);
  };

  // Query: fetch recipient lists
  const offset = (currentPage - 1) * pageSize;
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["recipientLists", currentCompanyId, debouncedSearch, currentPage],
    queryFn: () => {
      if (!currentCompanyId) return { items: [], total: 0, limit: pageSize, offset: 0 };
      return recipientListsApi.listRecipientLists(currentCompanyId, {
        search: debouncedSearch || undefined,
        limit: pageSize,
        offset,
      });
    },
    enabled: Boolean(currentCompanyId),
  });

  // Mutation: create list
  const createMutation = useMutation({
    mutationFn: (payload: RecipientListCreatePayload) => {
      if (!currentCompanyId) throw new Error("No active company");
      return recipientListsApi.createRecipientList(currentCompanyId, payload);
    },
    onSuccess: (newList) => {
      queryClient.invalidateQueries({ queryKey: ["recipientLists"] });
      showToast(`Recipient list "${newList.name}" created successfully.`);
    },
  });

  // Mutation: update list
  const updateMutation = useMutation({
    mutationFn: ({
      listId,
      payload,
    }: {
      listId: number;
      payload: RecipientListUpdatePayload;
    }) => {
      if (!currentCompanyId) throw new Error("No active company");
      return recipientListsApi.updateRecipientList(currentCompanyId, listId, payload);
    },
    onSuccess: (updatedList) => {
      queryClient.invalidateQueries({ queryKey: ["recipientLists"] });
      showToast(`List updated to "${updatedList.name}".`);
    },
  });

  // Mutation: delete list
  const deleteMutation = useMutation({
    mutationFn: (listId: number) => {
      if (!currentCompanyId) throw new Error("No active company");
      return recipientListsApi.deleteRecipientList(currentCompanyId, listId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["recipientLists"] });
      showToast("Recipient list deleted.");
      setDeleteTarget(null);
    },
  });

  // Handlers
  const handleManage = (list: RecipientList) => {
    navigate(`/recipient-lists/${list.id}`);
  };

  const handleCreateSubmit = async (payload: RecipientListCreatePayload) => {
    await createMutation.mutateAsync(payload);
  };

  const handleEditSubmit = async (
    listId: number,
    payload: RecipientListUpdatePayload
  ) => {
    await updateMutation.mutateAsync({ listId, payload });
  };

  const handleDeleteConfirm = async (listId: number) => {
    await deleteMutation.mutateAsync(listId);
  };

  const lists = data?.items || [];
  const total = data?.total || 0;
  const isSearchActive = Boolean(debouncedSearch);

  // Pagination bounds
  const startItem = total > 0 ? offset + 1 : 0;
  const endItem = Math.min(offset + lists.length, total);
  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-900 text-white shadow-xl text-xs font-medium animate-in fade-in slide-in-from-bottom-2 duration-200">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex flex-col">
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              Recipient Lists
            </h1>
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-600 border border-indigo-100">
              Audience
            </span>
          </div>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">
            Manage reusable contact lists for your email campaigns.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <Button
            onClick={() => setIsCreateOpen(true)}
            className="h-9 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1.5 shadow-xs transition-colors"
          >
            <Plus className="w-4 h-4" />
            <span>Create List</span>
          </Button>
        </div>
      </div>

      {/* Main Content Area */}
      {isLoading ? (
        <RecipientListSkeleton />
      ) : isError ? (
        <RecipientListErrorState
          message={
            error instanceof RequestError
              ? String(error.detail || error.message)
              : undefined
          }
          onRetry={() => refetch()}
        />
      ) : total === 0 && !isSearchActive ? (
        <RecipientListEmptyState onCreate={() => setIsCreateOpen(true)} />
      ) : (
        <div className="space-y-4">
          {/* Search Toolbar */}
          <div className="p-3 bg-white rounded-xl border border-slate-200 shadow-xs flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="relative flex-1 max-w-md">
              <div className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none flex items-center">
                <Search className="w-4 h-4" />
              </div>
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search recipient lists..."
                className="w-full h-9 pl-9 pr-8 bg-slate-50 rounded-lg text-slate-900 placeholder:text-slate-400 text-xs border border-transparent focus:border-indigo-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-all"
              />
              {searchInput && (
                <button
                  type="button"
                  onClick={() => setSearchInput("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-0.5 rounded transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            <div className="flex items-center justify-between sm:justify-end gap-3 text-slate-500 text-xs">
              <span className="font-medium text-slate-600">
                {total > 0
                  ? `Showing ${startItem}–${endItem} of ${total} lists`
                  : "0 lists found"}
              </span>
            </div>
          </div>

          {/* Table or Search Empty State */}
          {lists.length === 0 && isSearchActive ? (
            <RecipientListSearchEmptyState onClearSearch={() => setSearchInput("")} />
          ) : (
            <>
              <RecipientListsTable
                lists={lists}
                onManage={handleManage}
                onEdit={(list) => setEditTarget(list)}
                onDelete={(list) => setDeleteTarget(list)}
              />

              {/* Pagination controls if multiple pages */}
              {totalPages > 1 && (
                <div className="px-4 py-3 bg-white rounded-xl border border-slate-200 flex items-center justify-between text-xs text-slate-600">
                  <span>
                    Page {currentPage} of {totalPages}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                      disabled={currentPage <= 1}
                      className="h-8 px-2.5 text-xs"
                    >
                      <ChevronLeft className="w-3.5 h-3.5 mr-1" />
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                      disabled={currentPage >= totalPages}
                      className="h-8 px-2.5 text-xs"
                    >
                      Next
                      <ChevronRight className="w-3.5 h-3.5 ml-1" />
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Modals */}
      <CreateRecipientListModal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSubmit={handleCreateSubmit}
        isLoading={createMutation.isPending}
      />

      <EditRecipientListModal
        isOpen={Boolean(editTarget)}
        list={editTarget}
        onClose={() => setEditTarget(null)}
        onSubmit={handleEditSubmit}
        isLoading={updateMutation.isPending}
      />

      <DeleteRecipientListModal
        isOpen={Boolean(deleteTarget)}
        list={deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handleDeleteConfirm}
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
};
