import React from "react";
import { Check } from "lucide-react";

export interface WizardStepDef {
  number: number;
  id: string;
  label: string;
  shortLabel: string;
}

export const WIZARD_STEPS: WizardStepDef[] = [
  { number: 1, id: "details", label: "Details", shortLabel: "Details" },
  { number: 2, id: "sender", label: "Sender", shortLabel: "Sender" },
  { number: 3, id: "content", label: "Content", shortLabel: "Content" },
  { number: 4, id: "review", label: "Review", shortLabel: "Review" },
];

interface CampaignWizardStepperProps {
  currentStep: number;
  onStepClick: (step: number) => void;
  canNavigateToStep?: (step: number) => boolean;
}

export const CampaignWizardStepper: React.FC<CampaignWizardStepperProps> = ({
  currentStep,
  onStepClick,
  canNavigateToStep = (step) => step <= currentStep,
}) => {
  // Progress line width calculation
  const progressPercent = ((currentStep - 1) / (WIZARD_STEPS.length - 1)) * 100;

  return (
    <nav
      aria-label="Campaign Creation Progress"
      className="bg-white rounded-xl border border-slate-200 px-4 py-3 sm:py-3.5 shadow-2xs"
    >
      <div className="grid grid-cols-4 gap-2 relative">
        {/* Connecting line background */}
        <div
          aria-hidden="true"
          className="hidden sm:block absolute top-4 left-8 right-8 h-0.5 bg-slate-100 -z-0"
        />
        {/* Dynamic progress bar fill */}
        <div
          aria-hidden="true"
          className="hidden sm:block absolute top-4 left-8 h-0.5 bg-indigo-600 -z-0 transition-all duration-300"
          style={{ width: `calc(${progressPercent}% * 0.82)` }}
        />

        {WIZARD_STEPS.map((step) => {
          const isCompleted = step.number < currentStep;
          const isActive = step.number === currentStep;
          const isAccessible = canNavigateToStep(step.number);

          return (
            <button
              key={step.id}
              type="button"
              onClick={() => isAccessible && onStepClick(step.number)}
              disabled={!isAccessible}
              className={`flex flex-col items-center sm:items-start text-center sm:text-left gap-1 z-10 group focus:outline-none ${
                isAccessible ? "cursor-pointer" : "cursor-not-allowed opacity-75"
              }`}
              aria-current={isActive ? "step" : undefined}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold transition-all ${
                    isCompleted
                      ? "bg-indigo-600 text-white shadow-2xs"
                      : isActive
                      ? "bg-indigo-600 text-white ring-4 ring-indigo-50 shadow-2xs"
                      : "bg-slate-100 text-slate-500 border border-slate-200"
                  }`}
                >
                  {isCompleted ? (
                    <Check className="h-4 w-4 stroke-[2.5]" />
                  ) : (
                    step.number
                  )}
                </span>

                <div className="hidden md:block">
                  <span
                    className={`text-[10px] uppercase tracking-wider font-semibold block ${
                      isActive
                        ? "text-indigo-600"
                        : isCompleted
                        ? "text-slate-500"
                        : "text-slate-400"
                    }`}
                  >
                    Step {step.number}
                  </span>
                  <span
                    className={`text-xs font-semibold ${
                      isActive
                        ? "text-slate-900"
                        : isCompleted
                        ? "text-slate-700"
                        : "text-slate-400"
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
              </div>

              <span
                className={`md:hidden text-[11px] font-semibold ${
                  isActive
                    ? "text-indigo-600"
                    : isCompleted
                    ? "text-slate-700"
                    : "text-slate-400"
                }`}
              >
                {step.shortLabel}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
