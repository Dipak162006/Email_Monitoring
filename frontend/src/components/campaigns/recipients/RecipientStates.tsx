import React from "react";
import { UserX, SearchX, AlertCircle, RefreshCw, Plus, UploadCloud } from "lucide-react";

export const RecipientSkeleton: React.FC = () => {
  return (
    <div className="w-full bg-white rounded-xl border border-slate-200/80 p-6 space-y-4 animate-pulse">
      <div className="h-5 bg-slate-200 rounded w-1/4"></div>
      <div className="space-y-3">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="h-12 bg-slate-100 rounded-lg w-full"></div>
        ))}
      </div>
    </div>
  );
};

interface RecipientEmptyAudienceProps {
  isEditable: boolean;
  onSelectTab: (tab: "manual" | "csv") => void;
}

export const RecipientEmptyAudience: React.FC<RecipientEmptyAudienceProps> = ({
  isEditable,
  onSelectTab,
}) => {
  return (
    <div className="w-full bg-white rounded-xl border border-slate-200/80 p-12 flex flex-col items-center justify-center text-center shadow-2xs">
      <div className="w-14 h-14 rounded-full bg-slate-100 text-slate-500 flex items-center justify-center mb-3">
        <UserX className="h-7 w-7" />
      </div>
      <h3 className="text-sm font-bold text-slate-900">No recipients in campaign audience</h3>
      <p className="text-xs text-slate-500 mt-1 max-w-sm leading-relaxed">
        This campaign audience list is currently empty. Add individual contacts or bulk-import a CSV to populate records.
      </p>

      {isEditable && (
        <div className="mt-5 flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => onSelectTab("csv")}
            className="px-3.5 py-2 rounded-lg bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 transition-colors shadow-2xs flex items-center gap-1.5"
          >
            <UploadCloud className="h-4 w-4" />
            <span>Import CSV</span>
          </button>
          <button
            type="button"
            onClick={() => onSelectTab("manual")}
            className="px-3.5 py-2 rounded-lg bg-slate-100 text-slate-700 text-xs font-medium hover:bg-slate-200 transition-colors flex items-center gap-1.5"
          >
            <Plus className="h-4 w-4" />
            <span>Add Manually</span>
          </button>
        </div>
      )}
    </div>
  );
};

interface RecipientSearchEmptyProps {
  onClearFilters: () => void;
}

export const RecipientSearchEmpty: React.FC<RecipientSearchEmptyProps> = ({
  onClearFilters,
}) => {
  return (
    <div className="w-full bg-white rounded-xl border border-slate-200/80 p-12 flex flex-col items-center justify-center text-center shadow-2xs">
      <div className="w-14 h-14 rounded-full bg-slate-100 text-slate-500 flex items-center justify-center mb-3">
        <SearchX className="h-7 w-7" />
      </div>
      <h3 className="text-sm font-bold text-slate-900">No matching audience records</h3>
      <p className="text-xs text-slate-500 mt-1 max-w-sm leading-relaxed">
        No recipients matched your search query or status filter. Try broadening your keywords or removing filters.
      </p>
      <button
        type="button"
        onClick={onClearFilters}
        className="mt-5 px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-indigo-600 text-xs font-semibold transition-colors"
      >
        Clear Search & Filters
      </button>
    </div>
  );
};

interface RecipientErrorStateProps {
  message?: string;
  onRetry: () => void;
}

export const RecipientErrorState: React.FC<RecipientErrorStateProps> = ({
  message = "Failed to load campaign recipients.",
  onRetry,
}) => {
  return (
    <div className="w-full bg-white rounded-xl border border-rose-200 p-10 flex flex-col items-center justify-center text-center shadow-2xs">
      <div className="w-14 h-14 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center mb-3">
        <AlertCircle className="h-7 w-7" />
      </div>
      <h3 className="text-sm font-bold text-slate-900">Unable to query recipient repository</h3>
      <p className="text-xs text-slate-500 mt-1 max-w-sm leading-relaxed">
        {message}
      </p>
      <button
        type="button"
        onClick={onRetry}
        className="mt-5 px-4 py-2 rounded-lg bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 transition-colors shadow-2xs flex items-center gap-1.5"
      >
        <RefreshCw className="h-3.5 w-3.5" />
        <span>Retry Query</span>
      </button>
    </div>
  );
};
