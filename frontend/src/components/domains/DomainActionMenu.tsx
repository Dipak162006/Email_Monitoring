import React, { useState, useRef, useEffect } from "react";
import {
  MoreHorizontal,
  Eye,
  RefreshCw,
  Key,
  Trash2,
} from "lucide-react";
import type { Domain } from "../../types/domains";
import { cn } from "../../lib/utils";

interface DomainActionMenuProps {
  domain: Domain;
  canManage: boolean;
  isVerifying?: boolean;
  onViewDetails: (domain: Domain) => void;
  onVerify: (domain: Domain) => void;
  onEditDkim: (domain: Domain) => void;
  onDelete: (domain: Domain) => void;
  direction?: "down" | "up";
  className?: string;
}

export const DomainActionMenu: React.FC<DomainActionMenuProps> = ({
  domain,
  canManage,
  isVerifying = false,
  onViewDetails,
  onVerify,
  onEditDkim,
  onDelete,
  direction = "down",
  className,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close menu on click outside or Escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsOpen((prev) => !prev);
  };

  const handleAction = (action: () => void) => (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsOpen(false);
    action();
  };

  return (
    <div
      ref={menuRef}
      className={cn("relative inline-block text-left", isOpen ? "z-50" : "z-10", className)}
    >
      <button
        type="button"
        onClick={handleToggle}
        aria-label="Domain actions"
        aria-haspopup="menu"
        aria-expanded={isOpen}
        className={cn(
          "p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500/20",
          isOpen && "bg-slate-100 text-slate-700 ring-1 ring-slate-200"
        )}
      >
        <MoreHorizontal className="w-4 h-4" />
      </button>

      {isOpen && (
        <div
          role="menu"
          aria-orientation="vertical"
          aria-label="Domain actions menu"
          className={cn(
            "absolute right-0 w-44 rounded-xl bg-white border border-slate-200 shadow-xl py-1 text-xs animate-in fade-in zoom-in-95 duration-100",
            direction === "up" ? "bottom-full mb-1.5" : "top-full mt-1.5"
          )}
        >
          {/* View Details - Accessible to ALL roles */}
          <button
            type="button"
            role="menuitem"
            onClick={handleAction(() => onViewDetails(domain))}
            className="w-full text-left px-3.5 py-2 text-slate-700 hover:bg-slate-50 flex items-center gap-2.5 cursor-pointer transition-colors"
          >
            <Eye className="w-3.5 h-3.5 text-slate-400 shrink-0" />
            <span>View Details</span>
          </button>

          {/* Mutations - Only for OWNER / ADMIN */}
          {canManage && (
            <>
              {/* Verify DNS */}
              <button
                type="button"
                role="menuitem"
                disabled={isVerifying}
                onClick={handleAction(() => onVerify(domain))}
                className="w-full text-left px-3.5 py-2 text-slate-700 hover:bg-slate-50 flex items-center gap-2.5 cursor-pointer transition-colors disabled:opacity-50"
              >
                <RefreshCw
                  className={cn("w-3.5 h-3.5 text-slate-400 shrink-0", isVerifying && "animate-spin text-indigo-600")}
                />
                <span>{isVerifying ? "Verifying..." : "Verify DNS"}</span>
              </button>

              {/* Edit DKIM */}
              <button
                type="button"
                role="menuitem"
                onClick={handleAction(() => onEditDkim(domain))}
                className="w-full text-left px-3.5 py-2 text-slate-700 hover:bg-slate-50 flex items-center gap-2.5 cursor-pointer transition-colors"
              >
                <Key className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                <span>Edit DKIM</span>
              </button>

              <div className="my-1 border-t border-slate-100" />

              {/* Delete Domain */}
              <button
                type="button"
                role="menuitem"
                onClick={handleAction(() => onDelete(domain))}
                className="w-full text-left px-3.5 py-2 text-rose-600 hover:bg-rose-50 flex items-center gap-2.5 cursor-pointer font-medium transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5 text-rose-500 shrink-0" />
                <span>Delete Domain</span>
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
};
