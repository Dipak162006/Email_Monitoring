import { useState, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Inbox, AlertCircle } from "lucide-react";
import { emailsApi, emailAccountsApi } from "../services/api";
import type { EmailItem, EmailListParams } from "../types/emails";
import { MailboxHeader } from "../components/mailbox/MailboxHeader";
import { MailboxToolbar } from "../components/mailbox/MailboxToolbar";
import { EmailRow } from "../components/mailbox/EmailRow";
import { EmailDetailDrawer } from "../components/mailbox/EmailDetailDrawer";
import { EmptyState } from "../components/ui/EmptyState";
import { Button } from "../components/ui/Button";

const PAGE_SIZE = 25;

export function MailboxPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();

  // Active folder from URL search params (default to "inbox")
  const rawFolder = searchParams.get("folder")?.toLowerCase();
  const activeFolder = useMemo(() => {
    if (rawFolder && ["inbox", "sent", "drafts", "responses", "bounced", "trash"].includes(rawFolder)) {
      return rawFolder;
    }
    return "inbox";
  }, [rawFolder]);

  // Local state
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedAccountId, setSelectedAccountId] = useState<number | undefined>(undefined);
  const [unreadOnly, setUnreadOnly] = useState<boolean | undefined>(undefined);
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [selectedEmail, setSelectedEmail] = useState<EmailItem | null>(null);
  const [isSyncing, setIsSyncing] = useState(false);

  // Folder Title formatting
  const folderTitle = useMemo(() => {
    return activeFolder.charAt(0).toUpperCase() + activeFolder.slice(1);
  }, [activeFolder]);

  // Fetch Mailbox dynamic counts
  const { data: mailboxCounts, refetch: refetchCounts } = useQuery({
    queryKey: ["mailbox-counts"],
    queryFn: () => emailsApi.getMailboxCounts(),
    staleTime: 30000,
  });

  // Fetch Authorized Accounts for filter dropdown
  const { data: authorizedAccounts = [] } = useQuery({
    queryKey: ["authorized-accounts"],
    queryFn: () => emailAccountsApi.getAuthorizedAccounts(),
    staleTime: 60000,
  });

  // Query params for emails list
  const listParams: EmailListParams = useMemo(() => {
    return {
      folder: activeFolder,
      search: searchQuery.trim() || undefined,
      emailAccountId: selectedAccountId,
      isRead: unreadOnly ? false : undefined,
      limit: PAGE_SIZE,
      offset: (currentPage - 1) * PAGE_SIZE,
      sort: "newest",
    };
  }, [activeFolder, searchQuery, selectedAccountId, unreadOnly, currentPage]);

  // Fetch email list
  const {
    data: emailListData,
    isLoading,
    isError,
    error,
    refetch: refetchEmails,
  } = useQuery({
    queryKey: ["emails", listParams],
    queryFn: () => emailsApi.listEmails(listParams),
    staleTime: 15000,
  });

  const emails = emailListData?.emails || [];
  const totalEmails = emailListData?.total || 0;

  // Sync handler
  const handleSync = async () => {
    try {
      setIsSyncing(true);
      await Promise.all([refetchCounts(), refetchEmails()]);
    } finally {
      setTimeout(() => setIsSyncing(false), 600);
    }
  };

  // Quick Filter Pill Click
  const handleQuickFilter = (filter: { unread?: boolean; folder?: string }) => {
    if (filter.folder) {
      setSearchParams({ folder: filter.folder });
      setCurrentPage(1);
      setSelectedIds(new Set());
    } else if (filter.unread !== undefined) {
      setUnreadOnly(filter.unread ? true : undefined);
      setCurrentPage(1);
    }
  };

  // Selection Logic
  const handleToggleSelectAll = () => {
    if (selectedIds.size === emails.length && emails.length > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(emails.map((e: EmailItem) => e.id)));
    }
  };

  const handleToggleSelectRow = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  // Mutations for email actions
  const markReadMutation = useMutation({
    mutationFn: ({ id, isRead }: { id: number; isRead: boolean }) =>
      emailsApi.markRead(id, isRead),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["emails"] });
      queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
    },
  });

  const markStarMutation = useMutation({
    mutationFn: ({ id, isStarred }: { id: number; isStarred: boolean }) =>
      emailsApi.markStarred(id, isStarred),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["emails"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => emailsApi.softDelete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["emails"] });
      queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
      setSelectedIds((prev) => {
        const next = new Set(prev);
        // Clear if deleted
        return next;
      });
    },
  });

  // Single Row Handlers
  const handleToggleStar = (id: number, currentStarred: boolean) => {
    markStarMutation.mutate({ id, isStarred: !currentStarred });
  };

  const handleToggleRead = (id: number, currentRead: boolean) => {
    markReadMutation.mutate({ id, isRead: !currentRead });
  };

  const handleDeleteRow = (id: number) => {
    deleteMutation.mutate(id);
    if (selectedEmail?.id === id) {
      setSelectedEmail(null);
    }
  };

  const handleArchiveRow = (id: number) => {
    deleteMutation.mutate(id);
  };

  // Bulk Action Handlers
  const handleBulkStar = async () => {
    const ids = Array.from(selectedIds);
    await Promise.all(ids.map((id) => emailsApi.markStarred(id, true)));
    queryClient.invalidateQueries({ queryKey: ["emails"] });
  };

  const handleBulkMarkRead = async (isRead: boolean) => {
    const ids = Array.from(selectedIds);
    await Promise.all(ids.map((id) => emailsApi.markRead(id, isRead)));
    queryClient.invalidateQueries({ queryKey: ["emails"] });
    queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
  };

  const handleBulkArchive = async () => {
    const ids = Array.from(selectedIds);
    await Promise.all(ids.map((id) => emailsApi.softDelete(id)));
    setSelectedIds(new Set());
    queryClient.invalidateQueries({ queryKey: ["emails"] });
    queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
  };

  const handleBulkDelete = async () => {
    const ids = Array.from(selectedIds);
    await Promise.all(ids.map((id) => emailsApi.softDelete(id)));
    setSelectedIds(new Set());
    queryClient.invalidateQueries({ queryKey: ["emails"] });
    queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
  };

  // Row click opens drawer
  const handleEmailClick = (email: EmailItem) => {
    setSelectedEmail(email);
    // Mark as read automatically when opened if currently unread
    if (!email.is_read) {
      markReadMutation.mutate({ id: email.id, isRead: true });
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. Header with Breadcrumb, Total Count, Live Ingestion, Quick Indicators */}
      <MailboxHeader
        folderTitle={folderTitle}
        totalCount={totalEmails}
        mailboxCounts={mailboxCounts}
        isSyncing={isSyncing}
        onSync={handleSync}
        onFilterChange={handleQuickFilter}
        activeUnreadFilter={unreadOnly}
      />

      {/* 2. Primary Card: Integrated Toolbar & Table */}
      <div className="flex flex-col bg-white border border-slate-200/80 rounded-xl shadow-2xs overflow-hidden">
        {/* Integrated Horizontal Toolbar */}
        <MailboxToolbar
          isAllSelected={emails.length > 0 && selectedIds.size === emails.length}
          isSomeSelected={selectedIds.size > 0 && selectedIds.size < emails.length}
          selectedCount={selectedIds.size}
          totalVisibleCount={emails.length}
          onToggleSelectAll={handleToggleSelectAll}
          onBulkStar={handleBulkStar}
          onBulkMarkRead={handleBulkMarkRead}
          onBulkArchive={handleBulkArchive}
          onBulkDelete={handleBulkDelete}
          accounts={authorizedAccounts}
          selectedAccountId={selectedAccountId}
          onAccountChange={(id?: number) => {
            setSelectedAccountId(id);
            setCurrentPage(1);
          }}
          searchQuery={searchQuery}
          onSearchChange={(q: string) => {
            setSearchQuery(q);
            setCurrentPage(1);
          }}
          currentPage={currentPage}
          pageSize={PAGE_SIZE}
          totalCount={totalEmails}
          onPageChange={(page: number) => setCurrentPage(page)}
        />

        {/* Desktop Table Column Headers */}
        <div className="hidden lg:grid grid-cols-12 gap-4 px-5 py-2.5 bg-slate-50/80 border-b border-slate-200/80 text-[11px] uppercase tracking-wider text-slate-500 font-semibold select-none">
          <div className="col-span-1 flex items-center gap-2">
            <span>State</span>
          </div>
          <div className="col-span-3 flex items-center">
            <span>Sender &amp; Gateway</span>
          </div>
          <div className="col-span-5 flex items-center">
            <span>Subject &amp; Snippet</span>
          </div>
          <div className="col-span-2 flex items-center justify-center">
            <span>Telemetry Status</span>
          </div>
          <div className="col-span-1 flex items-center justify-end">
            <span>Timestamp</span>
          </div>
        </div>

        {/* Email Rows List Content */}
        <div className="flex flex-col divide-y divide-slate-100">
          {isLoading && (
            <div className="p-8 space-y-4">
              {[...Array(6)].map((_, i) => (
                <div key={i} className="flex items-center gap-4 animate-pulse">
                  <div className="h-4 w-4 bg-slate-100 rounded" />
                  <div className="h-7 w-7 rounded-full bg-slate-100" />
                  <div className="h-4 w-36 bg-slate-100 rounded" />
                  <div className="h-4 flex-1 bg-slate-100 rounded" />
                  <div className="h-4 w-16 bg-slate-100 rounded" />
                </div>
              ))}
            </div>
          )}

          {isError && (
            <div className="p-12 text-center space-y-3">
              <div className="inline-flex p-3 rounded-full bg-rose-50 text-rose-600">
                <AlertCircle className="h-6 w-6" />
              </div>
              <h3 className="text-sm font-semibold text-slate-900">Failed to load emails</h3>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                {(error as Error)?.message || "An unexpected error occurred while fetching emails."}
              </p>
              <Button size="sm" variant="outline" onClick={() => refetchEmails()} className="mt-2">
                Try Again
              </Button>
            </div>
          )}

          {!isLoading && !isError && emails.length === 0 && (
            <div className="p-12">
              <EmptyState
                icon={<Inbox className="h-8 w-8 text-indigo-500" />}
                title={`No messages in ${folderTitle}`}
                description={
                  searchQuery
                    ? `No messages matched your search term "${searchQuery}".`
                    : `Your ${folderTitle.toLowerCase()} folder is currently empty. Connect an account or trigger sync to ingest emails.`
                }
                actionLabel={searchQuery ? "Clear Search" : "Sync Mailbox"}
                onAction={() => {
                  if (searchQuery) {
                    setSearchQuery("");
                  } else {
                    handleSync();
                  }
                }}
              />
            </div>
          )}

          {!isLoading &&
            !isError &&
            emails.map((email: EmailItem) => (
              <EmailRow
                key={email.id}
                email={email}
                isSelected={selectedIds.has(email.id)}
                onToggleSelect={handleToggleSelectRow}
                onToggleStar={handleToggleStar}
                onToggleRead={handleToggleRead}
                onDelete={handleDeleteRow}
                onArchive={handleArchiveRow}
                onClick={handleEmailClick}
              />
            ))}
        </div>
      </div>

      {/* 3. Slide-Over Conversation & Message Detail Drawer */}
      <EmailDetailDrawer
        email={selectedEmail}
        onClose={() => setSelectedEmail(null)}
      />
    </div>
  );
}
