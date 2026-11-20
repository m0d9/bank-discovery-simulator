import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { bank, clients, created, products, session } from './fixtures';

/** An API error in the envelope the backend sends. */
export function apiError(code: string, status: number) {
  return HttpResponse.json(
    { error: { code, message_key: `errors.${code}`, detail: null } },
    { status },
  );
}

/** The happy path. Tests replace single routes with `server.use(...)`. */
export const server = setupServer(
  http.get('/api/bank', () => HttpResponse.json(bank)),
  http.get('/api/clients', () => HttpResponse.json(clients)),
  http.get('/api/products', () => HttpResponse.json(products)),
  http.post('/api/sessions', () => HttpResponse.json(created(), { status: 201 })),
  http.get('/api/sessions/:sessionId', ({ params }) =>
    HttpResponse.json(session({ session_id: String(params.sessionId) })),
  ),
);
