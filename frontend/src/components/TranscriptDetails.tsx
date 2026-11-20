import { useTranslation } from 'react-i18next';
import type { Turn } from '../api/types';
import { ChatLog } from './ChatLog';
import { ChevronDownIcon } from './icons';
import { card } from './styles';

interface TranscriptDetailsProps {
  turns: Turn[];
  /** The client's name in the UI language, for the screen-reader speaker labels. */
  clientName: string;
  /** Controlled when given, so an evidence link can open it. */
  open?: boolean;
  onToggle?: (open: boolean) => void;
  /** Shows each message's turn number, such as "Turn 3". */
  turnLabel?: (n: number) => string;
}

/** The interview, folded away for reference: on the wrap-up and feedback pages. */
export function TranscriptDetails({
  turns,
  clientName,
  open,
  onToggle,
  turnLabel,
}: TranscriptDetailsProps) {
  const { t } = useTranslation();
  return (
    <details
      className={`${card} group`}
      open={open}
      onToggle={(event) => onToggle?.(event.currentTarget.open)}
    >
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-5 py-3 font-semibold text-ink [&::-webkit-details-marker]:hidden">
        {t('common.transcript')}
        <ChevronDownIcon className="size-5 group-open:rotate-180" />
      </summary>
      <div className="border-t border-line p-4 sm:p-5">
        <ChatLog
          messages={turns}
          live={false}
          turnLabel={turnLabel}
          speakerLabel={(role) =>
            role === 'student'
              ? t('interview.youSaid')
              : t('interview.clientSaid', { name: clientName })
          }
        />
      </div>
    </details>
  );
}
