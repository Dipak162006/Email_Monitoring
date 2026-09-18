import React from "react";
import { Link } from "react-router-dom";
import { RefreshCw, Plus } from "lucide-react";
import type { MailboxCounts } from "../../services/api";

interface MailboxHeaderProps {
  folderTitle: string;
  totalCount: number;
  mailboxCounts?: MailboxCounts;
  isSyncing: boolean;
  onSync: () => void;
  onFilterChange: (filter: { unread?: boolean; folder?: string }) => void;
  activeUnreadFilter?: boolean;
}

export const MailboxHeader: React.FC<MailboxHeaderProps> = ({
  folderTitle,
  totalCount,
  mailboxCounts,
  isSyncing,
  onSync,
  onFilterChange,
  activeUnreadFilter,
}) => {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      {/* Title, Badges & Quick Indicator Pills */}
      <div className="flex flex-col space-y-1">
        <div className="flex items-center gap-3 flex-wrap">
          <h1 className="text-xl sm:text-2xl font-semibold text-slate-900 tracking-tight">
            {folderTitle}
          </h1>

          {/* Dynamic Total Count Badge */}
          {totalCount > 0 && (
            <span className="px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 text-xs font-semibold border border-indigo-200/60">
              {totalCount.toLocaleString()}
            </span>
          )}

          {/* Live Ingestion Indicator */}
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-xs font-medium border border-emerald-200/60">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            Live Ingestion
          </span>

          {/* Compact Telemetry Quick Indicator Pills */}
          <div className="flex items-center gap-1.5 ml-0 sm:ml-2 flex-wrap">
            <button
              type="button"
              onClick={() => onFilterChange({ unread: !activeUnreadFilter })}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border shadow-2xs transition-colors cursor-pointer ${
                activeUnreadFilter
                  ? "bg-indigo-50 text-indigo-700 border-indigo-300"
                  : "bg-white hover:bg-slate-50 text-slate-700 border-slate-200"
              }`}
              title="Toggle unread filter"
            >
              <span className="w-2 h-2 rounded-full bg-indigo-600" />
              <span>Unread</span>
              {mailboxCounts && (
                <span className="font-semibold text-indigo-600 ml-0.5">
                  {mailboxCounts.inbox}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => onFilterChange({ folder: "responses" })}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 shadow-2xs transition-colors cursor-pointer"
              title="View responses"
            >
              <span className="w-2 h-2 rounded-full bg-sky-500" />
              <span>Responses</span>
              {mailboxCounts && mailboxCounts.responses > 0 && (
                <span className="font-semibold text-sky-700 ml-0.5">
                  {mailboxCounts.responses}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => onFilterChange({ folder: "bounced" })}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 shadow-2xs transition-colors cursor-pointer"
              title="View bounced messages"
            >
              <span className="w-2 h-2 rounded-full bg-rose-500" />
              <span>Bounced</span>
              {mailboxCounts && mailboxCounts.bounced > 0 && (
                <span className="font-semibold text-rose-600 ml-0.5">
                  {mailboxCounts.bounced}
                </span>
              )}
            </button>
          </div>
        </div>

        <p className="text-xs text-slate-500">
          Incoming dispatches and telemetry events across connected exchangers.
        </p>
      </div>

      {/* Right Header Actions: Refresh & Compose */}
      <div className="flex items-center gap-2.5 self-start sm:self-center">
        <button
          type="button"
          onClick={onSync}
          disabled={isSyncing}
          className="p-2 rounded-lg bg-white border border-slate-200 text-slate-600 hover:text-indigo-600 hover:bg-slate-50 text-xs font-medium shadow-2xs transition-colors flex items-center justify-center group disabled:opacity-50"
          title="Synchronize all IMAP / POP3 sockets"
          aria-label="Synchronize mailbox"
        >
          <RefreshCw
            className={`h-4 w-4 ${isSyncing ? "animate-spin text-indigo-600" : "group-hover:rotate-180 transition-transform duration-500"}`}
          />
        </button>

        <Link to="/compose">
          <button
            type="button"
            className="flex items-center gap-2 px-3.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-xs shadow-xs transition-all group"
          >
            <Plus className="h-4 w-4 transition-transform group-hover:rotate-90" />
            <span>Compose Email</span>
          </button>
        </Link>
      </div>
    </div>
  );
};
