export interface ApiError {
  message: string;
  status?: number;
  detail?: string | Record<string, unknown> | Array<{ loc: string[]; msg: string; type: string }>;
}

export interface ApiResponse<T = unknown> {
  data: T;
  status: number;
}
