import React from "react";
import DOMPurify from "dompurify";
import { Tag, Send, FileText, Users, Edit, Paperclip } from "lucide-react";
import type { AuthorizedEmailAccount } from "../../types/emails";
import type { CampaignAttachment } from "../../types/campaign";

interface CampaignReviewStepProps {
  name: string;
  subject: string;
  bodyHtml: string;
  selectedSender?: AuthorizedEmailAccount | null;
  attachments?: CampaignAttachment[];
  sendIntervalSeconds?: number;
  onEditStep: (stepNumber: number) => void;
}

export const CampaignReviewStep: React.FC<CampaignReviewStepProps> = ({
  name,
  subject,
  bodyHtml,
  selectedSender,
  attachments = [],
  sendIntervalSeconds = 0,
  onEditStep,
}) => {
  // Format provider name
  const formatProvider = (p?: string) => {
    switch (p?.toUpperCase()) {
      case "GMAIL":
      case "GOOGLE":
        return "Google Workspace";
      case "OUTLOOK":
      case "OFFICE365":
      case "MICROSOFT":
        return "Microsoft 365";
      case "SMTP_IMAP":
      case "SMTP":
        return "Custom SMTP";
      case "ZOHO":
        return "Zoho Mail";
      default:
        return p || "Email Account";
    }
  };

  const senderInitials = (selectedSender?.name || selectedSender?.email_address || "MB")
    .split(" ")
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const sanitizedHtml = DOMPurify.sanitize(
    bodyHtml || "<p class='text-slate-400 italic'>No content provided.</p>",
    { ADD_ATTR: ["target"] }
  );

  return (
    <section className="space-y-6">
      <div className="space-y-1">
        <h2 className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight">
          Review Campaign
        </h2>
        <p className="text-xs sm:text-sm text-slate-500">
          Review all settings before continuing to the recipient allocation phase.
        </p>
      </div>

      <div className="space-y-4">
        {/* Card 1: Campaign Details */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 sm:p-6 shadow-2xs flex items-start justify-between gap-4">
          <div className="space-y-3 min-w-0">
            <div className="flex items-center gap-2">
              <Tag className="h-4 w-4 text-indigo-600 shrink-0" />
              <span className="text-[11px] uppercase tracking-wider font-semibold text-slate-500">
                Campaign Details
              </span>
            </div>
            <div>
              <p className="text-xs text-slate-500">Internal Name</p>
              <p
                id="review-campaign-name"
                className="text-xs sm:text-sm font-semibold text-slate-900 truncate mt-0.5"
              >
                {name || "Untitled Campaign"}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Subject Line</p>
              <p
                id="review-subject"
                className="text-xs sm:text-sm text-slate-800 truncate mt-0.5"
              >
                {subject || <span className="text-slate-400 italic">No subject set</span>}
              </p>
            </div>
            <div>
              <p className="text-xs text-slate-500">Sending Interval</p>
              <p
                id="review-sending-interval"
                className="text-xs sm:text-sm text-slate-800 font-medium truncate mt-0.5"
              >
                {sendIntervalSeconds && sendIntervalSeconds > 0
                  ? sendIntervalSeconds % 60 === 0
                    ? `${sendIntervalSeconds / 60} ${sendIntervalSeconds / 60 === 1 ? "minute" : "minutes"}`
                    : `${sendIntervalSeconds} seconds`
                  : "No intentional delay"}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => onEditStep(1)}
            aria-label="Edit Campaign Details"
            className="px-3 py-1.5 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-xs font-semibold text-indigo-600 flex items-center gap-1.5 transition-colors shrink-0 shadow-2xs"
          >
            <Edit className="h-3.5 w-3.5" />
            <span>Edit</span>
          </button>
        </div>

        {/* Card 2: Sender Account */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 sm:p-6 shadow-2xs flex items-start justify-between gap-4">
          <div className="space-y-3 min-w-0">
            <div className="flex items-center gap-2">
              <Send className="h-4 w-4 text-indigo-600 shrink-0" />
              <span className="text-[11px] uppercase tracking-wider font-semibold text-slate-500">
                Sender Account
              </span>
            </div>

            {selectedSender ? (
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-indigo-100 text-indigo-700 flex items-center justify-center text-xs font-bold shrink-0">
                  {senderInitials}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p
                      id="review-sender-name"
                      className="text-xs sm:text-sm font-semibold text-slate-900 truncate"
                    >
                      {selectedSender.name}
                    </p>
                    <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[10px] font-medium border border-slate-200">
                      {formatProvider(selectedSender.provider)}
                    </span>
                  </div>
                  <p
                    id="review-sender-email"
                    className="text-xs text-slate-500 truncate"
                  >
                    {selectedSender.email_address}
                  </p>
                </div>
              </div>
            ) : (
              <p className="text-xs text-red-600 font-medium">
                No sender account selected
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={() => onEditStep(2)}
            aria-label="Edit Sender Account"
            className="px-3 py-1.5 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-xs font-semibold text-indigo-600 flex items-center gap-1.5 transition-colors shrink-0 shadow-2xs"
          >
            <Edit className="h-3.5 w-3.5" />
            <span>Edit</span>
          </button>
        </div>

        {/* Card 3: Email Content */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 sm:p-6 shadow-2xs space-y-3">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-indigo-600 shrink-0" />
              <span className="text-[11px] uppercase tracking-wider font-semibold text-slate-500">
                Email Content
              </span>
            </div>
            <button
              type="button"
              onClick={() => onEditStep(3)}
              aria-label="Edit Email Content"
              className="px-3 py-1.5 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-xs font-semibold text-indigo-600 flex items-center gap-1.5 transition-colors shrink-0 shadow-2xs"
            >
              <Edit className="h-3.5 w-3.5" />
              <span>Edit</span>
            </button>
          </div>

          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200/80 space-y-2">
            <p className="text-[10px] uppercase tracking-wider font-semibold text-slate-400">
              Message Template Preview
            </p>
            <div
              id="review-content-snippet"
              dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
              className="text-xs sm:text-sm text-slate-800 leading-relaxed max-h-48 overflow-y-auto pr-2 space-y-2"
            />
          </div>

          {attachments.length > 0 && (
            <div className="pt-2 border-t border-slate-100 space-y-2">
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                <Paperclip className="h-3.5 w-3.5 text-slate-400" />
                <span>Attachments ({attachments.length})</span>
              </span>
              <div className="flex flex-wrap gap-2">
                {attachments.map((att) => (
                  <span
                    key={att.id}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200"
                  >
                    <Paperclip className="h-3 w-3 text-slate-400" />
                    <span>{att.file_name}</span>
                    <span className="text-slate-400 text-[10px]">
                      ({(att.file_size / 1024).toFixed(0)} KB)
                    </span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Card 4: Recipients Placeholder */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 sm:p-6 shadow-2xs flex items-start gap-3.5">
          <div className="w-10 h-10 rounded-xl bg-slate-100 text-slate-600 flex items-center justify-center shrink-0">
            <Users className="h-5 w-5" />
          </div>
          <div className="min-w-0 space-y-0.5">
            <h3 className="text-xs sm:text-sm font-semibold text-slate-900">
              Recipients Configuration
            </h3>
            <p className="text-xs text-slate-500 leading-relaxed">
              Recipients will be configured in the next step.
            </p>
            <span className="inline-block pt-1 text-[11px] font-medium text-indigo-600">
              Audience selection and recipient lists ready after draft save →
            </span>
          </div>
        </div>
      </div>
    </section>
  );
};
