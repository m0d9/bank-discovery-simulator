import { useCallback, useEffect, useState } from 'react';
import {
  type ApiError,
  getBank,
  getClients,
  getHealth,
  getProducts,
  getSession,
  onModelError,
  toApiError,
} from './client';
import type { Health } from './types';

export type Loadable<T> =
  | { status: 'loading' }
  | { status: 'ready'; data: T }
  | { status: 'error'; error: ApiError };

const LOADING = { status: 'loading' } as const;

/** Loads `fetcher(arg)` when the component mounts, when `arg` changes and on `reload()`.
 * A result that arrives after the component has moved on is dropped. */
export function useLoad<A, T>(
  fetcher: (arg: A) => Promise<T>,
  arg: A,
): Loadable<T> & { reload: () => void } {
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<{ arg: A; attempt: number; result: Loadable<T> }>();

  useEffect(() => {
    let current = true;
    fetcher(arg).then(
      (data) => {
        if (current) setSettled({ arg, attempt, result: { status: 'ready', data } });
      },
      (cause: unknown) => {
        if (current) {
          setSettled({ arg, attempt, result: { status: 'error', error: toApiError(cause) } });
        }
      },
    );
    return () => {
      current = false;
    };
  }, [fetcher, arg, attempt]);

  const reload = useCallback(() => {
    setAttempt((n) => n + 1);
  }, []);
  const result =
    settled !== undefined && settled.arg === arg && settled.attempt === attempt
      ? settled.result
      : LOADING;
  return { ...result, reload };
}

export function useBank() {
  return useLoad(getBank, undefined);
}

export function useClients() {
  return useLoad(getClients, undefined);
}

export function useProducts() {
  return useLoad(getProducts, undefined);
}

export function useSession(sessionId: string) {
  return useLoad(getSession, sessionId);
}

interface HealthCheck {
  /** The last answer from `/api/health`, or null before the first one. */
  health: Health | null;
  checking: boolean;
  recheck: () => void;
}

/** The model endpoint's health, checked on mount, on `recheck()` and after any request fails
 * with MODEL_UNAVAILABLE or MODEL_TIMEOUT. The last answer stays while a check runs, so a
 * banner built on it doesn't flicker, and when a check fails: the page then reports the
 * unreachable server itself. */
export function useHealth(): HealthCheck {
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<{ attempt: number; health: Health | null }>({
    attempt: -1,
    health: null,
  });

  useEffect(() => {
    let current = true;
    const settle = (health?: Health) => {
      if (current) setSettled((previous) => ({ attempt, health: health ?? previous.health }));
    };
    getHealth().then(settle, () => {
      settle();
    });
    return () => {
      current = false;
    };
  }, [attempt]);

  const recheck = useCallback(() => {
    setAttempt((n) => n + 1);
  }, []);
  useEffect(() => onModelError(recheck), [recheck]);
  return { health: settled.health, checking: settled.attempt !== attempt, recheck };
}
