import { useState, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Users,
  UserPlus,
  Mail,
  ShieldCheck,
  Search,
  ChevronDown,
  AlertCircle,
  CheckCircle2,
  X,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { Button } from "../components/ui/Button";
import { useAuth } from "../hooks/useAuth";
import { useWorkspace } from "../hooks/useWorkspace";
import { usePermissions } from "../hooks/usePermissions";
import { companiesApi, emailAccountsApi, invitationsApi } from "../services/api";
import type { CompanyMember, CompanyMemberAddPayload, CompanyInvitationItem } from "../types/auth";
import type { EmailAccountItem } from "../types/emails";

import { AddMemberModal } from "../components/team/AddMemberModal";
import { ChangeRoleModal } from "../components/team/ChangeRoleModal";
import { RemoveMemberModal } from "../components/team/RemoveMemberModal";
import { ManageEmailAccessModal } from "../components/team/ManageEmailAccessModal";
import { ManageAccountAccessModal } from "../components/team/ManageAccountAccessModal";
import { MemberRow, formatMemberDate } from "../components/team/MemberRow";
import { MobileMemberCard } from "../components/team/MobileMemberCard";
import { SharedInboxCard } from "../components/team/SharedInboxCard";

export function TeamPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  // Search & Filter States
  const [memberSearchQuery, setMemberSearchQuery] = useState("");
  const [memberRoleFilter, setMemberRoleFilter] = useState<"ALL" | "OWNER" | "ADMIN" | "MEMBER">("ALL");
  const [inboxSearchQuery, setInboxSearchQuery] = useState("");

  // Notification Alert Banner
  const [alertBanner, setAlertBanner] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  // Modal Interaction States
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [memberForRoleChange, setMemberForRoleChange] = useState<CompanyMember | null>(null);
  const [memberForRemoval, setMemberForRemoval] = useState<CompanyMember | null>(null);
  const [memberForAccess, setMemberForAccess] = useState<CompanyMember | null>(null);
  const [accountForAccess, setAccountForAccess] = useState<EmailAccountItem | null>(null);

  // In-flight mutation flags
  const [isSubmittingModal, setIsSubmittingModal] = useState(false);
  const [resendingId, setResendingId] = useState<number | null>(null);
  const [revokingId, setRevokingId] = useState<number | null>(null);

  // 1. Consume active workspace and centralized permissions
  const {
    currentCompany: activeCompany,
    isLoading: isWorkspaceLoading,
  } = useWorkspace();
  const {
    canAddMember,
    canChangeMemberRole,
    canRemoveMember,
    canGrantEmailAccess,
  } = usePermissions();

  // 2. Fetch all members of the active company
  const {
    data: members = [],
    isLoading: isMembersLoading,
  } = useQuery({
    queryKey: ["company-members", activeCompany?.id],
    queryFn: () => companiesApi.getMembers(activeCompany!.id),
    enabled: !!activeCompany?.id,
    staleTime: 30000,
  });

  // 3. Fetch all email accounts of the active company
  const {
    data: accounts = [],
  } = useQuery({
    queryKey: ["company-email-accounts", activeCompany?.id],
    queryFn: () => emailAccountsApi.listCompanyAccounts(activeCompany!.id),
    enabled: !!activeCompany?.id,
    staleTime: 30000,
  });

  // 4. Fetch company-wide email account access records (single fast query, zero N+1)
  const {
    data: accessRecords = [],
  } = useQuery({
    queryKey: ["company-email-accounts-access", activeCompany?.id],
    queryFn: () => companiesApi.getCompanyEmailAccountsAccess(activeCompany!.id),
    enabled: !!activeCompany?.id,
    staleTime: 30000,
  });

  // 5. Fetch company invitations (Owner/Admin only)
  const {
    data: invitations = [],
    isLoading: isInvitationsLoading,
    isError: isInvitationsError,
    refetch: refetchInvitations,
  } = useQuery({
    queryKey: ["company-invitations", activeCompany?.id],
    queryFn: () => invitationsApi.getCompanyInvitations(activeCompany!.id),
    enabled: !!activeCompany?.id && canAddMember,
    staleTime: 15000,
  });

  const pendingInvitations = useMemo(() => {
    return invitations.filter((inv) => inv.status === "PENDING");
  }, [invitations]);


  // Mapping lookup: User ID -> Array of EmailAccountItem
  const userAssignedAccountsMap = useMemo(() => {
    const map: Record<number, EmailAccountItem[]> = {};
    const accountsById = new Map<number, EmailAccountItem>(accounts.map((a) => [a.id, a]));

    for (const record of accessRecords) {
      const acc = accountsById.get(record.email_account_id);
      if (acc) {
        if (!map[record.user_id]) {
          map[record.user_id] = [];
        }
        map[record.user_id].push(acc);
      }
    }
    return map;
  }, [accessRecords, accounts]);

  // Mapping lookup: Account ID -> Array of CompanyMember (assigned regular members)
  const accountAssignedMembersMap = useMemo(() => {
    const map: Record<number, CompanyMember[]> = {};
    const membersByUserId = new Map<number, CompanyMember>(members.map((m) => [m.user_id, m]));

    for (const record of accessRecords) {
      const member = membersByUserId.get(record.user_id);
      // Only include regular members in explicit assignment chips
      if (member && member.role === "MEMBER") {
        if (!map[record.email_account_id]) {
          map[record.email_account_id] = [];
        }
        map[record.email_account_id].push(member);
      }
    }
    return map;
  }, [accessRecords, members]);

  // Summary Metrics Computation
  const totalMembersCount = members.length;
  const activeMembersCount = members.filter((m) => m.is_active).length;
  const inactiveMembersCount = totalMembersCount - activeMembersCount;

  const totalAccountsCount = accounts.length;
  const activeAccountsCount = accounts.filter((a) => a.is_active).length;

  // Managed access metric: number of regular members who have at least 1 assigned inbox
  const managedAccessMembersCount = useMemo(() => {
    return members.filter((m) => m.role === "MEMBER" && (userAssignedAccountsMap[m.user_id]?.length ?? 0) > 0).length;
  }, [members, userAssignedAccountsMap]);

  // Filtered members list for Section 1
  const filteredMembers = useMemo(() => {
    const q = memberSearchQuery.toLowerCase().trim();
    return members.filter((m) => {
      const name = (m.full_name || "").toLowerCase();
      const email = m.email.toLowerCase();
      const matchesQuery = !q || name.includes(q) || email.includes(q);
      const matchesRole = memberRoleFilter === "ALL" || m.role === memberRoleFilter;
      return matchesQuery && matchesRole;
    });
  }, [members, memberSearchQuery, memberRoleFilter]);

  // Filtered accounts list for Section 2
  const filteredAccounts = useMemo(() => {
    const q = inboxSearchQuery.toLowerCase().trim();
    return accounts.filter((acc) => {
      const name = acc.name.toLowerCase();
      const email = acc.email_address.toLowerCase();
      return !q || name.includes(q) || email.includes(q);
    });
  }, [accounts, inboxSearchQuery]);

  // ---------------------------------------------------------------------------
  // Mutations & Action Handlers
  // ---------------------------------------------------------------------------

  const invalidateTeamQueries = () => {
    if (!activeCompany) return;
    queryClient.invalidateQueries({ queryKey: ["company-members", activeCompany.id] });
    queryClient.invalidateQueries({ queryKey: ["company-email-accounts-access", activeCompany.id] });
    queryClient.invalidateQueries({ queryKey: ["company-email-accounts", activeCompany.id] });
    queryClient.invalidateQueries({ queryKey: ["company-invitations", activeCompany.id] });
  };

  // Add Member (Direct)
  const handleAddMember = async (payload: CompanyMemberAddPayload) => {
    if (!activeCompany) return;
    if (!canAddMember) {
      throw new Error("You do not have permission to add members to this workspace.");
    }
    setIsSubmittingModal(true);
    try {
      await companiesApi.addMember(activeCompany.id, payload);
      invalidateTeamQueries();
      setIsAddModalOpen(false);
      setAlertBanner({
        type: "success",
        message: `Successfully added ${payload.email} to the workspace.`,
      });
    } finally {
      setIsSubmittingModal(false);
    }
  };

  // Invite Member (Invitation)
  const handleCreateInvitation = async (payload: { email: string; role: "ADMIN" | "MEMBER" }) => {
    if (!activeCompany) return;
    if (!canAddMember) {
      throw new Error("You do not have permission to invite members to this workspace.");
    }
    setIsSubmittingModal(true);
    try {
      await invitationsApi.createInvitation(activeCompany.id, payload);
      invalidateTeamQueries();
      setIsAddModalOpen(false);
      setAlertBanner({
        type: "success",
        message: `Invitation created for ${payload.email}.`,
      });
    } finally {
      setIsSubmittingModal(false);
    }
  };

  // Resend Pending Invitation
  const handleResendInvitation = async (invitation: CompanyInvitationItem) => {
    if (!activeCompany) return;
    setResendingId(invitation.id);
    try {
      await invitationsApi.resendInvitation(activeCompany.id, invitation.id);
      queryClient.invalidateQueries({ queryKey: ["company-invitations", activeCompany.id] });
      setAlertBanner({
        type: "success",
        message: `Invitation refreshed for ${invitation.invited_email}.`,
      });
    } catch (err: unknown) {
      const errObj = err as { detail?: string; message?: string };
      setAlertBanner({
        type: "error",
        message: errObj.detail || errObj.message || "Failed to resend invitation. Please try again.",
      });
    } finally {
      setResendingId(null);
    }
  };

  // Revoke Pending Invitation
  const handleRevokeInvitation = async (invitation: CompanyInvitationItem) => {
    if (!activeCompany) return;
    setRevokingId(invitation.id);
    try {
      await invitationsApi.revokeInvitation(activeCompany.id, invitation.id);
      queryClient.invalidateQueries({ queryKey: ["company-invitations", activeCompany.id] });
      setAlertBanner({
        type: "success",
        message: `Invitation to ${invitation.invited_email} has been revoked.`,
      });
    } catch (err: unknown) {
      const errObj = err as { detail?: string; message?: string };
      setAlertBanner({
        type: "error",
        message: errObj.detail || errObj.message || "Failed to revoke invitation. Please try again.",
      });
    } finally {
      setRevokingId(null);
    }
  };

  // Change Role
  const handleChangeRole = async (userId: number, newRole: "ADMIN" | "MEMBER") => {
    if (!activeCompany) return;
    const targetMember = members.find((m) => m.user_id === userId);
    if (!canChangeMemberRole(targetMember)) {
      setAlertBanner({
        type: "error",
        message: userId === user?.id
          ? "You cannot change your own role."
          : "You do not have permission to change this member's role.",
      });
      setMemberForRoleChange(null);
      return;
    }
    setIsSubmittingModal(true);
    try {
      await companiesApi.updateMemberRole(activeCompany.id, userId, { role: newRole });
      invalidateTeamQueries();
      setMemberForRoleChange(null);
      setAlertBanner({
        type: "success",
        message: "Member role updated successfully.",
      });
    } catch {
      setAlertBanner({
        type: "error",
        message: "Failed to update member role. Please try again.",
      });
    } finally {
      setIsSubmittingModal(false);
    }
  };

  // Remove Member
  const handleRemoveMember = async (userId: number) => {
    if (!activeCompany) return;
    const targetMember = members.find((m) => m.user_id === userId);
    if (!canRemoveMember(targetMember)) {
      setAlertBanner({
        type: "error",
        message: userId === user?.id
          ? "You cannot remove yourself from the company."
          : "You do not have permission to remove this member.",
      });
      setMemberForRemoval(null);
      return;
    }
    setIsSubmittingModal(true);
    try {
      await companiesApi.removeMember(activeCompany.id, userId);
      invalidateTeamQueries();
      setMemberForRemoval(null);
      setAlertBanner({
        type: "success",
        message: "Member removed from the workspace.",
      });
    } catch {
      setAlertBanner({
        type: "error",
        message: "Failed to remove member. Please try again.",
      });
    } finally {
      setIsSubmittingModal(false);
    }
  };

  // Member-Centric Save Access
  const handleSaveMemberAccess = async (
    userId: number,
    accountIdsToGrant: number[],
    accountIdsToRevoke: number[]
  ) => {
    if (!activeCompany) return;
    if (!canGrantEmailAccess) {
      setAlertBanner({
        type: "error",
        message: "You do not have permission to manage email account access.",
      });
      return;
    }
    setIsSubmittingModal(true);
    try {
      const grantPromises = accountIdsToGrant.map((accId) =>
        emailAccountsApi.grantAccess(activeCompany.id, accId, userId)
      );
      const revokePromises = accountIdsToRevoke.map((accId) =>
        emailAccountsApi.revokeAccess(activeCompany.id, accId, userId)
      );
      await Promise.all([...grantPromises, ...revokePromises]);

      invalidateTeamQueries();
      setMemberForAccess(null);
      setAlertBanner({
        type: "success",
        message: "Email account access permissions saved successfully.",
      });
    } finally {
      setIsSubmittingModal(false);
    }
  };

  // Account-Centric Save Access
  const handleSaveAccountAccess = async (
    accountId: number,
    userIdsToGrant: number[],
    userIdsToRevoke: number[]
  ) => {
    if (!activeCompany) return;
    if (!canGrantEmailAccess) {
      setAlertBanner({
        type: "error",
        message: "You do not have permission to manage shared inbox permissions.",
      });
      return;
    }
    setIsSubmittingModal(true);
    try {
      const grantPromises = userIdsToGrant.map((uId) =>
        emailAccountsApi.grantAccess(activeCompany.id, accountId, uId)
      );
      const revokePromises = userIdsToRevoke.map((uId) =>
        emailAccountsApi.revokeAccess(activeCompany.id, accountId, uId)
      );
      await Promise.all([...grantPromises, ...revokePromises]);

      invalidateTeamQueries();
      setAccountForAccess(null);
      setAlertBanner({
        type: "success",
        message: "Shared inbox permissions saved successfully.",
      });
    } finally {
      setIsSubmittingModal(false);
    }
  };

  // Initial loading state
  if (isWorkspaceLoading || (activeCompany && isMembersLoading && members.length === 0)) {
    return (
      <div className="flex flex-col items-center justify-center py-24 space-y-3">
        <Loader2 className="h-8 w-8 text-indigo-600 animate-spin" />
        <p className="text-sm font-medium text-slate-500">Loading team & permissions...</p>
      </div>
    );
  }

  // Error state if user has no companies or company failed
  if (!activeCompany && !isWorkspaceLoading) {
    return (
      <div className="p-8 max-w-lg mx-auto text-center bg-white rounded-2xl border border-slate-200 space-y-4">
        <div className="w-12 h-12 rounded-xl bg-amber-50 border border-amber-200 text-amber-600 flex items-center justify-center mx-auto">
          <AlertCircle className="h-6 w-6" />
        </div>
        <h3 className="text-base font-bold text-slate-900">No Active Organization</h3>
        <p className="text-xs text-slate-500">
          You are not currently associated with an active company workspace. Please create or join a company to manage team permissions.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Alert Banner */}
      {alertBanner && (
        <div
          className={`p-4 rounded-xl border flex items-center justify-between gap-3 text-sm animate-in fade-in duration-150 ${
            alertBanner.type === "success"
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : "bg-rose-50 border-rose-200 text-rose-800"
          }`}
        >
          <div className="flex items-center gap-2.5">
            {alertBanner.type === "success" ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
            ) : (
              <AlertCircle className="h-4 w-4 text-rose-600 shrink-0" />
            )}
            <span className="font-medium text-xs sm:text-sm">{alertBanner.message}</span>
          </div>
          <button
            type="button"
            onClick={() => setAlertBanner(null)}
            className="text-slate-400 hover:text-slate-600 p-1 rounded-md transition-colors cursor-pointer"
            aria-label="Dismiss banner"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Page Title & Primary Action Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">Team &amp; Permissions</h1>
          <p className="text-sm text-slate-500 mt-0.5">Manage workspace members and shared inbox access</p>
        </div>
        <div className="flex items-center gap-3">
          {canAddMember && (
            <Button
              type="button"
              onClick={() => setIsAddModalOpen(true)}
              className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white font-medium px-4 py-2 rounded-lg shadow-xs text-sm transition-all cursor-pointer"
            >
              <UserPlus className="h-4 w-4" />
              <span>+ Add Member</span>
            </Button>
          )}
        </div>
      </div>

      {/* Summary Cards Row (3 Cards) */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* Total Members Card */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs flex items-center justify-between">
          <div className="flex flex-col">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Total Members
            </span>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-3xl font-bold text-slate-900 tracking-tight">
                {totalMembersCount}
              </span>
              <span className="text-xs font-medium text-slate-500">
                {inactiveMembersCount > 0
                  ? `${activeMembersCount} Active · ${inactiveMembersCount} Inactive`
                  : `${activeMembersCount} Active`}
              </span>
            </div>
          </div>
          <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shrink-0">
            <Users className="h-5 w-5" />
          </div>
        </div>

        {/* Connected Email Accounts Card */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs flex items-center justify-between">
          <div className="flex flex-col">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Connected Email Accounts
            </span>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-3xl font-bold text-slate-900 tracking-tight">
                {totalAccountsCount}
              </span>
              <span className="text-xs font-medium text-slate-500">
                {totalAccountsCount === 0
                  ? "No mailboxes connected"
                  : activeAccountsCount === totalAccountsCount
                  ? "All mailboxes operational"
                  : `${activeAccountsCount} of ${totalAccountsCount} operational`}
              </span>
            </div>
          </div>
          <div className="w-10 h-10 rounded-xl bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-700 shrink-0">
            <Mail className="h-5 w-5" />
          </div>
        </div>

        {/* Managed Access Card */}
        <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs flex items-center justify-between">
          <div className="flex flex-col">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Managed Access
            </span>
            <div className="flex items-baseline gap-2 mt-1">
              <span className="text-3xl font-bold text-slate-900 tracking-tight">
                {managedAccessMembersCount}
              </span>
              <span className="text-xs font-medium text-slate-500">
                Members with assigned inboxes
              </span>
            </div>
          </div>
          <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shrink-0">
            <ShieldCheck className="h-5 w-5" />
          </div>
        </div>
      </div>

      {/* Section 1: Workspace Members Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
        {/* Table Header / Controls */}
        <div className="p-5 sm:px-6 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            <h2 className="text-base font-semibold text-slate-900">Workspace Members</h2>
            <span className="bg-slate-100 text-slate-700 text-xs font-medium px-2.5 py-0.5 rounded-full">
              {members.length} {members.length === 1 ? "member" : "members"}
            </span>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
            {/* Search Members */}
            <div className="relative w-full sm:w-64">
              <Search className="absolute left-3 top-2.5 text-slate-400 h-4 w-4 pointer-events-none" />
              <input
                type="text"
                value={memberSearchQuery}
                onChange={(e) => setMemberSearchQuery(e.target.value)}
                placeholder="Search members..."
                className="w-full pl-9 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-indigo-500 focus:bg-white transition-all"
              />
              {memberSearchQuery && (
                <button
                  type="button"
                  onClick={() => setMemberSearchQuery("")}
                  className="absolute right-2 top-2 text-slate-400 hover:text-slate-600"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            {/* Role Filter */}
            <div className="relative">
              <select
                value={memberRoleFilter}
                onChange={(e) =>
                  setMemberRoleFilter(e.target.value as "ALL" | "OWNER" | "ADMIN" | "MEMBER")
                }
                className="w-full sm:w-auto appearance-none bg-slate-50 border border-slate-200 text-slate-700 text-xs font-medium pl-3 pr-8 py-1.5 rounded-lg focus:outline-none focus:border-indigo-500 cursor-pointer transition-all"
              >
                <option value="ALL">All Roles</option>
                <option value="OWNER">Owner</option>
                <option value="ADMIN">Admin</option>
                <option value="MEMBER">Member</option>
              </select>
              <ChevronDown className="absolute right-2.5 top-2.5 pointer-events-none text-slate-400 h-3.5 w-3.5" />
            </div>
          </div>
        </div>

        {/* Desktop / Tablet Table View */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-slate-50/80 text-[11px] font-semibold uppercase tracking-wider text-slate-500 border-b border-slate-200/80">
                <th className="py-3 px-6">User</th>
                <th className="py-3 px-4">Role</th>
                <th className="py-3 px-4">Email Account Access</th>
                <th className="py-3 px-4">Joined</th>
                <th className="py-3 px-6 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm">
              {filteredMembers.length > 0 ? (
                filteredMembers.map((member) => (
                  <MemberRow
                    key={member.id}
                    member={member}
                    assignedAccounts={userAssignedAccountsMap[member.user_id] || []}
                    isSelf={member.user_id === user?.id}
                    onOpenManageAccess={(m) => setMemberForAccess(m)}
                    onOpenChangeRole={(m) => setMemberForRoleChange(m)}
                    onOpenRemove={(m) => setMemberForRemoval(m)}
                  />
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="py-12 text-center text-xs text-slate-500">
                    {memberSearchQuery || memberRoleFilter !== "ALL"
                      ? "No workspace members match your search or filter criteria."
                      : "No team members found."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Mobile Stacked Card View */}
        <div className="block md:hidden p-4 space-y-3">
          {filteredMembers.length > 0 ? (
            filteredMembers.map((member) => (
              <MobileMemberCard
                key={member.id}
                member={member}
                assignedAccounts={userAssignedAccountsMap[member.user_id] || []}
                isSelf={member.user_id === user?.id}
                onOpenManageAccess={(m) => setMemberForAccess(m)}
                onOpenChangeRole={(m) => setMemberForRoleChange(m)}
                onOpenRemove={(m) => setMemberForRemoval(m)}
              />
            ))
          ) : (
            <div className="py-8 text-center text-xs text-slate-500">
              {memberSearchQuery || memberRoleFilter !== "ALL"
                ? "No workspace members match your search or filter criteria."
                : "No team members found."}
            </div>
          )}
        </div>
      </div>

      {/* Section: Pending Invitations (Owner / Admin Only) */}
      {canAddMember && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
          {/* Section Header */}
          <div className="p-5 sm:px-6 border-b border-slate-100 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <h2 className="text-base font-semibold text-slate-900">Pending Invitations</h2>
              <span className="bg-amber-50 text-amber-700 border border-amber-200 text-xs font-semibold px-2.5 py-0.5 rounded-full">
                {pendingInvitations.length} {pendingInvitations.length === 1 ? "pending" : "pending"}
              </span>
            </div>
          </div>

          {/* Loading State */}
          {isInvitationsLoading ? (
            <div className="p-8 flex items-center justify-center gap-2 text-xs text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin text-indigo-600" />
              <span>Loading pending invitations...</span>
            </div>
          ) : isInvitationsError ? (
            <div className="p-6 text-center text-xs text-rose-600 flex flex-col items-center gap-2">
              <p>Failed to load invitations.</p>
              <button
                type="button"
                onClick={() => refetchInvitations()}
                className="px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded text-xs font-medium cursor-pointer"
              >
                Retry
              </button>
            </div>
          ) : pendingInvitations.length > 0 ? (
            <div className="divide-y divide-slate-100">
              {pendingInvitations.map((inv) => {
                const isResending = resendingId === inv.id;
                const isRevoking = revokingId === inv.id;
                const isActionDisabled = isResending || isRevoking;

                return (
                  <div
                    key={inv.id}
                    className="p-4 sm:px-6 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50/50 transition-colors"
                  >
                    <div className="flex items-start sm:items-center gap-3">
                      <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shrink-0 mt-0.5 sm:mt-0">
                        <Mail className="h-4 w-4" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-semibold text-xs text-slate-900">{inv.invited_email}</span>
                          <span
                            className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded border ${
                              inv.role === "ADMIN"
                                ? "bg-purple-50 text-purple-700 border-purple-200"
                                : "bg-slate-100 text-slate-700 border-slate-200"
                            }`}
                          >
                            {inv.role}
                          </span>
                          <span className="text-[10px] font-medium bg-amber-50 text-amber-700 border border-amber-200 px-1.5 py-0.2 rounded-full">
                            Pending
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          {inv.updated_at && inv.updated_at !== inv.created_at
                            ? `Resent ${formatMemberDate(inv.updated_at)} · Created ${formatMemberDate(inv.created_at)}`
                            : `Invited ${formatMemberDate(inv.created_at)}`}
                          {inv.inviter_email ? ` by ${inv.inviter_email}` : ""}
                        </p>
                      </div>
                    </div>

                    {/* Actions: Resend and Revoke */}
                    <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                      <button
                        type="button"
                        disabled={isActionDisabled}
                        onClick={() => handleResendInvitation(inv)}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 rounded-lg transition-colors cursor-pointer disabled:opacity-50"
                        title="Resend invitation (refresh timestamp)"
                      >
                        {isResending ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-600" />
                        ) : (
                          <RefreshCw className="h-3.5 w-3.5 text-slate-500" />
                        )}
                        <span>{isResending ? "Resending..." : "Resend"}</span>
                      </button>
                      <button
                        type="button"
                        disabled={isActionDisabled}
                        onClick={() => handleRevokeInvitation(inv)}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-rose-600 bg-white border border-rose-200 hover:bg-rose-50 rounded-lg transition-colors cursor-pointer disabled:opacity-50"
                        title="Revoke invitation"
                      >
                        {isRevoking ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin text-rose-600" />
                        ) : (
                          <X className="h-3.5 w-3.5 text-rose-500" />
                        )}
                        <span>{isRevoking ? "Revoking..." : "Revoke"}</span>
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="py-8 text-center px-4">
              <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 mx-auto mb-2">
                <Mail className="h-4 w-4" />
              </div>
              <p className="text-xs font-medium text-slate-700">No pending invitations</p>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Invitations sent to team members who haven't joined yet will appear here.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Section 2: Shared Inbox Access */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-xs p-6 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Shared Inbox Access</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Manage which members can access each connected email account
            </p>
          </div>
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-2.5 text-slate-400 h-4 w-4 pointer-events-none" />
            <input
              type="text"
              value={inboxSearchQuery}
              onChange={(e) => setInboxSearchQuery(e.target.value)}
              placeholder="Search email accounts..."
              className="w-full pl-9 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-800 placeholder:text-slate-400 focus:outline-none focus:border-indigo-500 focus:bg-white transition-all"
            />
            {inboxSearchQuery && (
              <button
                type="button"
                onClick={() => setInboxSearchQuery("")}
                className="absolute right-2 top-2 text-slate-400 hover:text-slate-600"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* 2-column Card Layout for Connected Inboxes */}
        {filteredAccounts.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredAccounts.map((account) => (
              <SharedInboxCard
                key={account.id}
                account={account}
                assignedMembers={accountAssignedMembersMap[account.id] || []}
                isCurrentUserAdminOrOwner={canGrantEmailAccess}
                onOpenManageAccess={(acc) => setAccountForAccess(acc)}
              />
            ))}
          </div>
        ) : (
          <div className="py-10 text-center border border-dashed border-slate-200 rounded-xl text-xs text-slate-500">
            {inboxSearchQuery
              ? "No connected email accounts match your search query."
              : "No email accounts connected to this workspace yet."}
          </div>
        )}
      </div>

      {/* Modals */}
      {/* 1. Add Member Modal */}
      <AddMemberModal
        isOpen={isAddModalOpen}
        isSubmitting={isSubmittingModal}
        onClose={() => setIsAddModalOpen(false)}
        onSubmit={handleAddMember}
        onInvite={handleCreateInvitation}
      />

      {/* 2. Change Role Modal */}
      <ChangeRoleModal
        isOpen={!!memberForRoleChange}
        member={memberForRoleChange}
        isSubmitting={isSubmittingModal}
        onClose={() => setMemberForRoleChange(null)}
        onSubmit={handleChangeRole}
      />

      {/* 3. Remove Member Confirmation Modal */}
      <RemoveMemberModal
        isOpen={!!memberForRemoval}
        member={memberForRemoval}
        isRemoving={isSubmittingModal}
        onClose={() => setMemberForRemoval(null)}
        onConfirm={handleRemoveMember}
      />

      {/* 4. Manage Email Access Modal (Member-Centric) */}
      <ManageEmailAccessModal
        isOpen={!!memberForAccess}
        member={memberForAccess}
        accounts={accounts}
        currentAssignedAccountIds={
          memberForAccess
            ? (userAssignedAccountsMap[memberForAccess.user_id] || []).map((a) => a.id)
            : []
        }
        isSubmitting={isSubmittingModal}
        onClose={() => setMemberForAccess(null)}
        onSave={handleSaveMemberAccess}
      />

      {/* 5. Manage Shared Inbox Access Modal (Account-Centric) */}
      <ManageAccountAccessModal
        isOpen={!!accountForAccess}
        account={accountForAccess}
        members={members}
        currentAssignedUserIds={
          accountForAccess
            ? (accountAssignedMembersMap[accountForAccess.id] || []).map((m) => m.user_id)
            : []
        }
        isSubmitting={isSubmittingModal}
        onClose={() => setAccountForAccess(null)}
        onSave={handleSaveAccountAccess}
      />
    </div>
  );
}
