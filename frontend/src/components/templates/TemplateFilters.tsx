import React from "react";
import { Search, ChevronDown } from "lucide-react";
import type { AuthorizedEmailAccount } from "../../types/emails";

export type StatusFilter = "all" | "active" | "inactive";

export interface TemplateFiltersProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  accountFilter: string;
  onAccountFilterChange: (account: string) => void;
  statusFilter: StatusFilter;
  onStatusFilterChange: (status: StatusFilter) => void;
  accounts: AuthorizedEmailAccount[];
  activeCount: number;
  inactiveCount: number;
}

export const TemplateFilters: React.FC<TemplateFiltersProps> = ({
  searchQuery,
  onSearchChange,
  accountFilter,
  onAccountFilterChange,
  statusFilter,
  onStatusFilterChange,
  accounts,
  activeCount,
  inactiveCount,
}) => {
  const searchInputRef = React.useRef<HTMLInputElement>(null);

  // Global Cmd+K / Ctrl+K shortcut to focus search input
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-3 shadow-xs flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3">
      {/* Search Input with ⌘K Badge */}
      <div className="relative flex-1 min-w-[240px]">
        <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400 pointer-events-none" />
        <input
          ref={searchInputRef}
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search templates by title or subject..."
          className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-9 pr-12 py-1.5 text-xs text-slate-900 placeholder:text-slate-400 focus:bg-white focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none transition-all"
        />
        <span className="absolute right-2.5 top-2 text-[10px] font-mono text-slate-400 border border-slate-200 bg-white px-1.5 py-0.5 rounded select-none pointer-events-none">
          ⌘K
        </span>
      </div>

      {/* Filter Select & Pills */}
      <div className="flex flex-wrap items-center gap-2">
        {/* Email Account Scope Select Filter */}
        <div className="relative">
          <select
            value={accountFilter}
            onChange={(e) => onAccountFilterChange(e.target.value)}
            className="appearance-none bg-slate-50 hover:bg-white border border-slate-200 text-slate-700 text-xs font-medium rounded-lg pl-3 pr-8 py-1.5 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none transition-all cursor-pointer"
          >
            <option value="all">All Accounts (Global & Specific)</option>
            <option value="global">Global (All Connected)</option>
            {accounts.map((acc) => (
              <option key={acc.id} value={String(acc.id)}>
                {acc.name ? `${acc.name} (${acc.email_address})` : acc.email_address}
              </option>
            ))}
          </select>
          <ChevronDown className="absolute right-2 top-2 h-4 w-4 text-slate-400 pointer-events-none" />
        </div>

        {/* Status Filter Pills */}
        <div className="inline-flex rounded-lg border border-slate-200 p-0.5 bg-slate-50 text-xs">
          <button
            type="button"
            onClick={() => onStatusFilterChange("all")}
            className={`px-3 py-1 rounded-md font-medium transition-all ${
              statusFilter === "all"
                ? "bg-white text-slate-900 shadow-xs font-semibold"
                : "text-slate-500 hover:text-slate-900"
            }`}
          >
            All
          </button>
          <button
            type="button"
            onClick={() => onStatusFilterChange("active")}
            className={`px-3 py-1 rounded-md font-medium transition-all ${
              statusFilter === "active"
                ? "bg-white text-slate-900 shadow-xs font-semibold"
                : "text-slate-500 hover:text-slate-900"
            }`}
          >
            Active ({activeCount})
          </button>
          <button
            type="button"
            onClick={() => onStatusFilterChange("inactive")}
            className={`px-3 py-1 rounded-md font-medium transition-all ${
              statusFilter === "inactive"
                ? "bg-white text-slate-900 shadow-xs font-semibold"
                : "text-slate-500 hover:text-slate-900"
            }`}
          >
            Inactive ({inactiveCount})
          </button>
        </div>
      </div>
    </div>
  );
};
