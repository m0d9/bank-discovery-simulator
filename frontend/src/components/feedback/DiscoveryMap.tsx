import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { Feedback, LocalizedText } from '../../api/types';
import { currentLanguage } from '../../i18n';
import { formatNumber } from '../../i18n/format';
import { ContentText } from '../ContentText';
import { NeedStatusBadge } from './StatusBadges';
import { sectionHeading } from './styles';
import { type ShowTurn, TurnLink } from './TurnLink';

interface DiscoveryMapProps {
  analysis: Feedback['analysis'];
  describeNeed: (needId: string) => LocalizedText;
  onShowTurn: ShowTurn;
}

/** Section 1: each need, its status (icon and words), and the turn and question that found
 * it. Counts above it, never a score. */
export function DiscoveryMap({ analysis, describeNeed, onShowTurn }: DiscoveryMapProps) {
  const { t } = useTranslation();
  const language = currentLanguage();
  const { stats } = analysis;
  const outOf = (found: number, total: number) =>
    t('feedback.map.outOf', {
      found: formatNumber(found, language),
      total: formatNumber(total, language),
    });
  const notFound = (
    <>
      <span aria-hidden="true">–</span>
      <span className="sr-only">{t('feedback.map.notFound')}</span>
    </>
  );

  return (
    <section className="space-y-4">
      <h2 id="discovery-map" className={sectionHeading}>
        {t('feedback.map.title')}
      </h2>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label={t('feedback.map.needs')}>
          {outOf(stats.needs_uncovered, stats.needs_total)}
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
      <table aria-labelledby="discovery-map" className="w-full border-collapse text-start">
        <thead>
          <tr className="border-b border-line-strong text-sm text-ink-muted">
            <th scope="col" className="py-2 pe-3 text-start font-semibold">
              {t('feedback.map.need')}
            </th>
            <th scope="col" className="py-2 pe-3 text-start font-semibold">
              {t('feedback.map.status')}
            </th>
            <th scope="col" className="py-2 pe-3 text-start font-semibold">
              {t('feedback.map.turn')}
            </th>
            <th scope="col" className="py-2 text-start font-semibold">
              {t('feedback.map.question')}
            </th>
          </tr>
        </thead>
        <tbody>
          {analysis.needs.map((need) => (
            <tr key={need.need_id} className="border-b border-line align-top">
              <th scope="row" className="py-3 pe-3 text-start font-medium text-ink">
                <ContentText text={describeNeed(need.need_id)} />
              </th>
              <td className="py-3 pe-3">
                <NeedStatusBadge status={need.status} />
              </td>
              <td className="py-3 pe-3 whitespace-nowrap">
                {need.via ? <TurnLink n={need.via.turn} onShow={onShowTurn} /> : notFound}
              </td>
              <td className="py-3 text-ink">
                {need.via ? (
                  <q dir="auto" className="wrap-break-word">
                    {need.via.question}
                  </q>
                ) : (
                  notFound
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
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
