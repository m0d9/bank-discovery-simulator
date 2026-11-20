import { useTranslation } from 'react-i18next';
import type { Loadable } from '../api/hooks';
import type { LocalizedText, Product } from '../api/types';
import { currentLanguage } from '../i18n';
import { localize } from '../i18n/format';
import { ErrorBanner } from './ErrorBanner';
import { ChevronDownIcon } from './icons';
import { ProductBadges } from './ProductBadges';
import { card } from './styles';
import { useMediaQuery } from './useMediaQuery';

/** The width from which the interview has two columns (Tailwind's `lg`). */
const WIDE = '(min-width: 64rem)';

interface CatalogPanelProps {
  products: Loadable<Product[]> & { reload: () => void };
}

/** The product catalogue beside the chat. On narrow screens the whole panel folds into a
 * <details>, so the conversation comes first. */
export function CatalogPanel({ products }: CatalogPanelProps) {
  const { t } = useTranslation();
  const wide = useMediaQuery(WIDE);

  const content = (
    <>
      <p className="text-sm text-ink-muted">{t('catalog.intro')}</p>
      {products.status === 'loading' && (
        <p role="status" className="mt-4 text-sm text-ink-muted">
          {t('catalog.loading')}
        </p>
      )}
      {products.status === 'error' && (
        <div className="mt-4">
          <ErrorBanner error={products.error} onRetry={products.reload} />
        </div>
      )}
      {products.status === 'ready' && (
        <ul className="mt-4 space-y-3">
          {products.data.map((product) => (
            <li key={product.id}>
              <ProductItem product={product} />
            </li>
          ))}
        </ul>
      )}
    </>
  );

  return (
    <aside
      aria-labelledby="catalog-title"
      className="min-w-0 lg:sticky lg:top-6 lg:max-h-[calc(100vh-3rem)] lg:self-start lg:overflow-y-auto"
    >
      {wide ? (
        <div className={`${card} p-5`}>
          <h2 id="catalog-title" className="mb-1 text-lg font-semibold text-ink">
            {t('catalog.title')}
          </h2>
          {content}
        </div>
      ) : (
        <details className={`${card} group`}>
          <summary
            id="catalog-title"
            className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-5 py-3 text-lg font-semibold text-ink [&::-webkit-details-marker]:hidden"
          >
            {t('catalog.title')}
            <ChevronDownIcon className="size-5 group-open:rotate-180" />
          </summary>
          <div className="px-5 pb-5">{content}</div>
        </details>
      )}
    </aside>
  );
}

function ProductItem({ product }: { product: Product }) {
  const { t } = useTranslation();
  const language = currentLanguage();
  const text = (value: LocalizedText) => localize(value, language);

  return (
    <details className="group/item rounded-md border border-line bg-surface">
      <summary className="flex cursor-pointer list-none gap-3 p-3 [&::-webkit-details-marker]:hidden">
        <span className="min-w-0 flex-1 space-y-1.5">
          <span className="block font-semibold text-ink">{text(product.name)}</span>
          <ProductBadges product={product} />
          <span className="block text-sm text-ink-muted">{text(product.summary)}</span>
        </span>
        <ChevronDownIcon className="mt-1 size-5 text-ink-muted group-open/item:rotate-180" />
      </summary>
      <dl className="space-y-3 border-t border-line px-3 py-3 text-sm text-ink">
        <DetailList term={t('catalog.features')} items={product.features.map(text)} />
        <DetailList term={t('catalog.limitations')} items={product.limitations.map(text)} />
        <DetailList term={t('catalog.eligibility')} items={product.eligibility.map(text)} />
        <div>
          <dt className="font-semibold">{t('catalog.pricing')}</dt>
          <dd className="mt-1">{text(product.pricing)}</dd>
        </div>
      </dl>
    </details>
  );
}

function DetailList({ term, items }: { term: string; items: string[] }) {
  return (
    <div>
      <dt className="font-semibold">{term}</dt>
      <dd className="mt-1">
        <ul className="list-disc space-y-1 ps-5">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </dd>
    </div>
  );
}
