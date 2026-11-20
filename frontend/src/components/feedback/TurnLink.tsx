import { Fragment } from 'react';
import { useTranslation } from 'react-i18next';
import { textLink } from '../styles';

export type ShowTurn = (n: number) => void;

interface TurnLinkProps {
  n: number;
  onShow: ShowTurn;
}

/** "Turn 3": opens the transcript and moves focus to that message. A real link, so it reads
 * and works as one; the click is handled here because the transcript may be closed. */
export function TurnLink({ n, onShow }: TurnLinkProps) {
  const { t } = useTranslation();
  return (
    <a
      href={`#turn-${String(n)}`}
      className={textLink}
      onClick={(event) => {
        event.preventDefault();
        onShow(n);
      }}
    >
      {t('feedback.turn', { n })}
    </a>
  );
}

/** "Evidence: Turn 1, Turn 3", or nothing when there are no turns. */
export function EvidenceLinks({ turns, onShow }: { turns: number[]; onShow: ShowTurn }) {
  const { t } = useTranslation();
  if (turns.length === 0) return null;
  return (
    <p className="mt-2 text-sm text-ink-muted">
      {t('feedback.coach.evidence')}{' '}
      {turns.map((n, index) => (
        <Fragment key={n}>
          {index > 0 && t('feedback.listSeparator')}
          <TurnLink n={n} onShow={onShow} />
        </Fragment>
      ))}
    </p>
  );
}
