import { describe, expect, it } from 'vitest';
import tokens from './tokens.css?raw';

const MINIMUM = { text: 4.5, ui: 3 } as const;
const VALUE = /--color-([\w-]+):\s*(#[0-9a-f]{6})\b/gi;
const PAIR = /^\s*\*\s+([\w-]+) on ([\w-]+): ([\d.]+):1 \((text|ui)\)$/gm;

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16) / 255);
  const [r = 0, g = 0, b = 0] = channels.map((c) =>
    c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** The WCAG 2.1 contrast ratio of two colours. */
function contrast(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return ((light ?? 0) + 0.05) / ((dark ?? 0) + 0.05);
}

const colours = new Map([...tokens.matchAll(VALUE)].map(([, name = '', hex = '']) => [name, hex]));
const pairs = [...tokens.matchAll(PAIR)].map(([, fg = '', bg = '', stated = '', kind = '']) => ({
  fg,
  bg,
  stated: Number(stated),
  kind: kind as keyof typeof MINIMUM,
}));

describe('tokens.css contrast table', () => {
  it('documents the pairs', () => {
    expect(pairs.length).toBeGreaterThanOrEqual(20);
  });

  it.each(pairs)('$fg on $bg is $stated:1, as stated, and enough for $kind', (pair) => {
    const fg = colours.get(pair.fg);
    const bg = colours.get(pair.bg);
    expect(fg, `--color-${pair.fg} is not defined`).toBeDefined();
    expect(bg, `--color-${pair.bg} is not defined`).toBeDefined();
    const ratio = contrast(fg ?? '', bg ?? '');
    expect(ratio.toFixed(2)).toBe(pair.stated.toFixed(2));
    expect(ratio).toBeGreaterThanOrEqual(MINIMUM[pair.kind]);
  });
});
