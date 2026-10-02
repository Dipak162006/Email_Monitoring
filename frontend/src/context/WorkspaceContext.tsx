import {
  createContext,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { CompanyRole, CompanyWithRole } from "../types/auth";
import { companiesApi } from "../services/api";
import { useAuth } from "../hooks/useAuth";

export const ACTIVE_COMPANY_STORAGE_KEY = "pulsemail_active_company_id";

export interface WorkspaceContextType {
  currentCompany: CompanyWithRole | null;
  currentCompanyId: number | null;
  currentRole: CompanyRole | null;
  companies: CompanyWithRole[];
  memberships: CompanyWithRole[];
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  setActiveCompanyId: (companyId: number) => void;
  refreshWorkspaces: () => Promise<void>;
  refetch: () => Promise<unknown>;
}

export const WorkspaceContext = createContext<WorkspaceContextType | undefined>(undefined);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading: isAuthLoading } = useAuth();
  const queryClient = useQueryClient();

  // Internal state tracking the user's explicitly selected active company ID
  const [selectedCompanyId, setSelectedCompanyId] = useState<number | null>(() => {
    try {
      const stored = localStorage.getItem(ACTIVE_COMPANY_STORAGE_KEY);
      if (stored) {
        const parsed = parseInt(stored, 10);
        return isNaN(parsed) ? null : parsed;
      }
    } catch {
      // LocalStorage access may fail in certain environments
    }
    return null;
  });

  // Query authenticated user's company memberships
  const {
    data: companies = [],
    isLoading: isCompaniesLoading,
    isError,
    error,
    refetch,
  } = useQuery<CompanyWithRole[], Error>({
    queryKey: ["my-companies"],
    queryFn: () => companiesApi.getMyCompanies(),
    enabled: isAuthenticated,
    staleTime: 30000,
  });

  // Clear workspace state when logged out
  useEffect(() => {
    if (!isAuthenticated && !isAuthLoading) {
      setSelectedCompanyId(null);
      try {
        localStorage.removeItem(ACTIVE_COMPANY_STORAGE_KEY);
      } catch {
        // Ignore storage errors
      }
    }
  }, [isAuthenticated, isAuthLoading]);

  // Deterministic resolution of active workspace:
  // 1. Zero memberships -> null
  // 2. Exactly one membership -> that company
  // 3. Multiple memberships -> match selectedCompanyId or localStorage if valid; otherwise fallback to companies[0]
  const currentCompany = useMemo<CompanyWithRole | null>(() => {
    if (!companies || companies.length === 0) {
      return null;
    }

    if (companies.length === 1) {
      return companies[0];
    }

    // Check if selectedCompanyId matches a valid membership
    if (selectedCompanyId !== null) {
      const match = companies.find((c) => c.id === selectedCompanyId);
      if (match) return match;
    }

    // Check persisted localStorage if state hasn't updated or was reset
    try {
      const stored = localStorage.getItem(ACTIVE_COMPANY_STORAGE_KEY);
      if (stored) {
        const parsed = parseInt(stored, 10);
        const match = companies.find((c) => c.id === parsed);
        if (match) return match;
      }
    } catch {
      // Ignore storage errors
    }

    // Deterministic fallback for multiple memberships: select first company returned
    return companies[0];
  }, [companies, selectedCompanyId]);

  // Synchronize state and persistence with resolved active company
  useEffect(() => {
    if (currentCompany) {
      if (selectedCompanyId !== currentCompany.id) {
        setSelectedCompanyId(currentCompany.id);
      }
      try {
        localStorage.setItem(ACTIVE_COMPANY_STORAGE_KEY, String(currentCompany.id));
      } catch {
        // Ignore storage errors
      }
    } else if (companies.length === 0 && !isCompaniesLoading) {
      if (selectedCompanyId !== null) {
        setSelectedCompanyId(null);
      }
      try {
        localStorage.removeItem(ACTIVE_COMPANY_STORAGE_KEY);
      } catch {
        // Ignore storage errors
      }
    }
  }, [currentCompany, companies.length, isCompaniesLoading, selectedCompanyId]);

  // Method to safely switch active company (only allows setting authorized companies)
  const setActiveCompanyId = useCallback(
    (companyId: number) => {
      const match = companies.find((c) => c.id === companyId);
      if (match) {
        setSelectedCompanyId(companyId);
        try {
          localStorage.setItem(ACTIVE_COMPANY_STORAGE_KEY, String(companyId));
        } catch {
          // Ignore storage errors
        }
      } else {
        console.warn(
          `Cannot switch to company ${companyId}: User is not an authorized member of this workspace.`
        );
      }
    },
    [companies]
  );

  // Method to refresh memberships after creation, invitation acceptance, or role change
  const refreshWorkspaces = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: ["my-companies"] });
    await refetch();
  }, [queryClient, refetch]);

  // Unified loading state:
  // Still loading if auth check is in flight, or if user is authenticated and membership query is loading
  const isLoading = isAuthLoading || (isAuthenticated && isCompaniesLoading);

  const value = useMemo<WorkspaceContextType>(
    () => ({
      currentCompany,
      currentCompanyId: currentCompany ? currentCompany.id : null,
      currentRole: currentCompany ? currentCompany.role : null,
      companies,
      memberships: companies,
      isLoading,
      isError: isAuthenticated ? isError : false,
      error: isAuthenticated ? error : null,
      setActiveCompanyId,
      refreshWorkspaces,
      refetch,
    }),
    [
      currentCompany,
      companies,
      isLoading,
      isAuthenticated,
      isError,
      error,
      setActiveCompanyId,
      refreshWorkspaces,
      refetch,
    ]
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}
