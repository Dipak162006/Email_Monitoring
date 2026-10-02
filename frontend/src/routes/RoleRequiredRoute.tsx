import { ReactNode } from "react";
import { Navigate, Outlet, useNavigate } from "react-router-dom";
import { ShieldAlert, ArrowLeft, Building2 } from "lucide-react";
import { useWorkspace } from "../hooks/useWorkspace";
import { usePermissions, type PermissionsResult } from "../hooks/usePermissions";
import { LoadingSpinner } from "../components/ui/LoadingState";
import { Button } from "../components/ui/Button";
import type { CompanyRole } from "../types/auth";

export interface RoleRequiredRouteProps {
  allowedRoles?: CompanyRole[];
  check?: (permissions: PermissionsResult) => boolean;
  fallback?: "forbidden" | "redirect";
  redirectTo?: string;
  children?: ReactNode;
}

export function RoleRequiredRoute({
  allowedRoles = ["OWNER", "ADMIN"],
  check,
  fallback = "forbidden",
  redirectTo = "/dashboard",
  children,
}: RoleRequiredRouteProps) {
  const navigate = useNavigate();
  const { currentCompany, currentRole, isLoading } = useWorkspace();
  const permissions = usePermissions();

  // 1. Loading state: avoid flashing forbidden state while memberships resolve
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <LoadingSpinner message="Verifying permissions..." size="md" />
      </div>
    );
  }

  // 2. Determine authorization
  let isAuthorized = false;
  if (check) {
    isAuthorized = check(permissions);
  } else if (currentRole && allowedRoles.includes(currentRole)) {
    isAuthorized = true;
  }

  // 3. If authorized, render children or nested outlet
  if (isAuthorized) {
    return children ? <>{children}</> : <Outlet />;
  }

  // 4. If forbidden and configured for immediate redirect
  if (fallback === "redirect") {
    return <Navigate to={redirectTo} replace />;
  }

  // 5. Default: Render clear, branded Forbidden / Access Restricted view
  const formattedAllowedRoles = allowedRoles
    .map((r) => (r === "OWNER" ? "Owner" : r === "ADMIN" ? "Administrator" : "Member"))
    .join(" or ");

  const formattedCurrentRole = currentRole
    ? currentRole.charAt(0) + currentRole.slice(1).toLowerCase()
    : "Member";

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] px-4 py-12 text-center animate-in fade-in duration-200">
      <div className="max-w-md w-full bg-white rounded-2xl border border-slate-200/80 shadow-xs p-8 text-center space-y-5">
        <div className="w-14 h-14 rounded-2xl bg-amber-50 border border-amber-200/60 text-amber-600 mx-auto flex items-center justify-center shadow-2xs">
          <ShieldAlert className="w-7 h-7 text-amber-600" />
        </div>

        <div className="space-y-2">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 text-xs font-medium">
            <Building2 className="w-3.5 h-3.5 text-slate-500" />
            <span>{currentCompany?.name || "Active Workspace"}</span>
            <span className="text-slate-300">•</span>
            <span className="font-semibold text-slate-700">{formattedCurrentRole}</span>
          </div>

          <h2 className="text-xl font-bold text-slate-900 tracking-tight">Access Restricted</h2>
          <p className="text-xs sm:text-sm text-slate-500 leading-relaxed">
            Your current role (<span className="font-medium text-slate-700">{formattedCurrentRole}</span>) does not have permission to access this page in{" "}
            <span className="font-medium text-slate-800">{currentCompany?.name || "this workspace"}</span>.
            This area requires <span className="font-medium text-slate-800">{formattedAllowedRoles}</span> privileges.
          </p>
        </div>

        <div className="p-3 bg-slate-50 rounded-xl border border-slate-100 text-left">
          <p className="text-[11px] text-slate-500 leading-normal">
            <strong className="text-slate-700 font-semibold">Tip:</strong> If you belong to another workspace with administrative access, you can switch companies using the workspace switcher in the top bar.
          </p>
        </div>

        <div className="pt-2 flex flex-col sm:flex-row gap-2.5 justify-center">
          <Button
            onClick={() => navigate("/dashboard")}
            className="w-full justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs py-2.5 rounded-xl shadow-xs transition-all cursor-pointer"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Return to Dashboard</span>
          </Button>
        </div>
      </div>
    </div>
  );
}
