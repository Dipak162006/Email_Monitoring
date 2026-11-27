import React from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, ArrowLeft, Users, Sparkles } from "lucide-react";
import { useWorkspace } from "../hooks/useWorkspace";
import { recipientListsApi } from "../services/api";
import { Button } from "../components/ui/Button";

export const RecipientListPlaceholderPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const listId = Number(id);
  const { currentCompanyId } = useWorkspace();

  const { data: list, isLoading } = useQuery({
    queryKey: ["recipientList", currentCompanyId, listId],
    queryFn: () => {
      if (!currentCompanyId || isNaN(listId)) return null;
      return recipientListsApi.getRecipientList(currentCompanyId, listId);
    },
    enabled: Boolean(currentCompanyId && !isNaN(listId)),
  });

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-xs text-slate-500">
        <Link
          to="/recipient-lists"
          className="hover:text-slate-800 transition-colors inline-flex items-center gap-1"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Recipient Lists
        </Link>
        <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
        <span className="font-semibold text-slate-900 truncate">
          {isLoading ? "Loading list..." : list?.name || `List #${id}`}
        </span>
      </nav>

      {/* Header Banner */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
            <Users className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-slate-900">
                {list?.name || "Recipient List"}
              </h1>
              {list && (
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 font-medium border border-slate-200">
                  {list.recipient_count} contacts
                </span>
              )}
            </div>
            {list?.description && (
              <p className="text-xs text-slate-500 mt-1">{list.description}</p>
            )}
          </div>
        </div>

        <Link to="/recipient-lists">
          <Button variant="outline" className="text-xs font-semibold px-4 py-2 rounded-xl">
            Back to Recipient Lists
          </Button>
        </Link>
      </div>

      {/* Scope Notice Card */}
      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-8 text-center max-w-2xl mx-auto my-12 space-y-4">
        <div className="w-12 h-12 rounded-2xl bg-indigo-100 text-indigo-600 flex items-center justify-center mx-auto">
          <Sparkles className="w-6 h-6" />
        </div>
        <div className="space-y-1.5">
          <h3 className="text-base font-bold text-slate-900">
            Milestone R3: Recipient Contact Management
          </h3>
          <p className="text-xs text-slate-600 leading-relaxed max-w-lg mx-auto">
            Direct member management, CSV batch importing, manual additions, and contact-level editing for this list will be activated in Milestone R3.
          </p>
        </div>
        <div className="pt-2">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-semibold border border-emerald-200">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            List foundation and metadata active
          </span>
        </div>
      </div>
    </div>
  );
};
