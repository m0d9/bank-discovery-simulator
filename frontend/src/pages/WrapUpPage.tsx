import { type SubmitEvent, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useNavigate } from 'react-router';
import type { ApiError } from '../api/client';
import type { Product } from '../api/types';
import { useSessionModels } from '../components/AppShell';
import { ErrorBanner } from '../components/ErrorBanner';
import { ErrorSummary, type FieldError } from '../components/ErrorSummary';
import { PageHeading } from '../components/PageHeading';
import { ProductBadges } from '../components/ProductBadges';
import { SessionLost } from '../components/SessionLost';
import { TranscriptDetails } from '../components/TranscriptDetails';
import { card, primaryButton, secondaryButton } from '../components/styles';
import { currentLanguage } from '../i18n';
import { errorMessage } from '../i18n/errors';
import { formatNumber, localize, trimmedLength } from '../i18n/format';
import { useWrapUp, WRAP_UP_LIMITS } from './useWrapUp';

interface Problems {
  summary?: string;
  products?: string;
  reasons: Partial<Record<string, string>>;
}

const field =
  'mt-2 block w-full resize-y rounded-md border border-line-strong bg-surface p-3 text-base text-ink aria-invalid:border-danger';

export function WrapUpPage({ sessionId }: { sessionId: string }) {
  const { t } = useTranslation();
  const language = currentLanguage();
  const navigate = useNavigate();
  const form = useWrapUp(sessionId);
  const summaryRef = useRef<HTMLDivElement>(null);
  const [problems, setProblems] = useState<Problems | null>(null);
  const [failure, setFailure] = useState<ApiError | null>(null);
  const [attempts, setAttempts] = useState(0);
  const session = form.session.status === 'ready' ? form.session.data : undefined;
  const products = form.products.status === 'ready' ? form.products.data : [];
  useSessionModels(session?.models);

  // After each failed submit, the error summary takes focus, so it's read out.
  useEffect(() => {
    if (attempts > 0) summaryRef.current?.focus();
  }, [attempts]);

  const productName = (product: Product) => localize(product.name, language);
  const lengthHint = (limits: { min: number; max: number }) =>
    t('wrapup.lengthHint', {
      count: limits.max,
      min: formatNumber(limits.min, language),
      value: formatNumber(limits.max, language),
    });

  function validate(): Problems {
    const found: Problems = { reasons: {} };
    const { summary: summaryLimits, reason: reasonLimits } = WRAP_UP_LIMITS;
    const length = trimmedLength(form.summary);
    if (length < summaryLimits.min) found.summary = t('wrapup.errors.summaryShort');
    else if (length > summaryLimits.max) found.summary = t('wrapup.errors.summaryLong');
    if (form.chosen.length === 0) found.products = t('wrapup.errors.noProducts');
    for (const product of products.filter((item) => form.chosen.includes(item.id))) {
      const reason = trimmedLength(form.reasons[product.id] ?? '');
      const name = { product: productName(product) };
      if (reason === 0) found.reasons[product.id] = t('wrapup.errors.reasonMissing', name);
      else if (reason < reasonLimits.min) found.reasons[product.id] = t('wrapup.errors.reasonShort', name);
      else if (reason > reasonLimits.max) found.reasons[product.id] = t('wrapup.errors.reasonLong', name);
    }
    return found;
  }

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (form.submitting) return;
    const found = validate();
    const valid = !found.summary && !found.products && Object.keys(found.reasons).length === 0;
    setProblems(found);
    setFailure(null);
    if (!valid) {
      setAttempts((n) => n + 1);
      return;
    }
    const error = await form.submit();
    if (!error) {
      await navigate(`/feedback/${sessionId}`);
      return;
    }
    setFailure(error);
    setAttempts((n) => n + 1);
  }

  const name = session ? localize(session.client.name, language) : '';
  const heading = (
    <PageHeading title={session ? t('wrapup.title', { name }) : t('wrapup.titleShort')} />
  );

  if (!session) {
    return (
      <>
        {heading}
        <div className="mt-6">
          {form.session.status === 'loading' && (
            <p role="status" className="text-ink-muted">
              {t('common.loading')}
            </p>
          )}
          {form.session.status === 'error' &&
            (form.session.error.code === 'SESSION_NOT_FOUND' ? (
              <SessionLost />
            ) : (
              <ErrorBanner error={form.session.error} onRetry={form.session.reload} />
            ))}
        </div>
      </>
    );
  }

  if (session.status !== 'interviewing') {
    return <Navigate to={`/feedback/${sessionId}`} replace />;
  }

  const fieldErrors: FieldError[] = [];
  if (problems?.summary) fieldErrors.push({ id: 'summary', message: problems.summary });
  const firstProduct = products[0];
  if (problems?.products && firstProduct) {
    fieldErrors.push({ id: `product-${firstProduct.id}`, message: problems.products });
  }
  for (const product of products) {
    const message = problems?.reasons[product.id];
    if (message && form.chosen.includes(product.id)) {
      fieldErrors.push({ id: `reason-${product.id}`, message });
    }
  }
  const showSummary = fieldErrors.length > 0 || failure !== null;
  const atMax = form.chosen.length >= WRAP_UP_LIMITS.products.max;
  const describedBy = (...ids: (string | false | undefined)[]) => ids.filter(Boolean).join(' ');

  return (
    <div className="max-w-3xl">
      {heading}
      <p className="mt-3 text-lg text-ink-muted">{t('wrapup.intro')}</p>

      {showSummary && (
        <div className="mt-6">
          <ErrorSummary
            ref={summaryRef}
            title={t('wrapup.errorSummaryTitle')}
            errors={fieldErrors}
            message={failure ? errorMessage(t, failure) : undefined}
          >
            {failure?.code === 'SESSION_NOT_FOUND' && (
              <Link to="/" className={secondaryButton}>
                {t('common.startAgain')}
              </Link>
            )}
          </ErrorSummary>
        </div>
      )}

      <div className="mt-6">
        <TranscriptDetails turns={session.turns} clientName={name} />
      </div>

      <form noValidate onSubmit={(event) => void handleSubmit(event)} className="mt-8 space-y-8">
        <div>
          <label htmlFor="summary" className="block text-lg font-semibold text-ink">
            {t('wrapup.summaryLabel')}
          </label>
          <p id="summary-hint" className="mt-1 text-sm text-ink-muted">
            {lengthHint(WRAP_UP_LIMITS.summary)}
          </p>
          {problems?.summary && <InlineError id="summary-error" message={problems.summary} />}
          <textarea
            id="summary"
            rows={6}
            dir="auto"
            required
            value={form.summary}
            onChange={(event) => {
              form.setSummary(event.target.value);
            }}
            aria-invalid={problems?.summary ? true : undefined}
            aria-describedby={describedBy('summary-hint', problems?.summary && 'summary-error')}
            className={field}
          />
        </div>

        <fieldset
          aria-describedby={describedBy(
            'products-hint',
            'products-count',
            problems?.products && 'products-error',
          )}
        >
          <legend className="text-lg font-semibold text-ink">{t('wrapup.productsLegend')}</legend>
          <p id="products-hint" className="mt-1 text-sm text-ink-muted">
            {t('wrapup.productsHint', { count: WRAP_UP_LIMITS.products.max })}
          </p>
          <p id="products-count" aria-live="polite" className="mt-1 text-sm font-medium text-ink">
            {t('wrapup.chosen', {
              chosen: formatNumber(form.chosen.length, language),
              max: formatNumber(WRAP_UP_LIMITS.products.max, language),
            })}
            {atMax && <span className="block font-normal text-ink-muted">{t('wrapup.atMax')}</span>}
          </p>
          {problems?.products && <InlineError id="products-error" message={problems.products} />}
          {form.products.status === 'error' && (
            <div className="mt-3">
              <ErrorBanner error={form.products.error} onRetry={form.products.reload} />
            </div>
          )}
          <ul className="mt-4 space-y-3">
            {products.map((product) => {
              const checked = form.chosen.includes(product.id);
              const reasonError = checked ? problems?.reasons[product.id] : undefined;
              return (
                <li key={product.id} className={`${card} p-4`}>
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      id={`product-${product.id}`}
                      checked={checked}
                      disabled={!checked && atMax}
                      onChange={() => {
                        form.toggle(product.id);
                      }}
                      className="mt-1 size-5 shrink-0 accent-brand"
                    />
                    <label htmlFor={`product-${product.id}`} className="min-w-0 flex-1 space-y-1.5">
                      <span className="block font-semibold text-ink">{productName(product)}</span>
                      <ProductBadges product={product} />
                    </label>
                  </div>
                  {checked && (
                    <div className="mt-3 ps-8">
                      <label htmlFor={`reason-${product.id}`} className="block font-medium text-ink">
                        {t('wrapup.reasonLabel')}{' '}
                        <span className="sr-only">{productName(product)}</span>
                      </label>
                      <p id={`reason-${product.id}-hint`} className="mt-1 text-sm text-ink-muted">
                        {lengthHint(WRAP_UP_LIMITS.reason)}
                      </p>
                      {reasonError && (
                        <InlineError id={`reason-${product.id}-error`} message={reasonError} />
                      )}
                      <textarea
                        id={`reason-${product.id}`}
                        rows={3}
                        dir="auto"
                        required
                        value={form.reasons[product.id] ?? ''}
                        onChange={(event) => {
                          form.setReason(product.id, event.target.value);
                        }}
                        aria-invalid={reasonError ? true : undefined}
                        aria-describedby={describedBy(
                          `reason-${product.id}-hint`,
                          reasonError && `reason-${product.id}-error`,
                        )}
                        className={field}
                      />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </fieldset>

        <button
          type="submit"
          aria-disabled={form.submitting || undefined}
          className={primaryButton}
        >
          {form.submitting ? t('wrapup.submitting') : t('wrapup.submit')}
        </button>
      </form>
    </div>
  );
}

function InlineError({ id, message }: { id: string; message: string }) {
  return (
    <p id={id} className="mt-2 text-sm font-medium text-danger">
      {message}
    </p>
  );
}
