import type { MouseEvent, ReactNode, Ref } from 'react';
import { AlertIcon } from './icons';

export interface FieldError {
  /** The id of the field the error is about. */
  id: string;
  message: string;
}

interface ErrorSummaryProps {
  title: string;
  errors: FieldError[];
  /** A problem that isn't about one field, such as a failed request. */
  message?: string;
  children?: ReactNode;
  ref?: Ref<HTMLDivElement>;
}

/** The form's problems at the top: the page moves focus here after a failed submit, and each
 * entry links to its field. */
export function ErrorSummary({ title, errors, message, children, ref }: ErrorSummaryProps) {
  // Focus the field directly: following "#id" would add a history entry the router would see.
  function goTo(event: MouseEvent<HTMLAnchorElement>, id: string) {
    event.preventDefault();
    document.getElementById(id)?.focus();
  }

  return (
    <div ref={ref} tabIndex={-1} className="rounded-md border-2 border-danger bg-surface p-5">
      <div role="alert">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-ink">
          <AlertIcon className="size-5 text-danger" />
          {title}
        </h2>
        {message && <p className="mt-2 text-ink">{message}</p>}
        {errors.length > 0 && (
          <ul className="mt-3 space-y-1">
            {errors.map((error) => (
              <li key={error.id}>
                <a
                  href={`#${error.id}`}
                  onClick={(event) => {
                    goTo(event, error.id);
                  }}
                  className="font-medium text-danger underline underline-offset-4"
                >
                  {error.message}
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
      {children && <div className="mt-4">{children}</div>}
    </div>
  );
}
