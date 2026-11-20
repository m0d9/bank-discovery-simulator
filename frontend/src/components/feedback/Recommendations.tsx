import { useTranslation } from 'react-i18next';
import type { Feedback, LocalizedText, Product } from '../../api/types';
import { currentLanguage } from '../../i18n';
import { localize } from '../../i18n/format';
import { ContentText } from '../ContentText';
import { ProductBadges } from '../ProductBadges';
import { card } from '../styles';
import { VerdictBadge } from './StatusBadges';
import { sectionHeading, subHeading } from './styles';

interface RecommendationsProps {
  feedback: Feedback;
  product: (productId: string) => Product | undefined;
  describeNeed: (needId: string) => LocalizedText;
}

/** Section 2: each recommended product with its verdict (icon, words and reason), then the
 * suitable products the student didn't recommend. */
export function Recommendations({ feedback, product, describeNeed }: RecommendationsProps) {
  const { t } = useTranslation();
  const language = currentLanguage();
  const { analysis, wrapup } = feedback;
  const name = (id: string) => {
    const found = product(id);
    return found ? localize(found.name, language) : id;
  };
  const needList = (needIds: string[]) => (
    <ul className="mt-1 list-disc space-y-1 ps-5">
      {needIds.map((needId) => (
        <li key={needId}>
          <ContentText text={describeNeed(needId)} />
        </li>
      ))}
    </ul>
  );

  return (
    <section className="space-y-4">
      <h2 className={sectionHeading}>{t('feedback.recommendations.title')}</h2>
      <ul className="space-y-3">
        {analysis.products.map((verdict) => {
          const studentReason = wrapup.recommendations.find(
            (item) => item.product_id === verdict.product_id,
          )?.reason;
          const details = product(verdict.product_id);
          // Each distinct reason once, as shown: the same reason can come up for two needs.
          const reasons = [
            ...new Map(
              verdict.reasons.map((item) => [localize(item.reason, language), item.reason]),
            ).values(),
          ];
          return (
            <li key={verdict.product_id} className={`${card} space-y-3 p-4`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="font-semibold text-ink">{name(verdict.product_id)}</p>
                <VerdictBadge verdict={verdict.verdict} />
              </div>
              {details && <ProductBadges product={details} />}
              {verdict.verdict === 'unsuitable' && (
                <ul className="space-y-1 text-ink">
                  {reasons.map((reason) => (
                    <li key={reason.en}>
                      <ContentText text={reason} />
                    </li>
                  ))}
                </ul>
              )}
              {verdict.verdict === 'suitable' && (
                <div className="text-ink">
                  <p>{t('feedback.recommendations.meets')}</p>
                  {needList(verdict.needs)}
                </div>
              )}
              {verdict.verdict === 'not_in_key' && (
                <p className="text-ink">{t('feedback.recommendations.notInKey')}</p>
              )}
              {studentReason && (
                <p className="text-sm text-ink-muted">
                  {t('feedback.recommendations.yourReason')}{' '}
                  <span dir="auto" className="text-ink">
                    {studentReason}
                  </span>
                </p>
              )}
            </li>
          );
        })}
      </ul>
      {analysis.missed_opportunities.length > 0 && (
        <>
          <h3 className={subHeading}>{t('feedback.recommendations.missedTitle')}</h3>
          <ul className="space-y-3">
            {analysis.missed_opportunities.map((item) => (
              <li key={item.product_id} className={`${card} p-4 text-ink`}>
                <p className="font-semibold">{name(item.product_id)}</p>
                <p className="mt-2">{t('feedback.recommendations.meets')}</p>
                {needList(item.needs)}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
