import { Observable, firstValueFrom } from 'rxjs';

import { Page } from './portal.models';

/**
 * Reads a cursor-paged list (limit + cursor → { items, nextCursor }) until the last page or
 * `max` items. `truncated` tells the page to ask the user to narrow the filters.
 */
export async function fetchAll<T>(
  page: (cursor: string | undefined) => Observable<Page<T>>,
  max = 500,
): Promise<{ items: T[]; truncated: boolean }> {
  const items: T[] = [];
  let cursor: string | undefined;
  do {
    const res = await firstValueFrom(page(cursor));
    items.push(...res.items);
    cursor = res.nextCursor ?? undefined;
  } while (cursor && items.length < max);
  return { items: items.slice(0, max), truncated: !!cursor || items.length > max };
}
