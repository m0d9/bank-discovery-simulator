import { render, screen, within } from '@testing-library/react';
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
      },
    ],
  },
});

function show() {
  render(
    <Recommendations
      feedback={sameReasonTwice}
      product={(id) => products.find((item) => item.id === id)}
      describeNeed={(id) => ({ en: id, ar: null })}
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
});
