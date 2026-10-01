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

export interface CompanyWithRole {
  id: number;
  name: string;
  is_active: boolean;
  role: "OWNER" | "ADMIN" | "MEMBER";
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
