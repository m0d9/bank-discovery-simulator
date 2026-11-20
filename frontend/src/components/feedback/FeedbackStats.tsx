import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { Feedback } from '../../api/types';
import { currentLanguage } from '../../i18n';
import { formatNumber } from '../../i18n/format';
import { type ShowTurn, TurnLink } from './TurnLink';

interface FeedbackStatsProps {
  stats: Feedback['analysis']['stats'];
  onShowTurn: ShowTurn;
}

/** The counts at the top of the page, never a score. Only needs that the student's questions
 * found count as found; those that came out after a pitch are shown apart. */
export function FeedbackStats({ stats, onShowTurn }: FeedbackStatsProps) {
  const { t } = useTranslation();
  const language = currentLanguage();
  const outOf = (found: number, total: number) =>
    t('feedback.map.outOf', {
      found: formatNumber(found, language),
      total: formatNumber(total, language),
    });
  return (
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Stat label={t('feedback.map.needs')}>
        {outOf(stats.needs_uncovered, stats.needs_total)}
        {stats.needs_after_pitch > 0 && (
          <span className="block text-sm font-normal text-ink-muted">
            {/* A left-to-right mark, so right-to-left text shows "+1", not "1+". */}
            {'\u200e'}
            {t('feedback.map.afterPitch', { n: formatNumber(stats.needs_after_pitch, language) })}
          </span>
        )}
      </Stat>
      <Stat label={t('feedback.map.critical')}>
        {outOf(stats.critical_found, stats.critical_total)}
      </Stat>
      <Stat label={t('feedback.map.questions')}>
        {formatNumber(stats.student_turns, language)}
      </Stat>
      <Stat label={t('feedback.map.firstFind')}>
        {stats.first_unlock_turn === null ? (
          t('feedback.map.none')
        ) : (
          <TurnLink n={stats.first_unlock_turn} onShow={onShowTurn} />
        )}
      </Stat>
    </dl>
  );
}

function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-md border border-line bg-surface px-4 py-3">
      <dt className="text-sm text-ink-muted">{label}</dt>
      <dd className="mt-1 text-lg font-semibold text-ink">{children}</dd>
    </div>
  );
}
