import React, { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { X, FileText, Paperclip, AlertTriangle, Check, RefreshCw } from "lucide-react";
import { emailsApi } from "../../services/api";
import type { EmailItem } from "../../types/emails";

interface DraftImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectDraft: (draft: EmailItem) => void;
  selectedAccountId?: number | null;
  companyId?: number | null;
  hasExistingContent: boolean;
}

export const DraftImportModal: React.FC<DraftImportModalProps> = ({
  isOpen,
  onClose,
  onSelectDraft,
  selectedAccountId,
  companyId,
  hasExistingContent,
}) => {
  const [selectedDraft, setSelectedDraft] = useState<EmailItem | null>(null);
  const [showWarning, setShowWarning] = useState<boolean>(false);

  const {
    data: draftsResponse,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["drafts", companyId, selectedAccountId],
    queryFn: () =>
      emailsApi.listEmails({
        folder: "drafts",
        companyId: companyId || undefined,
        emailAccountId: selectedAccountId || undefined,
        limit: 50,
      }),
    enabled: isOpen && !!companyId,
    staleTime: 0,
    refetchOnMount: "always",
  });

  useEffect(() => {
    if (isOpen) {
      refetch();
      setSelectedDraft(null);
      setShowWarning(false);
    }
  }, [isOpen, refetch]);

  const drafts = draftsResponse?.emails || [];

  const handleDraftClick = (draft: EmailItem) => {
    if (hasExistingContent) {
      setSelectedDraft(draft);
      setShowWarning(true);
    } else {
      onSelectDraft(draft);
      onClose();
    }
  };

  const handleConfirmImport = () => {
    if (selectedDraft) {
      onSelectDraft(selectedDraft);
      setShowWarning(false);
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="draft-import-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs animate-in fade-in duration-150"
    >
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-xl w-full max-h-[85vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-indigo-50 text-indigo-600 rounded-lg">
              <FileText className="h-5 w-5" />
            </div>
            <div>
              <h3 id="draft-import-modal-title" className="text-base font-semibold text-slate-900">
                Use Existing Draft
              </h3>
              <p className="text-xs text-slate-500">
                Select an existing email draft to import into your campaign
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close modal"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition-colors cursor-pointer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          {showWarning && selectedDraft ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50/80 p-5 space-y-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <h4 className="text-sm font-semibold text-amber-900">
                    Replace Existing Campaign Content?
                  </h4>
                  <p className="text-xs text-amber-800 leading-relaxed">
                    Importing draft &ldquo;<strong>{selectedDraft.subject || "Untitled Draft"}</strong>&rdquo;
                    will overwrite your current campaign subject, body content, and attachments.
                  </p>
                  {selectedDraft.attachment_count && selectedDraft.attachment_count > 0 ? (
                    <p className="text-xs text-amber-700 font-medium">
                      Note: {selectedDraft.attachment_count} attachment{selectedDraft.attachment_count > 1 ? "s" : ""} from this draft will also be imported.
                    </p>
                  ) : null}
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowWarning(false)}
                  className="px-4 py-2 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg shadow-2xs transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleConfirmImport}
                  className="px-4 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-2xs transition-colors cursor-pointer flex items-center gap-1.5"
                >
                  <Check className="h-4 w-4" />
                  <span>Confirm & Import</span>
                </button>
              </div>
            </div>
          ) : null}

          {isLoading && (
            <div className="space-y-3 py-4">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-20 bg-slate-50 rounded-xl animate-pulse border border-slate-100" />
              ))}
            </div>
          )}

          {isError && (
            <div className="p-8 text-center space-y-3">
              <p className="text-sm text-rose-600 font-medium">Failed to load email drafts.</p>
              <button
                type="button"
                onClick={() => refetch()}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg shadow-2xs cursor-pointer"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                <span>Retry</span>
              </button>
            </div>
          )}

          {!isLoading && !isError && drafts.length === 0 && (
            <div className="p-10 text-center space-y-2">
              <div className="w-12 h-12 rounded-xl bg-slate-100 text-slate-400 mx-auto flex items-center justify-center">
                <FileText className="h-6 w-6" />
              </div>
              <p className="text-sm font-medium text-slate-800">No drafts available</p>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                No saved drafts were found for the selected email account. You can create drafts in the mailbox composer.
              </p>
            </div>
          )}

          {!isLoading && !isError && drafts.length > 0 && !showWarning && (
            <div className="space-y-2.5">
              <p className="text-xs text-slate-500 font-medium">
                Found {drafts.length} draft{drafts.length > 1 ? "s" : ""}:
              </p>
              {drafts.map((draft) => {
                const dateStr = draft.updated_at
                  ? new Date(draft.updated_at).toLocaleDateString([], {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })
                  : "";
                const cleanSnippet = (draft.body_text || "")
                  .replace(/\s+/g, " ")
                  .trim()
                  .slice(0, 120);

                return (
                  <div
                    key={draft.id}
                    onClick={() => handleDraftClick(draft)}
                    className="p-4 rounded-xl border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/20 transition-all cursor-pointer group text-left space-y-1.5"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <h4 className="text-xs sm:text-sm font-semibold text-slate-900 group-hover:text-indigo-600 transition-colors truncate">
                        {draft.subject || "(Untitled Draft)"}
                      </h4>
                      <span className="text-[11px] text-slate-400 shrink-0 font-medium">
                        {dateStr}
                      </span>
                    </div>

                    {cleanSnippet ? (
                      <p className="text-xs text-slate-500 line-clamp-2">
                        {cleanSnippet}
                      </p>
                    ) : (
                      <p className="text-xs text-slate-400 italic">No body text preview</p>
                    )}

                    <div className="flex items-center gap-3 pt-1 text-[11px] text-slate-400">
                      {draft.recipients && draft.recipients.length > 0 && (
                        <span>To: {draft.recipients.join(", ")}</span>
                      )}
                      {draft.attachment_count && draft.attachment_count > 0 ? (
                        <span className="inline-flex items-center gap-1 font-medium text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded">
                          <Paperclip className="h-3 w-3" />
                          <span>{draft.attachment_count} attachment{draft.attachment_count > 1 ? "s" : ""}</span>
                        </span>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-100 bg-slate-50 flex items-center justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-medium text-slate-700 bg-white hover:bg-slate-100 border border-slate-200 rounded-lg shadow-2xs transition-colors cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
