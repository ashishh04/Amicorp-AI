import { inject } from '@angular/core';
import { patchState, signalStore, withMethods, withState } from '@ngrx/signals';
import { firstValueFrom } from 'rxjs';

import { PortalApi, toProblem } from '../../core/api/portal-api.service';
import { KpiSummary, Problem } from '../../core/api/portal.models';

/** Ranges the KPI endpoint serves (GET /v1/kpis/summary?days=). */
export const RANGES = [7, 14, 30, 90] as const;
export const DEFAULT_RANGE = 14;

interface KpisState {
  days: number;
  kpis: KpiSummary | null;
  loading: boolean;
  problem: Problem | null;
  /** When the figures on screen were read (ISO). */
  loadedAt: string | null;
}

/** Operational KPIs for one time range; a refetch keeps the previous figures on screen. */
export const KpisStore = signalStore(
  withState<KpisState>({
    days: DEFAULT_RANGE,
    kpis: null,
    loading: false,
    problem: null,
    loadedAt: null,
  }),
  withMethods((store, api = inject(PortalApi)) => {
    let latest = 0;
    return {
      async load(days: number): Promise<void> {
        const request = ++latest;
        patchState(store, { days, loading: true, problem: null });
        try {
          const kpis = await firstValueFrom(api.kpis(days));
          if (request === latest) {
            patchState(store, { kpis, loading: false, loadedAt: new Date().toISOString() });
          }
        } catch (e) {
          if (request === latest) patchState(store, { loading: false, problem: toProblem(e) });
        }
      },
    };
  }),
);
