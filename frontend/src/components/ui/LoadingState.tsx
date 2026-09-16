import React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "../../lib/utils";

export interface LoadingStateProps extends React.HTMLAttributes<HTMLDivElement> {
  message?: string;
  size?: "sm" | "md" | "lg";
}

export function LoadingState({
  className,
  ...props
}: LoadingStateProps) {
  return (
    <div
      className={cn("flex flex-col items-center justify-center p-8 space-y-3 text-slate-500", className)}
      {...props}
    />
  );
}

export function LoadingSpinner({
  className,
  message = "Loading...",
  size = "md",
}: LoadingStateProps) {
  const iconSizes = {
    sm: "h-5 w-5",
    md: "h-8 w-8",
    lg: "h-10 w-10",
  };

  return (
    <div className={cn("flex flex-col items-center justify-center p-8 space-y-3", className)}>
      <Loader2 className={cn("animate-spin text-indigo-600", iconSizes[size])} />
      {message && <p className="text-xs font-medium text-slate-500">{message}</p>}
    </div>
  );
}
