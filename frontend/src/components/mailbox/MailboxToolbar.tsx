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
  onPageSizeChange?: (newPageSize: number) => void;
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
  onPageSizeChange,
}) => {
  const startItem = totalCount === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const endItem = Math.min(currentPage * pageSize, totalCount);
  const totalPages = Math.ceil(totalCount / pageSize) || 1;
  const canGoPrev = currentPage > 1;
  const canGoNext = currentPage < totalPages;

  const hasSelection = selectedCount > 0;

  return (
    <div className="flex items-center justify-between gap-2.5 sm:gap-3 px-4 sm:px-5 py-2.5 border-b border-slate-200/80 bg-white select-none flex-wrap md:flex-nowrap">
      {/* 1. Left: Selection & Conditional Bulk Actions */}
      <div className="flex items-center gap-2 shrink-0">
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
          <span className="text-xs font-medium whitespace-nowrap">
            {hasSelection ? (
              <span className="font-semibold text-indigo-600">
                {selectedCount} of {totalVisibleCount}
              </span>
            ) : (
              "Select All"
            )}
          </span>
        </label>

        {/* Conditional Bulk Actions - Only visible when 1 or more emails are selected */}
        {hasSelection && (
          <>
            <div className="h-4 w-px bg-slate-200 mx-0.5" />
            <div className="flex items-center gap-1 text-slate-500 animate-in fade-in duration-150">
              {isTrash ? (
                <>
                  <button
                    type="button"
                    disabled={isRestoring}
                    onClick={onRestore}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-indigo-50 border border-indigo-200 text-indigo-700 hover:bg-indigo-100 hover:text-indigo-800 transition-all cursor-pointer shadow-2xs"
                    title={`Restore ${selectedCount} selected email(s) to Inbox`}
                    aria-label="Restore selected emails"
                  >
                    {isRestoring ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <RotateCcw className="h-3.5 w-3.5" />
                    )}
                    <span className="hidden sm:inline">Restore</span>
                  </button>

                  <button
                    type="button"
                    onClick={onBulkStar}
                    className={`p-1.5 rounded-md hover:bg-slate-100 transition-colors cursor-pointer ${
                      isAllSelectedStarred ? "text-amber-500 hover:text-amber-600" : "text-slate-500 hover:text-amber-500"
                    }`}
                    title={isAllSelectedStarred ? "Unstar selected" : "Star selected"}
                    aria-label={isAllSelectedStarred ? "Unstar selected emails" : "Star selected emails"}
                  >
                    <Star className="h-4 w-4" fill={isAllSelectedStarred ? "currentColor" : "none"} />
                  </button>

                  <button
                    type="button"
                    onClick={() => onBulkMarkRead(true)}
                    className="p-1.5 rounded-md hover:text-indigo-600 hover:bg-slate-100 transition-colors cursor-pointer text-slate-500"
                    title="Mark as Read"
                    aria-label="Mark selected emails as read"
                  >
                    <MailOpen className="h-4 w-4" />
                  </button>

                  <button
                    type="button"
                    onClick={() => onBulkMarkRead(false)}
                    className="p-1.5 rounded-md hover:text-indigo-600 hover:bg-slate-100 transition-colors cursor-pointer text-slate-500"
                    title="Mark as Unread"
                    aria-label="Mark selected emails as unread"
                  >
                    <Mail className="h-4 w-4" />
                  </button>

                  <button
                    type="button"
                    disabled={isPermanentDeleting}
                    onClick={onBulkPermanentDelete}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-rose-50 border border-rose-200 text-rose-700 hover:bg-rose-100 hover:text-rose-800 transition-all cursor-pointer shadow-2xs ml-0.5"
                    title={`Permanently delete ${selectedCount} selected email(s)`}
                    aria-label="Permanently delete selected emails"
                  >
                    {isPermanentDeleting ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="h-3.5 w-3.5" />
                    )}
                    <span className="hidden sm:inline">Delete</span>
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={onBulkStar}
                    className={`p-1.5 rounded-md hover:bg-slate-100 transition-colors cursor-pointer ${
                      isAllSelectedStarred ? "text-amber-500 hover:text-amber-600" : "text-slate-500 hover:text-amber-500"
                    }`}
                    title={isAllSelectedStarred ? "Unstar selected" : "Star selected"}
                    aria-label={isAllSelectedStarred ? "Unstar selected emails" : "Star selected emails"}
                  >
                    <Star className="h-4 w-4" fill={isAllSelectedStarred ? "currentColor" : "none"} />
                  </button>

                  <button
                    type="button"
                    onClick={() => onBulkMarkRead(true)}
                    className="p-1.5 rounded-md hover:text-indigo-600 hover:bg-slate-100 transition-colors cursor-pointer text-slate-500"
                    title="Mark as Read"
                    aria-label="Mark selected emails as read"
                  >
                    <MailOpen className="h-4 w-4" />
                  </button>

                  <button
                    type="button"
                    onClick={() => onBulkMarkRead(false)}
                    className="p-1.5 rounded-md hover:text-indigo-600 hover:bg-slate-100 transition-colors cursor-pointer text-slate-500"
                    title="Mark as Unread"
                    aria-label="Mark selected emails as unread"
                  >
                    <Mail className="h-4 w-4" />
                  </button>

                  <button
                    type="button"
                    onClick={onBulkMoveToTrash}
                    className="p-1.5 rounded-md hover:text-rose-600 hover:bg-rose-50 transition-colors cursor-pointer text-slate-500"
                    title="Move to Trash"
                    aria-label="Move selected emails to trash"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </>
              )}
            </div>
          </>
        )}
      </div>

      {/* 2. Middle: Account Filter, Sort & Flexible Search */}
      <div className="flex items-center gap-2 flex-1 min-w-0">
        {/* Account Filter Dropdown */}
        <div className="relative shrink-0">
          <select
            value={selectedAccountId ?? ""}
            onChange={(e) => {
              const val = e.target.value;
              onAccountChange(val ? Number(val) : undefined);
            }}
            className="appearance-none bg-slate-50 border border-slate-200 text-slate-700 text-xs font-medium py-1.5 pl-2.5 pr-7 rounded-lg shadow-2xs hover:border-slate-300 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-600 focus:border-indigo-600 cursor-pointer transition-colors max-w-[150px] sm:max-w-[180px] truncate"
            aria-label="Filter by email account"
          >
            <option value="">All Accounts ({accounts.length})</option>
            {accounts.map((acc) => (
              <option key={acc.id} value={acc.id}>
                {acc.email_address} ({acc.provider})
              </option>
            ))}
          </select>
          <ChevronDown className="h-3.5 w-3.5 text-slate-400 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" />
        </div>

        {/* Sort Dropdown */}
        {onSortChange && (
          <div className="relative shrink-0">
            <select
              value={sortBy}
              onChange={(e) => onSortChange(e.target.value as "newest" | "oldest")}
              className="appearance-none bg-slate-50 border border-slate-200 text-slate-700 text-xs font-medium py-1.5 pl-2.5 pr-6 rounded-lg shadow-2xs hover:border-slate-300 focus:bg-white focus:outline-none focus:ring-1 focus:ring-indigo-600 focus:border-indigo-600 cursor-pointer transition-colors"
              aria-label="Sort order"
            >
              <option value="newest">Newest</option>
              <option value="oldest">Oldest</option>
            </select>
            <ChevronDown className="h-3 w-3 text-slate-400 absolute right-1.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
        )}

        {/* Flexible Search Input */}
        <div className="relative flex-1 min-w-[110px] max-w-xs">
          <Search className="h-3.5 w-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={folderTitle ? `Search ${folderTitle.toLowerCase()}...` : "Search messages..."}
            className="w-full bg-slate-50 border border-slate-200 text-slate-800 placeholder-slate-400 rounded-lg pl-8 pr-2.5 py-1.5 text-xs focus:bg-white focus:border-indigo-600 focus:ring-1 focus:ring-indigo-600 outline-none transition-all"
          />
        </div>
      </div>

      {/* 3. Right: Rows per page, Range Counter & Compact Previous/Next Controls */}
      <div className="flex items-center gap-2 sm:gap-2.5 shrink-0 text-xs text-slate-500 whitespace-nowrap">
        {/* Rows per page selector */}
        {onPageSizeChange && (
          <div className="flex items-center gap-1.5">
            <span className="hidden sm:inline text-slate-400">Per page:</span>
            <select
              id="mailbox-page-size-select"
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="bg-slate-50 border border-slate-200 text-slate-700 font-medium rounded-md px-1.5 py-1 text-xs focus:bg-white focus:border-indigo-600 focus:outline-none cursor-pointer shadow-2xs"
              aria-label="Emails per page"
            >
              {[25, 50, 100, 200].map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="h-4 w-px bg-slate-200 hidden sm:block" />

        {/* Range display */}
        <span>
          <strong className="text-slate-900 font-medium">{startItem}–{endItem}</strong> of{" "}
          <strong className="text-slate-900 font-medium">{totalCount.toLocaleString()}</strong>
        </span>

        {/* Compact Gmail-style < > icon navigation */}
        <div className="flex items-center gap-0.5 ml-1">
          <button
            type="button"
            disabled={!canGoPrev}
            onClick={() => onPageChange(currentPage - 1)}
            className="p-1.5 rounded-md text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-slate-600 cursor-pointer"
            title={canGoPrev ? "Previous page" : "First page"}
            aria-label="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>

          <button
            type="button"
            disabled={!canGoNext}
            onClick={() => onPageChange(currentPage + 1)}
            className="p-1.5 rounded-md text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent disabled:hover:text-slate-600 cursor-pointer"
            title={canGoNext ? "Next page" : "Last page"}
            aria-label="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
