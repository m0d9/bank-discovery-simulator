import type { ComponentType } from 'react';
import { useTranslation } from 'react-i18next';
import type { NeedStatus, Verdict } from '../../api/types';
import { Badge, type BadgeTone } from '../Badge';
import {
  CheckCircleIcon,
  CrossCircleIcon,
  DashedCircleIcon,
  HalfCircleIcon,
  MinusCircleIcon,
} from '../icons';

interface Look {
  tone: BadgeTone;
  Icon: ComponentType<{ className?: string }>;
}

const NEED: Record<NeedStatus, Look> = {
  uncovered: { tone: 'found', Icon: CheckCircleIcon },
  partial: { tone: 'neutral', Icon: HalfCircleIcon },
  missed: { tone: 'attention', Icon: DashedCircleIcon },
};

const VERDICT: Record<Verdict, Look> = {
  suitable: { tone: 'found', Icon: CheckCircleIcon },
  unsuitable: { tone: 'attention', Icon: CrossCircleIcon },
  not_in_key: { tone: 'neutral', Icon: MinusCircleIcon },
};

/** A need's status, as an icon and words (the tint only groups them). */
export function NeedStatusBadge({ status }: { status: NeedStatus }) {
  const { t } = useTranslation();
  const { tone, Icon } = NEED[status];
  return (
    <Badge tone={tone} icon={<Icon />}>
      {t(`feedback.status.${status}`)}
    </Badge>
  );
}

/** A recommended product's verdict, as an icon and words. */
export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const { t } = useTranslation();
  const { tone, Icon } = VERDICT[verdict];
  return (
    <Badge tone={tone} icon={<Icon />}>
      {t(`feedback.recommendations.verdict.${verdict}`)}
    </Badge>
  );
}
