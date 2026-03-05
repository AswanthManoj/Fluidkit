export interface QueryResponse<T> {
  result: T;
}

export interface MutationEntry {
  key: string;
  args: Record<string, unknown>;
  data: unknown;
  mutation_type: 'refresh' | 'set';
}

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

export interface FluidKitMeta {
  mutations: MutationEntry[];
  cookies: CookieInstruction[];
}

export interface CommandResponse<T> {
  result: T;
  __fluidkit: FluidKitMeta;
}

export interface RedirectData {
  status: number;
  location: string;
}

export interface RedirectResponse {
  redirect: RedirectData;
  __fluidkit: FluidKitMeta;
}

export interface FluidKitErrorDetails {
  type: string;
  traceback: string;
}

export interface ErrorResponse {
  message: string;
  __fluidkit_error?: FluidKitErrorDetails;
}

// Discriminated union for command/form responses
export type CommandOrRedirect<T> = CommandResponse<T> | RedirectResponse;

export function isRedirect(res: CommandOrRedirect<unknown>): res is RedirectResponse {
  return 'redirect' in res;
}
