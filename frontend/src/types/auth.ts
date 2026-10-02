export interface User {
  id: number;
  email: string;
  full_name: string | null;
  is_active: boolean;
  created_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterCredentials {
  email: string;
  password: string;
  full_name?: string;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

export type CompanyRole = "OWNER" | "ADMIN" | "MEMBER";

export interface CompanyWithRole {
  id: number;
  name: string;
  is_active: boolean;
  role: CompanyRole;
  created_at: string;
}

export interface CompanyMember {
  id: number;
  company_id: number;
  user_id: number;
  email: string;
  full_name: string | null;
  role: "OWNER" | "ADMIN" | "MEMBER";
  is_active: boolean;
  created_at: string;
}

export interface CompanyMemberAddPayload {
  email: string;
  role: "ADMIN" | "MEMBER";
}

export interface CompanyMemberRoleUpdatePayload {
  role: "ADMIN" | "MEMBER";
}

export interface EmailAccountAccessItem {
  id: number;
  email_account_id: number;
  user_id: number;
  user_email: string;
  user_full_name: string | null;
  created_at: string;
}

export interface UserInvitationItem {
  id: number;
  company_id: number;
  company_name: string;
  role: "ADMIN" | "MEMBER";
  inviter_email: string;
  inviter_name: string | null;
  status: "PENDING" | "ACCEPTED" | "DECLINED";
  created_at: string;
}

export interface CompanyInvitationItem {
  id: number;
  company_id: number;
  company_name?: string | null;
  invited_email: string;
  invited_user_id?: number | null;
  inviter_user_id: number;
  inviter_email?: string | null;
  inviter_name?: string | null;
  role: "ADMIN" | "MEMBER";
  status: "PENDING" | "ACCEPTED" | "DECLINED";
  created_at: string;
  accepted_at?: string | null;
  declined_at?: string | null;
}
