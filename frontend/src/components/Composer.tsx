import type { KeyboardEvent, ReactNode, Ref } from 'react';
import { useTranslation } from 'react-i18next';
import { currentLanguage } from '../i18n';
import { countChars, formatNumber } from '../i18n/format';
import { AlertIcon } from './icons';
import { primaryButton } from './styles';

interface ComposerProps {
  id: string;
  label: string;
  hint?: string;
  sendLabel: string;
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  maxChars: number;
  /** A message is on its way: the text can't change, but focus stays here. */
  sending: boolean;
  /** No more messages can be sent (for example, the turn limit). */
  disabled?: boolean;
  /** Another line under the field, such as the turn counter. */
  status?: ReactNode;
  textareaRef?: Ref<HTMLTextAreaElement>;
}

/** A labelled message field: Enter sends, Shift+Enter adds a new line. It counts characters
 * as the server does, and never cuts pasted text: over the limit, it says by how much and
 * won't send. */
export function Composer({
  id,
  label,
  hint,
  sendLabel,
  value,
  onChange,
  onSubmit,
  maxChars,
  sending,
  disabled = false,
  status,
  textareaRef,
}: ComposerProps) {
  const { t } = useTranslation();
  const language = currentLanguage();
  const count = countChars(value);
  const over = count - maxChars;
  const canSend = count > 0 && over <= 0 && !sending && !disabled;
  const ids = { hint: `${id}-hint`, counter: `${id}-counter`, status: `${id}-status`, error: `${id}-error` };
  const describedBy = [
    hint && ids.hint,
    ids.counter,
    status !== undefined && ids.status,
    over > 0 && ids.error,
  ]
    .filter(Boolean)
    .join(' ');

  function submit() {
    if (canSend) onSubmit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // While an input method is composing, Enter confirms the composition: don't send.
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <label htmlFor={id} className="block font-semibold text-ink">
        {label}
      </label>
      {hint && (
        <p id={ids.hint} className="mt-1 text-sm text-ink-muted">
          {hint}
        </p>
      )}
      <textarea
        id={id}
        ref={textareaRef}
        value={value}
        rows={3}
        dir="auto"
        readOnly={sending}
        disabled={disabled}
        aria-disabled={sending || undefined}
        aria-invalid={over > 0 || undefined}
        aria-describedby={describedBy}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        onKeyDown={handleKeyDown}
        className="mt-2 block w-full resize-y rounded-md border border-line-strong bg-surface p-3 text-base text-ink aria-disabled:bg-surface-sunken aria-invalid:border-danger disabled:cursor-not-allowed disabled:bg-surface-sunken"
      />
      {over > 0 && (
        <p id={ids.error} className="mt-2 flex gap-2 text-sm font-medium text-danger">
          <AlertIcon className="mt-0.5 size-4" />
          {t('interview.charsOver', { count: over, value: formatNumber(over, language) })}
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm text-ink-muted">
          <span id={ids.counter}>
            {t('interview.chars', {
              used: formatNumber(count, language),
              max: formatNumber(maxChars, language),
            })}
          </span>
          {status !== undefined && <span id={ids.status}>{status}</span>}
        </div>
        <button type="submit" disabled={!canSend} className={primaryButton}>
          {sendLabel}
        </button>
      </div>
    </form>
  );
}
