import React from "react";
import { SearchX, RotateCcw } from "lucide-react";
import { Button } from "../ui/Button";

interface CampaignSearchEmptyStateProps {
  onClearFilters: () => void;
}

export const CampaignSearchEmptyState: React.FC<CampaignSearchEmptyStateProps> = ({
  onClearFilters,
}) => {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-2xs p-12 sm:p-16 flex flex-col items-center justify-center text-center w-full">
      <div className="w-16 h-16 rounded-2xl bg-slate-100 flex items-center justify-center text-slate-400 mb-4">
        <SearchX className="h-7 w-7" />
      </div>
      <h3 className="text-base sm:text-lg font-bold text-slate-900 tracking-tight mb-1">
        No campaigns found
      </h3>
      <p className="text-xs sm:text-sm text-slate-500 max-w-sm mb-6 leading-relaxed">
        We couldn’t find any campaigns matching your query. Try changing your search keywords or resetting active filters.
      </p>
      <Button
        type="button"
        variant="secondary"
        size="md"
        onClick={onClearFilters}
        className="px-4 py-2 rounded-lg text-xs font-semibold flex items-center gap-2 border border-slate-200"
      >
        <RotateCcw className="h-3.5 w-3.5" />
        <span>Clear filters</span>
      </Button>
    </div>
  );
};
