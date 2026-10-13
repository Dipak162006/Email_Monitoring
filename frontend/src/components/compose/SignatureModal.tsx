import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { X, PenTool, Check, Award, Mail, Loader2, Sparkles } from "lucide-react";
import { signaturesApi } from "../../services/api";
import type { EmailSignatureItem } from "../../types/emails";

interface SignatureModalProps {
  isOpen: boolean;
  accountId?: number;
  companyId?: number;
  onClose: () => void;
  onSelectSignature: (signature: EmailSignatureItem) => void;
}

export const SignatureModal: React.FC<SignatureModalProps> = ({
  isOpen,
  accountId,
  companyId,
  onClose,
  onSelectSignature,
}) => {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<"account" | "all">("account");
  const [cloningId, setCloningId] = useState<number | null>(null);

  // 1. Fetch account-scoped signatures (preserves API contract and test expectations)
  const {
    data: accountSignatures = [],
    isLoading: isLoadingAccount,
    isError: isAccountError,
    error: accountError,
    refetch: refetchAccount,
  } = useQuery({
    queryKey: ["signatures", companyId, accountId],
    queryFn: () => signaturesApi.listSignatures(accountId, companyId),
    enabled: isOpen,
    staleTime: 30000,
  });

  // 2. Fetch all workspace signatures if companyId is available
  const {
    data: allWorkspaceSignatures = [],
    isLoading: isLoadingAll,
  } = useQuery({
    queryKey: ["signatures", companyId, "all-workspace"],
    queryFn: () => signaturesApi.listSignatures(undefined, companyId),
    enabled: isOpen && Boolean(companyId) && Boolean(accountId),
    staleTime: 30000,
  });

  if (!isOpen) return null;

  const isLoading = isLoadingAccount || (accountId && accountSignatures.length === 0 && isLoadingAll);
  const isError = isAccountError;
  const error = accountError;

  // Determine which list to display
  const hasAccountSignatures = accountSignatures.length > 0;
  const hasWorkspaceSignatures = allWorkspaceSignatures.length > 0;
  
  // Show workspace fallback if account has no signatures but workspace does
  const isUsingFallback = Boolean(
    accountId && !hasAccountSignatures && hasWorkspaceSignatures
  );

  const displayedSignatures =
    activeTab === "all" || isUsingFallback
      ? (allWorkspaceSignatures.length > 0 ? allWorkspaceSignatures : accountSignatures)
      : accountSignatures;

  const handleSelect = async (sig: EmailSignatureItem) => {
    // If signature was created for a different account, safely link/copy it for current account
    // so backend draft and send validation strictly succeed
    if (accountId && sig.email_account_id !== accountId) {
      // 1. Idempotency Check: if account already has an identical signature, use it immediately
      const existingMatch = accountSignatures.find(
        (s) =>
          s.email_account_id === accountId &&
          (s.body_html === sig.body_html && s.body_text === sig.body_text)
      );
      if (existingMatch) {
        onSelectSignature(existingMatch);
        onClose();
        return;
      }

      try {
        setCloningId(sig.id);
        const cloned = await signaturesApi.copySignature(sig.id, accountId);
        queryClient.invalidateQueries({ queryKey: ["signatures"] });
        onSelectSignature(cloned);
        onClose();
        return;
      } catch (err) {
        console.warn("Could not copy signature for current account, falling back to direct selection:", err);
      } finally {
        setCloningId(null);
      }
    }

    onSelectSignature(sig);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-lg w-full max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center gap-2">
            <PenTool className="h-5 w-5 text-indigo-600" />
            <h3 className="text-base font-semibold text-slate-900">Insert Email Signature</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition-colors cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Tab Switcher if account has signatures AND workspace has additional signatures */}
        {accountId && hasAccountSignatures && allWorkspaceSignatures.length > accountSignatures.length && (
          <div className="px-6 pt-3 pb-0 flex items-center gap-2 border-b border-slate-100 bg-white">
            <button
              type="button"
              onClick={() => setActiveTab("account")}
              className={`pb-2.5 px-2 text-xs font-semibold border-b-2 transition-colors cursor-pointer ${
                activeTab === "account"
                  ? "border-indigo-600 text-indigo-600"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              This Sender ({accountSignatures.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("all")}
              className={`pb-2.5 px-2 text-xs font-semibold border-b-2 transition-colors cursor-pointer ${
                activeTab === "all"
                  ? "border-indigo-600 text-indigo-600"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              All Workspace ({allWorkspaceSignatures.length})
            </button>
          </div>
        )}

        {/* Helpful Banner when falling back to workspace signatures */}
        {isUsingFallback && !isLoading && !isError && (
          <div className="mx-6 mt-4 p-3 rounded-xl bg-amber-50/80 border border-amber-200/80 text-xs text-amber-900 flex items-start gap-2.5">
            <Sparkles className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
            <div className="space-y-0.5">
              <p className="font-semibold text-amber-950">Workspace Signatures Available</p>
              <p className="text-amber-800 text-[11px] leading-relaxed">
                No signature specifically created for the current sender account. You can insert any signature from your workspace below.
              </p>
            </div>
          </div>
        )}

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-3">
          {isLoading && (
            <div className="space-y-2">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-16 bg-slate-50 rounded-xl animate-pulse" />
              ))}
            </div>
          )}

          {isError && !isLoading && (
            <div className="p-6 text-center space-y-3 bg-rose-50/50 rounded-xl border border-rose-100">
              <p className="text-sm font-semibold text-rose-700">Failed to load signatures</p>
              <p className="text-xs text-rose-500">
                {error instanceof Error ? error.message : "Unable to retrieve email signatures."}
              </p>
              <button
                type="button"
                onClick={() => refetchAccount()}
                className="px-3 py-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-700 bg-white border border-indigo-200 hover:bg-indigo-50/50 rounded-lg shadow-2xs transition-colors cursor-pointer"
              >
                Retry
              </button>
            </div>
          )}

          {!isLoading && !isError && displayedSignatures.length === 0 && (
            <div className="p-8 text-center text-slate-500 space-y-2">
              <p className="text-sm font-medium">No signatures found</p>
              <p className="text-xs text-slate-400">
                You can create custom email signatures in the Signatures configuration section.
              </p>
            </div>
          )}

          {!isLoading && !isError &&
            displayedSignatures.map((sig) => {
              const isDifferentAccount = accountId && sig.email_account_id !== accountId;
              const isCloningThis = cloningId === sig.id;

              return (
                <div
                  key={sig.id}
                  onClick={() => !isCloningThis && handleSelect(sig)}
                  className="p-3.5 rounded-xl border border-slate-200 bg-white hover:border-indigo-300 hover:bg-indigo-50/20 transition-all cursor-pointer group"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-slate-900 group-hover:text-indigo-700 transition-colors">
                        {sig.name}
                      </span>
                      {sig.is_default && (
                        <span className="px-1.5 py-0.2 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-0.5">
                          <Award className="h-3 w-3" />
                          Default
                        </span>
                      )}
                      {isDifferentAccount && (
                        <span className="px-1.5 py-0.2 rounded text-[10px] font-medium bg-slate-100 text-slate-600 border border-slate-200 flex items-center gap-1">
                          <Mail className="h-2.5 w-2.5" />
                          Other account
                        </span>
                      )}
                    </div>
                    <span className="text-xs font-medium text-indigo-600 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      {isCloningThis ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          Copying...
                        </>
                      ) : isDifferentAccount ? (
                        <>
                          <Check className="h-3.5 w-3.5" />
                          Copy & Insert
                        </>
                      ) : (
                        <>
                          <Check className="h-3.5 w-3.5" />
                          Insert
                        </>
                      )}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500 mt-1 line-clamp-2">
                    {sig.body_text || "HTML Signature"}
                  </p>
                </div>
              );
            })}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-100 bg-slate-50/60 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};

