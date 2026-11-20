import { useEffect, useState } from 'react';
import { type ApiError, sendMessage, toApiError } from '../api/client';
import { useSession } from '../api/hooks';
import type { Turn } from '../api/types';

/** After this long without a reply, the typing status adds that the first reply can be slow
 * while the model loads. The request itself never times out in the browser. */
export const SLOW_REPLY_MS = 8000;

/** The interview's state: the transcript loaded from the server (so a refresh loses
 * nothing), the turns added since, and the message on its way. */
export function useInterview(sessionId: string) {
  const loaded = useSession(sessionId);
  const [added, setAdded] = useState<Turn[]>([]);
  const [used, setUsed] = useState<number>();
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState<Turn | null>(null);
  const [slowTurn, setSlowTurn] = useState<number | null>(null);
  const [failure, setFailure] = useState<{ error: ApiError; text: string } | null>(null);

  useEffect(() => {
    if (!pending) return;
    const timer = window.setTimeout(() => {
      setSlowTurn(pending.n);
    }, SLOW_REPLY_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [pending]);

  const session = loaded.status === 'ready' ? loaded.data : undefined;
  const turns = session ? [...session.turns, ...added] : [];

  /** Send `text`. The student's message shows at once; on failure it's taken back and the
   * text returns to the composer. Nothing was saved, so sending it again is safe. */
  async function send(text: string): Promise<void> {
    if (!session || pending) return;
    setFailure(null);
    setDraft('');
    setPending({ n: turns.length, role: 'student', text: text.trim() });
    try {
      const result = await sendMessage(sessionId, text);
      setAdded((previous) => [...previous, result.student_turn, result.client_turn]);
      setUsed(result.student_turns_used);
    } catch (cause) {
      const error = toApiError(cause);
      setFailure({ error, text });
      setDraft(text);
      if (error.code === 'TURN_LIMIT') setUsed(session.max_student_turns);
    } finally {
      setPending(null);
    }
  }

  return {
    loaded,
    session,
    /** The transcript, then the student's message on its way. Keyed by turn number, so the
     * pending message becomes the saved one without being re-created. */
    messages: pending ? [...turns, pending] : turns,
    studentTurnsUsed: used ?? session?.student_turns_used ?? 0,
    draft,
    setDraft,
    sending: pending !== null,
    slow: pending !== null && slowTurn === pending.n,
    failure: failure?.error ?? null,
    send,
    /** Send the message that just failed, exactly as it was. */
    retry: () => (failure ? send(failure.text) : Promise.resolve()),
  };
}
