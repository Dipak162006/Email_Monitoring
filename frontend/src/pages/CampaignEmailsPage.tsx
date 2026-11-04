import React, { useState, useEffect } from "react";

import { useParams, useSearchParams, Link } from "react-router-dom";

import { useQuery } from "@tanstack/react-query";

import {

  ArrowLeft,

  Users,

  Send,

  Reply,

  AlertTriangle,

  AlertCircle,

  Search,

  X,

  RefreshCw,

  Mail,

  ChevronLeft,

  ChevronRight,

  ExternalLink,

  ShieldCheck,

  ShieldAlert,

  Clock,

  MessageSquare,

} from "lucide-react";



import { useWorkspace } from "../hooks/useWorkspace";

import { campaignsApi } from "../services/api";

import type {

  CampaignEmailsDrilldownResponse,

  CampaignRecipientStatus,

} from "../types/campaign";

import { CampaignStatusBadge } from "../components/campaigns/CampaignStatusBadge";

import { RecipientStatusBadge } from "../components/campaigns/recipients/RecipientStatusBadge";



type DrilldownStatus = "recipients" | "sent" | "replies" | "bounced" | "failed";



export const CampaignEmailsPage: React.FC = () => {

  const { campaignId } = useParams<{ campaignId: string }>();

  const campaignIdNum = Number(campaignId);

  const [searchParams, setSearchParams] = useSearchParams();

  const { currentCompanyId } = useWorkspace();



  // Selected card status from URL or default to "recipients"

  const rawStatus = (searchParams.get("status") || "recipients").toLowerCase();

  const activeStatus: DrilldownStatus = [

    "recipients",

    "sent",

    "replies",

    "bounced",

    "failed",

  ].includes(rawStatus)

    ? (rawStatus as DrilldownStatus)

    : "recipients";



  // Search and Pagination

  const [searchQuery, setSearchQuery] = useState(searchParams.get("q") || "");

  const [debouncedSearch, setDebouncedSearch] = useState(searchQuery);

  const [currentPage, setCurrentPage] = useState(

    Number(searchParams.get("page")) || 1

  );

  const pageSize = 25;



  // Debounce search query

  useEffect(() => {

    const timer = setTimeout(() => {

      setDebouncedSearch(searchQuery);

      setCurrentPage(1);

    }, 300);

    return () => clearTimeout(timer);

  }, [searchQuery]);



  // Sync currentPage from URL search params when status or page changes

  useEffect(() => {

    const pageFromUrl = Number(searchParams.get("page")) || 1;

    setCurrentPage(pageFromUrl);

  }, [searchParams]);



  // Keep URL in sync
  const handleStatusChange = (newStatus: DrilldownStatus) => {
    setSearchParams({
      status: newStatus,
      ...(searchQuery ? { q: searchQuery } : {}),
      page: "1",
    });
    setCurrentPage(1);
  };

  const handlePageChange = (newPage: number) => {
    setCurrentPage(newPage);
    setSearchParams({
      status: activeStatus,
      ...(searchQuery ? { q: searchQuery } : {}),
      page: String(newPage),
    });
  };



  // Fetch drilldown data

  const {

    data: drilldownData,

    isLoading,

    isError,

    error,

    refetch,

    isFetching,

  } = useQuery<CampaignEmailsDrilldownResponse, Error>({

    queryKey: [

      "campaignEmailsDrilldown",

      currentCompanyId,

      campaignIdNum,

      activeStatus,

      debouncedSearch,

      currentPage,

      pageSize,

    ],

    queryFn: () => {

      if (!currentCompanyId || !campaignIdNum) {

        return Promise.reject(new Error("Missing context"));

      }

      return campaignsApi.getCampaignEmailsDrilldown(

        currentCompanyId,

        campaignIdNum,

        {

          status: activeStatus,

          search: debouncedSearch.trim() || undefined,

          limit: pageSize,

          offset: (currentPage - 1) * pageSize,

        }

      );

    },

    enabled: Boolean(currentCompanyId && campaignIdNum),

  });



  // Fetch campaign basic details for header badge

  const { data: campaign } = useQuery({

    queryKey: ["campaign", currentCompanyId, campaignIdNum],

    queryFn: () => {

      if (!currentCompanyId || !campaignIdNum) return null;

      return campaignsApi.getCampaign(currentCompanyId, campaignIdNum);

    },

    enabled: Boolean(currentCompanyId && campaignIdNum),

  });



  // Cache summary data so summary cards never drop to 0 if a subquery or list fails

  const [cachedSummary, setCachedSummary] = useState<CampaignEmailsDrilldownResponse["summary"] | null>(null);



  useEffect(() => {

    if (drilldownData?.summary) {

      setCachedSummary(drilldownData.summary);

    }

  }, [drilldownData?.summary]);



  const summary = drilldownData?.summary || cachedSummary || {

    recipients_count: campaign?.recipient_count ?? 0,

    sent_count: (campaign?.total_sent_count ?? campaign?.sent_count) ?? 0,

    replies_count: campaign?.replied_count ?? 0,

    bounced_count: campaign?.bounced_count ?? 0,

    failed_count: campaign?.failed_count ?? 0,

  };



  const isStatusMatching = drilldownData?.selected_status === activeStatus;
  const totalItems = isStatusMatching ? (drilldownData?.total || 0) : 0;
  const totalPages = Math.ceil(totalItems / pageSize) || 1;
  const items = isStatusMatching ? (drilldownData?.items || []) : [];



  const cards: Array<{

    key: DrilldownStatus;

    title: string;

    count: number;

    subtext: string;

    icon: React.ComponentType<{ className?: string }>;

    accentColor: string;

    activeBorder: string;

    activeBg: string;

  }> = [

    {

      key: "recipients",

      title: "Recipients",

      count: summary.recipients_count,

      subtext: "Total Audience",

      icon: Users,

      accentColor: "text-indigo-600",

      activeBorder: "border-indigo-600 ring-2 ring-indigo-500/20",

      activeBg: "bg-indigo-50/70",

    },

    {

      key: "sent",

      title: "Sent",

      count: summary.sent_count,

      subtext: "Delivered Emails",

      icon: Send,

      accentColor: "text-emerald-600",

      activeBorder: "border-emerald-600 ring-2 ring-emerald-500/20",

      activeBg: "bg-emerald-50/70",

    },

    {

      key: "replies",

      title: "Replies",

      count: summary.replies_count,

      subtext: "Inbound Responses",

      icon: Reply,

      accentColor: "text-indigo-600",

      activeBorder: "border-indigo-600 ring-2 ring-indigo-500/20",

      activeBg: "bg-indigo-50/70",

    },

    {

      key: "bounced",

      title: "Bounced",

      count: summary.bounced_count,

      subtext: "Undeliverable",

      icon: AlertTriangle,

      accentColor: "text-rose-600",

      activeBorder: "border-rose-600 ring-2 ring-rose-500/20",

      activeBg: "bg-rose-50/70",

    },

    {

      key: "failed",

      title: "Failed",

      count: summary.failed_count,

      subtext: "Dispatch Errors",

      icon: AlertCircle,

      accentColor: "text-amber-600",

      activeBorder: "border-amber-600 ring-2 ring-amber-500/20",

      activeBg: "bg-amber-50/70",

    },

  ];



  const formatTimestamp = (dateStr?: string | null) => {

    if (!dateStr) return "—";

    try {

      const d = new Date(dateStr);

      return d.toLocaleString(undefined, {

        month: "short",

        day: "numeric",

        year: "numeric",

        hour: "2-digit",

        minute: "2-digit",

      });

    } catch {

      return dateStr;

    }

  };



  return (

    <div className="w-full max-w-7xl mx-auto min-w-0 px-4 sm:px-6 lg:px-8 py-5 space-y-4 sm:space-y-5 box-border">

      {/* 1. Breadcrumbs Navigation */}

      <div className="flex items-center justify-between gap-4">

        <Link

          to={`/campaigns/${campaignId}`}

          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-indigo-600 transition-colors"

        >

          <ArrowLeft className="h-4 w-4" />

          <span>Back to Campaign Details</span>

        </Link>

        <button

          onClick={() => refetch()}

          disabled={isFetching}

          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors disabled:opacity-50"

          title="Refresh data"

        >

          <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin text-indigo-600" : ""}`} />

          <span className="hidden sm:inline">Refresh</span>

        </button>

      </div>



      {/* 2. Page Header */}

      <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs">

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">

          <div className="space-y-1">

            <div className="flex items-center gap-2 flex-wrap">

              <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">

                {campaign?.name || drilldownData?.campaign_name || "Campaign Emails"}

              </h1>

              {campaign?.status && <CampaignStatusBadge status={campaign.status} />}

            </div>

            <p className="text-xs text-slate-500">

              Drill down into recipient delivery logs, sent emails, inbound replies, bounces, and errors.

            </p>

          </div>

          <div className="text-xs text-slate-500 bg-slate-50 px-3 py-1.5 rounded-lg border border-slate-100 shrink-0">

            <span>Showing status: </span>

            <span className="font-semibold text-slate-800 uppercase tracking-wider">

              {activeStatus}

            </span>

          </div>

        </div>

      </div>



      {/* 3. Five Clickable Status Summary Cards */}

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-3.5">

        {cards.map((card) => {

          const Icon = card.icon;

          const isSelected = activeStatus === card.key;

          return (

            <button

              key={card.key}

              onClick={() => handleStatusChange(card.key)}

              className={`p-3.5 sm:p-4 rounded-xl border text-left transition-all duration-150 cursor-pointer flex flex-col justify-between space-y-2 relative overflow-hidden ${

                isSelected

                  ? `${card.activeBorder} ${card.activeBg} shadow-sm`

                  : "bg-white border-slate-200/90 hover:border-slate-300 hover:bg-slate-50/70 shadow-2xs"

              }`}

            >

              <div className="flex items-center justify-between">

                <div

                  className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${

                    isSelected ? "bg-white shadow-2xs" : "bg-slate-100 text-slate-600"

                  }`}

                >

                  <Icon className={`h-4 w-4 ${card.accentColor}`} />

                </div>

                {isSelected && (

                  <span className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-indigo-600 text-white">

                    Active

                  </span>

                )}

              </div>

              <div>

                <p className="text-xl sm:text-2xl font-bold text-slate-900 leading-none">

                  {card.count.toLocaleString()}

                </p>

                <div className="flex items-center justify-between gap-1 mt-1">

                  <p className="text-xs font-semibold text-slate-700">{card.title}</p>

                  <span className="text-[10px] text-slate-400 hidden sm:inline">{card.subtext}</span>

                </div>

              </div>

            </button>

          );

        })}

      </div>



      {/* 4. Search & Filter Bar */}

      <div className="bg-white rounded-xl p-3 sm:p-4 border border-slate-200/90 shadow-2xs flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">

        <div className="relative flex-1 max-w-md">

          <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />

          <input

            type="text"

            placeholder={

              activeStatus === "replies"

                ? "Search by sender, recipient, subject..."

                : activeStatus === "sent"

                ? "Search by recipient, subject..."

                : "Search by email, name, details..."

            }

            value={searchQuery}

            onChange={(e) => setSearchQuery(e.target.value)}

            className="w-full pl-9 pr-8 py-2 text-xs sm:text-sm bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors"

          />

          {searchQuery && (

            <button

              onClick={() => setSearchQuery("")}

              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"

              title="Clear search"

            >

              <X className="h-3.5 w-3.5" />

            </button>

          )}

        </div>



        <div className="flex items-center justify-between sm:justify-end gap-2 text-xs text-slate-500">
          <span>
            {debouncedSearch ? (
              <>
                Filtered: <strong className="text-slate-800">{totalItems}</strong> matching (of <span className="font-semibold text-slate-700">{summary[`${activeStatus}_count` as keyof typeof summary] ?? totalItems}</span> total)
              </>
            ) : (
              <>
                Total: <strong className="text-slate-800">{totalItems}</strong>{" "}
                {activeStatus === "recipients"
                  ? "recipients"
                  : activeStatus === "sent"
                  ? "sent emails"
                  : activeStatus === "replies"
                  ? "replies"
                  : activeStatus === "bounced"
                  ? "bounces"
                  : "failed records"}
              </>
            )}
          </span>
        </div>

      </div>



      {/* 5. Main Email / Recipient List Area */}

      <div className="bg-white rounded-xl border border-slate-200/90 shadow-2xs overflow-hidden">

        {isLoading || (isFetching && !isStatusMatching) ? (

          <div className="p-8 space-y-4">

            {[1, 2, 3, 4, 5].map((i) => (

              <div key={i} className="animate-pulse flex items-center justify-between py-3 border-b border-slate-100 last:border-0">

                <div className="space-y-2 flex-1">

                  <div className="h-4 bg-slate-200 rounded w-1/4" />

                  <div className="h-3 bg-slate-100 rounded w-1/3" />

                </div>

                <div className="h-6 bg-slate-200 rounded w-20" />

              </div>

            ))}

          </div>

        ) : isError ? (

          <div className="p-10 text-center space-y-3">

            <AlertCircle className="h-8 w-8 text-rose-500 mx-auto" />

            <p className="text-sm font-semibold text-slate-800">Failed to load campaign emails</p>

            <p className="text-xs text-slate-500">{error?.message || "An unexpected error occurred."}</p>

            <button

              onClick={() => refetch()}

              className="px-3.5 py-1.5 text-xs font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700"

            >

              Retry

            </button>

          </div>

        ) : items.length === 0 ? (

          <div className="p-12 text-center space-y-2">

            <Mail className="h-8 w-8 text-slate-300 mx-auto" />

            <p className="text-sm font-semibold text-slate-700">

              {debouncedSearch

                ? `No matching records found for "${debouncedSearch}"`

                : `No ${activeStatus} records recorded yet`}

            </p>

            <p className="text-xs text-slate-400">

              {debouncedSearch

                ? "Try adjusting your search keyword or clearing the filter."

                : `Records will appear here once the campaign executes and events are recorded.`}

            </p>

          </div>

        ) : (

          <div className="overflow-x-auto">

            <table className="w-full text-left border-collapse text-xs sm:text-sm">

              <thead>

                <tr className="bg-slate-50/75 border-b border-slate-200/80 text-[11px] font-bold uppercase tracking-wider text-slate-500">

                  {/* Status-specific table headers */}

                  {activeStatus === "recipients" && (

                    <>

                      <th className="py-3 px-4">Recipient</th>

                      <th className="py-3 px-3">Status</th>

                      <th className="py-3 px-3">Current Step</th>

                      <th className="py-3 px-3">Replied / Scheduled</th>

                      <th className="py-3 px-4 text-right">Added Date</th>

                    </>

                  )}



                  {activeStatus === "sent" && (

                    <>

                      <th className="py-3 px-4">Recipient</th>

                      <th className="py-3 px-3">Subject</th>

                      <th className="py-3 px-3">Sequence Step</th>

                      <th className="py-3 px-3">Dispatched Time</th>

                      <th className="py-3 px-4 text-right">Email View</th>

                    </>

                  )}



                  {activeStatus === "replies" && (

                    <>

                      <th className="py-3 px-4">From (Lead)</th>

                      <th className="py-3 px-3">To (Account)</th>

                      <th className="py-3 px-3">Subject</th>

                      <th className="py-3 px-3">Attributed Step</th>

                      <th className="py-3 px-3">Received Time</th>

                      <th className="py-3 px-4 text-right">Conversation</th>

                    </>

                  )}



                  {activeStatus === "bounced" && (

                    <>

                      <th className="py-3 px-4">Recipient</th>

                      <th className="py-3 px-3">Bounce Diagnostic / Reason</th>

                      <th className="py-3 px-3">Step</th>

                      <th className="py-3 px-3">Suppression Status</th>

                      <th className="py-3 px-4 text-right">Bounced At</th>

                    </>

                  )}



                  {activeStatus === "failed" && (

                    <>

                      <th className="py-3 px-4">Recipient</th>

                      <th className="py-3 px-3">Failure Reason</th>

                      <th className="py-3 px-3">Step</th>

                      <th className="py-3 px-3">Attempts</th>

                      <th className="py-3 px-4 text-right">Last Attempt</th>

                    </>

                  )}

                </tr>

              </thead>

              <tbody className="divide-y divide-slate-100">

                {items.map((item) => (

                  <tr

                    key={String(item.id)}

                    className="hover:bg-slate-50/60 transition-colors"

                  >

                    {/* 1. Recipients Row */}

                    {activeStatus === "recipients" && (

                      <>

                        <td className="py-3 px-4">

                          <div className="font-medium text-slate-900">{item.email}</div>

                          {item.recipient_name && (

                            <div className="text-[11px] text-slate-400">{item.recipient_name}</div>

                          )}

                        </td>

                        <td className="py-3 px-3">

                          <RecipientStatusBadge

                            status={item.status as CampaignRecipientStatus}

                            stoppedReason={item.stopped_reason}

                            currentStepNumber={item.step_number || 0}

                            nextStepDueAt={item.next_step_due_at}

                          />

                        </td>

                        <td className="py-3 px-3 text-slate-600 font-medium">

                          {item.step_number ? `Step ${item.step_number}` : "Initial (Step 0)"}

                        </td>

                        <td className="py-3 px-3 text-slate-500 text-xs">

                          {item.replied_at ? (

                            <span className="text-indigo-600 font-medium inline-flex items-center gap-1">

                              <Reply className="h-3 w-3" />

                              {formatTimestamp(item.replied_at)}

                            </span>

                          ) : item.next_step_due_at ? (

                            <span className="text-amber-600 inline-flex items-center gap-1">

                              <Clock className="h-3 w-3" />

                              Due {formatTimestamp(item.next_step_due_at)}

                            </span>

                          ) : (

                            <span className="text-slate-400">—</span>

                          )}

                        </td>

                        <td className="py-3 px-4 text-right text-slate-500 text-xs">

                          {formatTimestamp(item.created_at)}

                        </td>

                      </>

                    )}



                    {/* 2. Sent Row */}

                    {activeStatus === "sent" && (

                      <>

                        <td className="py-3 px-4">

                          <div className="font-medium text-slate-900">{item.email}</div>

                          {item.recipient_name && (

                            <div className="text-[11px] text-slate-400">{item.recipient_name}</div>

                          )}

                        </td>

                        <td className="py-3 px-3 text-slate-800 font-medium max-w-xs truncate" title={item.subject || ""}>

                          {item.subject || "(No Subject)"}

                        </td>

                        <td className="py-3 px-3">

                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-100">

                            Step {item.step_number || 1}

                          </span>

                        </td>

                        <td className="py-3 px-3 text-slate-500 text-xs">

                          {formatTimestamp(item.sent_at)}

                        </td>

                        <td className="py-3 px-4 text-right">

                          {item.email_id ? (

                            <Link

                              to={`/emails/${item.email_id}`}

                              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-indigo-600 bg-indigo-50/70 hover:bg-indigo-100 rounded-md transition-colors"

                              title="Open email message"

                            >

                              <span>View Email</span>

                              <ExternalLink className="h-3 w-3" />

                            </Link>

                          ) : (

                            <span className="text-xs text-slate-400">Delivered</span>

                          )}

                        </td>

                      </>

                    )}



                    {/* 3. Replies Row */}

                    {activeStatus === "replies" && (

                      <>

                        <td className="py-3 px-4">

                          <div className="font-semibold text-indigo-700">{item.sender || item.email}</div>

                          {item.recipient_name && (

                            <div className="text-[11px] text-slate-400">{item.recipient_name}</div>

                          )}

                        </td>

                        <td className="py-3 px-3 text-slate-600 text-xs">

                          {item.recipient || "Campaign Sender"}

                        </td>

                        <td className="py-3 px-3 text-slate-800 font-medium max-w-xs truncate" title={item.subject || ""}>

                          {item.subject || "(No Subject)"}

                        </td>

                        <td className="py-3 px-3">

                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-100">

                            Step {item.step_number || 1}

                          </span>

                        </td>

                        <td className="py-3 px-3 text-slate-500 text-xs">

                          {formatTimestamp(item.received_at || item.sent_at)}

                        </td>

                        <td className="py-3 px-4 text-right">

                          {item.email_id ? (

                            <Link

                              to={`/emails/${item.email_id}`}

                              className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-md transition-colors shadow-2xs"

                              title="Open full conversation history"

                            >

                              <MessageSquare className="h-3 w-3" />

                              <span>View Thread</span>

                            </Link>

                          ) : (

                            <span className="text-xs text-slate-400">—</span>

                          )}

                        </td>

                      </>

                    )}



                    {/* 4. Bounced Row */}

                    {activeStatus === "bounced" && (

                      <>

                        <td className="py-3 px-4">

                          <div className="font-medium text-slate-900">{item.email}</div>

                          {item.recipient_name && (

                            <div className="text-[11px] text-slate-400">{item.recipient_name}</div>

                          )}

                        </td>

                        <td className="py-3 px-3 text-rose-700 font-medium max-w-md truncate" title={item.error_message || item.bounce_type || ""}>

                          {item.error_message || item.bounce_type || "Recipient mailbox bounced"}

                        </td>

                        <td className="py-3 px-3">

                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700">

                            Step {item.step_number || 1}

                          </span>

                        </td>

                        <td className="py-3 px-3">

                          {item.is_suppressed ? (

                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold bg-purple-50 text-purple-700 border border-purple-200">

                              <ShieldAlert className="h-3 w-3 text-purple-600" />

                              <span>Suppressed ({item.suppression_reason || "BOUNCE"})</span>

                            </span>

                          ) : (

                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-50 text-slate-500 border border-slate-200">

                              <ShieldCheck className="h-3 w-3 text-slate-400" />

                              <span>Standard</span>

                            </span>

                          )}

                        </td>

                        <td className="py-3 px-4 text-right text-slate-500 text-xs">

                          {formatTimestamp(item.bounced_at)}

                        </td>

                      </>

                    )}



                    {/* 5. Failed Row */}

                    {activeStatus === "failed" && (

                      <>

                        <td className="py-3 px-4">

                          <div className="font-medium text-slate-900">{item.email}</div>

                          {item.recipient_name && (

                            <div className="text-[11px] text-slate-400">{item.recipient_name}</div>

                          )}

                        </td>

                        <td className="py-3 px-3 text-amber-700 font-medium max-w-md truncate" title={item.error_message || ""}>

                          {item.error_message || "Delivery dispatch failed"}

                        </td>

                        <td className="py-3 px-3">

                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700">

                            Step {item.step_number || 1}

                          </span>

                        </td>

                        <td className="py-3 px-3 text-slate-600 text-xs">

                          {item.attempt_count ? `${item.attempt_count} attempts` : "1 attempt"}

                        </td>

                        <td className="py-3 px-4 text-right text-slate-500 text-xs">

                          {formatTimestamp(item.last_attempt_at)}

                        </td>

                      </>

                    )}

                  </tr>

                ))}

              </tbody>

            </table>

          </div>

        )}



        {/* 6. Pagination Footer */}

        {totalItems > 0 && (

          <div className="px-4 py-3 bg-slate-50/70 border-t border-slate-200/80 flex items-center justify-between text-xs text-slate-500 flex-wrap gap-2">

            <div>
              Showing <span className="font-semibold text-slate-800">{items.length === 0 ? 0 : (currentPage - 1) * pageSize + 1}</span> to{" "}
              <span className="font-semibold text-slate-800">
                {Math.min(currentPage * pageSize, totalItems)}
              </span>{" "}
              of <span className="font-semibold text-slate-800">{totalItems}</span> {debouncedSearch ? "matching results" : "records"}
            </div>



            <div className="flex items-center gap-1.5">

              <button

                onClick={() => handlePageChange(Math.max(1, currentPage - 1))}

                disabled={currentPage <= 1 || isLoading}

                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 font-medium hover:bg-slate-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"

              >

                <ChevronLeft className="h-3.5 w-3.5" />

                <span>Previous</span>

              </button>



              <span className="px-2 py-1 font-semibold text-slate-700">

                {currentPage} / {totalPages}

              </span>



              <button

                onClick={() => handlePageChange(Math.min(totalPages, currentPage + 1))}

                disabled={currentPage >= totalPages || isLoading}

                className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-slate-700 font-medium hover:bg-slate-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"

              >

                <span>Next</span>

                <ChevronRight className="h-3.5 w-3.5" />

              </button>

            </div>

          </div>

        )}

      </div>

    </div>

  );

};

