import React from "react";
import { cn } from "../../lib/utils";
import type { DomainVerificationStatus } from "../../types/domains";

interface DomainDnsStatusProps {
  mxStatus: DomainVerificationStatus;
  spfStatus: DomainVerificationStatus;
  dkimStatus: DomainVerificationStatus;
  dmarcStatus: DomainVerificationStatus;
  dkimSelector?: string | null;
  className?: string;
}

interface RecordConfig {
  key: "MX" | "SPF" | "DKIM" | "DMARC";
  label: string;
  status: DomainVerificationStatus;
}

export const DomainDnsStatus: React.FC<DomainDnsStatusProps> = ({
  mxStatus,
  spfStatus,
  dkimStatus,
  dmarcStatus,
  dkimSelector,
  className,
}) => {
  const dkimLabel = dkimSelector ? `DKIM (${dkimSelector})` : "DKIM";

  const records: RecordConfig[] = [
    { key: "MX", label: "MX", status: mxStatus },
    { key: "SPF", label: "SPF", status: spfStatus },
    { key: "DKIM", label: dkimLabel, status: dkimStatus },
    { key: "DMARC", label: "DMARC", status: dmarcStatus },
  ];

  const getStatusStyles = (status: DomainVerificationStatus) => {
    switch (status) {
      case "VERIFIED":
        return {
          pill: "bg-slate-100/90 text-slate-800 border-slate-200/80",
          dot: "bg-emerald-500",
          symbol: "✓",
          statusText: "Verified",
        };
      case "WARNING":
        return {
          pill: "bg-amber-50 text-amber-900 border-amber-200",
          dot: "bg-amber-500",
          symbol: "!",
          statusText: "Warning",
        };
      case "FAILED":
        return {
          pill: "bg-rose-50 text-rose-900 border-rose-200",
          dot: "bg-rose-500",
          symbol: "✕",
          statusText: "Failed",
        };
      case "PENDING":
      default:
        return {
          pill: "bg-slate-50 text-slate-600 border-slate-200",
          dot: "bg-slate-400",
          symbol: "○",
          statusText: "Pending",
        };
    }
  };

  return (
    <div
      className={cn("flex flex-wrap items-center gap-1.5", className)}
      role="group"
      aria-label="DNS diagnostics status matrix"
    >
      {records.map((rec) => {
        const { pill, dot, statusText } = getStatusStyles(rec.status);
        return (
          <span
            key={rec.key}
            title={`${rec.key}: ${statusText}`}
            aria-label={`${rec.label}: ${statusText}`}
            className={cn(
              "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-mono border transition-colors",
              pill
            )}
          >
            <span
              className={cn("w-1.5 h-1.5 rounded-full shrink-0", dot)}
              aria-hidden="true"
            />
            <span className="font-medium">{rec.label}</span>
            <span className="sr-only">({statusText})</span>
          </span>
        );
      })}
    </div>
  );
};
