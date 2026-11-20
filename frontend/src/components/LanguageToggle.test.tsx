import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { detectLanguage } from '../i18n';
import { LanguageToggle } from './LanguageToggle';

describe('LanguageToggle', () => {
  it('switches the language, sets lang and dir on <html>, and saves the choice', async () => {
    const user = userEvent.setup();
    render(<LanguageToggle />);

    await user.click(screen.getByRole('button', { name: 'العربية' }));
    expect(document.documentElement).toHaveAttribute('lang', 'ar');
    expect(document.documentElement).toHaveAttribute('dir', 'rtl');
    expect(localStorage.getItem('lang')).toBe('ar');

    await user.click(screen.getByRole('button', { name: 'English' }));
    expect(document.documentElement).toHaveAttribute('lang', 'en');
    expect(document.documentElement).toHaveAttribute('dir', 'ltr');
    expect(localStorage.getItem('lang')).toBe('en');
  });

  it("marks the other language's name with its lang", () => {
    render(<LanguageToggle />);
    expect(screen.getByText('العربية')).toHaveAttribute('lang', 'ar');
  });
});

describe('detectLanguage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function browserLanguages(...tags: string[]) {
    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(tags);
  }

  it('prefers the saved choice', () => {
    localStorage.setItem('lang', 'ar');
    browserLanguages('en-US');
    expect(detectLanguage()).toBe('ar');
  });

  it("then takes the first of the browser's languages that the app supports", () => {
    browserLanguages('fr-FR', 'ar-QA', 'en');
    expect(detectLanguage()).toBe('ar');
  });

  it('ignores a saved value that is not a supported language', () => {
    localStorage.setItem('lang', 'de');
    browserLanguages('en-GB');
    expect(detectLanguage()).toBe('en');
  });

  it('falls back to English', () => {
    browserLanguages('fr-FR', 'de');
    expect(detectLanguage()).toBe('en');
  });
});
