import React from "react";
import { Search, X } from "lucide-react";

interface RecipientToolbarProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  statusFilter: string;
  onStatusFilterChange: (status: string) => void;
  totalFilteredCount: number;
  totalLoadedCount: number;
  onClearFilters: () => void;
  hasActiveFilters: boolean;
}

export const RecipientToolbar: React.FC<RecipientToolbarProps> = ({
  searchQuery,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
  totalFilteredCount,
  totalLoadedCount,
  onClearFilters,
  hasActiveFilters,
}) => {
  return (
    <div className="w-full bg-white p-3 sm:p-4 rounded-xl border border-slate-200/80 shadow-2xs flex flex-col md:flex-row md:items-center justify-between gap-3 min-w-0">
      <div className="flex flex-1 flex-col sm:flex-row sm:items-center gap-3 min-w-0">
        {/* Search Field */}
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search recipients by email..."
            className="w-full pl-9 pr-8 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs sm:text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:bg-white focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => onSearchChange("")}
              className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600 transition-colors"
              title="Clear search"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Status Filter Dropdown */}
        <div className="relative shrink-0">
          <select
            value={statusFilter}
            onChange={(e) => onStatusFilterChange(e.target.value)}
            className="w-full sm:w-auto px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-xs sm:text-sm text-slate-700 font-medium focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all cursor-pointer"
          >
            <option value="ALL">All Statuses</option>
            <option value="PENDING">Pending Launch</option>
            <option value="SENT">Sent</option>
            <option value="FAILED">Failed</option>
            <option value="BOUNCED">Bounced</option>
            <option value="SUPPRESSED">Suppressed</option>
          </select>
        </div>
      </div>

      {/* Results stats & reset action */}
      <div className="flex items-center justify-between sm:justify-end gap-3 shrink-0 pt-2 md:pt-0">
        <span className="text-xs text-slate-500">
          Showing {totalFilteredCount} of {totalLoadedCount} records
        </span>
        {hasActiveFilters && (
          <button
            type="button"
            onClick={onClearFilters}
            className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 transition-colors"
          >
            Clear filters
          </button>
        )}
      </div>
    </div>
  );
};
