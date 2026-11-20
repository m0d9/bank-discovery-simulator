/** Class lists shared by several components, so buttons and links look the same everywhere.
 * Targets are at least 44 px high. A disabled control is dimmed and also says so in words or
 * through `aria-disabled`, never by colour alone. */

const button =
  'inline-flex min-h-11 items-center justify-center gap-2 rounded-md px-5 text-base font-semibold disabled:cursor-not-allowed disabled:opacity-60 aria-disabled:cursor-not-allowed aria-disabled:opacity-60';

export const primaryButton = `${button} bg-brand text-on-brand hover:bg-brand-strong`;

export const secondaryButton = `${button} border border-line-strong bg-surface text-ink hover:bg-surface-sunken`;

export const textLink = 'font-medium text-brand underline underline-offset-4 hover:text-brand-strong';

export const card = 'rounded-lg border border-line bg-surface shadow-sm';
