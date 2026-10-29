import React, { useState } from "react";
import DOMPurify from "dompurify";
import {
  FileText,
  Users,
  Edit,
  Paperclip,
  Clock,
  Zap,
  CornerDownRight,
  Mail,
  User,
  Info,
} from "lucide-react";
import type { AuthorizedEmailAccount } from "../../types/emails";
import type {
  CampaignAttachment,
  CampaignStepWritePayload,
  SendingWindowConfig,
} from "../../types/campaign";

interface CampaignReviewStepProps {
  name: string;
  subject: string;
  bodyHtml: string;
  selectedSender?: AuthorizedEmailAccount | null;
  attachments?: CampaignAttachment[];
  sendIntervalSeconds?: number;
  followupSteps?: CampaignStepWritePayload[];
  sendingWindow?: SendingWindowConfig | null;
  onEditStep: (stepNumber: number) => void;
}

export const CampaignReviewStep: React.FC<CampaignReviewStepProps> = ({
  name,
  subject,
  bodyHtml,
  selectedSender,
  attachments = [],
  sendIntervalSeconds = 0,
  followupSteps = [],
  sendingWindow,
  onEditStep,
}) => {
  const [selectedFollowupIdx, setSelectedFollowupIdx] = useState(0);

  // Format provider name
  const formatProvider = (p?: string) => {
    switch (p?.toUpperCase()) {
      case "GMAIL":
      case "GOOGLE":
        return "Google";
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

  const totalSteps = 1 + (followupSteps?.length || 0);

  const hasFollowups = followupSteps && followupSteps.length > 0;
  const safeFollowupIdx = hasFollowups
    ? Math.min(Math.max(0, selectedFollowupIdx), followupSteps.length - 1)
    : 0;
  const activeFollowup = hasFollowups ? followupSteps[safeFollowupIdx] : null;

  // Sanitized Initial Outreach HTML
  const sanitizedInitialHtml = React.useMemo(() => {
    if (
      !bodyHtml ||
      !bodyHtml.trim() ||
      bodyHtml.trim() === "<p><br></p>" ||
      bodyHtml.trim() === "<p></p>"
    ) {
      return null;
    }
    return DOMPurify.sanitize(bodyHtml.trim(), {
      ADD_TAGS: ["style"],
      ADD_ATTR: ["target"],
    });
  }, [bodyHtml]);

  // Sanitized Active Follow-up HTML
  const sanitizedActiveFollowupHtml = React.useMemo(() => {
    if (
      !activeFollowup?.body_html ||
      !activeFollowup.body_html.trim() ||
      activeFollowup.body_html.trim() === "<p><br></p>" ||
      activeFollowup.body_html.trim() === "<p></p>"
    ) {
      return null;
    }
    return DOMPurify.sanitize(activeFollowup.body_html.trim(), {
      ADD_TAGS: ["style"],
      ADD_ATTR: ["target"],
    });
  }, [activeFollowup?.body_html]);

  return (
    <section className="space-y-4 sm:space-y-5">
      {/* Accessible Title */}
      <h2 className="sr-only">Review Campaign</h2>

      <div className="space-y-4 sm:space-y-5">
        {/* Top Row: Details & Sender in a 2-Column Responsive Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-5 items-stretch">
          {/* Card 1: Campaign Details */}
          <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-2xs flex flex-col justify-between gap-4">
            <div className="space-y-3 min-w-0">
              <div className="flex items-center justify-between gap-2 pb-3 border-b border-slate-100">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                    <FileText className="h-4 w-4" />
                  </div>
                  <h3 className="text-sm sm:text-base font-bold text-slate-900 tracking-tight">
                    Campaign Details
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => onEditStep(1)}
                  aria-label="Edit Campaign Details"
                  className="px-2.5 py-1 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-xs font-semibold text-slate-700 hover:text-indigo-600 flex items-center gap-1.5 transition-colors shrink-0 shadow-2xs cursor-pointer"
                >
                  <Edit className="h-3.5 w-3.5" />
                  <span>Edit</span>
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3.5">
                <div>
                  <p className="text-xs text-slate-500 font-medium">Campaign Name</p>
                  <p
                    id="review-campaign-name"
                    className="text-xs sm:text-sm font-semibold text-slate-900 truncate mt-0.5"
                  >
                    {name || "Untitled Campaign"}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 font-medium">Sending Interval</p>
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
                <div>
                  <p className="text-xs text-slate-500 font-medium">Subject Line</p>
                  <p
                    id="review-subject"
                    className="text-xs sm:text-sm text-slate-800 truncate mt-0.5"
                  >
                    {subject || <span className="text-slate-400 italic">No subject set</span>}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 font-medium">Sending Window</p>
                  <p
                    id="review-sending-window"
                    className="text-xs sm:text-sm text-slate-800 font-medium truncate mt-0.5 flex items-center gap-1.5"
                  >
                    <Clock className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                    <span>
                      {sendingWindow?.enabled
                        ? `${sendingWindow.start_time} - ${sendingWindow.end_time} (${sendingWindow.timezone})`
                        : "Unrestricted (24/7)"}
                    </span>
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Card 2: Sender Account */}
          <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-2xs flex flex-col justify-between gap-4">
            <div className="space-y-3 min-w-0">
              <div className="flex items-center justify-between gap-2 pb-3 border-b border-slate-100">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
                    <User className="h-4 w-4" />
                  </div>
                  <h3 className="text-sm sm:text-base font-bold text-slate-900 tracking-tight">
                    Sender Account
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => onEditStep(2)}
                  aria-label="Edit Sender Account"
                  className="px-2.5 py-1 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-xs font-semibold text-slate-700 hover:text-indigo-600 flex items-center gap-1.5 transition-colors shrink-0 shadow-2xs cursor-pointer"
                >
                  <Edit className="h-3.5 w-3.5" />
                  <span>Edit</span>
                </button>
              </div>

              {selectedSender ? (
                <div className="flex items-center justify-between gap-4 flex-wrap sm:flex-nowrap">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-10 h-10 rounded-full bg-slate-100 text-slate-700 flex items-center justify-center text-sm font-bold shrink-0 border border-slate-200">
                      {senderInitials}
                    </div>
                    <div className="min-w-0">
                      <p
                        id="review-sender-name"
                        className="text-xs sm:text-sm font-semibold text-slate-900 truncate"
                      >
                        {selectedSender.name}
                      </p>
                      <p
                        id="review-sender-email"
                        className="text-xs text-slate-500 truncate mt-0.5"
                      >
                        {selectedSender.email_address}
                      </p>
                      <div className="flex items-center gap-1.5 mt-1">
                        <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                        <span className="text-[11px] font-medium text-emerald-600">
                          {selectedSender.is_active ? "Active" : "Inactive"}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-700 shadow-2xs">
                    {selectedSender.provider?.toUpperCase().includes("GOOGLE") ||
                    selectedSender.provider?.toUpperCase() === "GMAIL" ? (
                      <>
                        <svg className="w-3.5 h-3.5" viewBox="0 0 24 24">
                          <path
                            fill="#4285F4"
                            d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17Z"
                          />
                          <path
                            fill="#34A853"
                            d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.33 24 12 24Z"
                          />
                          <path
                            fill="#FBBC05"
                            d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.18 0 9.99 0 12s.45 3.82 1.25 5.42l4.03-3.15Z"
                          />
                          <path
                            fill="#EA4335"
                            d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98Z"
                          />
                        </svg>
                        <span>Google</span>
                      </>
                    ) : (
                      <span>{formatProvider(selectedSender.provider)}</span>
                    )}
                  </div>
                </div>
              ) : (
                <p className="text-xs text-red-600 font-medium">
                  No sender account selected
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Card 3: Email Content & Campaign Sequence (Two-Column Desktop Layout) */}
        <div className="bg-white rounded-xl border border-slate-200/90 p-5 shadow-2xs space-y-4">
          <div className="flex items-center justify-between gap-4 pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2 flex-wrap">
              <Mail className="h-4 w-4 text-indigo-600 shrink-0" />
              <span className="text-sm sm:text-base font-bold text-slate-900 tracking-tight">
                Email Content
              </span>
              <span className="px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 text-xs font-semibold border border-indigo-200/60">
                {totalSteps === 1 ? "Single Outreach Step" : `${totalSteps} Steps in Sequence`}
              </span>
            </div>
            <button
              type="button"
              onClick={() => onEditStep(3)}
              aria-label="Edit Email Content"
              className="px-2.5 py-1 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-xs font-semibold text-slate-700 hover:text-indigo-600 flex items-center gap-1.5 transition-colors shrink-0 shadow-2xs cursor-pointer"
            >
              <Edit className="h-3.5 w-3.5" />
              <span>Edit</span>
            </button>
          </div>

          {/* Two-Column Sequence Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-stretch">
            {/* Left Panel: Initial Outreach */}
            <div className="rounded-xl border border-slate-200/80 bg-slate-50/50 p-4 sm:p-5 flex flex-col space-y-3">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-indigo-600 text-white font-bold text-[11px] flex items-center justify-center shrink-0">
                    1
                  </span>
                  <span className="font-bold text-xs sm:text-sm text-slate-900">
                    Step 1: Initial Outreach
                  </span>
                  <span className="text-[11px] font-semibold text-emerald-600 flex items-center gap-1 ml-1">
                    <Zap className="h-3 w-3 fill-emerald-600" /> Immediate
                  </span>
                </div>
              </div>

              <p className="text-xs font-semibold text-slate-800">
                Subject: "{subject || <span className="italic text-slate-400">No subject</span>}"
              </p>

              {/* Email Preview Frame */}
              <div className="flex-1 w-full bg-white rounded-lg border border-slate-200 shadow-2xs overflow-hidden flex flex-col min-h-[320px] max-h-[460px]">
                {sanitizedInitialHtml ? (
                  <div
                    id="review-content-snippet"
                    className="p-4 sm:p-5 overflow-y-auto flex-1 text-xs text-slate-800 leading-relaxed max-h-72 min-h-[4.5rem] pulsemail-preview-canvas focus:outline-none [scrollbar-width:thin]"
                    dangerouslySetInnerHTML={{ __html: sanitizedInitialHtml }}
                  />
                ) : (
                  <div
                    id="review-content-snippet"
                    className="p-4 sm:p-5 overflow-y-auto flex-1 text-xs text-slate-800 leading-relaxed max-h-72 min-h-[4.5rem] pulsemail-preview-canvas focus:outline-none [scrollbar-width:thin]"
                  >
                    <div className="text-slate-400 italic">No content provided.</div>
                  </div>
                )}
              </div>

              {/* Attachments */}
              {attachments.length > 0 && (
                <div className="pt-2 border-t border-slate-200/60 flex items-center gap-2 flex-wrap">
                  <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1">
                    <Paperclip className="h-3 w-3 text-slate-400" />
                    <span>Attachments ({attachments.length})</span>
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {attachments.map((att) => (
                      <span
                        key={att.id}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-white text-slate-700 border border-slate-200 shadow-2xs"
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

            {/* Right Panel: Follow-up Sequence */}
            <div className="rounded-xl border border-slate-200/80 bg-slate-50/50 p-4 sm:p-5 flex flex-col space-y-3">
              <div className="flex items-start gap-2.5">
                <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0 mt-0.5">
                  <CornerDownRight className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="font-bold text-xs sm:text-sm text-slate-900 leading-tight">
                    Follow-Up Sequence
                  </h3>
                  <p className="text-[11px] sm:text-xs text-slate-500 mt-0.5">
                    Select a step to view its email content.
                  </p>
                </div>
              </div>

              {hasFollowups ? (
                <>
                  {/* Tabs / Segmented Control */}
                  <div className="flex items-center gap-2 flex-wrap">
                    {followupSteps.map((_, idx) => {
                      const isSelected = idx === safeFollowupIdx;
                      return (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => setSelectedFollowupIdx(idx)}
                          className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all shadow-2xs cursor-pointer ${
                            isSelected
                              ? "bg-indigo-600 text-white shadow-xs"
                              : "bg-white text-slate-700 border border-slate-200 hover:bg-slate-100"
                          }`}
                        >
                          Follow-up {idx + 1}
                        </button>
                      );
                    })}
                  </div>

                  {/* Selected Follow-up Step Details */}
                  {activeFollowup && (() => {
                    const isDays =
                      activeFollowup.delay_hours >= 24 && activeFollowup.delay_hours % 24 === 0;
                    const delayText = isDays
                      ? `${activeFollowup.delay_hours / 24} day${activeFollowup.delay_hours / 24 > 1 ? "s" : ""}`
                      : `${activeFollowup.delay_hours} hour${activeFollowup.delay_hours > 1 ? "s" : ""}`;
                    const stepNum = activeFollowup.step_number || safeFollowupIdx + 2;

                    return (
                      <div className="space-y-2.5 flex-1 flex flex-col">
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="flex items-center gap-2">
                            <span className="w-5 h-5 rounded-md bg-indigo-100 text-indigo-700 font-bold text-[11px] flex items-center justify-center shrink-0">
                              {stepNum}
                            </span>
                            <span className="font-bold text-xs sm:text-sm text-slate-900">
                              Follow-Up #{safeFollowupIdx + 1} (Step {stepNum})
                            </span>
                            <span className="text-[11px] text-slate-600 flex items-center gap-1 font-medium bg-white px-2 py-0.5 rounded border border-slate-200/60 shadow-2xs">
                              <Clock className="h-3 w-3 text-slate-400" />
                              <span>Waits {delayText} if no reply</span>
                            </span>
                          </div>
                        </div>

                        {/* Targeting summary */}
                        <div className="flex items-center gap-2 text-xs text-slate-600 flex-wrap">
                          <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                            TARGETING:
                          </span>
                          {activeFollowup.target_tags && activeFollowup.target_tags.length > 0 ? (
                            <div className="flex items-center gap-1 flex-wrap">
                              {activeFollowup.target_tags.map((t) => (
                                <span
                                  key={t}
                                  className="inline-flex items-center px-1.5 py-0.2 rounded bg-indigo-50 text-indigo-700 text-[11px] font-semibold border border-indigo-200/60"
                                >
                                  #{t}
                                </span>
                              ))}
                              <span className="text-[11px] text-slate-400 italic">
                                (OR matching)
                              </span>
                            </div>
                          ) : (
                            <span className="text-[11px] text-slate-500">
                              All recipients (untargeted)
                            </span>
                          )}
                          <span className="text-slate-300">•</span>
                          <span className="text-[11px] text-slate-500">
                            Threaded in same conversation
                          </span>
                        </div>

                        <p className="text-xs font-semibold text-slate-800">
                          Subject: "{activeFollowup.subject || `Re: ${subject || "Subject"}`}"
                        </p>

                        {/* Email Preview Frame */}
                        <div className="flex-1 w-full bg-white rounded-lg border border-slate-200 shadow-2xs overflow-hidden flex flex-col min-h-[300px] max-h-[420px]">
                          {sanitizedActiveFollowupHtml ? (
                            <div
                              className="p-4 sm:p-5 overflow-y-auto flex-1 text-xs text-slate-800 leading-relaxed max-h-64 min-h-[4rem] pulsemail-preview-canvas focus:outline-none [scrollbar-width:thin]"
                              dangerouslySetInnerHTML={{ __html: sanitizedActiveFollowupHtml }}
                            />
                          ) : activeFollowup.body_text?.trim() ? (
                            <div className="p-4 sm:p-5 overflow-y-auto flex-1 text-xs text-slate-800 leading-relaxed max-h-64 min-h-[4rem] whitespace-pre-wrap font-sans focus:outline-none [scrollbar-width:thin]">
                              {activeFollowup.body_text.trim()}
                            </div>
                          ) : (
                            <div className="p-4 sm:p-5 overflow-y-auto flex-1 text-xs text-slate-800 leading-relaxed max-h-64 min-h-[4rem] focus:outline-none [scrollbar-width:thin]">
                              <div className="text-slate-400 italic">No content provided.</div>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })()}
                </>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-white rounded-lg border border-dashed border-slate-200 min-h-[300px]">
                  <CornerDownRight className="h-8 w-8 text-slate-300 mb-2" />
                  <p className="text-xs text-slate-600 font-medium">
                    No follow-up steps configured for this campaign.
                  </p>
                  <p className="text-[11px] text-slate-400 mt-1 max-w-xs">
                    This campaign will send a single outreach email. You can configure automated
                    follow-up steps in the Sequence Editor.
                  </p>
                </div>
              )}

              {/* Accessible Follow-ups Sequence Overview for inactive steps */}
              {hasFollowups && (
                <div className="sr-only" aria-label="Automated follow-up steps summary">
                  <span>Automated Follow-Up Steps ({followupSteps.length})</span>
                  {followupSteps.map((s, idx) => {
                    if (idx === safeFollowupIdx) return null;
                    const isDays = s.delay_hours >= 24 && s.delay_hours % 24 === 0;
                    const delayText = isDays
                      ? `${s.delay_hours / 24} day${s.delay_hours / 24 > 1 ? "s" : ""}`
                      : `${s.delay_hours} hour${s.delay_hours > 1 ? "s" : ""}`;
                    const stepNum = s.step_number || idx + 2;
                    return (
                      <div key={idx}>
                        <span>
                          Follow-Up #{idx + 1} (Step {stepNum})
                        </span>
                        <span>Waits {delayText} if no reply</span>
                        {s.target_tags && s.target_tags.length > 0 ? (
                          s.target_tags.map((t) => <span key={t}>#{t}</span>)
                        ) : (
                          <span>All recipients (untargeted)</span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Card 4: Recipients Section (Compact Full-Width Row) */}
        <div className="bg-white rounded-xl border border-slate-200/90 p-4 sm:p-5 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
              <Users className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-xs sm:text-sm font-bold text-slate-900">
                Recipients Configuration
              </h3>
              <p className="text-xs text-slate-500 mt-0.5 leading-relaxed">
                Next, you'll select which recipients to include in this campaign.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2.5 px-4 py-2.5 rounded-lg bg-indigo-50/50 border border-indigo-100 text-xs text-indigo-900 max-w-md">
            <Info className="h-4 w-4 text-indigo-600 shrink-0" />
            <div>
              <p className="font-semibold text-indigo-900 text-xs">
                Recipients will be configured in the next step.
              </p>
              <p className="text-[11px] text-indigo-600/90 mt-0.5">
                You can import from CSV, select existing lists, or define filters.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};
