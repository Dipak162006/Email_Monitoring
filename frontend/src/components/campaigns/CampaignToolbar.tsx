import React from "react";
import { Search, X, RotateCcw, Mail, Filter } from "lucide-react";
import type { AuthorizedEmailAccount } from "../../types/emails";

interface CampaignToolbarProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  statusFilter: string;
  onStatusFilterChange: (status: string) => void;
  senderFilter: string;
  onSenderFilterChange: (senderId: string) => void;
  emailAccounts: AuthorizedEmailAccount[];
  onClearFilters: () => void;
  hasActiveFilters: boolean;
}

const CAMPAIGN_STATUSES: { label: string; value: string }[] = [
  { label: "All Statuses", value: "ALL" },
  { label: "DRAFT", value: "DRAFT" },
  { label: "SCHEDULED", value: "SCHEDULED" },
  { label: "QUEUED", value: "QUEUED" },
  { label: "RUNNING", value: "RUNNING" },
  { label: "PAUSED", value: "PAUSED" },
  { label: "COMPLETED", value: "COMPLETED" },
  { label: "CANCELLED", value: "CANCELLED" },
  { label: "FAILED", value: "FAILED" },
];

export const CampaignToolbar: React.FC<CampaignToolbarProps> = ({
  searchQuery,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
  senderFilter,
  onSenderFilterChange,
  emailAccounts,
  onClearFilters,
  hasActiveFilters,
}) => {
  return (
    <div className="bg-white p-3 rounded-xl border border-slate-200/80 shadow-2xs flex flex-wrap items-center justify-between gap-3 w-full">
      {/* Search Input */}
      <div className="relative w-full sm:w-72 md:w-80 flex items-center">
        <Search className="absolute left-3 h-4 w-4 text-slate-400 pointer-events-none" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Filter loaded campaigns..."
          aria-label="Filter loaded campaigns"
          title="Filter loaded campaigns on current page by name or subject"
          className="w-full h-9 pl-9 pr-8 rounded-lg bg-slate-50/70 hover:bg-slate-50 focus:bg-white border border-slate-200/80 text-slate-900 placeholder-slate-400 text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all shadow-2xs"
        />
        {searchQuery.length > 0 && (
          <button
            type="button"
            onClick={() => onSearchChange("")}
            title="Clear search"
            aria-label="Clear search"
            className="absolute right-2.5 p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition-colors"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>

      {/* Filter Controls */}
      <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
        {/* Status Filter */}
        <div className="relative flex items-center">
          <Filter className="absolute left-2.5 h-3.5 w-3.5 text-slate-400 pointer-events-none" />
          <select
            value={statusFilter}
            onChange={(e) => onStatusFilterChange(e.target.value)}
            aria-label="Filter by campaign status"
            className="h-9 pl-8 pr-7 rounded-lg bg-slate-50/70 hover:bg-slate-50 text-slate-800 text-xs font-medium border border-slate-200/80 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors cursor-pointer appearance-none shadow-2xs"
          >
            {CAMPAIGN_STATUSES.map((status) => (
              <option key={status.value} value={status.value}>
                {status.label}
              </option>
            ))}
          </select>
        </div>

        {/* Sender Filter */}
        <div className="relative flex items-center">
          <Mail className="absolute left-2.5 h-3.5 w-3.5 text-slate-400 pointer-events-none" />
          <select
            value={senderFilter}
            onChange={(e) => onSenderFilterChange(e.target.value)}
            aria-label="Filter by sender email account"
            className="h-9 pl-8 pr-7 rounded-lg bg-slate-50/70 hover:bg-slate-50 text-slate-800 text-xs font-medium border border-slate-200/80 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors cursor-pointer appearance-none max-w-[200px] truncate shadow-2xs"
          >
            <option value="ALL">All Senders</option>
            {emailAccounts.map((account) => (
              <option key={account.id} value={String(account.id)}>
                {account.name || account.email_address}
              </option>
            ))}
          </select>
        </div>

        {/* Clear Filters Action */}
        {hasActiveFilters && (
          <button
            type="button"
            onClick={onClearFilters}
            className="h-9 px-3 rounded-lg text-slate-500 hover:bg-slate-100/80 hover:text-slate-900 text-xs font-medium flex items-center gap-1.5 transition-colors border border-transparent hover:border-slate-200"
            title="Reset active filters"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span>Clear filters</span>
          </button>
        )}
      </div>
    </div>
  );
};
