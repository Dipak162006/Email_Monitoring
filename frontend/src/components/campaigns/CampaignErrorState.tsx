import React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "../ui/Button";

interface CampaignErrorStateProps {
  message?: string;
  onRetry: () => void;
}

export const CampaignErrorState: React.FC<CampaignErrorStateProps> = ({
  message = "Something went wrong while communicating with the campaign service. Please try again.",
  onRetry,
}) => {
  return (
    <div className="p-5 sm:p-6 rounded-xl bg-rose-50/70 border border-rose-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 shadow-2xs w-full">
      <div className="flex items-start gap-3.5 min-w-0">
        <div className="w-10 h-10 rounded-xl bg-rose-100 text-rose-600 flex items-center justify-center shrink-0 mt-0.5">
          <AlertCircle className="h-5 w-5" />
        </div>
        <div className="flex flex-col min-w-0">
          <h4 className="text-sm font-bold text-rose-900">
            Unable to load campaigns
          </h4>
          <p className="text-xs text-rose-700 mt-0.5 leading-relaxed">
            {message}
          </p>
        </div>
      </div>

      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onRetry}
        className="px-3.5 py-2 rounded-lg bg-white hover:bg-slate-50 text-slate-800 text-xs font-semibold flex items-center gap-1.5 border border-rose-200 transition-colors shadow-2xs shrink-0"
      >
        <RefreshCw className="h-3.5 w-3.5" />
        <span>Try again</span>
      </Button>
    </div>
  );
};
