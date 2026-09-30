import React from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import type { EmailSignatureItem } from "../../types/emails";

export interface DeleteSignatureModalProps {
  isOpen: boolean;
  signature: EmailSignatureItem | null;
  onClose: () => void;
  onConfirm: () => void;
  isDeleting?: boolean;
}

export const DeleteSignatureModal: React.FC<DeleteSignatureModalProps> = ({
  isOpen,
  signature,
  onClose,
  onConfirm,
  isDeleting = false,
}) => {
  if (!isOpen || !signature) return null;

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white border border-slate-200 rounded-2xl shadow-xl max-w-md w-full p-6 text-center animate-in fade-in zoom-in-95 duration-150">
        <div className="w-12 h-12 bg-rose-50 text-rose-600 rounded-full mx-auto flex items-center justify-center mb-4">
          <AlertTriangle className="h-6 w-6" />
        </div>

        <h3 className="text-base font-bold text-slate-900">Delete Email Signature?</h3>
        <p className="text-xs text-slate-500 mt-2 mb-6 leading-relaxed">
          Are you sure you want to delete <strong className="text-slate-800">"{signature.name}"</strong>? This action
          cannot be undone, and outgoing emails will no longer have this signature appended.
        </p>

        <div className="flex items-center justify-center gap-2.5">
          <button
            type="button"
            disabled={isDeleting}
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={isDeleting}
            onClick={onConfirm}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold transition-all shadow-xs disabled:opacity-50"
          >
            {isDeleting ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Deleting...</span>
              </>
            ) : (
              <span>Delete Signature</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
