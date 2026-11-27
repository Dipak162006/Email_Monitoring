import React from "react";
import { Users, Search, AlertCircle, Plus } from "lucide-react";
import { Button } from "../ui/Button";

export const RecipientListSkeleton: React.FC = () => {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden divide-y divide-slate-100">
      <div className="h-11 bg-slate-50/80 px-4 flex items-center justify-between">
        <div className="w-24 h-3.5 bg-slate-200/70 rounded animate-pulse" />
        <div className="w-32 h-3.5 bg-slate-200/70 rounded animate-pulse hidden md:block" />
        <div className="w-20 h-3.5 bg-slate-200/70 rounded animate-pulse" />
        <div className="w-24 h-3.5 bg-slate-200/70 rounded animate-pulse hidden lg:block" />
        <div className="w-16 h-3.5 bg-slate-200/70 rounded animate-pulse" />
      </div>
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} className="px-4 py-3.5 flex items-center justify-between gap-4 animate-pulse">
          <div className="flex items-center gap-3 w-1/3">
            <div className="w-8 h-8 rounded-lg bg-slate-100 shrink-0" />
            <div className="space-y-1.5 flex-1 min-w-0">
              <div className="h-4 bg-slate-200/70 rounded w-3/4" />
              <div className="h-3 bg-slate-100 rounded w-1/2 md:hidden" />
            </div>
          </div>
          <div className="w-1/3 hidden md:block">
            <div className="h-3.5 bg-slate-100 rounded w-4/5" />
          </div>
          <div className="w-24">
            <div className="h-6 bg-slate-100 rounded-full w-20" />
          </div>
          <div className="w-24 hidden lg:block">
            <div className="h-3.5 bg-slate-100 rounded w-16" />
          </div>
          <div className="w-20 flex justify-end gap-1.5">
            <div className="h-7 bg-slate-100 rounded w-12" />
          </div>
        </div>
      ))}
    </div>
  );
};

interface RecipientListEmptyStateProps {
  onCreate: () => void;
}

export const RecipientListEmptyState: React.FC<RecipientListEmptyStateProps> = ({ onCreate }) => {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-xs p-12 text-center flex flex-col items-center justify-center max-w-xl mx-auto my-6">
      <div className="w-14 h-14 rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center mb-4">
        <Users className="w-7 h-7" />
      </div>
      <h3 className="text-base font-bold text-slate-900">No recipient lists yet.</h3>
      <p className="text-xs text-slate-500 mt-1.5 max-w-md leading-relaxed">
        Create reusable lists to organize contacts and easily use them in future campaigns.
      </p>
      <Button
        onClick={onCreate}
        className="mt-6 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold px-4 py-2.5 rounded-xl shadow-xs inline-flex items-center gap-1.5"
      >
        <Plus className="w-4 h-4" />
        Create your first list
      </Button>
    </div>
  );
};

interface RecipientListSearchEmptyStateProps {
  onClearSearch: () => void;
}

export const RecipientListSearchEmptyState: React.FC<RecipientListSearchEmptyStateProps> = ({
  onClearSearch,
}) => {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-xs p-12 text-center flex flex-col items-center justify-center max-w-lg mx-auto my-6">
      <div className="w-12 h-12 rounded-2xl bg-slate-100 text-slate-500 flex items-center justify-center mb-4">
        <Search className="w-6 h-6" />
      </div>
      <h3 className="text-base font-bold text-slate-900">No lists found.</h3>
      <p className="text-xs text-slate-500 mt-1 max-w-sm leading-relaxed">
        Try adjusting your search.
      </p>
      <Button
        variant="outline"
        onClick={onClearSearch}
        className="mt-5 text-xs font-semibold px-3.5 py-2 rounded-xl text-slate-700"
      >
        Clear search filter
      </Button>
    </div>
  );
};

interface RecipientListErrorStateProps {
  message?: string;
  onRetry: () => void;
}

export const RecipientListErrorState: React.FC<RecipientListErrorStateProps> = ({
  message = "Failed to load recipient lists. Please check your connection and try again.",
  onRetry,
}) => {
  return (
    <div className="bg-white rounded-xl border border-rose-200 shadow-xs p-8 text-center flex flex-col items-center justify-center max-w-lg mx-auto my-6">
      <div className="w-12 h-12 rounded-2xl bg-rose-50 text-rose-600 flex items-center justify-center mb-3">
        <AlertCircle className="w-6 h-6" />
      </div>
      <h3 className="text-base font-bold text-slate-900">Unable to load lists</h3>
      <p className="text-xs text-slate-500 mt-1 mb-5">{message}</p>
      <Button
        variant="outline"
        onClick={onRetry}
        className="text-xs font-semibold px-4 py-2 rounded-xl border-slate-200"
      >
        Retry
      </Button>
    </div>
  );
};
