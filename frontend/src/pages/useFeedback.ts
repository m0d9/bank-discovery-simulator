import { useCallback, useEffect, useState } from 'react';
import { type ApiError, getFeedback, toApiError } from '../api/client';
import type { Feedback, Language } from '../api/types';

type Result = { feedback: Feedback } | { error: ApiError };

interface Settled {
  key: string;
  attempt: number;
  result: Result;
}

export interface FeedbackState {
  /** The feedback for this session and language; kept on screen while a retry runs. */
  feedback?: Feedback;
  error?: ApiError;
  /** A request is running: the first one, or a retry. */
  pending: boolean;
  retry: () => void;
}

/** Asks for the feedback once the session is wrapped up (`enabled`), again when the language
 * changes (each language has its own report; the server caches both), and on `retry()`. A
 * result that arrives after the page has moved on is dropped. */
export function useFeedback(
  sessionId: string,
  language: Language,
  enabled: boolean,
): FeedbackState {
  const key = `${sessionId}:${language}`;
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<Settled>();

  useEffect(() => {
    if (!enabled) return;
    let current = true;
    getFeedback(sessionId, language).then(
      (feedback) => {
        if (current) setSettled({ key, attempt, result: { feedback } });
      },
      (cause: unknown) => {
        if (current) setSettled({ key, attempt, result: { error: toApiError(cause) } });
      },
    );
    return () => {
      current = false;
    };
  }, [sessionId, language, key, enabled, attempt]);

  const retry = useCallback(() => {
    setAttempt((n) => n + 1);
  }, []);

  const sameKey = settled?.key === key ? settled : undefined;
  const pending = enabled && sameKey?.attempt !== attempt;
  if (sameKey && 'feedback' in sameKey.result) {
    return { feedback: sameKey.result.feedback, pending, retry };
  }
  if (sameKey && !pending && 'error' in sameKey.result) {
    return { error: sameKey.result.error, pending, retry };
  }
  return { pending, retry };
}
