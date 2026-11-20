import { screen, waitFor, within } from '@testing-library/react';
import type { UserEvent } from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import openapi from '../api/openapi.json';
import { session, transcript } from '../test/fixtures';
import { renderApp } from '../test/render';
import { apiError, server } from '../test/server';
import { WRAP_UP_LIMITS } from './useWrapUp';

const SUMMARY = 'Late payments from big clients squeeze her cash flow every quarter.';

function interviewWithTurns() {
  server.use(
    http.get('/api/sessions/:sessionId', () =>
      HttpResponse.json(session({ turns: transcript(3) })),
    ),
  );
}

async function open() {
  interviewWithTurns();
  const view = await renderApp('/wrapup/s1');
  await screen.findByRole('checkbox', { name: /Test Murabaha/ });
  return view;
}

async function choose(user: UserEvent, product: string, reason?: string) {
  await user.click(screen.getByRole('checkbox', { name: new RegExp(product) }));
  if (reason !== undefined) {
    await user.type(screen.getByRole('textbox', { name: `Why this product? ${product}` }), reason);
  }
}

describe('WrapUpPage', () => {
  it('shows the instructions, the transcript for reference and the product checklist', async () => {
    await open();
    expect(
      screen.getByRole('heading', { level: 1, name: 'Wrap up your interview with Sara Test' }),
    ).toBeInTheDocument();
    const transcriptBox = screen.getByText('Interview transcript').closest('details');
    expect(transcriptBox).not.toHaveAttribute('open');
    expect(within(transcriptBox as HTMLElement).getByText('Question 3?')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: "Summarise the client's needs" })).toBeRequired();
    expect(screen.getAllByRole('checkbox')).toHaveLength(4);
    expect(screen.getByText('Chosen: 0 of 3')).toBeInTheDocument();
  });

  it('asks why for each chosen product, in a required field', async () => {
    const { user } = await open();
    expect(screen.queryByRole('textbox', { name: /Why this product/ })).toBeNull();
    await choose(user, 'Test Overdraft');
    expect(screen.getByRole('textbox', { name: 'Why this product? Test Overdraft' })).toBeRequired();
  });

  it('allows at most 3 products', async () => {
    const { user } = await open();
    await choose(user, 'Test Murabaha');
    await choose(user, 'Test Overdraft');
    await choose(user, 'Test Account');
    const fourth = screen.getByRole('checkbox', { name: /Test Deposit/ });
    expect(fourth).toBeDisabled();
    await user.click(fourth);
    expect(fourth).not.toBeChecked();
    expect(screen.getByText(/Chosen: 3 of 3/)).toHaveTextContent(
      "That's the maximum. To choose a different product, untick one first.",
    );

    await user.click(screen.getByRole('checkbox', { name: /Test Account/ }));
    expect(fourth).toBeEnabled();
  });

  it('announces the errors, moves focus to the summary, and links each error to its field', async () => {
    const { user } = await open();
    await user.type(screen.getByRole('textbox', { name: "Summarise the client's needs" }), 'Too short');
    await choose(user, 'Test Overdraft');
    await user.click(screen.getByRole('button', { name: 'Submit wrap-up' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('There is a problem');
    expect(alert).toHaveTextContent('Your summary is too short.');
    expect(alert).toHaveTextContent('Say why you recommend Test Overdraft.');
    expect(alert.parentElement).toHaveFocus();

    const summary = screen.getByRole('textbox', { name: "Summarise the client's needs" });
    expect(summary).toHaveAttribute('aria-invalid', 'true');
    expect(summary).toHaveAccessibleDescription(
      'Use between 30 and 2,000 characters. Your summary is too short.',
    );

    await user.click(within(alert).getByRole('link', { name: 'Say why you recommend Test Overdraft.' }));
    expect(screen.getByRole('textbox', { name: 'Why this product? Test Overdraft' })).toHaveFocus();
  });

  it('asks for at least one product', async () => {
    const { user } = await open();
    await user.type(screen.getByRole('textbox', { name: "Summarise the client's needs" }), SUMMARY);
    await user.click(screen.getByRole('button', { name: 'Submit wrap-up' }));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Choose at least one product.');
    await user.click(within(alert).getByRole('link', { name: 'Choose at least one product.' }));
    expect(screen.getByRole('checkbox', { name: /Test Murabaha/ })).toHaveFocus();
  });

  it('submits the trimmed summary and reasons, then opens the feedback page', async () => {
    let body: unknown;
    server.use(
      http.post('/api/sessions/:sessionId/wrapup', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(session({ status: 'wrapped_up' }));
      }),
    );
    const { router, user } = await open();
    await user.type(screen.getByRole('textbox', { name: "Summarise the client's needs" }), `  ${SUMMARY}  `);
    await choose(user, 'Test Murabaha', ' Fits her Sharia preference. ');
    await choose(user, 'Test Account', 'Collects card payments.');
    await user.click(screen.getByRole('button', { name: 'Submit wrap-up' }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/feedback/s1');
    });
    expect(body).toEqual({
      needs_summary: SUMMARY,
      recommendations: [
        { product_id: 'test-murabaha', reason: 'Fits her Sharia preference.' },
        { product_id: 'test-account', reason: 'Collects card payments.' },
      ],
    });
  });

  it('puts a failed submission in the focused summary', async () => {
    server.use(
      http.post('/api/sessions/:sessionId/wrapup', () => apiError('INVALID_STATE', 409)),
    );
    const { user } = await open();
    await user.type(screen.getByRole('textbox', { name: "Summarise the client's needs" }), SUMMARY);
    await choose(user, 'Test Murabaha', 'Fits her preference.');
    await user.click(screen.getByRole('button', { name: 'Submit wrap-up' }));

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent("This step isn't available at this point in the interview.");
    expect(alert.parentElement).toHaveFocus();
  });

  it.each(['wrapped_up', 'feedback_ready'] as const)(
    'sends a %s session to the feedback page',
    async (status) => {
      server.use(
        http.get('/api/sessions/:sessionId', () => HttpResponse.json(session({ status }))),
      );
      const { router } = await renderApp('/wrapup/s1');
      await waitFor(() => {
        expect(router.state.location.pathname).toBe('/feedback/s1');
      });
    },
  );

  it("uses the API contract's limits", () => {
    const { WrapUpDTO, RecommendationDTO } = openapi.components.schemas;
    expect(WRAP_UP_LIMITS).toEqual({
      summary: {
        min: WrapUpDTO.properties.needs_summary.minLength,
        max: WrapUpDTO.properties.needs_summary.maxLength,
      },
      reason: {
        min: RecommendationDTO.properties.reason.minLength,
        max: RecommendationDTO.properties.reason.maxLength,
      },
      products: {
        min: WrapUpDTO.properties.recommendations.minItems,
        max: WrapUpDTO.properties.recommendations.maxItems,
      },
    });
  });
});
