import React, { useEffect, useLayoutEffect, useRef, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import {
  MoreHorizontal,
  Eye,
  Edit,
  Pause,
  Play,
  XCircle,
  Trash2,
  Send,
  Loader2,
  Users,
} from "lucide-react";
import type { Campaign } from "../../types/campaign";

interface CampaignActionsMenuProps {
  campaign: Campaign;
  isOpen: boolean;
  onToggle: (e: React.MouseEvent) => void;
  onClose: () => void;
  onView: (campaign: Campaign) => void;
  onEdit?: (campaign: Campaign) => void;
  onManageRecipients?: (campaign: Campaign) => void;
  onSendNow?: (campaign: Campaign) => void;
  onPause?: (campaign: Campaign) => void;
  onResume?: (campaign: Campaign) => void;
  onCancel?: (campaign: Campaign) => void;
  onDelete?: (campaign: Campaign) => void;
  isMutating?: boolean;
}

export const CampaignActionsMenu: React.FC<CampaignActionsMenuProps> = ({
  campaign,
  isOpen,
  onToggle,
  onClose,
  onView,
  onEdit,
  onManageRecipients,
  onSendNow,
  onPause,
  onResume,
  onCancel,
  onDelete,
  isMutating = false,
}) => {
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const [coords, setCoords] = useState<{
    top?: number;
    bottom?: number;
    left: number;
    width: number;
  } | null>(null);

  const updatePosition = useCallback(() => {
    if (!buttonRef.current || !buttonRef.current.isConnected) {
      return;
    }
    const rect = buttonRef.current.getBoundingClientRect();
    const menuWidth = 192;
    const estimatedHeight = 220;

    const viewportWidth = window.innerWidth || 1024;
    const viewportHeight = window.innerHeight || 768;

    // Viewport boundary clamping for horizontal alignment
    let left = rect.right - menuWidth;
    if (left < 8) {
      left = Math.max(8, rect.left);
    }
    if (left + menuWidth > viewportWidth - 8) {
      left = Math.max(8, viewportWidth - menuWidth - 8);
    }

    // Check vertical space: flip upward if near viewport bottom
    const spaceBelow = viewportHeight - rect.bottom;
    const shouldFlipUp = spaceBelow < estimatedHeight && rect.top > estimatedHeight;

    if (shouldFlipUp) {
      setCoords({
        bottom: viewportHeight - rect.top + 4,
        left,
        width: menuWidth,
      });
    } else {
      setCoords({
        top: rect.bottom + 4,
        left,
        width: menuWidth,
      });
    }
  }, []);

  // Compute position immediately when opening, or reset when closed
  useLayoutEffect(() => {
    if (!isOpen) {
      setCoords(null);
      return;
    }

    if (!buttonRef.current || !buttonRef.current.isConnected) {
      onClose();
      return;
    }

    updatePosition();
  }, [isOpen, onClose, updatePosition]);

  // Close on Escape, click outside, or update position on scroll/resize
  useEffect(() => {
    if (!isOpen) return;

    // Close menu if trigger button was removed from the DOM
    if (!buttonRef.current || !buttonRef.current.isConnected) {
      onClose();
      return;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        buttonRef.current?.focus();
      }
    };

    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        menuRef.current &&
        !menuRef.current.contains(target) &&
        buttonRef.current &&
        !buttonRef.current.contains(target)
      ) {
        onClose();
      }
    };

    const handleScrollOrResize = () => {
      updatePosition();
    };

    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("mousedown", handleClickOutside);
    window.addEventListener("resize", handleScrollOrResize);
    window.addEventListener("scroll", handleScrollOrResize, true);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("mousedown", handleClickOutside);
      window.removeEventListener("resize", handleScrollOrResize);
      window.removeEventListener("scroll", handleScrollOrResize, true);
    };
  }, [isOpen, onClose, updatePosition]);

  const status = (campaign.status || "").toUpperCase();

  return (
    <div className="inline-block text-left" onClick={(e) => e.stopPropagation()}>
      <button
        ref={buttonRef}
        type="button"
        onClick={onToggle}
        disabled={isMutating}
        aria-haspopup="menu"
        aria-expanded={isOpen}
        aria-label={`Actions for campaign ${campaign.name}`}
        className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100/80 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-colors disabled:opacity-50"
      >
        {isMutating ? (
          <Loader2 className="h-4 w-4 animate-spin text-slate-500" />
        ) : (
          <MoreHorizontal className="h-4 w-4" />
        )}
      </button>

      {isOpen &&
        coords &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            ref={menuRef}
            role="menu"
            aria-orientation="vertical"
            style={{
              position: "fixed",
              top: coords.top !== undefined ? `${coords.top}px` : undefined,
              bottom: coords.bottom !== undefined ? `${coords.bottom}px` : undefined,
              left: `${coords.left}px`,
              width: `${coords.width}px`,
              zIndex: 9999,
            }}
            className="rounded-xl bg-white shadow-xl border border-slate-200/90 p-1.5 text-left animate-in fade-in zoom-in-95 duration-100 focus:outline-none"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header indicator */}
            <div className="px-2 py-1 text-slate-400 text-[10px] uppercase font-bold tracking-wider">
              {status} Actions
            </div>

            {/* View Details - available for all states */}
            <button
              type="button"
              role="menuitem"
              onClick={(e) => {
                e.stopPropagation();
                onView(campaign);
                onClose();
              }}
              className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg hover:bg-slate-100 text-xs text-slate-700 transition-colors"
            >
              <Eye className="h-3.5 w-3.5 text-slate-500" />
              <span>View Details</span>
            </button>

            {/* Manage Recipients */}
            {onManageRecipients && (
              <button
                type="button"
                role="menuitem"
                onClick={(e) => {
                  e.stopPropagation();
                  onManageRecipients(campaign);
                  onClose();
                }}
                className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg hover:bg-slate-100 text-xs text-slate-700 transition-colors"
              >
                <Users className="h-3.5 w-3.5 text-slate-500" />
                <span>Manage Recipients</span>
              </button>
            )}

            {/* DRAFT specific */}
            {status === "DRAFT" && onEdit && (
              <button
                type="button"
                role="menuitem"
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit(campaign);
                  onClose();
                }}
                className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg hover:bg-slate-100 text-xs text-slate-700 transition-colors"
              >
                <Edit className="h-3.5 w-3.5 text-slate-500" />
                <span>Edit Draft</span>
              </button>
            )}

            {/* SCHEDULED specific */}
            {status === "SCHEDULED" && onSendNow && (
              <button
                type="button"
                role="menuitem"
                onClick={(e) => {
                  e.stopPropagation();
                  onSendNow(campaign);
                  onClose();
                }}
                className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg hover:bg-slate-100 text-xs text-indigo-600 font-medium transition-colors"
              >
                <Send className="h-3.5 w-3.5 text-indigo-500" />
                <span>Send Now</span>
              </button>
            )}

            {/* RUNNING specific */}
            {status === "RUNNING" && onPause && (
              <button
                type="button"
                role="menuitem"
                onClick={(e) => {
                  e.stopPropagation();
                  onPause(campaign);
                  onClose();
                }}
                className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg hover:bg-amber-50 text-xs text-amber-700 font-medium transition-colors"
              >
                <Pause className="h-3.5 w-3.5 text-amber-600" />
                <span>Pause Campaign</span>
              </button>
            )}

            {/* PAUSED specific */}
            {status === "PAUSED" && onResume && (
              <button
                type="button"
                role="menuitem"
                onClick={(e) => {
                  e.stopPropagation();
                  onResume(campaign);
                  onClose();
                }}
                className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg hover:bg-emerald-50 text-xs text-emerald-700 font-medium transition-colors"
              >
                <Play className="h-3.5 w-3.5 text-emerald-600" />
                <span>Resume Campaign</span>
              </button>
            )}

            {/* Cancel Campaign - available for SCHEDULED, QUEUED, RUNNING, PAUSED */}
            {(status === "SCHEDULED" ||
              status === "QUEUED" ||
              status === "RUNNING" ||
              status === "PAUSED") &&
              onCancel && (
                <>
                  <div className="h-px bg-slate-100 my-1" />
                  <button
                    type="button"
                    role="menuitem"
                    onClick={(e) => {
                      e.stopPropagation();
                      onCancel(campaign);
                      onClose();
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg hover:bg-rose-50 text-xs text-rose-600 transition-colors"
                  >
                    <XCircle className="h-3.5 w-3.5 text-rose-500" />
                    <span>Cancel Campaign</span>
                  </button>
                </>
              )}

            {/* Delete Draft / Finished Campaign - available for DRAFT, COMPLETED, CANCELLED, FAILED */}
            {(status === "DRAFT" ||
              status === "COMPLETED" ||
              status === "CANCELLED" ||
              status === "FAILED") &&
              onDelete && (
                <>
                  <div className="h-px bg-slate-100 my-1" />
                  <button
                    type="button"
                    role="menuitem"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete(campaign);
                      onClose();
                    }}
                    className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg hover:bg-rose-50 text-xs text-rose-600 transition-colors"
                  >
                    <Trash2 className="h-3.5 w-3.5 text-rose-500" />
                    <span>{status === "DRAFT" ? "Delete Draft" : "Delete Campaign"}</span>
                  </button>
                </>
              )}
          </div>,
          document.body
        )}
    </div>
  );
};
