// @vitest-environment node
import openapiTS, { astToString, COMMENT_HEADER } from 'openapi-typescript';
import { describe, expect, it } from 'vitest';
import openapi from './openapi.json';
import committed from './schema.d.ts?raw';

describe('schema.d.ts', () => {
  it('is what `npm run gen:api` generates from the committed openapi.json', async () => {
    // The same steps as the openapi-typescript CLI, with its default options.
    const generated = COMMENT_HEADER + astToString(await openapiTS(JSON.stringify(openapi)));
    expect(committed, 'schema.d.ts is stale: run `make openapi` (or `npm run gen:api`)').toBe(
      generated,
    );
  });
});
