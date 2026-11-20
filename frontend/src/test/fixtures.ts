/** Test-only data, typed from the API contract. Deliberately not the real content. */
import type {
  Bank,
  ClientCard,
  Feedback,
  Product,
  SessionCreated,
  SessionModels,
  SessionPublic,
  Turn,
} from '../api/types';

export const bank: Bank = {
  name: { en: 'Test Bank', ar: 'بنك الاختبار' },
  tagline: { en: 'Testing first', ar: 'الاختبار أولًا' },
  disclaimer: { en: 'A fictional bank for tests.', ar: 'بنك افتراضي للاختبارات.' },
  currency: 'QAR',
};

export const sara: ClientCard = {
  id: 'sara-test',
  segment: 'sme',
  difficulty: 'medium',
  name: { en: 'Sara Test', ar: 'سارة التجريبية' },
  headline: { en: 'Runs a test bakery', ar: 'صاحبة مخبز تجريبي' },
};

export const omar: ClientCard = {
  id: 'omar-test',
  segment: 'retail',
  difficulty: 'easy',
  name: { en: 'Omar Test', ar: 'عمر التجريبي' },
  headline: { en: 'A test engineer', ar: 'مهندس اختبارات' },
};

export const clients: ClientCard[] = [sara, omar];

function product(
  id: string,
  en: string,
  ar: string,
  flags: Pick<Product, 'sharia_compliant' | 'interest_based'>,
): Product {
  return {
    id,
    name: { en, ar },
    summary: { en: `${en} summary`, ar: `ملخص ${ar}` },
    segments: ['sme'],
    category: 'financing',
    ...flags,
    features: [{ en: `${en} feature`, ar: `ميزة ${ar}` }],
    limitations: [{ en: `${en} limitation`, ar: `قيد ${ar}` }],
    eligibility: [{ en: `${en} eligibility`, ar: `أهلية ${ar}` }],
    pricing: { en: `${en} pricing (fictional)`, ar: `تسعير ${ar} (أرقام افتراضية)` },
  };
}

export const products: Product[] = [
  product('test-murabaha', 'Test Murabaha', 'مرابحة تجريبية', {
    sharia_compliant: true,
    interest_based: false,
  }),
  product('test-overdraft', 'Test Overdraft', 'سحب على المكشوف تجريبي', {
    sharia_compliant: false,
    interest_based: true,
  }),
  product('test-account', 'Test Account', 'حساب تجريبي', {
    sharia_compliant: false,
    interest_based: false,
  }),
  product('test-deposit', 'Test Deposit', 'وديعة تجريبية', {
    sharia_compliant: true,
    interest_based: false,
  }),
];

export const models: SessionModels = { gate: 'gate-model', client: 'client-model', coach: 'coach-model' };

export const OPENING = 'Hello. I have a few minutes.';

/** The opening line, then `studentTurns` question-and-answer pairs. */
export function transcript(studentTurns: number): Turn[] {
  const turns: Turn[] = [{ n: 0, role: 'client', text: OPENING }];
  for (let i = 1; i <= studentTurns; i++) {
    turns.push({ n: turns.length, role: 'student', text: `Question ${String(i)}?` });
    turns.push({ n: turns.length, role: 'client', text: `Answer ${String(i)}.` });
  }
  return turns;
}

export function session(overrides: Partial<SessionPublic> = {}): SessionPublic {
  const turns = overrides.turns ?? transcript(0);
  return {
    session_id: 's1',
    client: sara,
    status: 'interviewing',
    language: 'en',
    turns,
    student_turns_used: turns.filter((turn) => turn.role === 'student').length,
    max_student_turns: 30,
    max_message_chars: 1000,
    models,
    ...overrides,
  };
}

export function created(client: ClientCard = sara, sessionId = 's1'): SessionCreated {
  return {
    session_id: sessionId,
    client,
    opening_line: { en: OPENING, ar: 'مرحبًا. لدي بضع دقائق.' },
    max_student_turns: 30,
    max_message_chars: 1000,
    models,
  };
}

const english = (en: string) => ({ en, ar: null });
const interestBased = { en: 'Interest-based.', ar: 'قائم على الفائدة.' };

/** Feedback on `transcript(3)`: one need found in full only after the pitch at turn 3, one
 * uncovered by the question at turn 1, one missed; an unsuitable and a not-in-key
 * recommendation; one missed opportunity; and the coach's report. */
