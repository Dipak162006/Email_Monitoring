import { useState, useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Calendar,
  RefreshCw,
  TrendingUp,
  AlertTriangle,
  Send,
  CornerDownLeft,
  AlertCircle,
  Mail,
  ChevronRight,
  PenSquare,
  PlusCircle,
  FileText,
  ShieldAlert,
  Inbox,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { LoadingSpinner } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import { EmptyState } from "../components/ui/EmptyState";
import { ActivityTrendChart } from "../components/dashboard/ActivityTrendChart";
import { dashboardApi, emailsApi, emailAccountsApi, RequestError } from "../services/api";

import type { DateRangePreset } from "../types/dashboard";
import type { EmailItem } from "../types/emails";

function formatRelativeTime(dateStr?: string | null): string {
  if (!dateStr) return "Never";
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffSec < 60) return "Just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay === 1) return "Yesterday";
  if (diffDay < 30) return `${diffDay}d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function getProviderDisplayName(provider?: string): string {
  switch (provider?.toUpperCase()) {
    case "GOOGLE":
      return "Google Workspace";
    case "ZOHO":
      return "Zoho Mail";
    case "YAHOO":
      return "Yahoo Business";
    case "CUSTOM":
      return "Custom IMAP";
    default:
      return provider || "Custom IMAP";
  }
}

export function DashboardPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [datePreset, setDatePreset] = useState<DateRangePreset>("7d");
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncFeedback, setSyncFeedback] = useState<string | null>(null);

  // Compute UTC date boundaries for selected preset
  const { dateFrom, dateTo } = useMemo(() => {
    const now = new Date();
    const toStr = now.toISOString();
    if (datePreset === "today") {
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
      return { dateFrom: todayStart.toISOString(), dateTo: toStr };
    }
    if (datePreset === "30d") {
      const thirtyDaysAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      return { dateFrom: thirtyDaysAgo.toISOString(), dateTo: toStr };
    }
    // Default 7 days
    const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    return { dateFrom: sevenDaysAgo.toISOString(), dateTo: toStr };
  }, [datePreset]);

  // 1. Primary Stats Query
  const {
    data: stats,
    isLoading: isStatsLoading,
    isError: isStatsError,
    error: statsError,
    refetch: refetchStats,
  } = useQuery({
    queryKey: ["dashboard-stats", datePreset, dateFrom, dateTo],
    queryFn: () => dashboardApi.getStats({ dateFrom, dateTo }),
  });

  // 2. Activity Trends Query
  const { data: activityData, isLoading: isActivityLoading } = useQuery({
    queryKey: ["dashboard-activity", datePreset, dateFrom, dateTo],
    queryFn: () => dashboardApi.getActivity({ dateFrom, dateTo }),
  });

  // 3. Account Health Query
  const { data: accountHealth, isLoading: isHealthLoading } = useQuery({
    queryKey: ["dashboard-account-health"],
    queryFn: () => dashboardApi.getAccountHealth(),
  });

  // 4. Recent Emails Query
  const { data: recentEmailsData, isLoading: isRecentLoading } = useQuery({
    queryKey: ["dashboard-recent-emails"],
    queryFn: () => emailsApi.getRecentEmails(7),
  });

  // Map email accounts for quick provider lookup
  const accountsMap = useMemo(() => {
    const map = new Map<number, { name: string; provider: string; email: string }>();
    if (accountHealth?.accounts) {
      for (const acc of accountHealth.accounts) {
        map.set(acc.id, { name: acc.name, provider: acc.provider, email: acc.email_address });
      }
    }
    return map;
  }, [accountHealth]);

  // Manual Refresh Handler
  const handleRefresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard-activity"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard-account-health"] }),
      queryClient.invalidateQueries({ queryKey: ["dashboard-recent-emails"] }),
    ]);
  };

  // Sync Now Handler
  const handleSyncNow = async () => {
    if (!accountHealth?.accounts || accountHealth.accounts.length === 0) {
      navigate("/email-accounts");
      return;
    }

    try {
      setIsSyncing(true);
      setSyncFeedback(null);
      // Trigger sync for active accounts
      const activeAccounts = accountHealth.accounts.filter((a) => a.is_active);
      const targetAccounts = activeAccounts.length > 0 ? activeAccounts : [accountHealth.accounts[0]];

      await Promise.all(targetAccounts.map((acc) => emailAccountsApi.triggerSync(acc.id, true)));
      setSyncFeedback("Sync queued successfully");
      setTimeout(() => {
        setSyncFeedback(null);
        handleRefresh();
      }, 2500);
    } catch {
      setSyncFeedback("Sync trigger failed");
      setTimeout(() => setSyncFeedback(null), 3000);
    } finally {
      setIsSyncing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* ===================================================================== */}
      {/* SECTION A: Dashboard Header */}
      {/* ===================================================================== */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Dashboard Overview</h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">
            Monitor email delivery, engagement, and account health.
          </p>
        </div>

        <div className="flex items-center space-x-2.5 self-start sm:self-auto">
          {/* Date Range Selector */}
          <div className="relative inline-flex items-center bg-white border border-slate-200 rounded-lg px-3 py-1.5 shadow-2xs hover:border-slate-300 transition-colors">
            <Calendar className="h-3.5 w-3.5 text-slate-400 mr-2 shrink-0" />
            <select
              id="date-range-select"
              value={datePreset}
              onChange={(e) => setDatePreset(e.target.value as DateRangePreset)}
              className="bg-transparent text-xs font-medium text-slate-700 focus:outline-none cursor-pointer pr-1"
            >
              <option value="today">Today</option>
              <option value="7d">Last 7 days</option>
              <option value="30d">Last 30 days</option>
            </select>
          </div>

          {/* Refresh Button */}
          <Button
            variant="outline"
            size="sm"
            onClick={handleRefresh}
            title="Refresh dashboard data"
            className="h-9 px-3 text-slate-600 hover:text-slate-900 border-slate-200"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${isStatsLoading || isActivityLoading ? "animate-spin text-indigo-600" : ""}`}
            />
          </Button>
        </div>
      </div>

      {/* Stats Error Banner: Compact & professional, only shown for non-auth errors */}
      {isStatsError && (statsError as RequestError)?.status !== 401 && (
        <ErrorState
          compact
          title="Unable to load dashboard statistics."
          message={(statsError as Error)?.message || "Failed to retrieve metrics from the server."}
          onRetry={refetchStats}
        />
      )}


      {/* ===================================================================== */}
      {/* SECTION B: Primary Statistics Cards (Equal width & height) */}
      {/* ===================================================================== */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Card 1: TOTAL SENT */}
        <Card className="flex flex-col justify-between border-slate-200/80 shadow-xs hover:shadow-sm transition-shadow">
          <CardHeader className="p-5 pb-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Total Sent
              </span>
              {stats?.sent_change_percent !== null && stats?.sent_change_percent !== undefined ? (
                <div
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold border ${
                    stats.sent_change_percent >= 0
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                      : "bg-rose-50 text-rose-700 border-rose-200"
                  }`}
                >
                  <TrendingUp className="h-3 w-3" />
                  <span>
                    {stats.sent_change_percent >= 0 ? "+" : ""}
                    {stats.sent_change_percent}% vs previous {datePreset === "30d" ? "30d" : datePreset === "today" ? "day" : "7d"}
                  </span>
                </div>
              ) : (
                <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
                  No prior data
                </div>
              )}
            </div>
            <div className="mt-2.5">
              <div className="text-3xl font-bold tracking-tight text-slate-900">
                {isStatsLoading ? (
                  <div className="h-9 w-28 bg-slate-100 animate-pulse rounded" />
                ) : (
                  (stats?.sent_count ?? 0).toLocaleString()
                )}
              </div>
              <p className="text-xs text-slate-500 mt-1">Emails sent during this period</p>
            </div>
          </CardHeader>
          <CardContent className="p-5 pt-0">
            <hr className="border-slate-100 mb-3" />
            <Link
              to="/mailbox?folder=sent"
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 inline-flex items-center gap-1 group"
            >
              <span>View Sent Emails</span>
              <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </CardContent>
        </Card>

        {/* Card 2: BOUNCED EMAILS */}
        <Card className="flex flex-col justify-between border-slate-200/80 shadow-xs hover:shadow-sm transition-shadow">
          <CardHeader className="p-5 pb-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Bounced Emails
              </span>
              <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                <AlertTriangle className="h-3 w-3" />
                <span>{(stats?.bounce_rate ?? 0.0).toFixed(2)}% bounce rate</span>
              </div>
            </div>
            <div className="mt-2.5">
              <div className="text-3xl font-bold tracking-tight text-slate-900">
                {isStatsLoading ? (
                  <div className="h-9 w-24 bg-slate-100 animate-pulse rounded" />
                ) : (
                  (stats?.bounced_count ?? 0).toLocaleString()
                )}
              </div>
              <p className="text-xs text-slate-500 mt-1">Emails that failed delivery</p>
            </div>
          </CardHeader>
          <CardContent className="p-5 pt-0">
            <hr className="border-slate-100 mb-3" />
            <Link
              to="/mailbox?folder=bounced"
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 inline-flex items-center gap-1 group"
            >
              <span>View Bounced Emails</span>
              <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </CardContent>
        </Card>

        {/* Card 3: CUSTOMER RESPONSES */}
        <Card className="flex flex-col justify-between border-slate-200/80 shadow-xs hover:shadow-sm transition-shadow">
          <CardHeader className="p-5 pb-3">
            <div className="flex items-center justify-between">
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
                Customer Responses
              </span>
              {stats?.response_change_percent !== null && stats?.response_change_percent !== undefined ? (
                <div
                  className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold border ${
                    stats.response_change_percent >= 0
                      ? "bg-indigo-50 text-indigo-700 border-indigo-200"
                      : "bg-rose-50 text-rose-700 border-rose-200"
                  }`}
                >
                  <TrendingUp className="h-3 w-3" />
                  <span>
                    {stats.response_change_percent >= 0 ? "+" : ""}
                    {stats.response_change_percent}% response volume
                  </span>
                </div>
              ) : (
                <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
                  No prior data
                </div>
              )}
            </div>
            <div className="mt-2.5">
              <div className="text-3xl font-bold tracking-tight text-slate-900">
                {isStatsLoading ? (
                  <div className="h-9 w-24 bg-slate-100 animate-pulse rounded" />
                ) : (
                  (stats?.response_count ?? 0).toLocaleString()
                )}
              </div>
              <p className="text-xs text-slate-500 mt-1">Replies received during this period</p>
            </div>
          </CardHeader>
          <CardContent className="p-5 pt-0">
            <hr className="border-slate-100 mb-3" />
            <Link
              to="/mailbox?folder=responses"
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 inline-flex items-center gap-1 group"
            >
              <span>View Responses</span>
              <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </CardContent>
        </Card>
      </div>

      {/* ===================================================================== */}
      {/* SECTION C: Email Activity Trends Chart */}
      {/* ===================================================================== */}
      <Card className="border-slate-200/80 shadow-xs">
        <CardHeader className="p-5 pb-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <CardTitle className="text-base font-bold text-slate-900">Email Activity Trends</CardTitle>
            <CardDescription className="text-xs text-slate-500 mt-0.5">
              Daily volume dispatches, inbound replies, and delivery failures
            </CardDescription>
          </div>

          {/* Legend */}
          <div className="flex items-center space-x-4 text-xs font-medium text-slate-600">
            <div className="flex items-center space-x-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-indigo-600" />
              <span>Sent</span>
            </div>
            <div className="flex items-center space-x-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-sky-500" />
              <span>Customer Responses</span>
            </div>
            <div className="flex items-center space-x-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-rose-500" />
              <span>Bounced</span>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-5 pt-2">
          <ActivityTrendChart
            points={activityData?.points || []}
            isLoading={isActivityLoading}
          />
        </CardContent>
      </Card>

      {/* ===================================================================== */}
      {/* SECTION D: Lower Two-Column Layout */}
      {/* ===================================================================== */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* LEFT COLUMN: Recent Email Activity (approx 8/12) */}
        <Card className="lg:col-span-8 flex flex-col justify-between border-slate-200/80 shadow-xs h-full">
          <CardHeader className="p-5 pb-3 flex flex-row items-center justify-between shrink-0">
            <div>
              <CardTitle className="text-base font-bold text-slate-900">Recent Email Activity</CardTitle>
              <CardDescription className="text-xs text-slate-500 mt-0.5">
                Latest dispatches, customer replies, and delivery events
              </CardDescription>
            </div>
            <Link
              to="/mailbox"
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 inline-flex items-center gap-1 group"
            >
              <span>View All in Mailbox</span>
              <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </CardHeader>

          <CardContent className="p-0 flex-1 flex flex-col justify-between">
            {isRecentLoading ? (
              <div className="p-8 flex-1 flex items-center justify-center">
                <LoadingSpinner message="Loading recent email events..." />
              </div>
            ) : !recentEmailsData?.emails || recentEmailsData.emails.length === 0 ? (
              <div className="p-8 flex-1 flex items-center justify-center">
                <EmptyState
                  icon={<Inbox className="h-6 w-6 text-indigo-500" />}
                  title="No email activity yet"
                  description="Sent emails, incoming customer replies, and delivery events will appear here once connected."
                  actionLabel="Compose an Email"
                  onAction={() => navigate("/compose")}
                  className="py-12 w-full"
                />
              </div>
            ) : (
              <div className="divide-y divide-slate-100 flex-1 flex flex-col">
                {recentEmailsData.emails.slice(0, 7).map((email: EmailItem) => {
                  const isSent = email.direction === "OUTGOING" && email.status === "SENT";
                  const isBounced = email.status === "BOUNCED";
                  const isResponse = email.direction === "INCOMING" && email.thread_id !== null;

                  // Resolve provider from account mapping
                  const accountInfo = accountsMap.get(email.email_account_id);
                  const providerLabel = getProviderDisplayName(accountInfo?.provider);

                  // Row icon and status pill
                  let rowIcon = <Mail className="h-4 w-4 text-slate-500" />;
                  let iconBg = "bg-slate-100 text-slate-600";
                  let statusLabel = email.status.charAt(0) + email.status.slice(1).toLowerCase();
                  let statusVariant: "default" | "secondary" | "success" | "warning" | "destructive" | "outline" =
                    "secondary";

                  if (isBounced) {
                    rowIcon = <AlertCircle className="h-4 w-4 text-rose-600" />;
                    iconBg = "bg-rose-50 text-rose-700";
                    statusLabel = "Bounced";
                    statusVariant = "destructive";
                  } else if (isResponse) {
                    rowIcon = <CornerDownLeft className="h-4 w-4 text-sky-600" />;
                    iconBg = "bg-sky-50 text-sky-700";
                    statusLabel = "Response";
                    statusVariant = "default";
                  } else if (isSent) {
                    rowIcon = <Send className="h-4 w-4 text-indigo-600" />;
                    iconBg = "bg-indigo-50 text-indigo-700";
                    statusLabel = "Sent";
                    statusVariant = "default";
                  } else if (email.direction === "INCOMING") {
                    statusLabel = email.is_read ? "Read" : "New";
                    statusVariant = email.is_read ? "secondary" : "default";
                  }

                  const relativeTime = formatRelativeTime(
                    email.sent_at || email.received_at || email.created_at
                  );

                  return (
                    <div
                      key={email.id}
                      onClick={() => navigate(`/emails/${email.id}`)}
                      className="px-5 py-3.5 hover:bg-slate-50/80 cursor-pointer transition-colors flex items-center justify-between gap-3 group"
                    >
                      {/* Left: Direction icon + Contact & Snippet */}
                      <div className="flex items-center space-x-3.5 min-w-0 flex-1">
                        <div
                          className={`h-9 w-9 rounded-xl flex items-center justify-center shrink-0 shadow-2xs ${iconBg}`}
                        >
                          {rowIcon}
                        </div>

                        <div className="min-w-0 flex-1">
                          <div className="flex items-center space-x-2">
                            <p className="text-xs font-semibold text-slate-900 truncate">
                              {email.direction === "OUTGOING" ? (
                                <>
                                  <span className="text-slate-800 font-bold">{email.sender}</span>
                                  <span className="text-slate-400 font-normal mx-1">to</span>
                                  <span className="text-slate-600">
                                    {email.recipients?.join(", ") || "Recipient"}
                                  </span>
                                </>
                              ) : (
                                <>
                                  <span className="text-slate-800 font-bold">{email.sender}</span>
                                </>
                              )}
                            </p>
                            {/* Provider Badge */}
                            <span className="hidden sm:inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-slate-600 shrink-0">
                              {providerLabel}
                            </span>
                          </div>

                          <p className="text-xs text-slate-500 truncate mt-0.5">
                            <span className="font-medium text-slate-700">{email.subject || "(No Subject)"}</span>
                            {email.body_text && (
                              <span className="text-slate-400 ml-1.5">— {email.body_text.slice(0, 75)}</span>
                            )}
                          </p>
                        </div>
                      </div>

                      {/* Right: Status badge & timestamp */}
                      <div className="flex items-center space-x-3 shrink-0">
                        <Badge variant={statusVariant} className="text-[11px] px-2 py-0.5">
                          {statusLabel}
                        </Badge>
                        <span className="text-[11px] text-slate-400 font-medium min-w-[50px] text-right">
                          {relativeTime}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* RIGHT COLUMN: Account Health & Quick Actions (approx 4/12) */}
        <div className="lg:col-span-4 flex flex-col gap-6">
          {/* Card 1: Account Health & Sync */}
          <Card className="border-slate-200/80 shadow-xs">
            <CardHeader className="p-5 pb-4">
              <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <CardTitle className="text-base font-bold text-slate-900 leading-tight">
                    Account Health & Sync
                  </CardTitle>
                  <CardDescription className="text-xs text-slate-500 mt-1">
                    Monitor connected email accounts and synchronization.
                  </CardDescription>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSyncNow}
                  disabled={isSyncing}
                  className="h-8 px-3 shrink-0 text-xs font-medium text-indigo-600 hover:text-indigo-700 border-indigo-200 hover:bg-indigo-50/60 gap-1.5 self-start sm:self-auto"
                >
                  <RefreshCw className={`h-3 w-3 ${isSyncing ? "animate-spin" : ""}`} />
                  <span>{isSyncing ? "Syncing..." : "Sync Now"}</span>
                </Button>
              </div>
            </CardHeader>

            <CardContent className="p-5 pt-0 space-y-4">
              {syncFeedback && (
                <div className="p-2 rounded-lg bg-indigo-50 text-indigo-700 text-xs font-medium text-center border border-indigo-100">
                  {syncFeedback}
                </div>
              )}

              {/* Summary Section: Responsive 2-column grid */}
              <div className="grid grid-cols-2 gap-2.5 p-3 rounded-xl bg-slate-50/80 border border-slate-100">
                <div className="p-2.5 rounded-lg bg-white border border-slate-200/60 shadow-2xs">
                  <span className="text-[11px] font-medium text-slate-500 block">Connected</span>
                  <span className="text-base font-bold text-slate-900 mt-0.5 block">
                    {accountHealth?.total_accounts ?? 0}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-white border border-slate-200/60 shadow-2xs">
                  <div className="flex items-center space-x-1.5">
                    <span className="h-2 w-2 rounded-full bg-emerald-500 shrink-0" />
                    <span className="text-[11px] font-medium text-slate-500 truncate">Operational</span>
                  </div>
                  <span className="text-base font-bold text-slate-900 mt-0.5 block">
                    {accountHealth?.active_accounts ?? 0}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-white border border-slate-200/60 shadow-2xs">
                  <div className="flex items-center space-x-1.5">
                    <span className="h-2 w-2 rounded-full bg-amber-400 shrink-0" />
                    <span className="text-[11px] font-medium text-slate-500 truncate">Syncing</span>
                  </div>
                  <span className="text-base font-bold text-slate-900 mt-0.5 block">
                    {accountHealth?.syncing_accounts ?? 0}
                  </span>
                </div>
                <div className="p-2.5 rounded-lg bg-white border border-slate-200/60 shadow-2xs">
                  <span className="text-[11px] font-medium text-slate-500 block">Last Synced</span>
                  <span className="text-xs font-semibold text-slate-700 mt-1 block truncate">
                    {formatRelativeTime(accountHealth?.last_synced_at)}
                  </span>
                </div>
              </div>

              {/* Account Profiles List / Empty State */}
              {isHealthLoading ? (
                <div className="py-4">
                  <LoadingSpinner message="Checking account status..." />
                </div>
              ) : !accountHealth?.accounts || accountHealth.accounts.length === 0 ? (
                <div className="py-6 px-4 flex flex-col items-center justify-center text-center rounded-xl border border-dashed border-slate-200 bg-slate-50/40">
                  <p className="text-xs font-medium text-slate-600 mb-3">No email accounts connected.</p>
                  <Link to="/email-accounts">
                    <Button size="sm" variant="outline" className="text-xs font-semibold gap-1.5 bg-white border-slate-300 hover:bg-slate-50 text-slate-800 shadow-2xs">
                      <PlusCircle className="h-3.5 w-3.5 text-indigo-600" />
                      <span>Connect Account</span>
                    </Button>
                  </Link>
                </div>
              ) : (
                <div className="space-y-2 pt-1">
                  {accountHealth.accounts.map((acc) => {
                    const avatarLetter = acc.name ? acc.name.charAt(0).toUpperCase() : "E";
                    const isHealthy = acc.is_active;

                    return (
                      <div
                        key={acc.id}
                        className="flex items-center justify-between p-2.5 rounded-lg border border-slate-100 hover:bg-slate-50 transition-colors"
                      >
                        <div className="flex items-center space-x-2.5 min-w-0">
                          <div className="h-7 w-7 rounded-lg bg-slate-100 border border-slate-200 text-slate-700 flex items-center justify-center font-bold text-xs shrink-0">
                            {avatarLetter}
                          </div>
                          <div className="min-w-0">
                            <p className="text-xs font-semibold text-slate-900 truncate">{acc.name}</p>
                            <p className="text-[10px] text-slate-400 truncate">{acc.email_address}</p>
                          </div>
                        </div>

                        <div className="shrink-0 ml-2">
                          {isHealthy ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                              • Healthy
                            </span>
                          ) : (
                            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
                              • Idle
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Card 2: Quick Actions */}
          <Card className="border-slate-200/80 shadow-xs">
            <CardHeader className="p-5 pb-3">
              <CardTitle className="text-base font-bold text-slate-900">Quick Actions</CardTitle>
              <CardDescription className="text-xs text-slate-500 mt-0.5">
                Operational triggers and configurations
              </CardDescription>
            </CardHeader>

            <CardContent className="p-3 space-y-1">
              {/* Action 1: Compose Email */}
              <Link
                to="/compose"
                className="flex items-center justify-between p-2.5 rounded-lg hover:bg-slate-50 transition-colors group"
              >
                <div className="flex items-center space-x-3">
                  <div className="h-8 w-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                    <PenSquare className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-slate-900 group-hover:text-indigo-600 transition-colors">
                      Compose Email
                    </p>
                    <p className="text-[11px] text-slate-500">Draft and dispatch outbound message</p>
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 text-slate-400 group-hover:text-slate-600 group-hover:translate-x-0.5 transition-all" />
              </Link>

              {/* Action 2: Connect Email Account */}
              <Link
                to="/email-accounts"
                className="flex items-center justify-between p-2.5 rounded-lg hover:bg-slate-50 transition-colors group"
              >
                <div className="flex items-center space-x-3">
                  <div className="h-8 w-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
                    <PlusCircle className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-slate-900 group-hover:text-emerald-600 transition-colors">
                      Connect Email Account
                    </p>
                    <p className="text-[11px] text-slate-500">Add SMTP/IMAP, Google or Zoho</p>
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 text-slate-400 group-hover:text-slate-600 group-hover:translate-x-0.5 transition-all" />
              </Link>

              {/* Action 3: Create Template */}
              <Link
                to="/templates"
                className="flex items-center justify-between p-2.5 rounded-lg hover:bg-slate-50 transition-colors group"
              >
                <div className="flex items-center space-x-3">
                  <div className="h-8 w-8 rounded-lg bg-purple-50 text-purple-600 flex items-center justify-center shrink-0">
                    <FileText className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-slate-900 group-hover:text-purple-600 transition-colors">
                      Create Template
                    </p>
                    <p className="text-[11px] text-slate-500">Design reusable company email layouts</p>
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 text-slate-400 group-hover:text-slate-600 group-hover:translate-x-0.5 transition-all" />
              </Link>

              {/* Action 4: View Bounced Emails */}
              <Link
                to="/mailbox?folder=bounced"
                className="flex items-center justify-between p-2.5 rounded-lg hover:bg-slate-50 transition-colors group"
              >
                <div className="flex items-center space-x-3">
                  <div className="h-8 w-8 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center shrink-0">
                    <ShieldAlert className="h-4 w-4" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-slate-900 group-hover:text-rose-600 transition-colors">
                      View Bounced Emails
                    </p>
                    <p className="text-[11px] text-slate-500">Audit suppression lists & delivery failures</p>
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 text-slate-400 group-hover:text-slate-600 group-hover:translate-x-0.5 transition-all" />
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
