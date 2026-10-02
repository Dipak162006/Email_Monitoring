import { useState, useRef, useEffect, useCallback, useId } from "react";
import { ChevronDown, Check, Info, Building2 } from "lucide-react";
import { useWorkspace } from "../../hooks/useWorkspace";
import { cn } from "../../lib/utils";
import type { CompanyRole } from "../../types/auth";

// Palette for company monogram avatars
const MONOGRAM_COLORS = [
  "bg-indigo-600",
  "bg-emerald-600",
  "bg-violet-600",
  "bg-sky-600",
  "bg-amber-600",
  "bg-teal-600",
  "bg-rose-600",
];

export function getCompanyColor(companyId: number): string {
  return MONOGRAM_COLORS[Math.abs(companyId) % MONOGRAM_COLORS.length];
}

export function getCompanyInitials(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "W";
  const words = trimmed.split(/\s+/).filter(Boolean);
  if (words.length >= 2) {
    return (words[0][0] + words[1][0]).toUpperCase();
  }
  return trimmed.slice(0, 2).toUpperCase();
}

export function formatRole(role: CompanyRole | string | null | undefined): string {
  if (!role) return "Member";
  const upper = role.toUpperCase();
  switch (upper) {
    case "OWNER":
      return "Owner";
    case "ADMIN":
      return "Admin";
    case "MEMBER":
      return "Member";
    default:
      return role.charAt(0).toUpperCase() + role.slice(1).toLowerCase();
  }
}

