import React from "react";
import { useQuery } from "@tanstack/react-query";
import { X, PenTool, Check, Award } from "lucide-react";
import { signaturesApi } from "../../services/api";
import type { EmailSignatureItem } from "../../types/emails";

interface SignatureModalProps {
  isOpen: boolean;
  accountId?: number;
  onClose: () => void;
  onSelectSignature: (signature: EmailSignatureItem) => void;
}

export const SignatureModal: React.FC<SignatureModalProps> = ({
  isOpen,
  accountId,
  onClose,
  onSelectSignature,
}) => {
  const { data: signatures = [], isLoading } = useQuery({
    queryKey: ["signatures", accountId],
    queryFn: () => signaturesApi.listSignatures(accountId),
    enabled: isOpen,
    staleTime: 30000,
  });

  if (!isOpen) return null;

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
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-3">
          {isLoading && (
            <div className="space-y-2">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-16 bg-slate-50 rounded-xl animate-pulse" />
              ))}
            </div>
          )}

          {!isLoading && signatures.length === 0 && (
            <div className="p-8 text-center text-slate-500 space-y-2">
              <p className="text-sm font-medium">No signatures found</p>
              <p className="text-xs text-slate-400">
                You can create custom email signatures in the Signatures configuration section.
              </p>
            </div>
          )}

          {!isLoading &&
            signatures.map((sig) => (
              <div
                key={sig.id}
                onClick={() => {
                  onSelectSignature(sig);
                  onClose();
                }}
                className="p-3.5 rounded-xl border border-slate-200 bg-white hover:border-indigo-300 hover:bg-indigo-50/20 transition-all cursor-pointer group"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-slate-900 group-hover:text-indigo-700 transition-colors">
                      {sig.name}
                    </span>
                    {sig.is_default && (
                      <span className="px-1.5 py-0.2 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-0.5">
                        <Award className="h-3 w-3" />
                        Default
                      </span>
                    )}
                  </div>
                  <span className="text-xs font-medium text-indigo-600 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Check className="h-3.5 w-3.5" />
                    Insert
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1 line-clamp-2">
                  {sig.body_text || "HTML Signature"}
                </p>
              </div>
            ))}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-100 bg-slate-50/60 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-900 rounded-lg hover:bg-slate-100 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};
