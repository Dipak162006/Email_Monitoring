import React from "react";
import { CheckCircle2, AlertTriangle, XCircle, Clock } from "lucide-react";
import { cn } from "../../lib/utils";
import type { DomainVerificationStatus } from "../../types/domains";

interface DomainStatusBadgeProps {
  status: DomainVerificationStatus;
  size?: "sm" | "md";
  className?: string;
  showIcon?: boolean;
}

export const DomainStatusBadge: React.FC<DomainStatusBadgeProps> = ({
  status,
  size = "md",
  className,
  showIcon = true,
}) => {
  const getStatusConfig = () => {
    switch (status) {
      case "VERIFIED":
        return {
          label: "VERIFIED",
          icon: CheckCircle2,
          containerClass:
            "bg-emerald-50 text-emerald-700 border-emerald-200/80 hover:bg-emerald-100/50",
          iconClass: "text-emerald-600",
        };
      case "WARNING":
        return {
          label: "WARNING",
          icon: AlertTriangle,
          containerClass:
            "bg-amber-50 text-amber-700 border-amber-200/80 hover:bg-amber-100/50",
          iconClass: "text-amber-600",
        };
      case "FAILED":
        return {
          label: "FAILED",
          icon: XCircle,
          containerClass:
            "bg-rose-50 text-rose-700 border-rose-200/80 hover:bg-rose-100/50",
          iconClass: "text-rose-600",
        };
      case "PENDING":
      default:
        return {
          label: "PENDING",
          icon: Clock,
          containerClass:
            "bg-slate-100 text-slate-700 border-slate-200/80 hover:bg-slate-200/50",
          iconClass: "text-slate-500",
        };
    }
  };

  const { label, icon: Icon, containerClass, iconClass } = getStatusConfig();

  const isSmall = size === "sm";

  return (
    <span
      className={cn(
        "inline-flex items-center font-semibold tracking-wide border rounded-full transition-colors select-none",
        isSmall
          ? "px-2 py-0.5 text-[11px] gap-1"
          : "px-2.5 py-1 text-xs gap-1.5",
        containerClass,
        className
      )}
      role="status"
      aria-label={`Domain status: ${label}`}
    >
      {showIcon && (
        <Icon
          className={cn(isSmall ? "w-3 h-3" : "w-3.5 h-3.5", iconClass, "shrink-0")}
          aria-hidden="true"
        />
      )}
      <span>{label}</span>
    </span>
  );
};
