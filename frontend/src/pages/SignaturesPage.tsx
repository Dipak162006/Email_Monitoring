import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  PenTool,
  Plus,
  Search,
  CheckCircle2,
  ChevronDown,
  X,
} from "lucide-react";
import { signaturesApi, emailAccountsApi } from "../services/api";
import type {
  AuthorizedEmailAccount,
  EmailSignatureCreatePayload,
  EmailSignatureItem,
  EmailSignatureUpdatePayload,
} from "../types/emails";
import { SignatureCard } from "../components/signatures/SignatureCard";
import { SignatureDrawer } from "../components/signatures/SignatureDrawer";
import { SignaturePreviewModal } from "../components/signatures/SignaturePreviewModal";
import { DeleteSignatureModal } from "../components/signatures/DeleteSignatureModal";
import { ErrorState } from "../components/ui/ErrorState";

export function SignaturesPage() {
  const queryClient = useQueryClient();

  // Filters State
  const [searchQuery, setSearchQuery] = useState("");
  const [accountFilter, setAccountFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  // Drawer & Modal State
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [editingSignature, setEditingSignature] = useState<EmailSignatureItem | null>(null);
  const [previewSignature, setPreviewSignature] = useState<EmailSignatureItem | null>(null);
  const [deletingSignature, setDeletingSignature] = useState<EmailSignatureItem | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const showToast = (message: string) => {
    setToastMessage(message);
    setTimeout(() => {
      setToastMessage((current) => (current === message ? null : current));
    }, 4000);
  };

  // 1. Fetch Authorized Email Accounts
  const { data: accounts = [] } = useQuery({
    queryKey: ["authorizedEmailAccounts"],
    queryFn: () => emailAccountsApi.getAuthorizedAccounts(),
    staleTime: 60000,
  });

  const accountMap = useMemo(() => {
    const map = new Map<number, string>();
    accounts.forEach((acc) => {
      map.set(acc.id, acc.email_address);
    });
    return map;
  }, [accounts]);

  // 2. Fetch Signatures
  const {
    data: signatures = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["signatures"],
    queryFn: () => signaturesApi.listSignatures(),
  });

  // Mutations
  const createMutation = useMutation({
    mutationFn: (data: EmailSignatureCreatePayload) => signaturesApi.createSignature(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["signatures"] });
      showToast("Email signature created successfully.");
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: EmailSignatureUpdatePayload }) =>
      signaturesApi.updateSignature(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["signatures"] });
      showToast("Email signature updated successfully.");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => signaturesApi.deleteSignature(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["signatures"] });
      setDeletingSignature(null);
      showToast("Email signature deleted.");
    },
  });

  const setDefaultMutation = useMutation({
    mutationFn: (id: number) => signaturesApi.setDefaultSignature(id),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ["signatures"] });
      showToast(`"${updated.name}" is now the default signature for this account.`);
    },
  });

  const duplicateMutation = useMutation({
    mutationFn: (sig: EmailSignatureItem) => {
      const copyPayload: EmailSignatureCreatePayload = {
        name: `${sig.name} (Copy)`,
        email_account_id: sig.email_account_id,
        body_text: sig.body_text,
        body_html: sig.body_html,
        is_default: false,
      };
      return signaturesApi.createSignature(copyPayload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["signatures"] });
      showToast("Signature duplicated successfully.");
    },
  });

  // Client-side Filter Logic
  const filteredSignatures = useMemo(() => {
    return signatures.filter((sig) => {
      // 1. Account Filter
      if (accountFilter !== "all" && String(sig.email_account_id) !== accountFilter) {
        return false;
      }

      // 2. Status Filter
      if (statusFilter === "default" && !sig.is_default) {
        return false;
      }
      if (statusFilter === "secondary" && sig.is_default) {
        return false;
      }

      // 3. Search Query Filter (name, account email, or text)
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase().trim();
        const accEmail = (accountMap.get(sig.email_account_id) || "").toLowerCase();
        const matchesName = sig.name.toLowerCase().includes(query);
        const matchesEmail = accEmail.includes(query);
        const matchesBody = (sig.body_text || "").toLowerCase().includes(query);
        if (!matchesName && !matchesEmail && !matchesBody) {
          return false;
        }
      }

      return true;
    });
  }, [signatures, accountFilter, statusFilter, searchQuery, accountMap]);

  // Drawer handlers
  const handleOpenCreate = () => {
    setEditingSignature(null);
    setIsDrawerOpen(true);
  };

  const handleOpenEdit = (sig: EmailSignatureItem) => {
    setEditingSignature(sig);
    setIsDrawerOpen(true);
  };

  const handleSaveSignature = async (
    data: EmailSignatureCreatePayload | EmailSignatureUpdatePayload,
    isEdit: boolean
  ) => {
    if (isEdit && editingSignature) {
      await updateMutation.mutateAsync({ id: editingSignature.id, data });
    } else {
      await createMutation.mutateAsync(data as EmailSignatureCreatePayload);
    }
  };

  return (
    <div className="space-y-6 max-w-[1600px] w-full mx-auto">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-5 right-5 z-50 flex items-center gap-2 bg-slate-900 text-white px-4 py-2.5 rounded-xl shadow-xl transition-all duration-300 text-sm font-medium animate-in fade-in slide-in-from-bottom-5">
          <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Top Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Email Signatures</h1>
          <p className="text-sm text-slate-500 mt-1">
            Create and manage reusable email signatures for your connected mailboxes.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleOpenCreate}
            className="h-9 px-4 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-xs shadow-xs flex items-center gap-1.5 transition-all"
          >
            <Plus className="h-4 w-4" />
            <span>New Signature</span>
          </button>
        </div>
      </div>

      {/* Search & Filter Toolbar */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-xs p-2.5 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
        {/* Search Field */}
        <div className="relative flex-1 flex items-center">
          <Search className="absolute left-3 h-4 w-4 text-slate-400 pointer-events-none" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search signatures by name or email..."
            className="w-full h-9 pl-9 pr-8 rounded-lg bg-slate-50 text-slate-900 placeholder:text-slate-400 text-xs focus:outline-none focus:bg-white focus:ring-1 focus:ring-indigo-500 transition-all border-0"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 p-0.5 rounded text-slate-400 hover:text-slate-600"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {/* Dropdown Filters */}
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          {/* Account Filter */}
          <div className="relative">
            <select
              value={accountFilter}
              onChange={(e) => setAccountFilter(e.target.value)}
              className="h-9 pl-3 pr-8 rounded-lg bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-medium appearance-none cursor-pointer focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all border-0"
            >
              <option value="all">All Accounts</option>
              {accounts.map((acc: AuthorizedEmailAccount) => (
                <option key={acc.id} value={String(acc.id)}>
                  {acc.email_address}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-2.5 top-2.5 h-4 w-4 text-slate-400 pointer-events-none" />
          </div>

          {/* Status Filter */}
          <div className="relative">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="h-9 pl-3 pr-8 rounded-lg bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-medium appearance-none cursor-pointer focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all border-0"
            >
              <option value="all">All Statuses</option>
              <option value="default">Default only</option>
              <option value="secondary">Non-default</option>
            </select>
            <ChevronDown className="absolute right-2.5 top-2.5 h-4 w-4 text-slate-400 pointer-events-none" />
          </div>
        </div>
      </div>

      {/* Result Count Meta Bar */}
      <div className="flex items-center justify-between text-xs text-slate-500 px-1">
        <span className="font-medium">
          Displaying {filteredSignatures.length}{" "}
          {filteredSignatures.length === 1 ? "signature" : "signatures"}
        </span>
      </div>

      {/* Content States */}
      {isLoading ? (
        /* Loading Skeleton */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-4">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="bg-white border border-slate-200/80 rounded-xl p-5 shadow-xs space-y-4 animate-pulse"
            >
              <div className="flex items-center justify-between">
                <div className="h-4 bg-slate-200 rounded w-1/2" />
                <div className="h-4 bg-slate-100 rounded-full w-14" />
              </div>
              <div className="h-3 bg-slate-100 rounded w-1/3" />
              <div className="h-24 bg-slate-50 rounded-lg" />
              <div className="h-4 bg-slate-100 rounded w-1/4 pt-2" />
            </div>
          ))}
        </div>
      ) : isError ? (
        /* Error State */
        <div className="py-8">
          <ErrorState
            title="Failed to Load Signatures"
            message={error instanceof Error ? error.message : "Could not fetch email signatures."}
            onRetry={() => refetch()}
          />
        </div>
      ) : signatures.length === 0 ? (
        /* Total Zero State */
        <div className="bg-white border border-slate-200 rounded-xl py-16 px-6 text-center shadow-xs">
          <div className="w-14 h-14 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto mb-4">
            <PenTool className="h-7 w-7" />
          </div>
          <h3 className="text-base font-semibold text-slate-900">No signatures yet</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1.5 mb-5 leading-relaxed">
            Craft your first standardized email signature to boost sender credibility and brand
            recognition across outgoing campaigns.
          </p>
          <button
            type="button"
            onClick={handleOpenCreate}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-xs transition-all"
          >
            <Plus className="h-4 w-4" />
            <span>Create Signature</span>
          </button>
        </div>
      ) : filteredSignatures.length === 0 ? (
        /* Filter Zero State */
        <div className="bg-white border border-slate-200 rounded-xl py-12 px-6 text-center shadow-xs">
          <p className="text-sm font-medium text-slate-700">No matching signatures found</p>
          <p className="text-xs text-slate-400 mt-1 mb-4">
            Try adjusting your search terms, account filter, or status selection.
          </p>
          <button
            type="button"
            onClick={() => {
              setSearchQuery("");
              setAccountFilter("all");
              setStatusFilter("all");
            }}
            className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-medium transition-colors"
          >
            Clear Filters
          </button>
        </div>
      ) : (
        /* Populated Signatures Grid */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-4">
          {filteredSignatures.map((sig) => (
            <SignatureCard
              key={sig.id}
              signature={sig}
              accountEmailOrName={accountMap.get(sig.email_account_id)}
              onEdit={handleOpenEdit}
              onSetDefault={(s) => setDefaultMutation.mutate(s.id)}
              onDuplicate={(s) => duplicateMutation.mutate(s)}
              onPreview={(s) => setPreviewSignature(s)}
              onDelete={(s) => setDeletingSignature(s)}
              isUpdatingDefault={setDefaultMutation.isPending}
            />
          ))}
        </div>
      )}

      {/* Slide-over Drawer for Create / Edit */}
      <SignatureDrawer
        isOpen={isDrawerOpen}
        onClose={() => {
          setIsDrawerOpen(false);
          setEditingSignature(null);
        }}
        signature={editingSignature}
        accounts={accounts}
        onSave={handleSaveSignature}
        isSaving={createMutation.isPending || updateMutation.isPending}
      />

      {/* Preview Modal */}
      <SignaturePreviewModal
        isOpen={Boolean(previewSignature)}
        signature={previewSignature}
        accountEmailOrName={
          previewSignature ? accountMap.get(previewSignature.email_account_id) : undefined
        }
        onClose={() => setPreviewSignature(null)}
      />

      {/* Delete Confirmation Modal */}
      <DeleteSignatureModal
        isOpen={Boolean(deletingSignature)}
        signature={deletingSignature}
        onClose={() => setDeletingSignature(null)}
        onConfirm={() => {
          if (deletingSignature) {
            deleteMutation.mutate(deletingSignature.id);
          }
        }}
        isDeleting={deleteMutation.isPending}
      />
    </div>
  );
}
