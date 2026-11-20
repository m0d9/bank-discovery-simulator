import { useState } from 'react';
import { type ApiError, submitWrapUp, toApiError } from '../api/client';
import { useProducts, useSession } from '../api/hooks';
import type { WrapUpRequest } from '../api/types';

/** The API's wrap-up limits (`WrapUpDTO` in openapi.json; a test keeps them in step). Lengths
 * count characters after trimming. */
export const WRAP_UP_LIMITS = {
  summary: { min: 30, max: 2000 },
  reason: { min: 5, max: 500 },
  products: { min: 1, max: 3 },
} as const;

/** The wrap-up form: the summary, the chosen products in the order chosen, and a reason for
 * each. Unticking a product forgets nothing: ticking it again brings its reason back. */
export function useWrapUp(sessionId: string) {
  const session = useSession(sessionId);
  const products = useProducts();
  const [summary, setSummary] = useState('');
  const [chosen, setChosen] = useState<string[]>([]);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  function toggle(productId: string) {
    setChosen((current) => {
      if (current.includes(productId)) return current.filter((id) => id !== productId);
      return current.length < WRAP_UP_LIMITS.products.max ? [...current, productId] : current;
    });
  }

  function setReason(productId: string, reason: string) {
    setReasons((current) => ({ ...current, [productId]: reason }));
  }

  /** Send the wrap-up. Resolves to the error, if it failed. */
  async function submit(): Promise<ApiError | null> {
    const body: WrapUpRequest = {
      needs_summary: summary.trim(),
      recommendations: chosen.map((id) => ({ product_id: id, reason: (reasons[id] ?? '').trim() })),
    };
    setSubmitting(true);
    try {
      await submitWrapUp(sessionId, body);
      return null;
    } catch (cause) {
      return toApiError(cause);
    } finally {
      setSubmitting(false);
    }
  }

  return {
    session,
    products,
    summary,
    setSummary,
    chosen,
    toggle,
    reasons,
    setReason,
    submitting,
    submit,
  };
}
