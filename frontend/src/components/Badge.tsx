import type { ReactNode } from 'react';

const TONES = {
  neutral: 'bg-surface-sunken text-ink',
  sharia: 'bg-sharia-tint text-sharia-ink',
  interest: 'bg-interest-tint text-interest-ink',
} as const;

interface BadgeProps {
  tone?: keyof typeof TONES;
  /** A decorative icon; the text always carries the meaning. */
  icon?: ReactNode;
  children: ReactNode;
}

export function Badge({ tone = 'neutral', icon, children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-sm font-medium ${TONES[tone]}`}
    >
      {icon}
      {children}
    </span>
  );
}
