import { computed, inject } from '@angular/core';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { fetchAll } from '../../core/api/paging';
import { PortalApi, toProblem } from '../../core/api/portal-api.service';
import { CardSummary, InboxView, Problem, Severity } from '../../core/api/portal.models';

export const INBOX_VIEWS: readonly InboxView[] = [
  'mine',
  'team',
  'due-soon',
  'overdue',
  'escalated',
  'closed',
];

/** What the URL says the inbox shows: ?view=&q=&uc=&severity=&type= */
export interface InboxQuery {
  view: InboxView;
  q: string;
  uc: string;
  severity: Severity | '';
  type: string;
}

export const EMPTY_QUERY: InboxQuery = { view: 'mine', q: '', uc: '', severity: '', type: '' };

interface InboxState {
  query: InboxQuery;
  items: CardSummary[];
  loading: boolean;
  problem: Problem | null;
  loadedAt: number | null;
  /** More cards match than the inbox reads (cursor paging); the page asks to narrow the filters. */
  truncated: boolean;
}

/** The inbox reads pages of 100 until this many cards; filters narrow anything larger. */
export const INBOX_MAX = 500;

/** Card queue for the inbox (LLD: InboxStore; GET /v1/cards, re-read on SSE events). */
export const InboxStore = signalStore(
  withState<InboxState>({
    query: EMPTY_QUERY,
    items: [],
    loading: false,
    problem: null,
    loadedAt: null,
    truncated: false,
  }),
  withComputed(({ query }) => ({
    filtered: computed(() => {
      const q = query();
      return !!(q.q || q.uc || q.severity || q.type);
    }),
  })),
  withMethods((store, api = inject(PortalApi)) => {
    let request = 0;

    const load = async (quiet = false): Promise<void> => {
      const id = ++request;
      const q = store.query();
      if (!quiet) patchState(store, { loading: true, problem: null });
      try {
        const { items, truncated } = await fetchAll(
          (cursor) =>
            api.listCards({
              view: q.view,
              q: q.q || undefined,
              useCase: q.uc || undefined,
              severity: q.severity || undefined,
              type: q.type || undefined,
              limit: 100,
              cursor,
            }),
          INBOX_MAX,
        );
        // A slower, older response must not overwrite a newer one.
        if (id === request) {
          patchState(store, {
            items,
            truncated,
            loading: false,
            problem: null,
            loadedAt: Date.now(),
          });
        }
      } catch (e) {
        if (id === request) patchState(store, { loading: false, problem: toProblem(e) });
      }
    };

    return {
      load,
      /** Applies the query from the URL and loads it. */
      apply(query: InboxQuery): Promise<void> {
        // The previous rows stay under the loading overlay until the new ones arrive.
        patchState(store, { query });
        return load();
      },
    };
  }),
);
