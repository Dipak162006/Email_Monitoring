export interface RecipientList {
  id: number;
  company_id: number;
  name: string;
  description: string | null;
  created_by_user_id: number | null;
  recipient_count: number;
  created_at: string;
  updated_at: string;
}

export interface RecipientListPaginationResponse {
  items: RecipientList[];
  total: number;
  limit: number;
  offset: number;
}

export interface RecipientListCreatePayload {
  name: string;
  description?: string | null;
}

export interface RecipientListUpdatePayload {
  name?: string;
  description?: string | null;
}

export interface RecipientListQueryParams {
  search?: string;
  limit?: number;
  offset?: number;
}

export interface RecipientListMember {
  id: number;
  list_id: number;
  email: string;
  first_name: string | null;
  last_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface RecipientListMemberPaginationResponse {
  items: RecipientListMember[];
  total: number;
  limit: number;
  offset: number;
}

export interface RecipientListMemberCreatePayload {
  email: string;
  first_name?: string | null;
  last_name?: string | null;
}

export interface RecipientListMemberUpdatePayload {
  email?: string;
  first_name?: string | null;
  last_name?: string | null;
}

export interface RecipientListMemberQueryParams {
  search?: string;
  limit?: number;
  offset?: number;
}

export interface RecipientListImportInvalidRow {
  row: number;
  email: string;
  reason: string;
}

export interface RecipientListMemberImportResponse {
  total_rows: number;
  imported_count: number;
  file_duplicates_count: number;
  existing_duplicates_count: number;
  invalid_rows_count: number;
  invalid_rows: RecipientListImportInvalidRow[];
}