export function feedback(overrides: Partial<Feedback> = {}): Feedback {
  return {
    session_id: 's1',
    language: 'en',
    analysis: {
      needs: [
        {
          need_id: 'cash-gap',
          status: 'revealed_by_pitch',
          facts: [
            { fact_id: 'late-payments', unlocked_at_turn: 1 },
            { fact_id: 'sharia', unlocked_at_turn: 3 },
          ],
          via: { turn: 3, question: 'Question 2?' },
        },
        {
          need_id: 'pay-staff',
          status: 'uncovered',
          facts: [{ fact_id: 'late-payments', unlocked_at_turn: 1 }],
          via: { turn: 1, question: 'Question 1?' },
        },
        {
          need_id: 'stock',
          status: 'missed',
          facts: [{ fact_id: 'big-order', unlocked_at_turn: null }],
          via: null,
        },
      ],
      facts: [
        {
          fact_id: 'late-payments',
          importance: 'critical',
          unlocked_at_turn: 1,
          discovered_by: 'question',
        },
        {
          fact_id: 'sharia',
          importance: 'critical',
          unlocked_at_turn: 3,
          discovered_by: 'product_pitch',
        },
        {
          fact_id: 'big-order',
          importance: 'important',
          unlocked_at_turn: null,
          discovered_by: null,
        },
      ],
      products: [
        {
          product_id: 'test-overdraft',
          verdict: 'unsuitable',
          reasons: [
            { need_id: 'cash-gap', reason: interestBased },
            { need_id: 'stock', reason: interestBased },
          ],
          needs: [],
          // The overdraft's own pitch brought out the preference, so nothing was said before.
          ruled_out_at: null,
          pitched_at: null,
        },
        {
          product_id: 'test-account',
          verdict: 'not_in_key',
          reasons: [],
          needs: [],
          ruled_out_at: null,
          pitched_at: null,
        },
      ],
      missed_opportunities: [{ product_id: 'test-murabaha', needs: ['cash-gap'] }],
      stats: {
        student_turns: 3,
        needs_uncovered: 1,
        needs_after_pitch: 1,
        needs_total: 3,
        critical_found: 2,
        critical_total: 2,
        first_unlock_turn: 1,
      },
    },
    report: {
      went_well: [{ point: 'You asked how her customers pay.', evidence_turns: [1, 3] }],
      missed: [
        {
          point: 'You pitched an overdraft before asking about her values.',
          need_id: 'cash-gap',
          product_id: 'test-overdraft',
          evidence_turns: [5],
          better_question: 'Is Islamic banking important to you?',
        },
      ],
      how_to_improve: [
        { tip: 'Ask about values before you pitch.', example: 'What matters to you in a bank?' },
      ],
      summary_feedback: 'Your summary names the cash gap but not the big order.',
    },
    degraded: false,
    models,
    generated_at: '2026-11-20T09:00:00Z',
    wrapup: {
      needs_summary: 'She is paid late and needs Islamic finance.',
      recommendations: [
        { product_id: 'test-overdraft', reason: 'Flexible cash.' },
        { product_id: 'test-account', reason: 'Collects payments.' },
      ],
    },
    revealed: {
      persona: {
        age: 38,
        occupation: english('Owner of a test bakery'),
        nationality: english('Qatari'),
        family: null,
        background: english('Started baking in 2019.'),
        personality: english('Warm and busy.'),
        speaking_style: english('Short sentences.'),
        financial_knowledge: 'low',
      },
      open_facts: [english('Runs a bakery in Doha.')],
      hidden_facts: [
        {
          id: 'late-payments',
          content: english('Customers pay 90 days late.'),
          importance: 'critical',
          unlocked_at_turn: 1,
        },
        {
          id: 'sharia',
          content: english('Uses only Sharia-compliant products.'),
          importance: 'critical',
          unlocked_at_turn: 3,
        },
        {
          id: 'big-order',
          content: english('A big order is coming.'),
          importance: 'important',
          unlocked_at_turn: null,
        },
      ],
      needs: [
        {
          id: 'cash-gap',
          description: { en: 'Bridge the cash gap.', ar: 'سدّ الفجوة النقدية.' },
          status: 'revealed_by_pitch',
          suitable_products: ['test-murabaha'],
          unsuitable_products: [{ id: 'test-overdraft', reason: interestBased }],
        },
        {
          id: 'pay-staff',
          description: { en: 'Pay staff on time.', ar: 'دفع رواتب الموظفين في موعدها.' },
          status: 'uncovered',
          suitable_products: ['test-account'],
          unsuitable_products: [],
        },
        {
          id: 'stock',
          description: english('Finance the stock.'),
          status: 'missed',
          suitable_products: ['test-murabaha'],
          unsuitable_products: [],
        },
      ],
      no_catalogue_fit: false,
      referral_note: null,
    },
    ...overrides,
  };
}
