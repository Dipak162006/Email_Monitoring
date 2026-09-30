import React, { useState, useRef, useEffect } from "react";
import DOMPurify from "dompurify";
import {
  Mail,
  Edit2,
  MoreVertical,
  Star,
  Copy,
  Eye,
  Trash2,
  Award,
} from "lucide-react";
import type { EmailSignatureItem } from "../../types/emails";

export interface SignatureCardProps {
  signature: EmailSignatureItem;
  accountEmailOrName?: string;
  onEdit: (sig: EmailSignatureItem) => void;
  onSetDefault: (sig: EmailSignatureItem) => void;
  onDuplicate: (sig: EmailSignatureItem) => void;
  onPreview: (sig: EmailSignatureItem) => void;
  onDelete: (sig: EmailSignatureItem) => void;
  isUpdatingDefault?: boolean;
}

function formatRelativeTime(dateString: string): string {
  try {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHours = Math.floor(diffMin / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffDays === 0) {
      if (diffHours === 0) {
        if (diffMin <= 1) return "just now";
        return `${diffMin} minutes ago`;
      }
      return `${diffHours} ${diffHours === 1 ? "hour" : "hours"} ago`;
    }
    if (diffDays === 1) return "yesterday";
    if (diffDays < 7) return `${diffDays} days ago`;
    if (diffDays < 30) {
      const weeks = Math.floor(diffDays / 7);
      return `${weeks} ${weeks === 1 ? "week" : "weeks"} ago`;
    }
    const months = Math.floor(diffDays / 30);
    return `${months} ${months === 1 ? "month" : "months"} ago`;
  } catch {
    return "recently";
  }
}

export const SignatureCard: React.FC<SignatureCardProps> = ({
  signature,
  accountEmailOrName,
  onEdit,
  onSetDefault,
  onDuplicate,
  onPreview,
  onDelete,
  isUpdatingDefault = false,
}) => {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close overflow menu on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsMenuOpen(false);
      }
    }
    if (isMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isMenuOpen]);

  const sanitizedPreview = signature.body_html
    ? DOMPurify.sanitize(signature.body_html)
    : null;

  return (
    <div className="bg-white rounded-xl p-5 shadow-[0_1px_4px_rgba(0,0,0,0.03)] hover:shadow-[0_4px_12px_rgba(0,0,0,0.05)] border border-slate-200/80 transition-all flex flex-col justify-between group">
      <div>
        {/* Top Header Row */}
        <div className="flex items-start justify-between gap-2">
          <h3
            className="font-semibold text-base text-slate-900 group-hover:text-indigo-600 transition-colors line-clamp-1 cursor-pointer"
            onClick={() => onEdit(signature)}
            title={signature.name}
          >
            {signature.name}
          </h3>
          <div className="flex items-center gap-1.5 shrink-0 flex-wrap justify-end">
            <span className="bg-emerald-50 text-emerald-700 border border-emerald-200/60 text-xs px-2.5 py-0.5 rounded-full font-medium flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
              Active
            </span>
            {signature.is_default && (
              <span className="bg-indigo-50 text-indigo-700 border border-indigo-200/60 text-xs px-2.5 py-0.5 rounded-full font-medium flex items-center gap-1">
                <Award className="h-3 w-3" />
                Default
              </span>
            )}
          </div>
        </div>

        {/* Linked Account */}
        <div className="flex items-center gap-1.5 text-slate-500 text-xs mt-1.5">
          <Mail className="h-3.5 w-3.5 text-slate-400 shrink-0" />
          <span className="truncate">{accountEmailOrName || `Account #${signature.email_account_id}`}</span>
        </div>

        {/* Live Preview Container */}
        <div
          className="bg-slate-50/80 border border-slate-100 rounded-lg p-3.5 mt-3.5 text-xs text-slate-600 space-y-1 max-h-[140px] overflow-hidden relative cursor-pointer hover:border-slate-200 transition-colors"
          onClick={() => onPreview(signature)}
          title="Click to view full preview"
        >
          {sanitizedPreview ? (
            <div
              className="line-clamp-4 leading-relaxed font-sans"
              dangerouslySetInnerHTML={{ __html: sanitizedPreview }}
            />
          ) : signature.body_text ? (
            <div className="whitespace-pre-line line-clamp-4 leading-relaxed">
              {signature.body_text}
            </div>
          ) : (
            <div className="text-slate-400 italic">Empty signature content</div>
          )}
        </div>
      </div>

      {/* Footer Row */}
      <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between">
        <span className="text-xs text-slate-400">
          Updated {formatRelativeTime(signature.updated_at)}
        </span>

        <div className="flex items-center gap-1">
          {/* Edit Action */}
          <button
            type="button"
            onClick={() => onEdit(signature)}
            className="flex items-center gap-1 text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50/60 text-xs font-medium px-2.5 py-1 rounded-lg transition-colors"
          >
            <Edit2 className="h-3.5 w-3.5" />
            <span>Edit</span>
          </button>

          {/* Overflow Menu */}
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              onClick={() => setIsMenuOpen((prev) => !prev)}
              className="w-7 h-7 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
              title="More actions"
            >
              <MoreVertical className="h-4 w-4" />
            </button>

            {isMenuOpen && (
              <div className="absolute right-0 bottom-full mb-1.5 w-44 bg-white border border-slate-200 rounded-xl shadow-xl py-1 z-50 text-xs font-medium text-slate-700 text-left animate-in fade-in duration-100">
                {!signature.is_default && (
                  <button
                    type="button"
                    disabled={isUpdatingDefault}
                    onClick={() => {
                      setIsMenuOpen(false);
                      onSetDefault(signature);
                    }}
                    className="w-full px-3.5 py-2 flex items-center gap-2.5 hover:bg-slate-50 text-slate-700 transition-colors text-xs font-medium disabled:opacity-50"
                  >
                    <Star className="h-3.5 w-3.5 text-amber-500 shrink-0" />
                    <span>Mark as Default</span>
                  </button>
                )}

                <button
                  type="button"
                  onClick={() => {
                    setIsMenuOpen(false);
                    onDuplicate(signature);
                  }}
                  className="w-full px-3.5 py-2 flex items-center gap-2.5 hover:bg-slate-50 text-slate-700 transition-colors text-xs font-medium"
                >
                  <Copy className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                  <span>Duplicate</span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setIsMenuOpen(false);
                    onPreview(signature);
                  }}
                  className="w-full px-3.5 py-2 flex items-center gap-2.5 hover:bg-slate-50 text-slate-700 transition-colors text-xs font-medium"
                >
                  <Eye className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                  <span>Preview</span>
                </button>

                <div className="my-1 border-t border-slate-100" />

                <button
                  type="button"
                  onClick={() => {
                    setIsMenuOpen(false);
                    onDelete(signature);
                  }}
                  className="w-full px-3.5 py-2 flex items-center gap-2.5 hover:bg-rose-50 text-rose-600 transition-colors text-xs font-medium"
                >
                  <Trash2 className="h-3.5 w-3.5 shrink-0" />
                  <span>Delete</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
