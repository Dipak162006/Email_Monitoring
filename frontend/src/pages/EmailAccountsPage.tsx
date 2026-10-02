import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Mail,
  Plus,
  Server,
  RefreshCw,
  Edit3,
  Trash2,
  AlertCircle,
  CheckCircle2,
  X,
  ChevronRight,
  ShieldCheck,
  Building,
} from "lucide-react";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { EmailAccountDrawer } from "../components/accounts/EmailAccountDrawer";
import { DeleteAccountConfirmModal } from "../components/accounts/DeleteAccountConfirmModal";
import { useWorkspace } from "../hooks/useWorkspace";
import { usePermissions } from "../hooks/usePermissions";
import { emailAccountsApi } from "../services/api";
import type { EmailAccountItem } from "../types/emails";

export function EmailAccountsPage() {
  const queryClient = useQueryClient();

  // Drawer & Modal states
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [selectedAccountForEdit, setSelectedAccountForEdit] = useState<EmailAccountItem | null>(
    null
  );
  const [accountToDelete, setAccountToDelete] = useState<EmailAccountItem | null>(null);
  const [syncingAccountId, setSyncingAccountId] = useState<number | null>(null);

  // User notification banner
  const [alertBanner, setAlertBanner] = useState<{
    type: "success" | "error" | "info";
    message: string;
  } | null>(null);

  // 1. Consume active workspace and centralized permissions
  const {
    currentCompany: activeCompany,
    isLoading: isWorkspaceLoading,
    isError: isWorkspaceError,
  } = useWorkspace();

  const { canManageEmailAccounts } = usePermissions();

  // 2. Fetch email accounts for current active company
  const {
    data: accounts = [],
    isLoading: isAccountsLoading,
    isError: isAccountsError,
    error: accountsErrorObj,
    refetch: refetchAccounts,
  } = useQuery({
    queryKey: ["company-email-accounts", activeCompany?.id],
    queryFn: () => emailAccountsApi.listCompanyAccounts(activeCompany!.id),
    enabled: !!activeCompany?.id,
    staleTime: 30000,
  });

  // 3. Delete mutation
  const deleteMutation = useMutation({
    mutationFn: async ({
      companyId,
      accountId,
    }: {
      companyId: number;
      accountId: number;
    }) => {
      if (!canManageEmailAccounts) {
        throw new Error("You do not have permission to delete email accounts in this workspace.");
      }
      return emailAccountsApi.deleteAccount(companyId, accountId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["company-email-accounts"] });
      queryClient.invalidateQueries({ queryKey: ["authorized-accounts"] });
      setAccountToDelete(null);
      setAlertBanner({
        type: "success",
        message: "Email account successfully removed.",
      });
    },
    onError: (err: unknown) => {
      const errorObj = err as { detail?: string; message?: string };
      setAccountToDelete(null);
      setAlertBanner({
        type: "error",
        message:
          errorObj.detail || errorObj.message || "Failed to remove email account. Please try again.",
      });
    },
  });

  // Handle Sync action
  const handleSyncAccount = async (accountId: number, accountName: string) => {
    try {
      setSyncingAccountId(accountId);
      const res = await emailAccountsApi.triggerSync(accountId, false);

      if ("total_discovered" in res) {
        if (res.status === "SUCCESS") {
          const countMsg =
            res.new_messages > 0
              ? `${res.new_messages} new email${res.new_messages === 1 ? "" : "s"} fetched.`
              : "Mailbox is up to date (no new emails).";
          setAlertBanner({
            type: "success",
            message: `Synchronized ${accountName}: ${countMsg}`,
          });
        } else if (res.status === "PARTIAL") {
          setAlertBanner({
            type: "info",
            message: `Partial sync for ${accountName}: ${res.new_messages} new email(s) fetched. ${res.error_message || ""}`.trim(),
          });
        } else {
          setAlertBanner({
            type: "error",
            message: `Sync failed for ${accountName}: ${res.error_message || "Synchronization failed."}`,
          });
        }
      } else {
        setAlertBanner({
          type: "success",
          message: `Synchronization task queued for ${accountName}.`,
        });
      }

      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["company-email-accounts"] }),
        queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] }),
        queryClient.invalidateQueries({ queryKey: ["emails"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] }),
        queryClient.invalidateQueries({ queryKey: ["dashboard-activity"] }),
      ]);
    } catch (err: unknown) {
      const errorObj = err as { message?: string; detail?: string };
      const rawMsg =
        errorObj.detail ||
        errorObj.message ||
        `Failed to synchronize ${accountName}. Please check configuration.`;
      setAlertBanner({
        type: "error",
        message: `${accountName}: ${rawMsg}`,
      });
    } finally {
      setSyncingAccountId(null);
    }
  };

  const handleOpenCreate = () => {
    if (!canManageEmailAccounts) return;
    setSelectedAccountForEdit(null);
    setIsDrawerOpen(true);
  };

  const handleOpenEdit = (account: EmailAccountItem) => {
    if (!canManageEmailAccounts) return;
    setSelectedAccountForEdit(account);
    setIsDrawerOpen(true);
  };

  const formatLastSynced = (dateStr?: string | null) => {
    if (!dateStr) return "Never";
    try {
      const date = new Date(dateStr);
      const diffMs = Date.now() - date.getTime();
      const diffMin = Math.floor(diffMs / 60000);
      if (diffMin < 1) return "Just now";
      if (diffMin < 60) return `${diffMin}m ago`;
      const diffHours = Math.floor(diffMin / 60);
      if (diffHours < 24) return `${diffHours}h ago`;
      return date.toLocaleDateString([], { month: "short", day: "numeric" });
    } catch {
      return "Unknown";
    }
  };

  const getProviderLabel = (provider: string) => {
    switch (provider) {
      case "GOOGLE":
        return "Google Workspace";
      case "YAHOO":
        return "Yahoo Mail";
      case "ZOHO":
        return "Zoho Mail";
      default:
        return "Custom IMAP / SMTP";
    }
  };

  const isLoading = isWorkspaceLoading || (!!activeCompany && isAccountsLoading);

  return (
    <div className="space-y-6">
      {/* Subheader / Action Bar matching Stitch design */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-1.5 text-xs text-slate-500 font-medium mb-1">
            <span>Settings</span>
            <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-indigo-600 font-semibold">Connected Accounts</span>
            {activeCompany && (
              <>
                <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
                <span className="inline-flex items-center gap-1 text-slate-600 font-medium">
                  <Building className="w-3 h-3 text-slate-400" />
                  {activeCompany.name}
                </span>
              </>
            )}
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Connected Email Accounts
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-0.5">
            Manage incoming and outgoing email servers, sync frequencies, and routing protocols.
          </p>
        </div>

        <div className="flex items-center gap-3 self-start md:self-auto">
          <Button
            size="sm"
            onClick={handleOpenCreate}
            disabled={!activeCompany || !canManageEmailAccounts}
            className="gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white shadow-sm shadow-indigo-200 cursor-pointer"
          >
            <Plus className="h-3.5 w-3.5" />
            Add New Account
          </Button>
        </div>
      </div>

      {/* Operation Alert Notification Banner */}
      {alertBanner && (
        <div
          className={`flex items-center justify-between px-4 py-3 rounded-xl border text-xs font-medium transition-all ${
            alertBanner.type === "success"
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : alertBanner.type === "error"
              ? "bg-rose-50 border-rose-200 text-rose-800"
              : "bg-blue-50 border-blue-200 text-blue-800"
          }`}
        >
          <div className="flex items-center gap-2">
            {alertBanner.type === "success" ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
            ) : (
              <AlertCircle className="h-4 w-4 text-rose-600 shrink-0" />
            )}
            <span>{alertBanner.message}</span>
          </div>
          <button
            type="button"
            onClick={() => setAlertBanner(null)}
            className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-200/50 cursor-pointer"
            aria-label="Dismiss alert"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Cluster / Telemetry Info Banner matching Stitch */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="w-11 h-11 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shrink-0">
            <Server className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <span className="font-semibold text-slate-900 text-sm sm:text-base">
                Relay Gateway Cluster (v2.4)
              </span>
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-medium">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                All Systems Operational
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-1">
              Active company: <strong className="text-slate-700">{activeCompany?.name || "None"}</strong> ·{" "}
              {accounts.length} {accounts.length === 1 ? "account" : "accounts"} configured
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-500 font-mono">
          <ShieldCheck className="w-4 h-4 text-indigo-600" />
          <span>AES-GCM Credential Encryption</span>
        </div>
      </div>

      {/* Content Rendering: Loading, Error, Empty, or Cards Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {[1, 2, 3].map((idx) => (
            <div
              key={idx}
              className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs animate-pulse space-y-4"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-slate-100" />
                <div className="space-y-2 flex-1">
                  <div className="h-4 bg-slate-100 rounded w-2/3" />
                  <div className="h-3 bg-slate-100 rounded w-1/2" />
                </div>
              </div>
              <div className="h-20 bg-slate-50 rounded-lg" />
              <div className="h-8 bg-slate-100 rounded" />
            </div>
          ))}
        </div>
      ) : isAccountsError || isWorkspaceError ? (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center space-y-3">
          <AlertCircle className="w-8 h-8 text-rose-500 mx-auto" />
          <h3 className="text-sm font-semibold text-slate-900">Failed to load email accounts</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            {accountsErrorObj instanceof Error
              ? accountsErrorObj.message
              : "Unable to communicate with the email accounts service. Please check your network connection."}
          </p>
          <Button variant="outline" size="sm" onClick={() => refetchAccounts()}>
            Try Again
          </Button>
        </div>
      ) : !activeCompany ? (
        <EmptyState
          icon={<Building className="h-6 w-6 text-indigo-500" />}
          title="No company organization found"
          description="You are currently not associated with an active company organization. Please join or create a company to configure email accounts."
        />
      ) : accounts.length === 0 ? (
        <EmptyState
          icon={<Mail className="h-6 w-6 text-indigo-500" />}
          title="No email accounts configured"
          description="Add an email account with IMAP host, port, and credentials to enable automatic email synchronization and SMTP outgoing mail."
          actionLabel="Add Email Account"
          onAction={handleOpenCreate}
        />
      ) : (
        /* Connected Account Cards Grid matching Stitch */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {accounts.map((account) => {
            const isSyncing = syncingAccountId === account.id;

            return (
              <div
                key={account.id}
                className="bg-white rounded-xl border border-slate-200 shadow-xs hover:shadow-md transition-shadow flex flex-col justify-between overflow-hidden"
              >
                <div className="p-5">
                  {/* Top card header */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-10 h-10 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center border border-indigo-100 shrink-0">
                        <Mail className="w-5 h-5" />
                      </div>
                      <div className="min-w-0">
                        <h3 className="font-semibold text-slate-900 text-sm truncate">
                          {account.name}
                        </h3>
                        <p className="font-mono text-xs text-slate-500 truncate">
                          {account.email_address}
                        </p>
                      </div>
                    </div>

                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium shrink-0 ${
                        account.is_active
                          ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                          : "bg-slate-100 text-slate-600 border border-slate-200"
                      }`}
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${
                          account.is_active ? "bg-emerald-500" : "bg-slate-400"
                        }`}
                      />
                      {account.is_active ? "Connected" : "Inactive"}
                    </span>
                  </div>

                  {/* Metadata table matching Stitch */}
                  <div className="mt-4 space-y-2 text-xs text-slate-600 bg-slate-50/80 border border-slate-100 rounded-lg p-3">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-500">Provider</span>
                      <span className="font-medium text-slate-900">
                        {getProviderLabel(account.provider)}
                      </span>
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="text-slate-500">Incoming (IMAP)</span>
                      <span className="font-mono text-slate-800 text-[11px]">
                        {account.imap_host
                          ? `${account.imap_host}:${account.imap_port ?? 993}`
                          : "Not configured"}
                      </span>
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="text-slate-500">Outgoing (SMTP)</span>
                      <span className="font-mono text-slate-800 text-[11px]">
                        {account.smtp_host
                          ? `${account.smtp_host}:${account.smtp_port ?? 587}`
                          : "Not configured"}
                      </span>
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="text-slate-500">Last Synced</span>
                      <span className="font-medium text-slate-900">
                        {formatLastSynced(account.last_synced_at)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Card footer actions matching Stitch */}
                <div className="px-5 py-3 bg-slate-50 border-t border-slate-100 flex items-center justify-between">
                  <button
                    type="button"
                    disabled={isSyncing}
                    onClick={() => handleSyncAccount(account.id, account.name)}
                    className="flex items-center gap-1.5 text-xs font-medium text-slate-600 hover:text-indigo-600 transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? "animate-spin text-indigo-600" : ""}`} />
                    <span>{isSyncing ? "Syncing..." : "Sync Now"}</span>
                  </button>

                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      disabled={!canManageEmailAccounts}
                      onClick={() => handleOpenEdit(account)}
                      className="p-1.5 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 transition-colors disabled:opacity-30 cursor-pointer"
                      title="Edit Configuration"
                      aria-label={`Edit ${account.name}`}
                    >
                      <Edit3 className="w-4 h-4" />
                    </button>

                    <button
                      type="button"
                      disabled={!canManageEmailAccounts}
                      onClick={() => setAccountToDelete(account)}
                      className="p-1.5 rounded-md text-rose-400 hover:text-rose-600 hover:bg-rose-50 transition-colors disabled:opacity-30 cursor-pointer"
                      title="Remove Account"
                      aria-label={`Remove ${account.name}`}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Slide-over Drawer for Add/Edit Account */}
      {activeCompany && (
        <EmailAccountDrawer
          isOpen={isDrawerOpen}
          onClose={() => setIsDrawerOpen(false)}
          companyId={activeCompany.id}
          initialAccount={selectedAccountForEdit}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ["company-email-accounts"] });
            queryClient.invalidateQueries({ queryKey: ["authorized-accounts"] });
            queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
            setAlertBanner({
              type: "success",
              message: selectedAccountForEdit
                ? `Account "${selectedAccountForEdit.name}" updated successfully.`
                : "New email account successfully configured and connected.",
            });
          }}
        />
      )}

      {/* Delete Confirmation Modal */}
      {accountToDelete && activeCompany && (
        <DeleteAccountConfirmModal
          isOpen={!!accountToDelete}
          accountName={accountToDelete.name}
          accountEmail={accountToDelete.email_address}
          isDeleting={deleteMutation.isPending}
          onClose={() => {
            if (!deleteMutation.isPending) setAccountToDelete(null);
          }}
          onConfirm={() => {
            deleteMutation.mutate({
              companyId: activeCompany.id,
              accountId: accountToDelete.id,
            });
          }}
        />
      )}
    </div>
  );
}
