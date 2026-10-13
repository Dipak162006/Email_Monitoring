import React from "react";
import { SlidersHorizontal, Plus } from "lucide-react";
import { Button } from "../ui/Button";

interface CampaignPageHeaderProps {
  totalCount: number;
  showViewOptions?: boolean;
  onToggleViewOptions?: () => void;
  onCreateCampaign: () => void;
  isCreating?: boolean;
}

export const CampaignPageHeader: React.FC<CampaignPageHeaderProps> = ({
  totalCount,
  showViewOptions = false,
  onToggleViewOptions,
  onCreateCampaign,
  isCreating = false,
}) => {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 w-full">
      {/* Title & Total Count */}
      <div className="flex flex-col min-w-0">
        <div className="flex items-center gap-2.5 flex-wrap">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Campaigns</h1>
          <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200/50 shadow-2xs">
            {totalCount} total
          </span>
        </div>
        <p className="text-xs sm:text-sm text-slate-500 mt-1 leading-normal">
          Create, schedule, and manage your automated outreach pipelines.
        </p>
      </div>

      {/* Action Controls */}
      <div className="flex items-center gap-2.5 shrink-0 flex-wrap sm:flex-nowrap">
        {onToggleViewOptions && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onToggleViewOptions}
            className={`h-9 px-3.5 text-xs text-slate-700 hover:text-slate-900 flex items-center gap-1.5 ${
              showViewOptions ? "bg-slate-100 border-slate-300" : ""
            }`}
            title="Toggle summary KPI cards"
          >
            <SlidersHorizontal className="h-4 w-4 text-slate-500" />
            <span>View Options</span>
          </Button>
        )}

        <Button
          type="button"
          variant="primary"
          size="sm"
          onClick={onCreateCampaign}
          isLoading={isCreating}
          className="h-9 px-4 text-xs font-semibold flex items-center gap-1.5 shadow-sm"
        >
          <Plus className="h-4 w-4" />
          <span>Create Campaign</span>
        </Button>
      </div>
    </div>
  );
};
