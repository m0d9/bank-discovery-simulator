import { describe, expect, it } from 'vitest';

// The app's source as text: components, pages and styles (not tests or generated files).
const sources = import.meta.glob<string>(
  ['/src/**/*.{ts,tsx,css}', '!/src/**/*.test.{ts,tsx}', '!/src/test/**', '!/src/api/schema.d.ts'],
  { query: '?raw', import: 'default', eager: true },
);

/** Tailwind utilities tied to left or right, after any variants (`hover:`, `lg:`…). */
const PHYSICAL_UTILITY =
  /^-?(?:m[lr]|p[lr]|scroll-[mp][lr]|left|right|inset-[lr]|border-[lr]|rounded-[lr]|rounded-[tb][lr]|(?:text|float|clear)-(?:left|right))(?:-|$)/;
const PHYSICAL_CSS = /\b(?:margin|padding|border)-(?:left|right)\b|\b(?:left|right)\s*:|:\s*(?:left|right)\b/;
const STRING_LITERAL = /(['"`])((?:\\.|(?!\1)[^\\])*)\1/g;

/** The code without comments, whose apostrophes ("won't") would pair up as quotes. */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1');
}

function physicalUtilities(source: string): string[] {
  const found: string[] = [];
  for (const [, , text = ''] of withoutComments(source).matchAll(STRING_LITERAL)) {
    for (const token of text.split(/\s+/)) {
      const utility = token.split(':').pop() ?? '';
      if (PHYSICAL_UTILITY.test(utility.replace(/^!/, ''))) found.push(token);
    }
  }
  return found;
}

describe('source conventions', () => {
  it('finds the source files', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(20);
  });

  it.each(Object.entries(sources).filter(([path]) => /\.tsx?$/.test(path)))(
    '%s uses logical utilities only (start/end, never left/right)',
    (_path, source) => {
      expect(physicalUtilities(source)).toEqual([]);
    },
  );

  it.each(Object.entries(sources).filter(([path]) => path.endsWith('.tsx')))(
    '%s has no inline styles',
    (_path, source) => {
      expect(source).not.toMatch(/\bstyle=\{/);
    },
  );

  it.each(Object.entries(sources).filter(([path]) => path.endsWith('.css')))(
    '%s has no left/right properties',
    (_path, source) => {
      expect(source, 'the style sheet was read as empty text').not.toBe('');
      const withoutComments = source.replace(/\/\*[\s\S]*?\*\//g, '');
      expect(withoutComments).not.toMatch(PHYSICAL_CSS);
    },
  );

  it('catches what it should', () => {
    expect(physicalUtilities(`className="pl-4 hover:mr-2 text-right"`)).toEqual([
      'pl-4',
      'hover:mr-2',
      'text-right',
    ]);
    expect(physicalUtilities(`className="ps-4 border-line rounded-lg prose -me-1 start-0"`)).toEqual(
      [],
    );
    // An apostrophe in a comment doesn't hide what follows.
    expect(physicalUtilities(`// won't send\nconst a = 'ml-2';`)).toEqual(['ml-2']);
  });
});