export function WorkspaceSwitcher() {
  const { currentCompany, currentCompanyId, currentRole, companies, setActiveCompanyId } =
    useWorkspace();

  const [isOpen, setIsOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();

  const hasMultipleCompanies = companies && companies.length > 1;

  // Close when clicking outside
  useEffect(() => {
    function handlePointerDown(e: MouseEvent | TouchEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener("mousedown", handlePointerDown);
      document.addEventListener("touchstart", handlePointerDown);
      return () => {
        document.removeEventListener("mousedown", handlePointerDown);
        document.removeEventListener("touchstart", handlePointerDown);
      };
    }
  }, [isOpen]);

  // Handle Escape key and keyboard focus
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (!isOpen) return;

      if (e.key === "Escape") {
        e.preventDefault();
        setIsOpen(false);
        buttonRef.current?.focus();
      }
    }

    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => {
        document.removeEventListener("keydown", handleKeyDown);
      };
    }
  }, [isOpen]);

  // Keyboard navigation within the dropdown list
  const handleListKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!listRef.current) return;
    const items = Array.from(
      listRef.current.querySelectorAll<HTMLButtonElement>('[role="option"]')
    );
    const activeIndex = items.findIndex((el) => el === document.activeElement);

    if (e.key === "ArrowDown") {
      e.preventDefault();
      const nextIndex = activeIndex < items.length - 1 ? activeIndex + 1 : 0;
      items[nextIndex]?.focus();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const prevIndex = activeIndex > 0 ? activeIndex - 1 : items.length - 1;
      items[prevIndex]?.focus();
    } else if (e.key === "Tab") {
      setIsOpen(false);
    }
  };

  const toggleDropdown = useCallback(() => {
    if (!hasMultipleCompanies) return;
    setIsOpen((prev) => !prev);
  }, [hasMultipleCompanies]);

  const handleSelect = (companyId: number) => {
    if (companyId !== currentCompanyId) {
      setActiveCompanyId(companyId);
    }
    setIsOpen(false);
    buttonRef.current?.focus();
  };

  if (!currentCompany) {
    return null;
  }

  const activeInitials = getCompanyInitials(currentCompany.name);
  const activeColor = getCompanyColor(currentCompany.id);
  const activeRoleLabel = formatRole(currentRole || currentCompany.role);

  return (
    <div className="relative shrink-0" ref={wrapperRef}>
      {/* Selector Trigger Button */}
      <button
        ref={buttonRef}
        type="button"
        id="workspace-switcher-trigger"
        onClick={toggleDropdown}
        aria-haspopup={hasMultipleCompanies ? "listbox" : undefined}
        aria-expanded={hasMultipleCompanies ? isOpen : undefined}
        aria-controls={hasMultipleCompanies ? listboxId : undefined}
        aria-label={`Active workspace: ${currentCompany.name}, role: ${activeRoleLabel}${
          hasMultipleCompanies ? ". Click to switch workspace." : ""
        }`}
        title={`${currentCompany.name} (${activeRoleLabel})`}
        disabled={!hasMultipleCompanies}
        className={cn(
          "inline-flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-medium text-slate-800 shadow-2xs transition-all",
          hasMultipleCompanies
            ? "hover:bg-slate-50 hover:border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 cursor-pointer"
            : "cursor-default"
        )}
      >
        {/* Monogram Avatar */}
        <span
          className={cn(
            "w-5 h-5 rounded text-white font-semibold text-[10px] flex items-center justify-center tracking-tight shrink-0",
            activeColor
          )}
          aria-hidden="true"
        >
          {activeInitials || <Building2 className="w-3 h-3" />}
        </span>

        {/* Company Name (Truncated) */}
        <span className="font-semibold text-slate-900 max-w-[110px] sm:max-w-[140px] md:max-w-[160px] truncate text-left">
          {currentCompany.name}
        </span>

        {/* Role Pill */}
        <span className="text-[10px] font-medium bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded border border-slate-200 shrink-0">
          {activeRoleLabel}
        </span>

        {/* Dropdown Chevron (Only shown when multiple companies exist) */}
        {hasMultipleCompanies && (
          <ChevronDown
            className={cn(
              "w-3.5 h-3.5 text-slate-400 shrink-0 transform transition-transform duration-150",
              isOpen && "rotate-180"
            )}
            aria-hidden="true"
          />
        )}
      </button>

      {/* Dropdown Menu */}
      {isOpen && hasMultipleCompanies && (
        <div
          id={listboxId}
          className="absolute left-0 mt-2 w-80 bg-white rounded-xl shadow-xl border border-slate-200 z-50 overflow-hidden divide-y divide-slate-100 transition-all duration-150 origin-top-left animate-in fade-in zoom-in-95 duration-100"
          onKeyDown={handleListKeyDown}
        >
          {/* Menu Header */}
          <div className="px-3.5 py-2.5 bg-slate-50/80 flex items-center justify-between select-none">
            <div>
              <h3 className="text-xs font-bold text-slate-900">Switch workspace</h3>
              <p className="text-[11px] text-slate-500">
                Select an organization to switch telemetry
              </p>
            </div>
            <span className="text-[10px] font-semibold bg-indigo-50 text-indigo-600 border border-indigo-100 px-1.5 py-0.5 rounded-full shrink-0">
              {companies.length} Available
            </span>
          </div>

          {/* Company Items List */}
          <div
            ref={listRef}
            className="p-1.5 space-y-0.5 max-h-72 overflow-y-auto"
            role="listbox"
            aria-label="Available workspaces"
            tabIndex={-1}
          >
            {companies.map((company) => {
              const isActive = company.id === currentCompanyId;
              const initials = getCompanyInitials(company.name);
              const colorClass = getCompanyColor(company.id);
              const roleLabel = formatRole(company.role);

              return (
                <button
                  key={company.id}
                  type="button"
                  role="option"
                  aria-selected={isActive}
                  onClick={() => handleSelect(company.id)}
                  className={cn(
                    "company-item w-full flex items-center justify-between px-3 py-2 rounded-lg font-medium cursor-pointer transition-colors text-left focus:outline-none focus:ring-1 focus:ring-indigo-500",
                    isActive
                      ? "bg-indigo-50/80 text-indigo-950 border border-indigo-100"
                      : "hover:bg-slate-50 text-slate-700 border border-transparent"
                  )}
                >
                  <div className="flex items-center gap-2.5 min-w-0 pr-2">
                    <span
                      className={cn(
                        "w-7 h-7 rounded-md text-white font-bold text-xs flex items-center justify-center shrink-0 shadow-2xs",
                        colorClass
                      )}
                      aria-hidden="true"
                    >
                      {initials}
                    </span>
                    <div className="min-w-0 text-left">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-semibold text-slate-900 truncate">
                          {company.name}
                        </span>
                        <span
                          className={cn(
                            "text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded shrink-0",
                            isActive
                              ? "bg-indigo-100 text-indigo-700"
                              : "bg-slate-100 text-slate-600"
                          )}
                        >
                          {roleLabel}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 truncate">
                        {company.is_active ? "Active workspace" : "Inactive workspace"}
                      </p>
                    </div>
                  </div>
                  {isActive && (
                    <span className="check-icon text-indigo-600 shrink-0 ml-1.5" aria-hidden="true">
                      <Check className="w-4 h-4" />
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Footer Callout */}
          <div className="px-3.5 py-2.5 bg-slate-50 text-[11px] text-slate-500 flex items-center gap-2 select-none">
            <Info className="w-3.5 h-3.5 text-indigo-500 shrink-0" aria-hidden="true" />
            <span>Telemetry is scoped per workspace.</span>
          </div>
        </div>
      )}
    </div>
  );
}
