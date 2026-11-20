import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { Feedback } from '../../api/types';
import i18n from '../../i18n';
import { feedback, products } from '../../test/fixtures';
import { Recommendations } from './Recommendations';

const sameReasonTwice: Feedback = feedback({
  analysis: {
    ...feedback().analysis,
    products: [
      {
        product_id: 'test-overdraft',
        verdict: 'unsuitable',
        reasons: [
          { need_id: 'cash-gap', reason: { en: 'Interest-based.', ar: 'قائم على الفائدة.' } },
          { need_id: 'stock', reason: { en: 'Interest-based.', ar: 'قائم على الفائدة.' } },
          { need_id: 'pay-staff', reason: { en: 'Too new to qualify.', ar: 'حديث العهد.' } },
        ],
        needs: [],
        ruled_out_at: null,
        pitched_at: null,
      },
    ],
  },
});

const alreadyRuledOut: Feedback = feedback({
  analysis: {
    ...feedback().analysis,
    products: [
      {
        product_id: 'test-overdraft',
        verdict: 'unsuitable',
        reasons: [
          { need_id: 'cash-gap', reason: { en: 'Interest-based.', ar: 'قائم على الفائدة.' } },
        ],
        needs: [],
        ruled_out_at: 4,
        pitched_at: 5,
      },
    ],
  },
});

function show(data: Feedback = sameReasonTwice, onShowTurn: (n: number) => void = () => {}) {
  render(
    <Recommendations
      feedback={data}
      product={(id) => products.find((item) => item.id === id)}
      describeNeed={(id) => ({ en: id, ar: null })}
      onShowTurn={onShowTurn}
    />,
  );
  return screen.getByText(/Test Overdraft|سحب على المكشوف تجريبي/).closest('li') as HTMLElement;
}

describe('Recommendations', () => {
  it('shows each distinct reason once', () => {
    const card = show();

    expect(within(card).getAllByText('Interest-based.')).toHaveLength(1);
    expect(within(card).getByText('Too new to qualify.')).toBeInTheDocument();
  });

  it('shows each distinct reason once in Arabic too', async () => {
    await i18n.changeLanguage('ar');
    const card = show();

    expect(within(card).getAllByText('قائم على الفائدة.')).toHaveLength(1);
    expect(within(card).getByText('حديث العهد.')).toBeInTheDocument();
  });

  it('says when the client had already ruled the product out, and links that turn', async () => {
    const shown: number[] = [];
    const card = show(alreadyRuledOut, (n) => shown.push(n));

    expect(card).toHaveTextContent(
      'The client had already said something that rules this out (Turn 4).',
    );
    await userEvent.setup().click(within(card).getByRole('link', { name: 'Turn 4' }));
    expect(shown).toEqual([4]);
  });

  it('says it in Arabic too', async () => {
    await i18n.changeLanguage('ar');
    const card = show(alreadyRuledOut);

    expect(card).toHaveTextContent('كانت المقابلة قد كشفت ما يستبعد هذا المنتج (الرسالة 4).');
  });

  it('says nothing when the product was not ruled out beforehand', () => {
    const card = show();

    expect(card).not.toHaveTextContent('already said');
  });
});
