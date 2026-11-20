interface TypingIndicatorProps {
  active: boolean;
  text: string;
  /** A second line once the reply is slow. */
  slowText?: string;
}

const DOT_DELAYS = ['', '[animation-delay:150ms]', '[animation-delay:300ms]'];

/** "{name} is typing…", shown and announced. The region is always in the page, so screen
 * readers announce what appears in it; it sits outside the chat log, so a reply is announced
 * by the log alone. The dots only move when the user allows motion. */
export function TypingIndicator({ active, text, slowText }: TypingIndicatorProps) {
  return (
    <div role="status" className="text-sm text-ink-muted">
      {active && (
        <div className="space-y-1 py-2">
          <p className="flex items-center gap-2">
            <span aria-hidden="true" className="inline-flex gap-1">
              {DOT_DELAYS.map((delay) => (
                <span
                  key={delay}
                  className={`size-1.5 rounded-full bg-ink-muted motion-safe:animate-typing ${delay}`}
                />
              ))}
            </span>
            {text}
          </p>
          {slowText && <p>{slowText}</p>}
        </div>
      )}
    </div>
  );
}
