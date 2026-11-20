import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderApp } from '../test/render';

describe('AppShell', () => {
  it('shows the bank name in the header and its disclaimer in the footer', async () => {
    await renderApp('/nowhere');
    expect(await screen.findByRole('link', { name: 'Test Bank' })).toBeInTheDocument();
    expect(screen.getByRole('contentinfo')).toHaveTextContent('A fictional bank for tests.');
  });

  it('shows the bank in Arabic when the UI is in Arabic', async () => {
    await renderApp('/nowhere', { language: 'ar' });
    expect(await screen.findByRole('link', { name: 'بنك الاختبار' })).toBeInTheDocument();
    expect(screen.getByRole('contentinfo')).toHaveTextContent('بنك افتراضي للاختبارات.');
  });

  it('starts with a skip link that moves focus to <main>', async () => {
    const { user } = await renderApp('/nowhere');
    await user.tab();
    const skip = screen.getByRole('link', { name: 'Skip to main content' });
    expect(skip).toHaveFocus();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('main')).toHaveFocus();
  });

  it('shows a localized not-found page with its document title', async () => {
    await renderApp('/nowhere', { language: 'ar' });
    expect(screen.getByRole('heading', { level: 1, name: 'الصفحة غير موجودة' })).toBeInTheDocument();
    expect(document.title).toBe('الصفحة غير موجودة – محاكي اكتشاف احتياجات عملاء البنك');
  });
});
