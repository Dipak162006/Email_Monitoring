import React, { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import {
  Users,
  Search,
  CheckCircle2,
  AlertCircle,
  Loader2,
  FolderPlus,
  X,
} from "lucide-react";
import { recipientListsApi, campaignsApi, RequestError } from "../../../services/api";
import type {
  CampaignRecipientListImportResponse,
} from "../../../types/campaign";
import type { RecipientList } from "../../../types/recipientList";
import { Button } from "../../ui/Button";

interface CampaignRecipientListSelectorProps {
  companyId: number;
  campaignId: number;
  disabled?: boolean;
  onImportSuccess?: (result: CampaignRecipientListImportResponse) => void;
}

export const CampaignRecipientListSelector: React.FC<CampaignRecipientListSelectorProps> = ({
  companyId,
  campaignId,
  disabled = false,
  onImportSuccess,
}) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedListIds, setSelectedListIds] = useState<number[]>([]);
  const [importResult, setImportResult] = useState<CampaignRecipientListImportResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Fetch available recipient lists for this company
  const {
    data: listsResponse,
    isLoading: isListsLoading,
    isError: isListsError,
    error: listsError,
  } = useQuery({
    queryKey: ["recipientLists", companyId, "forSelector"],
    queryFn: () => recipientListsApi.listRecipientLists(companyId, { limit: 100 }),
    enabled: Boolean(companyId),
  });

  const availableLists = listsResponse?.items || [];

  // Filter lists by search query
  const filteredLists = availableLists.filter((list) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      list.name.toLowerCase().includes(q) ||
      (list.description && list.description.toLowerCase().includes(q))
    );
  });

  // Calculate total contacts across selected lists
  const selectedContactsCount = availableLists
    .filter((l) => selectedListIds.includes(l.id))
    .reduce((sum, l) => sum + (l.recipient_count || 0), 0);

  // Toggle list selection
  const handleToggleList = (listId: number) => {
    if (disabled) return;
    setImportResult(null);
    setErrorMessage(null);
    setSelectedListIds((prev) =>
      prev.includes(listId) ? prev.filter((id) => id !== listId) : [...prev, listId]
    );
  };

  const handleSelectAll = () => {
    if (disabled) return;
    const allFilteredIds = filteredLists.map((l) => l.id);
    const areAllSelected = allFilteredIds.every((id) => selectedListIds.includes(id));
    if (areAllSelected) {
      setSelectedListIds((prev) => prev.filter((id) => !allFilteredIds.includes(id)));
    } else {
      setSelectedListIds((prev) => Array.from(new Set([...prev, ...allFilteredIds])));
    }
  };

  // Mutation to import from selected lists
  const importMutation = useMutation({
    mutationFn: () => {
      return campaignsApi.importRecipientsFromLists(companyId, campaignId, {
        list_ids: selectedListIds,
      });
    },
    onSuccess: (result) => {
      setImportResult(result);
      setErrorMessage(null);
      setSelectedListIds([]);
      if (onImportSuccess) {
        onImportSuccess(result);
      }
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof RequestError
          ? String(err.detail || err.message)
          : (err as any)?.response?.data?.detail || "Failed to import contacts from selected lists.";
      setErrorMessage(msg);
    },
  });

  const handleImport = () => {
    if (selectedListIds.length === 0 || disabled || importMutation.isPending) return;
    importMutation.mutate();
  };

  return (
    <div className="w-full space-y-4">
      {/* Header Info */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">
            Import Reusable Recipient Lists
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Select one or more existing contact lists to snapshot into this campaign draft.
          </p>
        </div>

        {/* Search Input */}
        {availableLists.length > 0 && (
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400 pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search lists..."
              className="w-full pl-8 pr-7 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 placeholder:text-slate-400 focus:outline-none focus:bg-white focus:border-indigo-500 transition-all"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute right-2 top-2 text-slate-400 hover:text-slate-600 p-0.5"
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
        )}
      </div>

      {/* Error Alert */}
      {errorMessage && (
        <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl flex items-center gap-2.5 text-xs text-rose-700">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span className="font-medium">{errorMessage}</span>
        </div>
      )}

      {/* Post-Import Results Breakdown */}
      {importResult && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs space-y-3 animate-in fade-in">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
                <CheckCircle2 className="h-4 w-4" />
              </div>
              <div>
                <h4 className="text-xs font-bold text-slate-900">
                  Recipient Lists Imported Successfully
                </h4>
                <p className="text-xs text-slate-500">
                  Total contacts evaluated from selected lists:{" "}
                  <span className="font-semibold text-slate-900">
                    {importResult.total_contacts_processed}
                  </span>
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
            <div className="bg-emerald-50 text-emerald-800 p-2.5 rounded-xl border border-emerald-100">
              <span className="block text-base font-bold">{importResult.inserted_count}</span>
              <span className="text-[11px] font-medium">Added to Audience</span>
            </div>
            <div className="bg-slate-50 text-slate-700 p-2.5 rounded-xl border border-slate-200">
              <span className="block text-base font-bold">{importResult.skipped_existing_count}</span>
              <span className="text-[11px]">Already in Campaign</span>
            </div>
            <div className="bg-amber-50 text-amber-800 p-2.5 rounded-xl border border-amber-100">
              <span className="block text-base font-bold">{importResult.skipped_list_duplicates_count}</span>
              <span className="text-[11px]">Duplicates in Lists</span>
            </div>
          </div>
        </div>
      )}

      {/* Lists Loading State */}
      {isListsLoading ? (
        <div className="p-8 text-center bg-slate-50 rounded-2xl border border-slate-200">
          <Loader2 className="h-6 w-6 animate-spin text-indigo-600 mx-auto mb-2" />
          <p className="text-xs text-slate-500">Loading your recipient lists...</p>
        </div>
      ) : isListsError ? (
        <div className="p-6 text-center bg-rose-50 rounded-2xl border border-rose-200 text-xs text-rose-700">
          <p>Failed to load recipient lists: {(listsError as any)?.message}</p>
        </div>
      ) : availableLists.length === 0 ? (
        <div className="p-8 text-center bg-slate-50 rounded-2xl border border-slate-200 space-y-2">
          <Users className="h-8 w-8 text-slate-400 mx-auto" />
          <h4 className="text-xs font-bold text-slate-800">No Recipient Lists Created Yet</h4>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            You don't have any reusable recipient lists in this workspace yet. You can create one from the Recipient Lists section or continue with CSV or manual entry.
          </p>
        </div>
      ) : filteredLists.length === 0 ? (
        <div className="p-6 text-center bg-slate-50 rounded-2xl border border-slate-200">
          <p className="text-xs text-slate-500">
            No recipient lists match "<span className="font-semibold">{searchQuery}</span>".
          </p>
        </div>
      ) : (
        /* List Selection Grid */
        <div className="space-y-3">
          <div className="flex items-center justify-between text-xs text-slate-500 px-1">
            <button
              type="button"
              onClick={handleSelectAll}
              disabled={disabled}
              className="text-indigo-600 hover:text-indigo-700 font-medium disabled:opacity-50"
            >
              {filteredLists.every((l) => selectedListIds.includes(l.id))
                ? "Deselect All"
                : "Select All Filtered"}
            </button>
            <span>
              {selectedListIds.length} list{selectedListIds.length === 1 ? "" : "s"} selected
              {selectedListIds.length > 0 && ` (${selectedContactsCount} potential contacts)`}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-72 overflow-y-auto p-0.5">
            {filteredLists.map((list: RecipientList) => {
              const isSelected = selectedListIds.includes(list.id);
              return (
                <div
                  key={list.id}
                  onClick={() => handleToggleList(list.id)}
                  className={`p-3.5 rounded-xl border text-left transition-all cursor-pointer flex items-start gap-3 select-none ${
                    isSelected
                      ? "border-indigo-500 bg-indigo-50/40 ring-1 ring-indigo-500/20"
                      : "border-slate-200 bg-white hover:bg-slate-50/80"
                  } ${disabled ? "opacity-60 cursor-not-allowed" : ""}`}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => handleToggleList(list.id)}
                    disabled={disabled}
                    className="mt-1 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/20 cursor-pointer"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <h4 className="text-xs font-bold text-slate-900 truncate">
                        {list.name}
                      </h4>
                      <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-medium shrink-0">
                        {list.recipient_count} {list.recipient_count === 1 ? "contact" : "contacts"}
                      </span>
                    </div>
                    {list.description && (
                      <p className="text-[11px] text-slate-500 mt-1 line-clamp-1">
                        {list.description}
                      </p>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Action Row */}
          <div className="pt-2 flex items-center justify-between border-t border-slate-100">
            <span className="text-xs text-slate-500">
              Importing copies contacts as a snapshot into this campaign. Future changes to lists won't affect this campaign.
            </span>
            <Button
              type="button"
              onClick={handleImport}
              disabled={selectedListIds.length === 0 || disabled || importMutation.isPending}
              className="px-5 py-2 text-xs font-semibold rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white flex items-center gap-1.5 shadow-sm disabled:opacity-50"
            >
              {importMutation.isPending ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Importing...</span>
                </>
              ) : (
                <>
                  <FolderPlus className="h-4 w-4" />
                  <span>
                    Import {selectedListIds.length > 0 ? `${selectedListIds.length} ` : ""}List
                    {selectedListIds.length === 1 ? "" : "s"}
                  </span>
                </>
              )}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};
