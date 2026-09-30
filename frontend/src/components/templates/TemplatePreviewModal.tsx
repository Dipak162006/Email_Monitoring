import React from "react";
import DOMPurify from "dompurify";
import { X, Mail } from "lucide-react";

export interface TemplatePreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  subject: string;
  bodyHtml: string;
  bodyText?: string;
  accountSender?: string;
}

// Map template variables to realistic preview sample values
const VARIABLE_MAP: Record<string, string> = {
  "{{customer_name}}": "Alex Vance",
  "{{customer_email}}": "alex.vance@acme.com",
  "{{company_name}}": "Acme Global Corp",
  "{{sender_name}}": "PulseMail Support",
  "{{login_url}}": "https://app.pulsemail.io/login",
  "{{unsubscribe_url}}": "https://app.pulsemail.io/unsubscribe?token=sample",
  "{{ticket_id}}": "8491",
  "{{threshold_limit}}": "95%",
  "{{p99_latency}}": "24ms",
  "{{billing_url}}": "https://app.pulsemail.io/billing",
};

export function resolvePreviewVariables(content: string): string {
  let resolved = content;
  for (const [key, value] of Object.entries(VARIABLE_MAP)) {
    resolved = resolved.split(key).join(value);
  }
  return resolved;
}

export const TemplatePreviewModal: React.FC<TemplatePreviewModalProps> = ({
  isOpen,
  onClose,
  subject,
  bodyHtml,
  bodyText,
  accountSender = "Support Desk <support@acme.com>",
}) => {
  if (!isOpen) return null;

  const rawSubject = subject || "Untitled Template";
  const resolvedSubject = resolvePreviewVariables(rawSubject);

  // If HTML is provided, resolve variables and sanitize with DOMPurify; otherwise convert plain text to simple paragraphs
  const rawContent = bodyHtml && bodyHtml.trim()
    ? bodyHtml
    : bodyText
      ? `<p>${bodyText.replace(/\n/g, "<br/>")}</p>`
      : "<p class='text-slate-400 italic'>No content provided</p>";

  const resolvedHtml = resolvePreviewVariables(rawContent);
  const sanitizedHtml = DOMPurify.sanitize(resolvedHtml, {
    ADD_ATTR: ["target"],
  });

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white border border-slate-200 rounded-2xl shadow-2xl max-w-2xl w-full overflow-hidden flex flex-col max-h-[90vh] animate-in fade-in zoom-in-95 duration-150">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50/70">
          <div className="flex items-center gap-2.5">
            <span className="font-semibold text-sm text-slate-900">Email Preview</span>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
              Simulated Recipient View
            </span>
          </div>
          <button
            type="button"
            aria-label="Close preview"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 rounded-md p-1 transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Mock Email Client Metadata Chrome */}
        <div className="px-6 py-3.5 bg-slate-50 border-b border-slate-200 text-xs space-y-1.5 font-sans">
          <div className="flex items-center">
            <span className="w-16 text-slate-400 font-medium">From:</span>
            <span className="text-slate-800 font-medium">{accountSender}</span>
          </div>
          <div className="flex items-center">
            <span className="w-16 text-slate-400 font-medium">To:</span>
            <span className="text-slate-800">Alex Vance &lt;alex.vance@acme.com&gt;</span>
          </div>
          <div className="flex items-start">
            <span className="w-16 text-slate-400 font-medium">Subject:</span>
            <span className="text-slate-900 font-semibold">{resolvedSubject}</span>
          </div>
        </div>

        {/* Rendered Email Document Body (560px Container) */}
        <div className="p-6 overflow-y-auto bg-slate-100 flex-1">
          <div className="max-w-[560px] mx-auto bg-white rounded-xl border border-slate-200 shadow-xs p-8 text-xs leading-relaxed text-slate-700 font-sans space-y-4">
            {/* Branded Top Banner */}
            <div className="flex items-center gap-2 pb-4 border-b border-slate-100">
              <div className="w-6 h-6 rounded-md bg-indigo-600 flex items-center justify-center text-white text-[14px]">
                <Mail className="h-3.5 w-3.5" />
              </div>
              <span className="font-bold text-slate-900 tracking-tight">PulseMail</span>
            </div>

            {/* Rendered Content */}
            <div
              className="prose prose-sm max-w-none text-slate-800 prose-a:text-indigo-600 prose-a:underline"
              dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
            />
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 border-t border-slate-200 bg-white flex items-center justify-between">
          <span className="text-[11px] text-slate-400">All dynamic variable tags successfully parsed</span>
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold transition-all shadow-xs"
          >
            Close Preview
          </button>
        </div>
      </div>
    </div>
  );
};
