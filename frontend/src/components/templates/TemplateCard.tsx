import React from "react";
import { MoreHorizontal, Edit2, PlayCircle, PauseCircle, Trash2 } from "lucide-react";
import type { EmailTemplateItem } from "../../types/emails";

export interface TemplateCardProps {
  template: EmailTemplateItem;
  accountEmailOrName?: string;
  onEdit: (template: EmailTemplateItem) => void;
  onToggleActive: (template: EmailTemplateItem) => void;
  onDelete: (template: EmailTemplateItem) => void;
  isTogglingActive?: boolean;
}

export function formatRelativeTime(dateString: string): string {
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return "Recently";
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return "Recently";
  }
}

// Strip HTML tags to produce a safe plain text preview
function extractPlainPreview(html?: string | null, text?: string | null): string {
  if (text && text.trim()) {
    return text.trim();
  }
  if (!html) return "No message body provided";
  const doc = new DOMParser().parseFromString(html, "text/html");
  return doc.body.textContent || doc.body.innerText || "No message body provided";
}

// Extract variables matching {{...}}
function extractVariables(subject?: string, bodyText?: string | null, bodyHtml?: string | null): string[] {
  const combined = `${subject || ""} ${bodyText || ""} ${bodyHtml || ""}`;
  const matches = combined.match(/\{\{[a-zA-Z0-9_]+\}\}/g);
  if (!matches) return [];
  return Array.from(new Set(matches)).slice(0, 4);
}

export const TemplateCard: React.FC<TemplateCardProps> = ({
  template,
  accountEmailOrName,
  onEdit,
  onToggleActive,
  onDelete,
  isTogglingActive = false,
}) => {
  const [isMenuOpen, setIsMenuOpen] = React.useState(false);
  const menuRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsMenuOpen(false);
      }
    };
    if (isMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isMenuOpen]);

  const previewText = extractPlainPreview(template.body_html, template.body_text);
  const variableChips = extractVariables(template.subject, template.body_text, template.body_html);

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-xs hover:shadow-md hover:border-slate-300 transition-all flex flex-col justify-between group">
      <div>
        {/* Top Badges and More Menu */}
        <div className="flex items-start justify-between gap-2 mb-3">
          <div className="flex flex-wrap items-center gap-1.5">
            {template.is_active ? (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/60 select-none">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5 animate-pulse" />
                Active
              </span>
            ) : (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-600 border border-slate-200 select-none">
                Inactive
              </span>
            )}

            {template.email_account_id ? (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-amber-50 text-amber-700 border border-amber-200/60 max-w-[150px] truncate select-none">
                {accountEmailOrName || `Account #${template.email_account_id}`}
              </span>
            ) : (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-indigo-50 text-indigo-700 border border-indigo-200/60 select-none">
                Global
              </span>
            )}
          </div>

          {/* 3-Dots More Menu */}
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              aria-label="Template actions"
              onClick={() => setIsMenuOpen((prev) => !prev)}
              className="p-1 rounded-md text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors focus:outline-none"
            >
              <MoreHorizontal className="h-4 w-4" />
            </button>

            {isMenuOpen && (
              <div className="absolute right-0 mt-1 w-36 bg-white border border-slate-200 rounded-lg shadow-lg py-1 z-20 text-xs animate-in fade-in zoom-in-95 duration-100">
                <button
                  type="button"
                  onClick={() => {
                    setIsMenuOpen(false);
                    onEdit(template);
                  }}
                  className="w-full text-left px-3 py-1.5 hover:bg-slate-50 text-slate-700 flex items-center gap-2"
                >
                  <Edit2 className="h-3.5 w-3.5 text-slate-500" />
                  Edit
                </button>

                <button
                  type="button"
                  disabled={isTogglingActive}
                  onClick={() => {
                    setIsMenuOpen(false);
                    onToggleActive(template);
                  }}
                  className="w-full text-left px-3 py-1.5 hover:bg-slate-50 text-slate-700 flex items-center gap-2"
                >
                  {template.is_active ? (
                    <>
                      <PauseCircle className="h-3.5 w-3.5 text-slate-500" />
                      Deactivate
                    </>
                  ) : (
                    <>
                      <PlayCircle className="h-3.5 w-3.5 text-slate-500" />
                      Activate
                    </>
                  )}
                </button>

                <div className="h-px bg-slate-100 my-1" />

                <button
                  type="button"
                  onClick={() => {
                    setIsMenuOpen(false);
                    onDelete(template);
                  }}
                  className="w-full text-left px-3 py-1.5 hover:bg-rose-50 text-rose-600 flex items-center gap-2"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Template Title */}
        <h3 className="text-sm font-semibold text-slate-900 group-hover:text-indigo-600 transition-colors line-clamp-1">
          {template.name}
        </h3>

        {/* Subject Preview */}
        <p className="text-xs font-medium text-slate-700 mt-1 line-clamp-1">
          <span className="text-slate-400 font-normal">Subj: </span>
          {template.subject || <span className="text-slate-400 italic">No subject</span>}
        </p>

        {/* Short Body Preview */}
        <p className="text-xs text-slate-500 mt-2 line-clamp-2 leading-relaxed">
          {previewText}
        </p>

        {/* Variable Chips */}
        <div className="mt-3.5 flex flex-wrap items-center gap-1.5">
          {variableChips.length > 0 ? (
            variableChips.map((v) => (
              <span
                key={v}
                className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-100 text-slate-700 border border-slate-200 select-none"
              >
                {v}
              </span>
            ))
          ) : (
            <span className="text-[11px] text-slate-400 italic">No variables attached</span>
          )}
        </div>
      </div>

      {/* Card Bottom Footer */}
      <div className="pt-4 mt-4 border-t border-slate-100 flex items-center justify-between">
        <span className="text-[11px] text-slate-400 font-medium">
          Updated {formatRelativeTime(template.updated_at)}
        </span>
        <button
          type="button"
          onClick={() => onEdit(template)}
          className="px-2.5 py-1 rounded-md text-xs font-medium text-indigo-600 bg-indigo-50/50 hover:bg-indigo-50 border border-indigo-200/80 transition-colors"
        >
          Edit
        </button>
      </div>
    </div>
  );
};
