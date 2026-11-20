import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Navigate, useNavigate } from 'react-router';
import { useProducts } from '../api/hooks';
import { useSessionModels } from '../components/AppShell';
import { Badge } from '../components/Badge';
import { CatalogPanel } from '../components/CatalogPanel';
import { ChatLog } from '../components/ChatLog';
import { Composer } from '../components/Composer';
import { EndInterviewDialog } from '../components/EndInterviewDialog';
import { ErrorBanner } from '../components/ErrorBanner';
import { InfoIcon } from '../components/icons';
import { PageHeading } from '../components/PageHeading';
import { canRetry, SessionLost } from '../components/SessionLost';
import { card, secondaryButton } from '../components/styles';
import { TypingIndicator } from '../components/TypingIndicator';
import { currentLanguage } from '../i18n';
import { formatNumber, localize } from '../i18n/format';
import { useInterview } from './useInterview';

/** The student must ask at least this many questions before ending the interview. */
const MIN_TURNS_TO_END = 3;

export function InterviewPage({ sessionId }: { sessionId: string }) {
  const { t } = useTranslation();
  const language = currentLanguage();
  const navigate = useNavigate();
  const interview = useInterview(sessionId);
  const products = useProducts();
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const endRef = useRef<HTMLButtonElement>(null);
  const [confirming, setConfirming] = useState(false);
  const { session, loaded, failure } = interview;
  useSessionModels(session?.models);

  // Keep the composer in view as the conversation grows.
  const messageCount = interview.messages.length;
  useEffect(() => {
    composerRef.current?.scrollIntoView({ block: 'nearest' });
  }, [messageCount]);

  // Focus stays in (or comes back to) the composer after every reply.
  async function submit(text: string) {
    await interview.send(text);
    composerRef.current?.focus();
  }

  async function submitRetry() {
    await interview.retry();
    composerRef.current?.focus();
  }

  const name = session ? localize(session.client.name, language) : '';
  const heading = (
    <PageHeading title={session ? t('interview.title', { name }) : t('interview.titleShort')} />
  );

  if (!session) {
    return (
      <>
        {heading}
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
        </div>
      </>
    );
  }

  if (session.status !== 'interviewing') {
    return <Navigate to={`/feedback/${sessionId}`} replace />;
  }

  const lost = failure?.code === 'SESSION_NOT_FOUND';
  const atLimit = interview.studentTurnsUsed >= session.max_student_turns;
  const canEnd = interview.studentTurnsUsed >= MIN_TURNS_TO_END;

  return (
    <>
      {heading}
      <p className="mt-2 text-ink-muted">{localize(session.client.headline, language)}</p>
      <ul className="mt-3 flex flex-wrap gap-2">
        <li>
          <Badge>{t(`common.segment.${session.client.segment}`)}</Badge>
        </li>
        <li>
          <Badge>
            {t('common.difficultyLabel', {
              level: t(`common.difficulty.${session.client.difficulty}`),
            })}
          </Badge>
        </li>
      </ul>
      {language === 'ar' && (
        <p className="mt-4 flex gap-2 text-sm text-ink-muted">
          <InfoIcon className="mt-1 size-4" />
          {t('interview.arabicNote')}
        </p>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="min-w-0 space-y-6">
          <section aria-labelledby="conversation-title" className={`${card} p-4 sm:p-6`}>
            <h2 id="conversation-title" className="sr-only">
              {t('interview.conversation')}
            </h2>
            <ChatLog
              messages={interview.messages}
              labelledBy="conversation-title"
              speakerLabel={(role) =>
                role === 'student' ? t('interview.youSaid') : t('interview.clientSaid', { name })
              }
            />
            <TypingIndicator
              active={interview.sending}
              text={t('interview.typing', { name })}
              slowText={interview.slow ? t('interview.slowReply') : undefined}
            />
            {failure && !lost && (
              <div className="mt-4">
                <ErrorBanner
                  error={failure}
                  onRetry={canRetry(failure) ? () => void submitRetry() : undefined}
                />
              </div>
            )}
            <div className="mt-4 border-t border-line pt-4">
              {lost ? (
                <SessionLost />
              ) : (
                <Composer
                  id="message"
                  label={t('interview.messageLabel')}
                  hint={atLimit ? t('interview.turnLimit') : t('interview.messageHint')}
                  sendLabel={t('interview.send')}
                  value={interview.draft}
                  onChange={interview.setDraft}
                  onSubmit={() => void submit(interview.draft)}
                  maxChars={session.max_message_chars}
                  sending={interview.sending}
                  disabled={atLimit}
                  textareaRef={composerRef}
                  status={t('interview.turns', {
                    used: formatNumber(interview.studentTurnsUsed, language),
                    max: formatNumber(session.max_student_turns, language),
                  })}
                />
              )}
            </div>
          </section>

          {!lost && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <button
                ref={endRef}
                type="button"
                aria-disabled={!canEnd || interview.sending || undefined}
                aria-describedby={canEnd ? undefined : 'end-hint'}
                onClick={() => {
                  if (canEnd && !interview.sending) setConfirming(true);
                }}
                className={secondaryButton}
              >
                {t('interview.end')}
              </button>
              {!canEnd && (
                <p id="end-hint" className="text-sm text-ink-muted">
                  {t('interview.endHint', { count: MIN_TURNS_TO_END })}
                </p>
              )}
            </div>
          )}
        </div>

        <CatalogPanel products={products} />
      </div>

      <EndInterviewDialog
        open={confirming}
        onCancel={() => {
          setConfirming(false);
          endRef.current?.focus();
        }}
        onConfirm={() => void navigate(`/wrapup/${sessionId}`)}
      />
    </>
  );
}
