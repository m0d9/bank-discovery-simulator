/** Test-only data, typed from the API contract. Deliberately not the real content. */
import type {
  Bank,
  ClientCard,
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
