import { type SyntheticEvent, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { primaryButton, secondaryButton } from './styles';

interface EndInterviewDialogProps {
  open: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

/** A native modal <dialog>: it traps focus, Escape cancels, and the first button (the safe
 * choice) takes focus when it opens. */
export function EndInterviewDialog({ open, onCancel, onConfirm }: EndInterviewDialogProps) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  function cancel(event: SyntheticEvent<HTMLDialogElement>) {
    // Escape: let the parent close it, so its state and the dialog agree.
    event.preventDefault();
    onCancel();
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby="end-dialog-title"
      aria-describedby="end-dialog-body"
      onCancel={cancel}
      onClose={() => {
        // The browser can close it by itself (a repeated Escape); keep the parent in step.
        if (open) onCancel();
      }}
      className="m-auto w-[min(32rem,calc(100%-2rem))] rounded-lg border border-line bg-surface p-6 text-ink shadow-xl backdrop:bg-ink/50"
    >
      <h2 id="end-dialog-title" className="text-xl font-semibold">
        {t('interview.endDialog.title')}
      </h2>
      <p id="end-dialog-body" className="mt-3 text-ink-muted">
        {t('interview.endDialog.body')}
      </p>
      <div className="mt-6 flex flex-wrap justify-end gap-3">
        <button type="button" onClick={onCancel} className={secondaryButton}>
          {t('interview.endDialog.cancel')}
        </button>
        <button type="button" onClick={onConfirm} className={primaryButton}>
          {t('interview.endDialog.confirm')}
        </button>
      </div>
    </dialog>
  );
}
