import React, { useState } from "react";
import DOMPurify from "dompurify";
import { X, Mail, Laptop, Smartphone, CheckCircle } from "lucide-react";

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
  "{{first_name}}": "Alex",
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
  const [deviceMode, setDeviceMode] = useState<"desktop" | "mobile">("desktop");

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
    ADD_ATTR: ["target", "style", "role", "cellpadding", "cellspacing", "border", "align", "valign", "width", "height"],
    ADD_TAGS: ["style"],
  });

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white border border-slate-200 rounded-2xl shadow-2xl max-w-4xl w-full overflow-hidden flex flex-col max-h-[92vh] animate-in fade-in zoom-in-95 duration-150">
        {/* Modal Header */}
        <div className="px-6 py-3.5 border-b border-slate-200 flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center gap-2.5">
            <span className="font-bold text-sm text-slate-900">Email Live Preview</span>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
              Simulated Recipient
            </span>
          </div>

          {/* Device Toggle Buttons */}
          <div className="flex items-center bg-slate-200/70 p-1 rounded-lg text-xs font-semibold text-slate-600">
            <button
              type="button"
              onClick={() => setDeviceMode("desktop")}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition-all ${
                deviceMode === "desktop"
                  ? "bg-white text-indigo-700 shadow-2xs font-bold"
                  : "hover:text-slate-900"
              }`}
            >
              <Laptop className="h-3.5 w-3.5" />
              <span>Desktop (600px)</span>
            </button>
            <button
              type="button"
              onClick={() => setDeviceMode("mobile")}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-md transition-all ${
                deviceMode === "mobile"
                  ? "bg-white text-indigo-700 shadow-2xs font-bold"
                  : "hover:text-slate-900"
              }`}
            >
              <Smartphone className="h-3.5 w-3.5" />
              <span>Mobile (375px)</span>
            </button>
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
        <div className="px-6 py-3 bg-slate-50/50 border-b border-slate-200 text-xs space-y-1 font-sans">
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

        {/* Rendered Email Document Body */}
        <div className="p-6 overflow-y-auto bg-slate-100/80 flex-1 flex items-start justify-center">
          {deviceMode === "desktop" ? (
            /* Desktop Container (600px Standard) */
            <div className="w-full max-w-[660px] bg-white rounded-xl border border-slate-200 shadow-sm p-4 sm:p-6 text-xs leading-relaxed text-slate-800 font-sans space-y-4 my-auto overflow-x-auto">
              {/* Branded Top Banner */}
              <div className="flex items-center gap-2 pb-4 border-b border-slate-100">
                <div className="w-6 h-6 rounded-md bg-indigo-600 flex items-center justify-center text-white text-[14px]">
                  <Mail className="h-3.5 w-3.5" />
                </div>
                <span className="font-bold text-slate-900 tracking-tight">PulseMail</span>
              </div>

              {/* Rendered HTML */}
              <div
                className="prose prose-sm max-w-none text-slate-800 overflow-x-auto pulsemail-preview-canvas"
                dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
              />
            </div>
          ) : (
            /* Mobile Device Frame (375px Screen) */
            <div className="w-[375px] my-auto bg-slate-900 rounded-[36px] p-3 shadow-2xl border-4 border-slate-800">
              {/* Phone Speaker Notch */}
              <div className="w-24 h-4 bg-slate-800 rounded-full mx-auto mb-2 flex items-center justify-center">
                <div className="w-3 h-3 rounded-full bg-slate-900 border border-slate-700" />
              </div>

              {/* Phone Screen Canvas */}
              <div className="bg-white rounded-[26px] overflow-hidden max-h-[580px] overflow-y-auto p-4 text-xs text-slate-800 font-sans shadow-inner">
                {/* Mobile Email Header */}
                <div className="flex items-center gap-2 pb-3 mb-3 border-b border-slate-100">
                  <div className="w-5 h-5 rounded bg-indigo-600 flex items-center justify-center text-white text-[11px]">
                    <Mail className="h-3 w-3" />
                  </div>
                  <span className="font-bold text-xs text-slate-900">PulseMail</span>
                  <span className="ml-auto text-[10px] text-slate-400 font-mono">10:42 AM</span>
                </div>

                {/* Rendered HTML */}
                <div
                  className="prose prose-xs max-w-none text-slate-800 overflow-x-auto"
                  dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
                />
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 border-t border-slate-200 bg-white flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-[11px] text-emerald-600 font-medium">
            <CheckCircle className="h-3.5 w-3.5" />
            <span>Variables resolved • Responsive inline email format</span>
          </div>
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
