import type { ReactNode } from 'react';

interface IconProps {
  className?: string;
}

/** A decorative icon: always next to text that carries the meaning, so hidden from assistive
 * technology. */
function Icon({ className = 'size-4', children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={`shrink-0 ${className}`}
    >
      {children}
    </svg>
  );
}

export function GlobeIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z" />
    </Icon>
  );
}

/** Sharia-compliant: a balance, not a tick, so the badge doesn't read as "good". */
export function ScaleIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 4v16M8 20h8M5 7h14" />
      <path d="M5 7l-3 6a3 3 0 0 0 6 0zM19 7l-3 6a3 3 0 0 0 6 0z" />
    </Icon>
  );
}

/** Interest-based: a percent sign, not a cross, so the badge doesn't read as "bad". */
export function PercentIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M19 5L5 19" />
      <circle cx="7" cy="7" r="2.5" />
      <circle cx="17" cy="17" r="2.5" />
    </Icon>
  );
}

export function InfoIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5M12 8h.01" />
    </Icon>
  );
}

export function AlertIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 4l9 16H3z" />
      <path d="M12 10v4M12 17h.01" />
    </Icon>
  );
}

/** Points down; turned over when its disclosure is open. The same in both directions. */
export function ChevronDownIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6 9l6 6 6-6" />
    </Icon>
  );
}

/** Found in full: a circle with a tick. */
export function CheckCircleIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12.5l2.5 2.5L16 9.5" />
    </Icon>
  );
}

/** Found in part: a circle, half filled. Mirrors with the page, which is fine for "half". */
export function HalfCircleIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" />
    </Icon>
  );
}

/** Not found: an empty, dashed circle. */
export function DashedCircleIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="9" strokeDasharray="3.5 3" />
    </Icon>
  );
}

/** Not suitable: a circle with a cross. */
export function CrossCircleIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M9 9l6 6M15 9l-6 6" />
    </Icon>
  );
}

/** Not in the answer key: a circle with a dash. */
export function MinusCircleIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12h8" />
    </Icon>
  );
}

export function DownloadIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 4v11M7 10l5 5 5-5M5 20h14" />
    </Icon>
  );
}

/** Came out in reaction to something the student did: an arrow turning back. */
export function ReplyIcon(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M9 14L4 9l5-5" />
      <path d="M4 9h10a6 6 0 0 1 6 6v5" />
    </Icon>
  );
}
