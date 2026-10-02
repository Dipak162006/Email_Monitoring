import { useMemo } from "react";
import { useWorkspace } from "./useWorkspace";
import { useAuth } from "./useAuth";
import type { CompanyRole, CompanyMember } from "../types/auth";

export interface PermissionsResult {
  // Active role and company context
  role: CompanyRole | null;
  companyId: number | null;
  isLoading: boolean;
  hasWorkspace: boolean;

  // Basic role flags
  isOwner: boolean;
  isAdmin: boolean;
  isMember: boolean;
  isAdminOrOwner: boolean;

  // Page-level access flags
  canAccessDashboard: boolean;
  canAccessMailbox: boolean;
  canAccessCompose: boolean;
  canAccessEmailAccounts: boolean;
  canAccessTemplates: boolean;
  canAccessSignatures: boolean;
  canAccessTeam: boolean;
  canAccessDiagnostics: boolean;
  canAccessSettings: boolean;

  // Route path check
  canAccessRoute: (pathname: string) => boolean;

  // High-level management capabilities
  canManageTeam: boolean;
  canInviteMembers: boolean;
  canAddMember: boolean;
  canManageEmailAccounts: boolean;
  canGrantEmailAccess: boolean;

  // Granular member-level target checks (respecting self-protection & owner-protection)
  canChangeMemberRole: (targetMember?: CompanyMember | null) => boolean;
  canRemoveMember: (targetMember?: CompanyMember | null) => boolean;
  canManageMemberAccess: (targetMember?: CompanyMember | null) => boolean;
}

export function usePermissions(): PermissionsResult {
  const { user } = useAuth();
  const { currentCompany, currentRole, isLoading } = useWorkspace();

  return useMemo<PermissionsResult>(() => {
    const hasWorkspace = Boolean(currentCompany);
    const role = hasWorkspace ? currentRole : null;

    const isOwner = role === "OWNER";
    const isAdmin = role === "ADMIN";
    const isMember = role === "MEMBER";
    const isAdminOrOwner = isOwner || isAdmin;

    // Page access definitions:
    // Dashboard, Mailbox, Compose, Templates, Signatures: accessible by all active company members.
    // Team & Permissions, Connected Accounts, Diagnostics: restricted to ADMIN and OWNER.
    const canAccessDashboard = hasWorkspace;
    const canAccessMailbox = hasWorkspace;
    const canAccessCompose = hasWorkspace;
    const canAccessTemplates = hasWorkspace;
    const canAccessSignatures = hasWorkspace;
    const canAccessTeam = hasWorkspace && isAdminOrOwner;
    const canAccessEmailAccounts = hasWorkspace && isAdminOrOwner;
    const canAccessDiagnostics = hasWorkspace && isAdminOrOwner;
    const canAccessSettings = hasWorkspace && isAdminOrOwner;

    const canAccessRoute = (pathname: string): boolean => {
      if (!hasWorkspace) return false;
      const cleanPath = pathname.split("?")[0].replace(/\/$/, "");

      if (cleanPath === "/team") return canAccessTeam;
      if (cleanPath === "/email-accounts") return canAccessEmailAccounts;
      if (cleanPath === "/diagnostics") return canAccessDiagnostics;
      if (cleanPath === "/settings") return canAccessSettings;

      // All other application routes are accessible to all valid workspace roles
      return true;
    };

    // Management capabilities
    const canManageTeam = hasWorkspace && isAdminOrOwner;
    const canInviteMembers = hasWorkspace && isAdminOrOwner;
    const canAddMember = hasWorkspace && isAdminOrOwner;
    const canManageEmailAccounts = hasWorkspace && isAdminOrOwner;
    const canGrantEmailAccess = hasWorkspace && isAdminOrOwner;

    // Granular member checks
    const canChangeMemberRole = (targetMember?: CompanyMember | null): boolean => {
      if (!hasWorkspace || !isAdminOrOwner) return false;
      if (!targetMember) return true;
      // Cannot modify self
      if (user && targetMember.user_id === user.id) return false;
      // Cannot modify the OWNER
      if (targetMember.role === "OWNER") return false;
      return true;
    };

    const canRemoveMember = (targetMember?: CompanyMember | null): boolean => {
      if (!hasWorkspace || !isAdminOrOwner) return false;
      if (!targetMember) return true;
      // Cannot remove self
      if (user && targetMember.user_id === user.id) return false;
      // Cannot remove the OWNER
      if (targetMember.role === "OWNER") return false;
      return true;
    };

    const canManageMemberAccess = (targetMember?: CompanyMember | null): boolean => {
      if (!hasWorkspace || !isAdminOrOwner) return false;
      if (!targetMember) return true;
      // Only regular MEMBERs receive explicit account access grants; OWNER and ADMIN have global access
      return targetMember.role === "MEMBER";
    };

    return {
      role,
      companyId: currentCompany ? currentCompany.id : null,
      isLoading,
      hasWorkspace,

      isOwner,
      isAdmin,
      isMember,
      isAdminOrOwner,

      canAccessDashboard,
      canAccessMailbox,
      canAccessCompose,
      canAccessEmailAccounts,
      canAccessTemplates,
      canAccessSignatures,
      canAccessTeam,
      canAccessDiagnostics,
      canAccessSettings,

      canAccessRoute,

      canManageTeam,
      canInviteMembers,
      canAddMember,
      canManageEmailAccounts,
      canGrantEmailAccess,

      canChangeMemberRole,
      canRemoveMember,
      canManageMemberAccess,
    };
  }, [user, currentCompany, currentRole, isLoading]);
}
