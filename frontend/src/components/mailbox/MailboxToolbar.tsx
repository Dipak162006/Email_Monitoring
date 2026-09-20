import React from "react";
import {
  Star,
  Mail,
  MailOpen,
  Trash2,
  Search,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  RotateCcw,
  Loader2,
} from "lucide-react";
import type { AuthorizedEmailAccount } from "../../types/emails";

interface MailboxToolbarProps {
  // Selection
  isAllSelected: boolean;
  isSomeSelected: boolean;
  selectedCount: number;
  totalVisibleCount: number;
  onToggleSelectAll: () => void;
  // Bulk Actions
  onBulkStar: () => void;
  isAllSelectedStarred?: boolean;
  onBulkMarkRead: (read: boolean) => void;
  onBulkMoveToTrash?: () => void;
  // Trash folder actions
  isTrash?: boolean;
  onRestore?: () => void;
  isRestoring?: boolean;
  onBulkPermanentDelete?: () => void;
  isPermanentDeleting?: boolean;
  // Account filter
  accounts: AuthorizedEmailAccount[];
  selectedAccountId?: number;
  onAccountChange: (accountId?: number) => void;
  // Sorting
  sortBy?: "newest" | "oldest";
  onSortChange?: (sort: "newest" | "oldest") => void;
  // Search
  searchQuery: string;
  onSearchChange: (query: string) => void;
  folderTitle?: string;
  // Pagination
  currentPage: number;
  pageSize: number;
  totalCount: number;
  onPageChange: (newPage: number) => void;
}

