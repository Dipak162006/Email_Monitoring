import React from "react";
import { Send, Plus } from "lucide-react";
import { Button } from "../ui/Button";

interface CampaignEmptyStateProps {
  onCreateCampaign: () => void;
}

export const CampaignEmptyState: React.FC<CampaignEmptyStateProps> = ({
  onCreateCampaign,
}) => {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-2xs p-12 sm:p-16 flex flex-col items-center justify-center text-center w-full">
      <div className="w-16 h-16 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 mb-4 shadow-2xs">
        <Send className="h-7 w-7" />
      </div>
      <h3 className="text-base sm:text-lg font-bold text-slate-900 tracking-tight mb-1">
        No campaigns yet
      </h3>
      <p className="text-xs sm:text-sm text-slate-500 max-w-md mb-6 leading-relaxed">
        Create your first campaign to start sending targeted emails, product updates, and automated sequences.
      </p>
      <Button
        type="button"
        variant="primary"
        size="md"
        onClick={onCreateCampaign}
        className="px-4 py-2 rounded-lg text-xs font-semibold flex items-center gap-2 shadow-sm"
      >
        <Plus className="h-4 w-4" />
        <span>Create Campaign</span>
      </Button>
    </div>
  );
};
