import { useCallback, useEffect, useState } from 'react';
import { type ApiError, getBank, getClients, getProducts, getSession, toApiError } from './client';

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
