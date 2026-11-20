import { useTranslation } from 'react-i18next';
import type { Feedback, Product } from '../../api/types';
import { currentLanguage } from '../../i18n';
import { formatNumber, localize } from '../../i18n/format';
import { ContentText } from '../ContentText';
import { ChevronDownIcon } from '../icons';
import { card } from '../styles';
import { NeedStatusBadge } from './StatusBadges';
import { subHeading } from './styles';
import { type ShowTurn, TurnLink } from './TurnLink';

interface RevealedProfileProps {
  feedback: Feedback;
  product: (productId: string) => Product | undefined;
  onShowTurn: ShowTurn;
}

/** "Behind the scenes": the client's private profile, folded away. The persona and the facts
 * are English-only content, so in Arabic a note says so. */
export function RevealedProfile({ feedback, product, onShowTurn }: RevealedProfileProps) {
  const { t } = useTranslation();
  const language = currentLanguage();
  const { revealed, analysis } = feedback;
  const persona = revealed.persona;
  const name = (id: string) => {
    const found = product(id);
    return found ? localize(found.name, language) : id;
  };
  const howFound = new Map(analysis.facts.map((fact) => [fact.fact_id, fact.discovered_by]));
  const personaRows = [
    { label: t('feedback.profile.occupation'), value: <ContentText text={persona.occupation} /> },
    { label: t('feedback.profile.age'), value: formatNumber(persona.age, language) },
    { label: t('feedback.profile.nationality'), value: <ContentText text={persona.nationality} /> },
    ...(persona.family
      ? [{ label: t('feedback.profile.family'), value: <ContentText text={persona.family} /> }]
      : []),
    { label: t('feedback.profile.background'), value: <ContentText text={persona.background} /> },
    {
      label: t('feedback.profile.personality'),
      value: <ContentText text={persona.personality} />,
    },
    {
      label: t('feedback.profile.speakingStyle'),
      value: <ContentText text={persona.speaking_style} />,
    },
    {
      label: t('feedback.profile.financialKnowledge'),
      value: t(`feedback.profile.knowledge.${persona.financial_knowledge}`),
    },
  ];

  return (
    <details className={`${card} group`}>
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-5 py-3 font-semibold text-ink [&::-webkit-details-marker]:hidden">
        {t('feedback.profile.title')}
        <ChevronDownIcon className="size-5 group-open:rotate-180" />
      </summary>
      <div className="space-y-6 border-t border-line p-4 text-ink sm:p-5">
        {language === 'ar' && (
          <p className="text-sm text-ink-muted">{t('feedback.profile.englishOnly')}</p>
        )}
        <div>
          <h3 className={subHeading}>{t('feedback.profile.persona')}</h3>
          <dl className="mt-2 space-y-2">
            {personaRows.map((row) => (
              <div key={row.label} className="sm:flex sm:gap-3">
                <dt className="shrink-0 font-medium sm:w-44">{row.label}</dt>
                <dd>{row.value}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div>
          <h3 className={subHeading}>{t('feedback.profile.openFacts')}</h3>
          <ul className="mt-2 list-disc space-y-1 ps-5">
            {revealed.open_facts.map((fact) => (
              <li key={fact.en}>
                <ContentText text={fact} />
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3 className={subHeading}>{t('feedback.profile.hiddenFacts')}</h3>
          <ul className="mt-2 space-y-3">
            {revealed.hidden_facts.map((fact) => (
              <li key={fact.id} className="border-s-4 border-line ps-3">
                <p>
                  <ContentText text={fact.content} />
                </p>
                <p className="mt-1 text-sm text-ink-muted">
                  {t(`feedback.profile.importance.${fact.importance}`)}
                  {' · '}
                  {fact.unlocked_at_turn === null ? (
                    t('feedback.profile.notFound')
                  ) : (
                    <>
                      {t('feedback.profile.foundAt')}{' '}
                      <TurnLink n={fact.unlocked_at_turn} onShow={onShowTurn} />
                      {howFound.get(fact.id) === 'product_pitch' && (
                        <> ({t('feedback.profile.byPitch')})</>
                      )}
                    </>
                  )}
                </p>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h3 className={subHeading}>{t('feedback.profile.needs')}</h3>
          <ul className="mt-2 space-y-4">
            {revealed.needs.map((need) => (
              <li key={need.id} className="space-y-2 border-s-4 border-line ps-3">
                <p className="font-medium">
                  <ContentText text={need.description} />
                </p>
                <NeedStatusBadge status={need.status} />
                <p>
                  <span className="font-medium">{t('feedback.profile.suitable')}</span>{' '}
                  {need.suitable_products.length > 0
                    ? need.suitable_products.map(name).join(t('feedback.listSeparator'))
                    : t('feedback.profile.none')}
                </p>
                <div>
                  <p className="font-medium">{t('feedback.profile.unsuitable')}</p>
                  {need.unsuitable_products.length > 0 ? (
                    <ul className="mt-1 list-disc space-y-1 ps-5">
                      {need.unsuitable_products.map((entry) => (
                        <li key={entry.id}>
                          {name(entry.id)}: <ContentText text={entry.reason} />
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p>{t('feedback.profile.none')}</p>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>

        {revealed.referral_note && (
          <div>
            <h3 className={subHeading}>{t('feedback.profile.referral')}</h3>
            <p className="mt-2">
              <ContentText text={revealed.referral_note} />
            </p>
          </div>
        )}
      </div>
    </details>
  );
}
