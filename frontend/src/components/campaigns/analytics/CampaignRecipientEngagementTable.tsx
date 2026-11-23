import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Eye,
  MousePointer,
  Bot,
  UserCheck,
  HelpCircle,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  Info,
  AlertCircle,
  Users,
} from "lucide-react";
import { campaignsApi, RequestError } from "../../../services/api";
import { useWorkspace } from "../../../hooks/useWorkspace";
import type {
  CampaignRecipientEngagementResponse,
  CampaignRecipientEngagementItem,
} from "../../../types/campaign";

interface CampaignRecipientEngagementTableProps {
  campaignId: number;
  stepNumber?: number | null;
  initialEventType?: "OPEN" | "CLICK";
  eventType?: "OPEN" | "CLICK";
  onEventTypeChange?: (eventType: "OPEN" | "CLICK") => void;
}

function formatTimestamp(isoStr?: string | null): string {
  if (!isoStr) return "—";
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return isoStr;
  }
}

export const CampaignRecipientEngagementTable: React.FC<CampaignRecipientEngagementTableProps> = ({
  campaignId,
  stepNumber = null,
  initialEventType = "OPEN",
  eventType: controlledEventType,
  onEventTypeChange,
}) => {
  const { currentCompanyId } = useWorkspace();
  const [internalEventType, setInternalEventType] = useState<"OPEN" | "CLICK">(initialEventType);
  const eventType = controlledEventType ?? internalEventType;
  const [page, setPage] = useState<number>(1);
  const pageSize = 10;

  // Reset page when scope or event type changes
  React.useEffect(() => {
    setPage(1);
  }, [stepNumber, eventType]);

  // React Query fetching with pagination and step-level scope
  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery<CampaignRecipientEngagementResponse, Error>({
    queryKey: [
      "campaignRecipientEngagement",
      currentCompanyId,
      campaignId,
      eventType,
      stepNumber,
      page,
      pageSize,
    ],
    queryFn: () => {
      if (!currentCompanyId || !campaignId) {
        throw new Error("Missing company or campaign context");
      }
      return campaignsApi.getCampaignRecipientEngagement(currentCompanyId, campaignId, {
        event_type: eventType,
        step_number: stepNumber,
        limit: pageSize,
        offset: (page - 1) * pageSize,
      });
    },
    enabled: Boolean(currentCompanyId && campaignId),
  });

  const handleEventTypeChange = (newType: "OPEN" | "CLICK") => {
    if (newType !== eventType) {
      if (onEventTypeChange) {
        onEventTypeChange(newType);
      } else {
        setInternalEventType(newType);
      }
      setPage(1);
    }
  };

  const totalItems = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  const items = data?.items ?? [];

  return (
    <div
      className="bg-white rounded-xl border border-slate-200/90 shadow-2xs space-y-4 p-4 sm:p-5"
      data-testid="campaign-recipient-drilldown"
    >
      {/* Header with Type Selector and Refresh */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
              <Users className="h-3.5 w-3.5" />
            </div>
            <h3 className="text-sm font-bold text-slate-900">
              Recipient Engagement Drilldown <span className="sr-only">Recipient Engagement</span>
            </h3>
            {stepNumber !== null && (
              <span
                data-testid="drilldown-scope-indicator"
                className="text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200/80 px-2 py-0.5 rounded-full"
              >
                Step {stepNumber} Scoped
              </span>
            )}
          </div>
          <p className="text-[11px] text-slate-500 mt-0.5">
            {stepNumber !== null
              ? `Filtered to recipients recording ${eventType.toLowerCase()} events for Step ${stepNumber}.`
              : `Recipients recording ${eventType.toLowerCase()} events across all campaign emails.`}
          </p>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto">
          {/* Segmented Switch */}
          <div
            className="inline-flex rounded-lg p-1 bg-slate-100 border border-slate-200"
            role="tablist"
            aria-label="Engagement Type"
          >
            <button
              type="button"
              role="tab"
              aria-selected={eventType === "OPEN"}
              onClick={() => handleEventTypeChange("OPEN")}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold transition-all cursor-pointer ${
                eventType === "OPEN"
                  ? "bg-white text-indigo-700 shadow-2xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
              data-testid="tab-opens"
            >
              <Eye className="h-3.5 w-3.5" />
              <span>Opened Recipients</span>
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={eventType === "CLICK"}
              onClick={() => handleEventTypeChange("CLICK")}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-semibold transition-all cursor-pointer ${
                eventType === "CLICK"
                  ? "bg-white text-indigo-700 shadow-2xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
              data-testid="tab-clicks"
            >
              <MousePointer className="h-3.5 w-3.5" />
              <span>Clicked Recipients</span>
            </button>
          </div>

          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-1.5 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-colors disabled:opacity-50 cursor-pointer"
            title="Refresh engagement drilldown"
            data-testid="refresh-drilldown"
          >
            <RefreshCw className={`h-4 w-4 ${isFetching ? "animate-spin text-indigo-600" : ""}`} />
          </button>
        </div>
      </div>

      {/* Classification Disclaimer Banner */}
      <div className="p-3 bg-slate-50 border border-slate-200/80 rounded-lg flex items-start gap-2.5 text-xs text-slate-600">
        <Info className="h-4 w-4 text-indigo-600 shrink-0 mt-0.5" />
        <div className="text-[11px] leading-relaxed">
          <span>
            <strong>PII & Classification Notice:</strong> Recipient email addresses are masked to safeguard privacy. Non-bot classifications indicate no automated link scanners or known proxies were detected; <strong>non-bot activity does not guarantee verified human interaction.</strong>
          </span>
        </div>
      </div>

      {/* Loading State */}
      {isLoading && (
        <div className="py-12 flex flex-col items-center justify-center text-center space-y-3" data-testid="drilldown-loading">
          <RefreshCw className="h-6 w-6 text-indigo-600 animate-spin" />
          <p className="text-xs font-semibold text-slate-700">Loading recipient engagement...</p>
        </div>
      )}

      {/* Error State */}
      {!isLoading && isError && (
        <div
          className="p-6 rounded-xl border border-rose-200 bg-rose-50/50 text-center space-y-2"
          data-testid="drilldown-error"
        >
          <AlertCircle className="h-6 w-6 text-rose-500 mx-auto" />
          <p className="text-xs font-semibold text-rose-900">Failed to load recipient drilldown</p>
          <p className="text-[11px] text-rose-700">
            {error instanceof RequestError ? String(error.detail || error.message) : error.message}
          </p>
          <button
            type="button"
            onClick={() => refetch()}
            className="mt-2 inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-white border border-rose-200 text-xs font-semibold text-rose-700 hover:bg-rose-50 transition-colors cursor-pointer"
          >
            <span>Retry</span>
          </button>
        </div>
      )}

      {/* Empty State (Compact & Visually Balanced) */}
      {!isLoading && !isError && items.length === 0 && (
        <div
          className="py-6 px-4 rounded-lg border border-dashed border-slate-200 text-center space-y-1.5 bg-slate-50/50"
          data-testid="drilldown-empty"
        >
          <div className="w-8 h-8 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mx-auto mb-1">
            {eventType === "OPEN" ? <Eye className="h-4 w-4" /> : <MousePointer className="h-4 w-4" />}
          </div>
          <p className="text-xs font-semibold text-slate-800">
            No {eventType === "OPEN" ? "opened" : "clicked"} recipients recorded{stepNumber ? ` for Step ${stepNumber}` : ""}
          </p>
          <p className="text-[11px] text-slate-500 max-w-sm mx-auto leading-relaxed">
            {stepNumber
              ? `No recipients have recorded ${eventType.toLowerCase()} events for Step ${stepNumber} yet.`
              : `Interaction events will appear here as recipients engage with this campaign and telemetry synchronizes.`}
          </p>
        </div>
      )}

      {/* Recipient Table */}
      {!isLoading && !isError && items.length > 0 && (
        <>
          <div className="overflow-x-auto [scrollbar-width:thin]">
            <table className="w-full text-left text-xs" data-testid="drilldown-table">
              <thead>
                <tr className="border-b border-slate-200 text-[11px] text-slate-400 uppercase font-semibold bg-slate-50/50">
                  <th className="py-2.5 px-3">Recipient (Masked)</th>
                  <th className="py-2.5 px-3 text-center">Total Events</th>
                  <th className="py-2.5 px-3 text-center">Non-Bot</th>
                  <th className="py-2.5 px-3 text-center">Bot</th>
                  <th className="py-2.5 px-3 text-center">Unknown</th>
                  <th className="py-2.5 px-3">First Recorded</th>
                  <th className="py-2.5 px-3">Most Recent</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {items.map((item: CampaignRecipientEngagementItem) => (
                  <tr
                    key={item.recipient_id}
                    className="hover:bg-slate-50/70 transition-colors"
                    data-testid={`drilldown-row-${item.recipient_id}`}
                  >
                    {/* Masked Email */}
                    <td className="py-3 px-3 font-mono text-[11px] font-semibold text-slate-900">
                      {item.masked_email || `Recipient #${item.recipient_id}`}
                    </td>

                    {/* Total Events */}
                    <td className="py-3 px-3 text-center font-bold text-slate-900">
                      {item.total_events_count}
                    </td>

                    {/* Non-Bot Count */}
                    <td className="py-3 px-3 text-center">
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200/70">
                        <UserCheck className="h-3 w-3 text-emerald-600" />
                        <span>{item.non_bot_events_count}</span>
                      </span>
                    </td>

                    {/* Bot Count */}
                    <td className="py-3 px-3 text-center">
                      {item.bot_events_count > 0 ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200/70">
                          <Bot className="h-3 w-3 text-rose-600" />
                          <span>{item.bot_events_count}</span>
                        </span>
                      ) : (
                        <span className="text-slate-400 font-medium">0</span>
                      )}
                    </td>

                    {/* Unknown Count */}
                    <td className="py-3 px-3 text-center">
                      {item.unknown_events_count > 0 ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-600 border border-slate-200">
                          <HelpCircle className="h-3 w-3 text-slate-400" />
                          <span>{item.unknown_events_count}</span>
                        </span>
                      ) : (
                        <span className="text-slate-400 font-medium">0</span>
                      )}
                    </td>

                    {/* First Event Timestamp */}
                    <td className="py-3 px-3 text-slate-500 whitespace-nowrap text-[11px]">
                      {formatTimestamp(item.first_event_at)}
                    </td>

                    {/* Last Event Timestamp */}
                    <td className="py-3 px-3 text-slate-900 font-medium whitespace-nowrap text-[11px]">
                      {formatTimestamp(item.last_event_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-3 border-t border-slate-100 text-xs text-slate-600">
            <div>
              <span>
                Showing <strong>{((page - 1) * pageSize) + 1}</strong> to{" "}
                <strong>{Math.min(page * pageSize, totalItems)}</strong> of{" "}
                <strong>{totalItems}</strong> unique recipients
              </span>
            </div>

            <div className="flex items-center gap-1.5 self-end sm:self-auto">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || isFetching}
                className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
                aria-label="Previous Page"
                data-testid="drilldown-prev-page"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>

              <span className="px-2.5 py-1 rounded-md bg-slate-50 border border-slate-200 font-medium text-slate-700">
                Page {page} of {totalPages}
              </span>

              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages || isFetching}
                className="p-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
                aria-label="Next Page"
                data-testid="drilldown-next-page"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
