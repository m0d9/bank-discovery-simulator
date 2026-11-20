import { useTranslation } from 'react-i18next';
import type { Product } from '../api/types';
import { Badge } from './Badge';
import { PercentIcon, ScaleIcon } from './icons';

/** "Sharia-compliant" or "Interest-based", each with an icon and words. A product that is
 * neither (an account, a transfer service) gets no badge. */
export function ProductBadges({ product }: { product: Product }) {
  const { t } = useTranslation();
  if (!product.sharia_compliant && !product.interest_based) return null;
  return (
    <span className="flex flex-wrap gap-2">
      {product.sharia_compliant && (
        <Badge tone="sharia" icon={<ScaleIcon />}>
          {t('catalog.sharia')}
        </Badge>
      )}
      {product.interest_based && (
        <Badge tone="interest" icon={<PercentIcon />}>
          {t('catalog.interest')}
        </Badge>
      )}
    </span>
  );
}