export const MailboxToolbar: React.FC<MailboxToolbarProps> = ({
  isAllSelected,
  isSomeSelected,
  selectedCount,
  totalVisibleCount,
  onToggleSelectAll,
  onBulkStar,
  isAllSelectedStarred = false,
  onBulkMarkRead,
  onBulkMoveToTrash,
  isTrash = false,
  onRestore,
  isRestoring = false,
  onBulkPermanentDelete,
  isPermanentDeleting = false,
  accounts,
  selectedAccountId,
  onAccountChange,
  sortBy = "newest",
  onSortChange,
  searchQuery,
  onSearchChange,
  folderTitle,
  currentPage,
  pageSize,
  totalCount,
  onPageChange,
}) => {
  const startItem = totalCount === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const endItem = Math.min(currentPage * pageSize, totalCount);
  const totalPages = Math.ceil(totalCount / pageSize) || 1;
  const canGoPrev = currentPage > 1;
  const canGoNext = currentPage < totalPages;

  const hasSelection = selectedCount > 0;

  return (
    <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 px-5 py-3 border-b border-slate-200/80 bg-white select-none">
      {/* Left: Bulk Actions Toolbar */}
      <div className="flex items-center gap-2.5 flex-wrap">
        {/* Select All Checkbox */}
        <label className="flex items-center gap-2 cursor-pointer py-1 text-slate-700 hover:text-slate-900">
          <input
            type="checkbox"
            checked={isAllSelected}
            ref={(el) => {
              if (el) el.indeterminate = isSomeSelected && !isAllSelected;
            }}
            onChange={onToggleSelectAll}
            className="w-4 h-4 rounded text-indigo-600 border-slate-300 focus:ring-indigo-500 accent-indigo-600 cursor-pointer"
            aria-label="Select all visible emails"
          />
          <span className="text-xs font-medium">
            {hasSelection ? (
              <span className="font-semibold text-indigo-600">
                Selected {selectedCount} of {totalVisibleCount}
              </span>
            ) : (
              "Select All"
            )}
          </span>
        </label>

        <div className="h-4 w-px bg-slate-200 mx-1 hidden sm:block" />

        {/* Action Icon Buttons */}
        <div className="flex items-center gap-1 text-slate-500">
          {isTrash ? (
            <>
              <button
                type="button"
                disabled={!hasSelection || isRestoring}
                onClick={onRestore}
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold bg-indigo-50 border border-indigo-200 text-indigo-700 hover:bg-indigo-100 hover:text-indigo-800 transition-all disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer shadow-2xs mr-1"
                title={hasSelection ? `Restore ${selectedCount} selected email(s) to Inbox` : "Select emails to restore"}
                aria-label="Restore selected emails"
              >
                {isRestoring ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RotateCcw className="h-3.5 w-3.5" />
                )}
                <span>Restore{selectedCount > 0 ? ` (${selectedCount})` : ""}</span>
              </button>

              <button
                type="button"
                disabled={!hasSelection}
                onClick={onBulkStar}
                className={`p-1.5 rounded-md hover:bg-slate-100 transition-colors disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-slate-500 cursor-pointer disabled:cursor-not-allowed ${
                  isAllSelectedStarred ? "text-amber-500 hover:text-amber-600" : "text-slate-500 hover:text-amber-500"
                }`}
                title={isAllSelectedStarred ? "Unstar selected" : "Star selected"}
                aria-label={isAllSelectedStarred ? "Unstar selected emails" : "Star selected emails"}
              >
                <Star className="h-4 w-4" fill={isAllSelectedStarred ? "currentColor" : "none"} />
              </button>

              <button
                type="button"
                disabled={!hasSelection}
                onClick={() => onBulkMarkRead(true)}
                className="p-1.5 rounded-md hover:text-indigo-600 hover:bg-slate-100 transition-colors disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-slate-500 cursor-pointer disabled:cursor-not-allowed"
                title="Mark as Read"
                aria-label="Mark selected emails as read"
              >
                <MailOpen className="h-4 w-4" />
              </button>

              <button
                type="button"
                disabled={!hasSelection}
                onClick={() => onBulkMarkRead(false)}
                className="p-1.5 rounded-md hover:text-indigo-600 hover:bg-slate-100 transition-colors disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-slate-500 cursor-pointer disabled:cursor-not-allowed"
                title="Mark as Unread"
                aria-label="Mark selected emails as unread"
              >
                <Mail className="h-4 w-4" />
              </button>

              <button
                type="button"
                disabled={!hasSelection || isPermanentDeleting}
                onClick={onBulkPermanentDelete}
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold bg-rose-50 border border-rose-200 text-rose-700 hover:bg-rose-100 hover:text-rose-800 transition-all disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer shadow-2xs ml-1"
                title={hasSelection ? `Permanently delete ${selectedCount} selected email(s)` : "Select emails to permanently delete"}
                aria-label="Permanently delete selected emails"
              >
                {isPermanentDeleting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Trash2 className="h-3.5 w-3.5" />
                )}
                <span>Delete Permanently{selectedCount > 0 ? ` (${selectedCount})` : ""}</span>
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                disabled={!hasSelection}
                onClick={onBulkStar}
                className={`p-1.5 rounded-md hover:bg-slate-100 transition-colors disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-slate-500 cursor-pointer disabled:cursor-not-allowed ${
                  isAllSelectedStarred ? "text-amber-500 hover:text-amber-600" : "text-slate-500 hover:text-amber-500"
                }`}
                title={isAllSelectedStarred ? "Unstar selected" : "Star selected"}
                aria-label={isAllSelectedStarred ? "Unstar selected emails" : "Star selected emails"}
              >
                <Star className="h-4 w-4" fill={isAllSelectedStarred ? "currentColor" : "none"} />
              </button>

              <button
                type="button"
                disabled={!hasSelection}
                onClick={() => onBulkMarkRead(true)}
                className="p-1.5 rounded-md hover:text-indigo-600 hover:bg-slate-100 transition-colors disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-slate-500 cursor-pointer disabled:cursor-not-allowed"
                title="Mark as Read"
                aria-label="Mark selected emails as read"
              >
                <MailOpen className="h-4 w-4" />
              </button>

              <button
                type="button"
                disabled={!hasSelection}
                onClick={() => onBulkMarkRead(false)}
                className="p-1.5 rounded-md hover:text-indigo-600 hover:bg-slate-100 transition-colors disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-slate-500 cursor-pointer disabled:cursor-not-allowed"
                title="Mark as Unread"
                aria-label="Mark selected emails as unread"
              >
                <Mail className="h-4 w-4" />
              </button>

              <button
                type="button"
                disabled={!hasSelection}
                onClick={onBulkMoveToTrash}
                className="p-1.5 rounded-md hover:text-rose-600 hover:bg-rose-50 transition-colors disabled:opacity-40 disabled:hover:bg-transparent disabled:hover:text-slate-500 cursor-pointer disabled:cursor-not-allowed"
                title="Move to Trash"
                aria-label="Move selected emails to trash"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Right: Account Filter, Sort, Local Search & Pagination Controls */}
      <div className="flex items-center gap-3 flex-wrap lg:flex-nowrap">
        {/* Account Filter Dropdown */}
        <div className="relative">
          <select
            value={selectedAccountId ?? ""}
            onChange={(e) => {
              const val = e.target.value;
              onAccountChange(val ? Number(val) : undefined);
            }}
            className="appearance-none bg-slate-50 border border-slate-200 text-slate-700 text-xs font-medium py-1.5 pl-3 pr-8 rounded-lg shadow-2xs hover:border-slate-300 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-600 focus:border-indigo-600 cursor-pointer transition-colors"
          >
            <option value="">All Accounts ({accounts.length} Connected)</option>
            {accounts.map((acc) => (
              <option key={acc.id} value={acc.id}>
                {acc.email_address} ({acc.provider})
              </option>
            ))}
          </select>
          <ChevronDown className="h-3.5 w-3.5 text-slate-400 absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
        </div>

        {/* Sort Dropdown */}
        {onSortChange && (
          <div className="relative">
            <select
              value={sortBy}
              onChange={(e) => onSortChange(e.target.value as "newest" | "oldest")}
              className="appearance-none bg-slate-50 border border-slate-200 text-slate-700 text-xs font-medium py-1.5 pl-3 pr-7 rounded-lg shadow-2xs hover:border-slate-300 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-600 focus:border-indigo-600 cursor-pointer transition-colors"
              aria-label="Sort order"
            >
              <option value="newest">Newest First</option>
              <option value="oldest">Oldest First</option>
            </select>
            <ChevronDown className="h-3.5 w-3.5 text-slate-400 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
        )}

        {/* Mailbox Search Input */}
        <div className="relative">
          <Search className="h-3.5 w-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={folderTitle ? `Search ${folderTitle.toLowerCase()}...` : "Search messages..."}
            className="w-44 lg:w-56 bg-slate-50 border border-slate-200 text-slate-800 placeholder-slate-400 rounded-lg pl-8 pr-3 py-1.5 text-xs focus:bg-white focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 outline-none transition-all"
          />
        </div>

        <div className="h-4 w-px bg-slate-200 hidden sm:block" />

        {/* Pagination Counter & Arrows */}
        <div className="flex items-center gap-2 text-xs text-slate-500 whitespace-nowrap">
          <span>
            Showing <strong className="text-slate-900 font-medium">{startItem}–{endItem}</strong> of{" "}
            <strong className="text-slate-900 font-medium">{totalCount.toLocaleString()}</strong>
          </span>

          <div className="flex items-center gap-1">
            <button
              type="button"
              disabled={!canGoPrev}
              onClick={() => onPageChange(currentPage - 1)}
              className="p-1 rounded-md border border-slate-200 shadow-2xs transition-colors disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-100 hover:text-slate-900"
              title="Previous page"
              aria-label="Previous page"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
            </button>

            <button
              type="button"
              disabled={!canGoNext}
              onClick={() => onPageChange(currentPage + 1)}
              className="p-1 rounded-md border border-slate-200 shadow-2xs transition-colors disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-100 hover:text-slate-900"
              title="Next page"
              aria-label="Next page"
            >
              <ChevronRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
