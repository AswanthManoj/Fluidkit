export interface CookieInstruction {
  name: string;
  value: string;
  path?: string;
  httpOnly?: boolean;
  secure?: boolean;
  sameSite?: 'lax' | 'strict' | 'none';
  maxAge?: number;
  domain?: string;
  expires?: string;
}

export interface MutationEntry {
  key: string;
  args: Record<string, unknown>;
  data: unknown;
  mutation_type: 'refresh' | 'set';
}

export interface FluidKitMeta {
  mutations: MutationEntry[];
  cookies: CookieInstruction[];
}

export interface QueryResponse<T> {
  result: T;
  __fk_locals?: Record<string, unknown>;
}

export interface BatchQueryResponse {
  results: unknown[];
  __fk_locals?: Record<string, unknown>;
}

export interface CommandResponse<T> {
  result: T;
  __fluidkit: FluidKitMeta;
  __fk_cookies?: CookieInstruction[];
  __fk_locals?: Record<string, unknown>;
}

export interface RedirectData {
  status: number;
  location: string;
}

export interface RedirectResponse {
  redirect: RedirectData;
  __fluidkit: FluidKitMeta;
  __fk_cookies?: CookieInstruction[];
  __fk_locals?: Record<string, unknown>;
}

export interface FluidKitErrorDetails {
  type: string;
  traceback: string;
}

export interface ErrorResponse {
  message: string;
  __fluidkit_error?: FluidKitErrorDetails;
}

export type CommandOrRedirect<T> = CommandResponse<T> | RedirectResponse;

export function isRedirect(res: CommandOrRedirect<unknown>): res is RedirectResponse {
  return 'redirect' in res;
}
