import type { ReactNode } from 'react';

const TONES = {
  neutral: 'bg-surface-sunken text-ink',
  sharia: 'bg-sharia-tint text-sharia-ink',
  interest: 'bg-interest-tint text-interest-ink',
  found: 'bg-brand-tint text-brand-strong',
  attention: 'bg-attention-tint text-attention',
} as const;

export type BadgeTone = keyof typeof TONES;

interface BadgeProps {
  tone?: BadgeTone;
  /** A decorative icon; the text always carries the meaning. */
  icon?: ReactNode;
  /** Keep the words on one line, for short labels in narrow table columns. */
  nowrap?: boolean;
  children: ReactNode;
}

export function Badge({ tone = 'neutral', icon, nowrap = false, children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-sm font-medium ${TONES[tone]}${nowrap ? ' whitespace-nowrap' : ''}`}
    >
      {icon}
      {children}
    </span>
  );
}
