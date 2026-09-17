import React from "react";
import { AlertCircle, RefreshCw } from "lucide-react";
import { cn } from "../../lib/utils";
import { Button } from "./Button";

export interface ErrorStateProps extends React.HTMLAttributes<HTMLDivElement> {
  title?: string;
  message: string;
  onRetry?: () => void;
  compact?: boolean;
}

export function ErrorState({
  className,
  title = "An error occurred",
  message,
  onRetry,
  compact = false,
  ...props
}: ErrorStateProps) {
  if (compact) {
    return (
      <div
        className={cn(
          "flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3.5 rounded-xl border border-rose-200 bg-rose-50/60 text-slate-800 shadow-2xs",
          className
        )}
        {...props}
      >
        <div className="flex items-center space-x-2.5 min-w-0">
          <div className="h-8 w-8 rounded-lg bg-rose-100 text-rose-600 flex items-center justify-center shrink-0">
            <AlertCircle className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <h4 className="text-xs font-semibold text-rose-900 leading-tight">{title}</h4>
            <p className="text-[11px] text-rose-700 truncate mt-0.5">{message}</p>
          </div>
        </div>
        {onRetry && (
          <Button
            size="sm"
            variant="outline"
            onClick={onRetry}
            className="h-8 px-3 text-xs bg-white border-rose-200 text-rose-800 hover:bg-rose-100/70 hover:text-rose-900 shrink-0 self-start sm:self-auto shadow-2xs"
          >
            <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
            Try Again
          </Button>
        )}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center p-8 rounded-xl border border-rose-200 bg-rose-50/40 text-slate-800",
        className
      )}
      {...props}
    >
      <div className="h-10 w-10 rounded-full bg-rose-100 flex items-center justify-center text-rose-600 mb-3">
        <AlertCircle className="h-5 w-5" />
      </div>
      <h4 className="text-sm font-semibold text-rose-900 mb-1">{title}</h4>
      <p className="text-xs text-rose-700 max-w-md mb-4 leading-relaxed">{message}</p>
      {onRetry && (
        <Button size="sm" variant="outline" onClick={onRetry} className="bg-white border-rose-200 text-rose-800 hover:bg-rose-50">
          <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
          Try Again
        </Button>
      )}
    </div>
  );
}

