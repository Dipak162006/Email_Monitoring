import { Navigate, Outlet } from "react-router-dom";
import { useWorkspace } from "../hooks/useWorkspace";
import { LoadingSpinner } from "../components/ui/LoadingState";
import { Button } from "../components/ui/Button";
import { AlertCircle, RefreshCw } from "lucide-react";

export function WorkspaceRequiredRoute() {
  const { currentCompany, companies, isLoading, isError, error, refetch } = useWorkspace();

  // 1. Loading: avoid rendering workspace-dependent pages before resolved; prevent premature redirects
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <LoadingSpinner message="Checking workspace..." size="lg" />
      </div>
    );
  }

  // 2. API Failure: do not interpret server/network error as no workspace (never trigger false onboarding)
  if (isError) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 p-4">
        <div className="max-w-md w-full bg-white rounded-2xl border border-slate-200/80 shadow-sm p-6 text-center space-y-4">
          <div className="w-12 h-12 rounded-full bg-red-50 text-red-600 mx-auto flex items-center justify-center">
            <AlertCircle className="w-6 h-6 text-red-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Failed to load workspace</h2>
            <p className="text-sm text-slate-500 mt-1">
              {error?.message || "We encountered an issue checking your company memberships. Please try again."}
            </p>
          </div>
          <Button
            onClick={() => refetch()}
            className="w-full bg-[#4f46e5] hover:bg-[#4338ca] text-white flex items-center justify-center gap-2 cursor-pointer"
          >
            <RefreshCw className="w-4 h-4" />
            <span>Retry</span>
          </Button>
        </div>
      </div>
    );
  }

  // 3. Authenticated user with no workspace memberships -> redirect to onboarding flow
  if (!currentCompany || companies.length === 0) {
    return <Navigate to="/onboarding" replace />;
  }

  // 4. Authorized user with active workspace -> allow access to child routes
  return <Outlet />;
}
