import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import type { MessageResult, SessionPublic, Turn } from '../api/types';
import { bank, clients, created, products, session, transcript } from './fixtures';

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

interface FakeInterviewOptions {
  /** The transcript the session starts with (default: the opening line only). */
  turns?: Turn[];
  /** Other session fields, such as `max_message_chars` or `status`. */
  overrides?: Partial<SessionPublic>;
  /** Awaited before each reply, to hold a reply back. */
  beforeReply?: () => Promise<void>;
}

/** A small stateful stand-in for one interview: GET returns the transcript so far, and each
 * message gets the reply "Reply <n>.". `sent` records the texts the server received. */
export function fakeInterview({ turns: start, overrides, beforeReply }: FakeInterviewOptions = {}) {
  const turns = [...(start ?? transcript(0))];
  const sent: string[] = [];
  const studentTurns = () => turns.filter((turn) => turn.role === 'student').length;

  server.use(
    http.get('/api/sessions/:sessionId', ({ params }) =>
      HttpResponse.json(
        session({
          ...overrides,
          session_id: String(params.sessionId),
          turns: [...turns],
          student_turns_used: studentTurns(),
        }),
      ),
    ),
    http.post('/api/sessions/:sessionId/messages', async ({ request }) => {
      const { text } = (await request.json()) as { text: string };
      sent.push(text);
      await beforeReply?.();
      const student: Turn = { n: turns.length, role: 'student', text: text.trim() };
      const client: Turn = {
        n: turns.length + 1,
        role: 'client',
        text: `Reply ${String(studentTurns() + 1)}.`,
      };
      turns.push(student, client);
      const result: MessageResult = {
        student_turn: student,
        client_turn: client,
        student_turns_used: studentTurns(),
        max_student_turns: overrides?.max_student_turns ?? 30,
      };
      return HttpResponse.json(result);
    }),
  );
  return { sent };
}
