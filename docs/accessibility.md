# Accessibility

This page says what is checked automatically, what was checked by hand, and what hasn't been checked.

## Target

[WCAG 2.1](https://www.w3.org/TR/WCAG21/) level **AA**, in English (LTR) and Arabic (RTL).

**A full screen-reader audit was not done.** The automated checks below can't replace one. The *Manual check* section records one pass with the keyboard and Narrator, in English.

## What is automated

Every check below runs in CI on each pull request (`npm run lint` and `npm test` in the frontend job).

### jest-axe: every page and key state, in both languages

`frontend/src/a11y.test.tsx` renders the whole app with the API mocked and runs axe on the document. It does this for each state below, in `en` and in `ar`, and checks that `<html lang>` follows the language. That's 15 states × 2 languages.

| Page | States |
|---|---|
| Client list | ready; loading; failed to load; the model health banner (Ollama unreachable), with its details open |
| Interview | ready; the wide two-column layout; the "End interview" dialog open; a lost session |
| Wrap-up | ready; submitted empty, with the error summary shown |
| Feedback | ready; the transcript and the client's profile open; the coach writing (loading); the coach unavailable (degraded) |
| Not found | ready |

jest-axe runs axe-core 4.12.1 in jsdom, and jsdom has no layout. So jest-axe **switches off the colour-contrast rules**, and it can't judge focus visibility, reflow, zoom or target size. Those are covered by the checks below, or not covered at all (see *Known gaps*).

### Other automated checks

- **Contrast:** `src/styles/tokens.test.ts` recomputes every ratio in the table below from the colour values in `tokens.css`. It fails if a stated ratio is wrong or below its minimum. Tailwind's default palette is switched off, so no other colour can be used.
- **Lint:**
  - `eslint-plugin-jsx-a11y` (recommended rules), for things like labels, alt text, roles and interactive elements;
  - `eslint-plugin-i18next` (`no-literal-string`, JSX text, an error), so no UI text bypasses translation.
- **Source conventions:** `src/conventions.test.ts` allows only logical Tailwind utilities (`ms-`, `pe-`, `start-`…), never left/right ones, and no inline styles, so the layout mirrors correctly in Arabic.
- **Locales:** `src/locales/locales.test.ts` checks four things:
  - both languages have the same keys;
  - Arabic has the plural forms it needs;
  - no value is empty;
  - every API error code and health hint code has a message.
- **Behaviour, in component tests:**
  - the skip link moves focus to `<main>`;
  - errors are announced (`role="alert"`) and the error summary links each error to its field (`aria-invalid`, `aria-describedby`);
  - evidence links move focus to the transcript turn;
  - the health banner's Retry keeps focus while it checks.

### One-off checks in Chrome (not repeated after PR #6)

- **[PR #5](https://github.com/m0d9/bank-discovery-simulator/pull/5):** axe-core 4.14.1 in Chrome against `make dev`, scripted, in both languages. No violations in 18 states.
- **[PR #6](https://github.com/m0d9/bank-discovery-simulator/pull/6):** the same over the Chrome DevTools Protocol. Clean on 8 feedback states in both languages, evidence links focus the turn, and there's no horizontal scroll at 375 px.

These ran in a real browser, so they included the colour-contrast rules.

## How the UI is built for it

- **Native elements first:**
  - the "End interview" confirmation is a modal `<dialog>`, which traps focus; Escape cancels, and focus returns to the button that opened it;
  - the transcript, the client's profile and the health details are `<details>`;
  - every control is a `<button>`, a link, or a labelled form field.
- **Structure:**
  - a skip link;
  - `header`, `main` and `footer` landmarks;
  - one `<h1>` per page, which takes focus after in-app navigation so screen readers start at the new page;
  - section headings in order (axe's `heading-order` rule passes in every state).
- **Focus:** one visible style for everything, a 3 px outline in the `focus` token (at least 8.9:1 on every background it sits on).
- **Targets:** buttons and standalone links are at least 44 px high (`min-h-11`). Links inside a sentence are exempt.
- **Live regions:**
  - the conversation is a `role="log"`;
  - loading, typing and the health banner are `role="status"` (polite);
  - errors are `role="alert"`.
  - The health banner's region is always present, so its message is announced once when it appears.
- **Meaning never by colour alone:** verdicts, statuses, errors and notices all have an icon and words, and colour only adds to them.
- **Motion:** animations run only under `motion-safe`, and `prefers-reduced-motion: reduce` stops all animation and transitions.
- **Language and direction:**
  - `<html lang dir>` follows the UI language;
  - text written by the student or a model has `dir="auto"`;
  - host and model names are isolated with `<bdi>`;
  - the health hint from the server (English only) is marked `lang="en"`.

## Contrast table (from `tokens.css`)

Text needs at least 4.5:1. Large text, icons, focus rings and the borders of controls ("ui") need at least 3:1. `tokens.test.ts` keeps this table in step with the colours.

| Foreground | Background | Ratio | Use |
|---|---|---|---|
| ink | canvas | 14.33:1 | text |
| ink | surface | 15.75:1 | text |
| ink | surface-sunken | 13.74:1 | text |
| ink | brand-tint | 13.29:1 | text |
| ink | danger-tint | 13.93:1 | text |
| ink-muted | canvas | 6.53:1 | text |
| ink-muted | surface | 7.18:1 | text |
| ink-muted | surface-sunken | 6.26:1 | text |
| ink-muted | brand-tint | 6.06:1 | text |
| on-brand | brand | 7.83:1 | text |
| on-brand | brand-strong | 10.59:1 | text |
| brand | surface | 7.83:1 | text |
| brand | canvas | 7.13:1 | text |
| brand-strong | surface | 10.59:1 | text |
| danger | surface | 7.28:1 | text |
| danger | danger-tint | 6.44:1 | text |
| sharia-ink | sharia-tint | 6.93:1 | text |
| interest-ink | interest-tint | 6.98:1 | text |
| brand-strong | brand-tint | 8.94:1 | text |
| attention | attention-tint | 7.69:1 | text |
| attention | surface | 9.12:1 | text |
| ink | attention-tint | 13.27:1 | text |
| line-strong | surface | 4.39:1 | ui |
| line-strong | canvas | 4.00:1 | ui |
| focus | canvas | 9.63:1 | ui |
| focus | surface | 10.59:1 | ui |
| focus | brand-tint | 8.94:1 | ui |
| danger | canvas | 6.62:1 | ui |

## Known gaps

- **Not checked by hand:** Narrator with the Arabic UI, NVDA, the 320 px width, and the reduced-motion setting.
- **No full screen-reader audit.**
  - The one manual pass used Narrator, in English. JAWS, VoiceOver and TalkBack haven't been tried.
  - Of the live regions, the pass checked only the conversation's. It didn't include the loading and error announcements or the health banner.
- **Zoom and reflow aren't tested automatically.** 200% zoom was checked by hand once (see *Manual check*), and 375 px once, in [PR #6](https://github.com/m0d9/bank-discovery-simulator/pull/6).
- **No browser-based axe run in CI.** jsdom can't check contrast, visible focus or layout. The Chrome runs in [PR #5](https://github.com/m0d9/bank-discovery-simulator/pull/5) and [PR #6](https://github.com/m0d9/bank-discovery-simulator/pull/6) were one-off, and the states that [PR #9](https://github.com/m0d9/bank-discovery-simulator/pull/9) added to jest-axe weren't run in Chrome.
- **Mixed-language reading is unverified:** how screen readers pronounce English model and product names inside Arabic text, and Arabic inside English.
- **Windows high contrast (forced colours) is untested.**
- **The models' text can't be guaranteed.** The AI client's and the coach's replies are free text. Their clarity, length and Arabic quality aren't accessibility-checked (see `docs/evaluation.md` for their quality).

## Manual check

One pass through the whole flow, with the keyboard and Narrator.

- **Tester:** Mahmoud Abdelaziz
- **Date:** 2026-11-21
- **Setup:** Edge on Windows 11, with Narrator, and the UI in English

| Check | Result |
|---|---|
| The skip link is the first Tab stop and moves focus to the main content | Pass |
| The language switch works by keyboard, and the page flips to RTL and back | Pass |
| Every client card is reachable, and the focus is always visible | Pass |
| Enter on a card opens the interview | Pass (see the observation below) |
| Enter sends the message, and focus stays in the message box after the reply | Pass |
| Narrator reads the client's reply once | Pass |
| The "End interview" dialog opens with focus inside it. Esc closes it and returns focus to the button, and confirming goes to the wrap-up | Pass |
| Submitting an empty wrap-up shows the error, and the field can be reached | Pass |
| The whole wrap-up works by keyboard, with products ticked using Space | Pass |
| A "Turn" link opens the transcript, with that message focused and the focus ring visible | Pass |
| "Behind the scenes" (the client's full profile) opens and closes with Enter | Pass |
| At 200% zoom there's no horizontal scrolling, and nothing is cut off | Pass |

**An observation, not a failure:** opening the interview doesn't move focus to the message box, so it's reached with Tab. This is by design: after a navigation inside the app, focus goes to the new page's heading, so that screen readers start at the new page.

**Not checked by hand:** Narrator with the Arabic UI, NVDA, the 320 px width, and reduced motion (see *Known gaps*).
