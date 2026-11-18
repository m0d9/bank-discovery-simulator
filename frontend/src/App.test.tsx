import { render, screen } from '@testing-library/react';
import { axe } from 'jest-axe';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from './App.tsx';

describe('App placeholder', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders a heading, shows the health status and has no axe violations', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response(JSON.stringify({ status: 'ok', version: '0.1.0' })))),
    );
    const { container } = render(<App />);

    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument();
    expect(await screen.findByText('ok')).toBeInTheDocument();
    const results = await axe(container);
    expect(results.violations).toHaveLength(0);
  });
});
