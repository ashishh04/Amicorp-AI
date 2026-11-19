import { computed, inject } from '@angular/core';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { fetchAll } from '../../core/api/paging';
import { PortalApi, toProblem } from '../../core/api/portal-api.service';
import { AuditEvent, Problem } from '../../core/api/portal.models';

export type AuditRange = '24h' | '7d' | '30d' | 'all';

export const AUDIT_RANGES: { value: AuditRange; label: string; hours: number | null }[] = [
  { value: '24h', label: 'Last 24 hours', hours: 24 },
  { value: '7d', label: 'Last 7 days', hours: 7 * 24 },
  { value: '30d', label: 'Last 30 days', hours: 30 * 24 },
  { value: 'all', label: 'All time', hours: null },
];

export const AUDIT_ENTITIES = [
  { value: 'card', label: 'Cards' },
  { value: 'statement', label: 'Statements' },
  { value: 'ruleset', label: 'Rulesets' },
  { value: 'transaction', label: 'Transactions' },
  { value: 'scan', label: 'Scans' },
];

const DEFAULT_RANGE: AuditRange = '7d';

/** The page reads pages of 200 until this many events; filters narrow anything larger. */
export const AUDIT_MAX = 1000;

interface AuditState {
  q: string;
  entity: string;
  actor: string;
  range: AuditRange;
  items: AuditEvent[];
  loading: boolean;
  loaded: boolean;
  problem: Problem | null;
  /** More events match than the page reads; the page asks to narrow the filters. */
  truncated: boolean;
}

type AuditFilters = Pick<AuditState, 'q' | 'entity' | 'actor' | 'range'>;

/** Audit trail search (GET /v1/audit/events); the API limits the MLRO to the AML events. */
export const AuditStore = signalStore(
  withState<AuditState>({
    q: '',
    entity: '',
    actor: '',
    range: DEFAULT_RANGE,
    items: [],
    loading: false,
    loaded: false,
    problem: null,
    truncated: false,
  }),
  withComputed(({ q, entity, actor, range }) => ({
    filtered: computed(() => !!(q() || entity() || actor()) || range() !== DEFAULT_RANGE),
  })),
  withMethods((store, api = inject(PortalApi)) => {
    let latest = 0;
    const load = async (): Promise<void> => {
      const request = ++latest;
      const hours = AUDIT_RANGES.find((r) => r.value === store.range())?.hours ?? null;
      patchState(store, { loading: true, problem: null });
      try {
        const { items, truncated } = await fetchAll(
          (cursor) =>
            api.listAudit({
              q: store.q() || undefined,
              entity: store.entity() || undefined,
              actor: store.actor() || undefined,
              since: hours ? new Date(Date.now() - hours * 3_600_000).toISOString() : undefined,
              limit: 200,
              cursor,
            }),
          AUDIT_MAX,
        );
        if (request === latest) {
          patchState(store, { items, truncated, loading: false, loaded: true });
        }
      } catch (e) {
        if (request === latest) {
          patchState(store, { items: [], loading: false, loaded: true, problem: toProblem(e) });
        }
      }
    };
    return {
      load,
      setFilter(change: Partial<AuditFilters>): Promise<void> {
        patchState(store, change);
        return load();
      },
      clear(): Promise<void> {
        patchState(store, { q: '', entity: '', actor: '', range: DEFAULT_RANGE });
        return load();
      },
    };
  }),
);
