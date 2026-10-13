import React from "react";
import { ArrowLeft } from "lucide-react";

interface CampaignWizardHeaderProps {
  currentStep: number;
  totalSteps?: number;
  onBackToCampaigns: () => void;
  title?: string;
  subtitle?: string;
}

export const CampaignWizardHeader: React.FC<CampaignWizardHeaderProps> = ({
  currentStep,
  totalSteps = 4,
  onBackToCampaigns,
  title = "Create Campaign",
  subtitle = "Create and prepare your outreach campaign.",
}) => {
  return (
    <header className="space-y-2 pb-0.5">
      <div className="flex items-center justify-between gap-4">
        <button
          type="button"
          onClick={onBackToCampaigns}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 -ml-2.5 rounded-lg text-xs sm:text-sm font-medium text-slate-600 hover:text-indigo-600 hover:bg-slate-100/70 transition-all group focus:outline-none focus:ring-2 focus:ring-indigo-500/20 cursor-pointer"
        >
          <ArrowLeft className="h-4 w-4 transition-transform group-hover:-translate-x-0.5 text-slate-400 group-hover:text-indigo-600" />
          <span>Back to Campaigns</span>
        </button>
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white border border-slate-200 text-slate-700 text-xs font-semibold shadow-2xs">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-600 animate-pulse" />
          <span>Step {currentStep} of {totalSteps}</span>
        </span>
      </div>
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
          {title}
        </h1>
        <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
          {subtitle}
        </p>
      </div>
    </header>
  );
};
