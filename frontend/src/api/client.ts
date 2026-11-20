import createClient from 'openapi-fetch';
import type { paths } from './schema';
import type {
  Bank,
  ClientCard,
  Feedback,
  Language,
  MessageResult,
  Product,
  SessionCreated,
  SessionPublic,
  WrapUpRequest,
} from './types';

/** Error codes the browser produces itself. The API's codes are listed in `error-codes.json`. */
export const NETWORK = 'NETWORK';
export const GENERIC = 'GENERIC';

/** A failed API call: the code and locale key from the error envelope, or `NETWORK` when the
 * server didn't answer with one. */
export class ApiError extends Error {
  readonly code: string;
  readonly messageKey: string;
  readonly detail: string | null;

  constructor(code: string, messageKey = `errors.${code}`, detail: string | null = null) {
    super(detail ? `${code}: ${detail}` : code);
    this.name = 'ApiError';
    this.code = code;
    this.messageKey = messageKey;
    this.detail = detail;
  }
}

const api = createClient<paths>({
  baseUrl: window.location.origin,
  // Look `fetch` up on every call rather than once at import, so test interceptors see requests.
  fetch: (request) => globalThis.fetch(request),
});

interface ErrorEnvelope {
  error: { code: string; message_key: string; detail: string | null };
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== 'object' || value === null || !('error' in value)) return false;
  const { error } = value;
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    typeof error.code === 'string' &&
    'message_key' in error &&
    typeof error.message_key === 'string'
  );
}

/** Any thrown value as an `ApiError`. */
export function toApiError(cause: unknown): ApiError {
  return cause instanceof ApiError ? cause : new ApiError(GENERIC);
}

interface CallResult<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

/** The data of an openapi-fetch call, or an `ApiError`. */
async function unwrap<T>(call: Promise<CallResult<T>>): Promise<T> {
  let result: CallResult<T>;
  try {
    result = await call;
  } catch {
    // fetch itself failed: the server is unreachable.
    throw new ApiError(NETWORK);
  }
  const { data, error, response } = result;
  if (response.ok && data !== undefined) return data;
  if (isErrorEnvelope(error)) {
    throw new ApiError(error.error.code, error.error.message_key, error.error.detail);
  }
  // Without the envelope, the reply didn't come from the API itself. In dev, Vite's proxy
  // answers 502 in plain text when the backend is down.
  throw new ApiError(response.ok ? GENERIC : NETWORK);
}

export function getBank(): Promise<Bank> {
  return unwrap(api.GET('/api/bank'));
}

export function getClients(): Promise<ClientCard[]> {
  return unwrap(api.GET('/api/clients'));
}

export function getProducts(): Promise<Product[]> {
  return unwrap(api.GET('/api/products'));
}

export function getSession(sessionId: string): Promise<SessionPublic> {
  return unwrap(
    api.GET('/api/sessions/{session_id}', { params: { path: { session_id: sessionId } } }),
  );
}

export function createSession(clientId: string, language: Language): Promise<SessionCreated> {
  return unwrap(api.POST('/api/sessions', { body: { client_id: clientId, language } }));
}

export function sendMessage(sessionId: string, text: string): Promise<MessageResult> {
  return unwrap(
    api.POST('/api/sessions/{session_id}/messages', {
      params: { path: { session_id: sessionId } },
      body: { text },
    }),
  );
}

export function submitWrapUp(sessionId: string, wrapUp: WrapUpRequest): Promise<SessionPublic> {
  return unwrap(
    api.POST('/api/sessions/{session_id}/wrapup', {
      params: { path: { session_id: sessionId } },
      body: wrapUp,
    }),
  );
}

/** The analysis and the coach's report, in `language`. The first call can take a minute. */
export function getFeedback(sessionId: string, language: Language): Promise<Feedback> {
  return unwrap(
    api.POST('/api/sessions/{session_id}/feedback', {
      params: { path: { session_id: sessionId }, query: { lang: language } },
    }),
  );
}

/** Where the browser downloads the session as Markdown (the server names the file). */
export function exportUrl(sessionId: string): string {
  return `/api/sessions/${encodeURIComponent(sessionId)}/export?format=md`;
}
