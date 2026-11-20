import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Navigate, useNavigate } from 'react-router';
import { type ApiError, createSession, exportUrl, toApiError } from '../api/client';
import { useProducts, useSession } from '../api/hooks';
import type { Feedback, LocalizedText, Product, SessionPublic } from '../api/types';
import { useSessionModels } from '../components/AppShell';
import { ErrorBanner } from '../components/ErrorBanner';
import { CoachSections } from '../components/feedback/CoachSections';
import { DegradedNotice } from '../components/feedback/DegradedNotice';
import { DiscoveryMap } from '../components/feedback/DiscoveryMap';
import { Recommendations } from '../components/feedback/Recommendations';
import { RevealedProfile } from '../components/feedback/RevealedProfile';
import { DownloadIcon } from '../components/icons';
import { PageHeading } from '../components/PageHeading';
import { SessionLost } from '../components/SessionLost';
import { card, primaryButton, secondaryButton } from '../components/styles';
import { TranscriptDetails } from '../components/TranscriptDetails';
import { currentLanguage } from '../i18n';
import { localize } from '../i18n/format';
import { type FeedbackState, useFeedback } from './useFeedback';

const DOT_DELAYS = ['', '[animation-delay:150ms]', '[animation-delay:300ms]'];

/** The coach's feedback on a wrapped-up interview: the discovery map, the verdicts on the
 * student's recommendations, the coach's report, the transcript and the client's profile. */
export function FeedbackPage({ sessionId }: { sessionId: string }) {
  const { t } = useTranslation();
  const language = currentLanguage();
  const loaded = useSession(sessionId);
  const session = loaded.status === 'ready' ? loaded.data : undefined;
  useSessionModels(session?.models);
  const wrappedUp = session !== undefined && session.status !== 'interviewing';
  const feedback = useFeedback(sessionId, language, wrappedUp);

  // Nothing has been submitted yet: back to the interview.
  if (session?.status === 'interviewing') {
    return <Navigate to={`/interview/${sessionId}`} replace />;
  }

  const title = session
    ? t('feedback.titleWithName', { name: localize(session.client.name, language) })
    : t('feedback.title');

  return (
    <div className="max-w-3xl">
      <PageHeading title={title} />
      <div className="mt-6">
        {loaded.status === 'loading' && (
          <p role="status" className="text-ink-muted">
            {t('common.loading')}
          </p>
        )}
        {loaded.status === 'error' &&
          (loaded.error.code === 'SESSION_NOT_FOUND' ? (
            <SessionLost />
          ) : (
            <ErrorBanner error={loaded.error} onRetry={loaded.reload} />
          ))}
        {session && wrappedUp && <FeedbackView session={session} state={feedback} />}
      </div>
    </div>
  );
}

function FeedbackView({ session, state }: { session: SessionPublic; state: FeedbackState }) {
  const { t } = useTranslation();
  const products = useProducts();
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const [focusRequest, setFocusRequest] = useState<{ n: number } | null>(null);
  const language = currentLanguage();
  const clientName = localize(session.client.name, language);
  const { feedback, pending } = state;

  // Runs after the transcript has opened, so the turn can take focus.
  useEffect(() => {
    if (!focusRequest) return;
    const turn = document.getElementById(`turn-${String(focusRequest.n)}`);
    turn?.scrollIntoView({ block: 'center' });
    turn?.focus();
  }, [focusRequest]);

  const showTurn = useCallback((n: number) => {
    setTranscriptOpen(true);
    setFocusRequest({ n });
  }, []);

  const catalogue = products.status === 'ready' ? products.data : [];
  const product = (id: string): Product | undefined => catalogue.find((item) => item.id === id);

  return (
    <div className="space-y-10">
      {/* Outside the busy region, so the message is announced while the coach writes. */}
      <div role="status">
        {pending ? (
          <div className={`${card} flex items-center gap-3 p-6 text-ink`}>
            <span aria-hidden="true" className="inline-flex shrink-0 gap-1">
              {DOT_DELAYS.map((delay) => (
                <span
                  key={delay}
                  className={`size-2 rounded-full bg-brand motion-safe:animate-typing ${delay}`}
                />
              ))}
            </span>
            <p>{t('feedback.loading')}</p>
          </div>
        ) : (
          feedback &&
          !feedback.degraded && <span className="sr-only">{t('feedback.ready')}</span>
        )}
      </div>

      {state.error &&
        (state.error.code === 'SESSION_NOT_FOUND' ? (
          <SessionLost />
        ) : (
          <ErrorBanner error={state.error} onRetry={state.retry} />
        ))}

      {feedback && (
        <div aria-busy={pending} className="space-y-10">
          {feedback.degraded && <DegradedNotice onRetry={state.retry} retrying={pending} />}
          <FeedbackSections
            feedback={feedback}
            product={product}
            onShowTurn={showTurn}
            summary={feedback.wrapup.needs_summary}
          />
          <div className="space-y-4">
            <TranscriptDetails
              turns={session.turns}
              clientName={clientName}
              open={transcriptOpen}
              onToggle={setTranscriptOpen}
              turnLabel={(n) => t('feedback.turn', { n })}
            />
            <RevealedProfile feedback={feedback} product={product} onShowTurn={showTurn} />
          </div>
        </div>
      )}

      {(feedback ?? state.error) && <Actions session={session} />}
    </div>
  );
}

interface FeedbackSectionsProps {
  feedback: Feedback;
  product: (id: string) => Product | undefined;
  onShowTurn: (n: number) => void;
  summary: string;
}

function FeedbackSections({ feedback, product, onShowTurn, summary }: FeedbackSectionsProps) {
  const needs = new Map(feedback.revealed.needs.map((need) => [need.id, need.description]));
  const describeNeed = (needId: string): LocalizedText =>
    needs.get(needId) ?? { en: needId, ar: null };
  return (
    <>
      <DiscoveryMap
        analysis={feedback.analysis}
        describeNeed={describeNeed}
        onShowTurn={onShowTurn}
      />
      <Recommendations feedback={feedback} product={product} describeNeed={describeNeed} />
      {feedback.report && (
        <CoachSections report={feedback.report} summary={summary} onShowTurn={onShowTurn} />
      )}
    </>
  );
}

/** Start again with the same client, choose another, or download the whole session. */
function Actions({ session }: { session: SessionPublic }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [starting, setStarting] = useState(false);
  const [failure, setFailure] = useState<ApiError | null>(null);

  async function tryAgain() {
    if (starting) return;
    setStarting(true);
    setFailure(null);
    try {
      const created = await createSession(session.client.id, currentLanguage());
      await navigate(`/interview/${created.session_id}`);
    } catch (cause) {
      setFailure(toApiError(cause));
      setStarting(false);
    }
  }

  return (
    <div className="space-y-4">
      {failure && <ErrorBanner error={failure} />}
      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => void tryAgain()}
          aria-disabled={starting || undefined}
          className={primaryButton}
        >
          {starting ? t('feedback.actions.starting') : t('feedback.actions.tryAgain')}
        </button>
        <Link to="/" className={secondaryButton}>
          {t('feedback.actions.another')}
        </Link>
        <a href={exportUrl(session.session_id)} download className={secondaryButton}>
          <DownloadIcon className="size-5" />
          {t('feedback.actions.download')}
        </a>
      </div>
    </div>
  );
}
