import React from "react";
import { ArrowLeft, ArrowRight, Save, Loader2, Users } from "lucide-react";

interface CampaignWizardFooterProps {
  currentStep: number;
  totalSteps?: number;
  onBack: () => void;
  onContinue: () => void;
  onSaveDraft: () => void;
  isSaving?: boolean;
  continueLabel?: string;
  isContinueDisabled?: boolean;
}

export const CampaignWizardFooter: React.FC<CampaignWizardFooterProps> = ({
  currentStep,
  onBack,
  onContinue,
  onSaveDraft,
  isSaving = false,
  continueLabel,
  isContinueDisabled = false,
}) => {
  const isFinalStep = currentStep === 4;

  const defaultContinueText = isFinalStep
    ? "Continue to Recipients"
    : "Continue";

  const buttonText = continueLabel || defaultContinueText;

  return (
    <footer className="pt-4 flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-slate-100">
      {/* Left: Back action */}
      <div className="w-full sm:w-auto">
        <button
          type="button"
          onClick={onBack}
          disabled={isSaving}
          className="w-full sm:w-auto px-4 py-2.5 rounded-lg text-xs sm:text-sm font-semibold transition-colors flex items-center justify-center gap-1.5 shadow-2xs bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 focus:outline-none focus:ring-2 focus:ring-slate-300 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>Back</span>
        </button>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-2.5 w-full sm:w-auto justify-end">
        <button
          type="button"
          onClick={onSaveDraft}
          disabled={isSaving}
          className="w-1/2 sm:w-auto px-4 py-2.5 rounded-lg bg-white hover:bg-slate-50 text-slate-700 font-semibold text-xs sm:text-sm border border-slate-200 shadow-2xs transition-colors flex items-center justify-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-slate-300 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {isSaving ? (
            <Loader2 className="h-4 w-4 animate-spin text-indigo-600" />
          ) : (
            <Save className="h-4 w-4 text-slate-500" />
          )}
          <span>{isSaving ? "Saving..." : "Save Draft"}</span>
        </button>

        <button
          type="button"
          onClick={onContinue}
          disabled={isSaving || isContinueDisabled}
          className="w-1/2 sm:w-auto px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs sm:text-sm shadow-sm transition-colors flex items-center justify-center gap-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          <span>{buttonText}</span>
          {isFinalStep ? (
            <Users className="h-4 w-4" />
          ) : (
            <ArrowRight className="h-4 w-4" />
          )}
        </button>
      </div>
    </footer>
  );
};
