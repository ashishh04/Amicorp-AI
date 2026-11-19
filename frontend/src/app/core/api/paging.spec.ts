import { of } from 'rxjs';

import { fetchAll } from './paging';
import { Page } from './portal.models';

function pages(total: number, size: number) {
  const calls: (string | undefined)[] = [];
  const page = (cursor: string | undefined) => {
    calls.push(cursor);
    const start = Number(cursor ?? 0);
    const items = Array.from({ length: Math.min(size, total - start) }, (_, i) => start + i);
    const next = start + size < total ? String(start + size) : null;
    return of<Page<number>>({ items, nextCursor: next });
  };
  return { page, calls };
}

describe('fetchAll', () => {
  it('follows nextCursor to the last page', async () => {
    const { page, calls } = pages(250, 100);
    const result = await fetchAll(page);
    expect(result.items.length).toBe(250);
    expect(result.truncated).toBe(false);
    expect(calls).toEqual([undefined, '100', '200']);
  });

  it('stops at the cap and says the list was truncated', async () => {
    const { page } = pages(1200, 100);
    const result = await fetchAll(page, 500);
    expect(result.items.length).toBe(500);
    expect(result.truncated).toBe(true);
  });

  it('treats a missing nextCursor as the last page', async () => {
    const result = await fetchAll(() => of({ items: [1, 2, 3] }));
    expect(result).toEqual({ items: [1, 2, 3], truncated: false });
  });
});
