import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { CoachReport } from '../../api/types';
import { card } from '../styles';
import { sectionHeading } from './styles';
import { EvidenceLinks, type ShowTurn } from './TurnLink';

interface CoachSectionsProps {
  report: CoachReport;
  /** The student's own summary, which the last section comments on. */
  summary: string;
  onShowTurn: ShowTurn;
}

/** Sections 3 to 6: the AI coach's report. Its text comes from a model, so it keeps its own
 * direction (`dir="auto"`). */
export function CoachSections({ report, summary, onShowTurn }: CoachSectionsProps) {
  const { t } = useTranslation();
  return (
    <>
      <Section title={t('feedback.coach.wentWell')} empty={report.went_well.length === 0}>
        {report.went_well.map((item, index) => (
          <li key={index} className={`${card} p-4`}>
            <p dir="auto" className="text-ink">
              {item.point}
            </p>
            <EvidenceLinks turns={item.evidence_turns} onShow={onShowTurn} />
          </li>
        ))}
      </Section>
      <Section title={t('feedback.coach.missed')} empty={report.missed.length === 0}>
        {report.missed.map((item, index) => (
          <li key={index} className={`${card} p-4`}>
            <p dir="auto" className="text-ink">
              {item.point}
            </p>
            <EvidenceLinks turns={item.evidence_turns} onShow={onShowTurn} />
            {item.better_question && (
              <p className="mt-3 border-s-4 border-brand-tint ps-3 text-ink">
                <span className="font-medium">{t('feedback.coach.betterQuestion')}</span>{' '}
                <q dir="auto">{item.better_question}</q>
              </p>
            )}
          </li>
        ))}
      </Section>
      <Section title={t('feedback.coach.improve')} empty={report.how_to_improve.length === 0}>
        {report.how_to_improve.map((item, index) => (
          <li key={index} className={`${card} p-4`}>
            <p dir="auto" className="text-ink">
              {item.tip}
            </p>
            {item.example && (
              <p className="mt-2 text-ink">
                <span className="font-medium">{t('feedback.coach.example')}</span>{' '}
                <q dir="auto">{item.example}</q>
              </p>
            )}
          </li>
        ))}
      </Section>
      <section className="space-y-3">
        <h2 className={sectionHeading}>{t('feedback.coach.summary')}</h2>
        <figure className={`${card} p-4`}>
          <figcaption className="text-sm font-medium text-ink-muted">
            {t('feedback.coach.yourSummary')}
          </figcaption>
          <blockquote dir="auto" className="mt-2 whitespace-pre-wrap text-ink">
            {summary}
          </blockquote>
        </figure>
        <p dir="auto" className="text-ink">
          {report.summary_feedback}
        </p>
      </section>
    </>
  );
}

interface SectionProps {
  title: string;
  empty: boolean;
  children: ReactNode;
}

function Section({ title, empty, children }: SectionProps) {
  const { t } = useTranslation();
  return (
    <section className="space-y-3">
      <h2 className={sectionHeading}>{title}</h2>
      {empty ? (
        <p className="text-ink-muted">{t('feedback.coach.empty')}</p>
      ) : (
        <ul className="space-y-3">{children}</ul>
      )}
    </section>
  );
}
