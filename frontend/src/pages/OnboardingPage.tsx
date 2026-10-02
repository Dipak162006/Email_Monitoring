import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Mail,
  User as UserIcon,
  Shield,
  CheckCircle,
  AlertCircle,
  Loader2,
  ArrowRight,
  X,
} from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import { useWorkspace } from "../hooks/useWorkspace";
import { companiesApi, invitationsApi } from "../services/api";
import { LoadingSpinner } from "../components/ui/LoadingState";
import type { UserInvitationItem } from "../types/auth";

export function OnboardingPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // 1. Consume centralized workspace context
  const {
    companies,
    isLoading: isCompaniesLoading,
    refreshWorkspaces,
    setActiveCompanyId,
  } = useWorkspace();

  // 2. Fetch pending invitations for this user
  const {
    data: invitations,
    isLoading: isInvitationsLoading,
    refetch: refetchInvitations,
  } = useQuery({
    queryKey: ["my-pending-invitations"],
    queryFn: () => invitationsApi.getMyPendingInvitations(),
    staleTime: 10000,
  });

  // Workspace creation state
  const [workspaceName, setWorkspaceName] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  // Invitation interaction states
  const [acceptingId, setAcceptingId] = useState<number | null>(null);
  const [decliningId, setDecliningId] = useState<number | null>(null);
  const [invitationActionError, setInvitationActionError] = useState<string | null>(null);

  // If checking workspace memberships or invitations, show loading spinner
  if (isCompaniesLoading || isInvitationsLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f9f9ff]">
        <LoadingSpinner message="Loading workspace information..." size="lg" />
      </div>
    );
  }

  // Only redirect to dashboard if the user already has workspaces AND has no pending invitations to review
  if (companies && companies.length > 0 && (!invitations || invitations.length === 0)) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleWorkspaceSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = workspaceName.trim();
    if (!trimmed) {
      setValidationError("Workspace name is required.");
      return;
    }

    setValidationError(null);
    setApiError(null);
    setIsCreating(true);

    try {
      const createdCompany = await companiesApi.createCompany(trimmed);
      // Invalidate and refresh companies context
      await refreshWorkspaces();
      if (createdCompany && createdCompany.id) {
        setActiveCompanyId(createdCompany.id);
      }
      setIsSuccess(true);
      setTimeout(() => {
        navigate("/dashboard", { replace: true });
      }, 900);
    } catch {
      setApiError("We couldn't create the workspace. Please try again.");
      setIsCreating(false);
    }
  };

  const handleAccept = async (invitation: UserInvitationItem) => {
    setAcceptingId(invitation.id);
    setInvitationActionError(null);

    try {
      await invitationsApi.acceptInvitation(invitation.id);
      await Promise.all([
        refreshWorkspaces(),
        queryClient.invalidateQueries({ queryKey: ["my-pending-invitations"] }),
      ]);
      if (invitation.company_id) {
        setActiveCompanyId(invitation.company_id);
      }
      navigate("/dashboard", { replace: true });
    } catch {
      setInvitationActionError("Failed to accept invitation. Please try again.");
      setAcceptingId(null);
    }
  };

  const handleDecline = async (invitation: UserInvitationItem) => {
    setDecliningId(invitation.id);
    setInvitationActionError(null);

    try {
      await invitationsApi.declineInvitation(invitation.id);
      await Promise.all([
        refetchInvitations(),
        queryClient.invalidateQueries({ queryKey: ["my-pending-invitations"] }),
      ]);
    } catch {
      setInvitationActionError("Failed to decline invitation. Please try again.");
    } finally {
      setDecliningId(null);
    }
  };

  const formatRelativeTime = (isoString: string): string => {
    try {
      const date = new Date(isoString);
      const now = new Date();
      const diffMs = now.getTime() - date.getTime();
      const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

      if (diffDays <= 0) return "today";
      if (diffDays === 1) return "yesterday";
      if (diffDays < 30) return `${diffDays} days ago`;
      return date.toLocaleDateString();
    } catch {
      return "recently";
    }
  };

  return (
    <div className="bg-[#f9f9ff] text-slate-800 min-h-screen flex flex-col justify-between selection:bg-indigo-100 selection:text-indigo-900">
      {/* HEADER */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-[#f9f9ff]/90 backdrop-blur-xl border-b border-slate-200/50 shadow-[0_1px_8px_rgba(0,0,0,0.04)]">
        <div className="h-16 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between">
          {/* Logo & Branding */}
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-[#4f46e5] flex items-center justify-center text-white shadow-sm">
              <Mail className="w-[18px] h-[18px]" />
            </div>
            <span className="text-[17px] font-semibold text-slate-900 tracking-tight">PulseMail</span>
            <span className="text-[11px] font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full border border-slate-200/60">
              v2.4
            </span>
          </div>

          {/* User Profile & Logout */}
          <div className="flex items-center gap-3 sm:gap-4">
            {user?.email && (
              <div className="hidden sm:flex items-center gap-1.5 text-xs text-slate-500">
                <span>Logged in as</span>
                <span className="font-medium text-slate-900">{user.email}</span>
              </div>
            )}
            <div className="w-8 h-8 rounded-full bg-[#4f46e5] flex items-center justify-center text-white shadow-xs">
              <UserIcon className="w-[18px] h-[18px]" />
            </div>
            <button
              onClick={() => {
                logout();
                navigate("/login");
              }}
              type="button"
              className="text-[13px] font-medium text-slate-600 hover:text-slate-900 px-2.5 py-1 rounded-md hover:bg-slate-100 transition-colors"
            >
              Log out
            </button>
          </div>
        </div>
      </header>

      {/* MAIN CONTENT AREA */}
      <main className="w-full pt-20 pb-12 flex-1 flex flex-col justify-center items-center px-4 sm:px-6">
        <div className="w-full max-w-xl mx-auto space-y-6 my-auto">
          {/* PAGE TITLE */}
          <div className="text-center sm:text-left space-y-1">
            <h1 className="text-[24px] sm:text-[28px] font-semibold text-slate-900 tracking-tight leading-tight">
              Set up your workspace
            </h1>
            <p className="text-[14px] sm:text-[15px] text-slate-500">
              Create a workspace or join one you&apos;ve been invited to.
            </p>
          </div>

          {/* CARD 1: CREATE WORKSPACE */}
          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-6 sm:p-8 transition-all">
            {!isSuccess ? (
              <div className="space-y-6">
                <div>
                  <h2 className="text-[18px] font-semibold text-slate-900 tracking-tight">
                    Create a workspace
                  </h2>
                  <p className="text-[14px] text-slate-500 mt-1">
                    Set up a workspace for your team and start managing email accounts together.
                  </p>
                </div>

                {/* Inline API Error Alert */}
                {apiError && (
                  <div className="p-3.5 bg-red-50 text-red-700 border border-red-200/70 rounded-lg flex items-center justify-between text-[13px] font-medium animate-in fade-in">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="w-[18px] h-[18px] text-red-600 shrink-0" />
                      <span>{apiError}</span>
                    </div>
                    <button
                      onClick={() => setApiError(null)}
                      type="button"
                      className="text-red-700 hover:opacity-75 transition-opacity p-0.5 rounded"
                      aria-label="Dismiss error"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                )}

                <form onSubmit={handleWorkspaceSubmit} className="space-y-4" noValidate>
                  <div>
                    <label
                      htmlFor="workspace-name-input"
                      className="block text-[13px] font-medium text-slate-900 mb-1.5"
                    >
                      Workspace name <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="workspace-name-input"
                      type="text"
                      value={workspaceName}
                      onChange={(e) => {
                        setWorkspaceName(e.target.value);
                        if (validationError) setValidationError(null);
                        if (apiError) setApiError(null);
                      }}
                      disabled={isCreating}
                      placeholder="e.g. Acme Corporation"
                      className={`w-full px-3.5 py-2.5 rounded-lg text-[14px] text-slate-900 placeholder:text-slate-400 focus:outline-none transition-all ${
                        validationError
                          ? "bg-red-50/50 border border-red-500 focus:border-red-600"
                          : "bg-[#f1f3ff] border border-transparent focus:border-[#4f46e5] focus:bg-white"
                      }`}
                    />
                    {validationError && (
                      <p className="text-[12px] text-red-600 mt-1.5 flex items-center gap-1 font-medium">
                        <AlertCircle className="w-3.5 h-3.5" />
                        {validationError}
                      </p>
                    )}
                  </div>

                  {/* Owner Note */}
                  <div className="flex items-center gap-2 text-[13px] text-slate-500 pt-0.5">
                    <Shield className="w-4 h-4 text-[#4f46e5] shrink-0" />
                    <span>You will become the workspace owner.</span>
                  </div>

                  {/* Submit Button */}
                  <div className="pt-2">
                    <button
                      id="create-workspace-btn"
                      type="submit"
                      disabled={isCreating}
                      className="w-full bg-[#4f46e5] hover:bg-[#4338ca] text-white font-medium text-[14px] py-2.5 px-5 rounded-lg shadow-sm transition flex items-center justify-center gap-2 cursor-pointer disabled:opacity-60 disabled:cursor-not-allowed"
                    >
                      {isCreating ? (
                        <>
                          <Loader2 className="animate-spin h-4 w-4 text-white" />
                          <span>Creating workspace...</span>
                        </>
                      ) : (
                        <span>Create workspace</span>
                      )}
                    </button>
                  </div>
                </form>
              </div>
            ) : (
              /* Success View */
              <div className="py-6 text-center space-y-4">
                <div className="w-12 h-12 rounded-full bg-emerald-50 text-emerald-600 mx-auto flex items-center justify-center">
                  <CheckCircle className="w-7 h-7" />
                </div>
                <div>
                  <h3 className="text-[18px] font-semibold text-slate-900">Workspace created</h3>
                  <p className="text-[14px] text-slate-500 mt-1">Your workspace is ready.</p>
                </div>
                <div className="pt-2 max-w-xs mx-auto">
                  <button
                    onClick={() => navigate("/dashboard", { replace: true })}
                    type="button"
                    className="w-full bg-[#4f46e5] hover:bg-[#4338ca] text-white font-medium text-[14px] py-2.5 px-5 rounded-lg shadow-sm transition flex items-center justify-center gap-2 cursor-pointer"
                  >
                    <span>Continue to PulseMail</span>
                    <ArrowRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* CARD 2: WORKSPACE INVITATIONS */}
          <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm p-6 sm:p-8 space-y-4 transition-all">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <h2 className="text-[16px] font-semibold text-slate-900">Workspace invitations</h2>
                {invitations && invitations.length > 0 && (
                  <span
                    id="invitation-count-badge"
                    className="px-2 py-0.5 rounded-full text-[12px] font-semibold bg-[#e9edff] text-slate-600"
                  >
                    {invitations.length}
                  </span>
                )}
              </div>
            </div>

            {/* Error on action */}
            {invitationActionError && (
              <div className="p-3 bg-red-50 text-red-700 border border-red-200/70 rounded-lg flex items-center justify-between text-xs font-medium">
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
                  <span>{invitationActionError}</span>
                </div>
                <button
                  onClick={() => setInvitationActionError(null)}
                  type="button"
                  className="text-red-700 hover:opacity-75 p-0.5 rounded"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* Invitations List / Loading / Empty */}
            {isInvitationsLoading ? (
              <div className="py-6 flex items-center justify-center">
                <LoadingSpinner message="Checking for invitations..." size="sm" />
              </div>
            ) : invitations && invitations.length > 0 ? (
              <div className="space-y-3" id="invitations-list">
                {invitations.map((inv) => (
                  <div
                    key={inv.id}
                    className="p-4 rounded-xl bg-[#f1f3ff]/70 border border-slate-200/60 flex flex-col sm:flex-row sm:items-center justify-between gap-4 transition-all hover:border-slate-300"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-medium text-[15px] text-slate-900">
                          {inv.company_name}
                        </span>
                        <span
                          className={`text-[11px] font-medium px-2 py-0.5 rounded-full ${
                            inv.role === "ADMIN"
                              ? "bg-indigo-50 text-indigo-700 border border-indigo-100"
                              : "bg-slate-100 text-slate-700 border border-slate-200"
                          }`}
                        >
                          {inv.role === "ADMIN" ? "Admin" : "Member"}
                        </span>
                      </div>
                      <p className="text-[13px] text-slate-500">
                        Invited by{" "}
                        <span className="font-medium text-slate-800">{inv.inviter_email}</span>{" "}
                        • Received {formatRelativeTime(inv.created_at)}
                      </p>
                    </div>

                    <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                      <button
                        onClick={() => handleDecline(inv)}
                        disabled={decliningId === inv.id || acceptingId === inv.id}
                        type="button"
                        className="px-3 py-1.5 rounded-lg text-[13px] font-medium text-slate-600 hover:text-red-600 hover:bg-red-50 transition cursor-pointer disabled:opacity-50"
                      >
                        {decliningId === inv.id ? "Declining..." : "Decline"}
                      </button>
                      <button
                        onClick={() => handleAccept(inv)}
                        disabled={acceptingId === inv.id || decliningId === inv.id}
                        type="button"
                        className="px-3.5 py-1.5 rounded-lg text-[13px] font-medium bg-[#e1e8fd] hover:bg-[#4f46e5] text-slate-900 hover:text-white transition flex items-center gap-1.5 cursor-pointer disabled:opacity-60"
                      >
                        {acceptingId === inv.id ? (
                          <>
                            <Loader2 className="animate-spin h-3.5 w-3.5 text-current" />
                            <span>Joining...</span>
                          </>
                        ) : (
                          <span>Accept invitation</span>
                        )}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              /* Empty Invitations State */
              <div
                id="empty-invitations-state"
                className="py-8 px-4 text-center rounded-xl bg-[#f1f3ff]/40 border border-dashed border-slate-300"
              >
                <div className="w-10 h-10 rounded-full bg-[#e9edff] mx-auto flex items-center justify-center text-slate-400 mb-2.5">
                  <Mail className="w-5 h-5 text-slate-500" />
                </div>
                <p className="text-[14px] font-medium text-slate-900">No pending invitations</p>
                <p className="text-[13px] text-slate-500 mt-0.5">
                  You can create your own workspace or wait for an invitation.
                </p>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* FOOTER */}
      <footer className="w-full py-6 text-center text-[13px] text-slate-500 flex items-center justify-center gap-2">
        <span>PulseMail</span>
        <span className="opacity-40">•</span>
        <a href="#" className="hover:text-slate-900 hover:underline transition-colors">
          Need help? Contact support
        </a>
      </footer>
    </div>
  );
}
