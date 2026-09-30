import React from "react";
import DOMPurify from "dompurify";
import { X, Mail, Award } from "lucide-react";
import type { EmailSignatureItem } from "../../types/emails";

export interface SignaturePreviewModalProps {
  isOpen: boolean;
  signature: EmailSignatureItem | null;
  accountEmailOrName?: string;
  onClose: () => void;
}

export const SignaturePreviewModal: React.FC<SignaturePreviewModalProps> = ({
  isOpen,
  signature,
  accountEmailOrName,
  onClose,
}) => {
  if (!isOpen || !signature) return null;

  const sanitizedHtml = signature.body_html
    ? DOMPurify.sanitize(signature.body_html)
    : null;

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white border border-slate-200 rounded-2xl shadow-2xl max-w-xl w-full flex flex-col max-h-[90vh] overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/80">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-slate-900">{signature.name}</h3>
              {signature.is_default && (
                <span className="bg-indigo-50 text-indigo-700 border border-indigo-200/60 text-[11px] px-2 py-0.5 rounded-full font-medium flex items-center gap-1">
                  <Award className="h-3 w-3" />
                  Default
                </span>
              )}
            </div>
            {accountEmailOrName && (
              <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-0.5">
                <Mail className="h-3.5 w-3.5 text-slate-400" />
                <span>{accountEmailOrName}</span>
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content: Realistic Email Preview */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          <div className="bg-slate-50/70 border border-slate-200/80 rounded-xl p-5 font-sans text-sm text-slate-800 space-y-4">
            {/* Mock Email Message */}
            <div className="space-y-2 text-slate-600 border-b border-slate-200/60 pb-4">
              <p>Hi there,</p>
              <p>
                Thanks for reaching out! Please find the information you requested below. Let me know if you
                have any questions.
              </p>
            </div>

            {/* Signature Presentation */}
            <div className="space-y-1.5 pt-1">
              <div className="text-xs text-slate-400 italic">Best regards,</div>
              {sanitizedHtml ? (
                <div
                  className="prose prose-sm max-w-none text-slate-800 leading-relaxed"
                  dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
                />
              ) : signature.body_text ? (
                <div className="whitespace-pre-line text-slate-800 leading-relaxed">
                  {signature.body_text}
                </div>
              ) : (
                <div className="text-xs text-slate-400 italic">No signature content configured.</div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-slate-100 flex items-center justify-end bg-slate-50/50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-xs transition-all"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
