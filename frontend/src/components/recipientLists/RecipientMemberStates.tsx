import React from "react";
import { Users, SearchX, AlertCircle, RefreshCw, Plus, UploadCloud } from "lucide-react";
import { Button } from "../ui/Button";

export const RecipientMemberSkeleton: React.FC = () => {
  return (
    <div className="w-full bg-white rounded-2xl border border-slate-200 p-6 space-y-4 animate-pulse">
      <div className="h-6 bg-slate-200 rounded-lg w-1/4"></div>
      <div className="space-y-3">
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div key={i} className="h-12 bg-slate-100 rounded-xl w-full"></div>
        ))}
      </div>
    </div>
  );
};

interface RecipientMemberEmptyStateProps {
  onAddRecipient: () => void;
  onImportCsv: () => void;
}

export const RecipientMemberEmptyState: React.FC<RecipientMemberEmptyStateProps> = ({
  onAddRecipient,
  onImportCsv,
}) => {
  return (
    <div className="w-full bg-white rounded-2xl border border-slate-200 p-12 flex flex-col items-center justify-center text-center shadow-xs">
      <div className="w-14 h-14 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center mb-4">
        <Users className="h-7 w-7" />
      </div>
      <h3 className="text-base font-bold text-slate-900">No contacts in this list yet</h3>
      <p className="text-xs text-slate-500 mt-1.5 max-w-sm leading-relaxed">
        Start building your reusable contact audience by manually adding individual recipients or bulk importing a CSV file.
      </p>

      <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
        <Button
          type="button"
          onClick={onImportCsv}
          className="px-4 py-2 text-xs font-semibold rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 flex items-center gap-2 shadow-2xs"
        >
          <UploadCloud className="h-4 w-4 text-slate-500" />
          <span>Import CSV</span>
        </Button>
        <Button
          type="button"
          onClick={onAddRecipient}
          className="px-4 py-2 text-xs font-semibold rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white flex items-center gap-1.5 shadow-sm"
        >
          <Plus className="h-4 w-4" />
          <span>Add Contact</span>
        </Button>
      </div>
    </div>
  );
};

interface RecipientMemberSearchEmptyStateProps {
  searchTerm: string;
  onClearSearch: () => void;
}

export const RecipientMemberSearchEmptyState: React.FC<RecipientMemberSearchEmptyStateProps> = ({
  searchTerm,
  onClearSearch,
}) => {
  return (
    <div className="w-full bg-white rounded-2xl border border-slate-200 p-10 flex flex-col items-center justify-center text-center shadow-xs">
      <div className="w-12 h-12 rounded-2xl bg-slate-100 text-slate-400 flex items-center justify-center mb-3">
        <SearchX className="h-6 w-6" />
      </div>
      <h3 className="text-sm font-bold text-slate-900">No contacts found</h3>
      <p className="text-xs text-slate-500 mt-1 max-w-sm">
        No contacts match <span className="font-semibold text-slate-700 font-mono">"{searchTerm}"</span>. Try adjusting your search term.
      </p>
      <Button
        type="button"
        variant="outline"
        onClick={onClearSearch}
        className="mt-4 px-3.5 py-1.5 text-xs font-medium rounded-xl"
      >
        Clear Search
      </Button>
    </div>
  );
};

interface RecipientMemberErrorStateProps {
  error?: string | null;
  onRetry: () => void;
}

export const RecipientMemberErrorState: React.FC<RecipientMemberErrorStateProps> = ({
  error,
  onRetry,
}) => {
  return (
    <div className="w-full bg-white rounded-2xl border border-rose-200 p-8 flex flex-col items-center justify-center text-center shadow-xs">
      <div className="w-12 h-12 rounded-2xl bg-rose-50 text-rose-600 flex items-center justify-center mb-3">
        <AlertCircle className="h-6 w-6" />
      </div>
      <h3 className="text-sm font-bold text-slate-900">Failed to load contacts</h3>
      <p className="text-xs text-slate-500 mt-1 max-w-md">
        {error || "An unexpected error occurred while fetching contacts for this list."}
      </p>
      <Button
        type="button"
        onClick={onRetry}
        className="mt-4 px-4 py-2 text-xs font-semibold rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white flex items-center gap-1.5 shadow-sm"
      >
        <RefreshCw className="h-3.5 w-3.5" />
        <span>Retry</span>
      </Button>
    </div>
  );
};
