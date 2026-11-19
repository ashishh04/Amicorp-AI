import { inject } from '@angular/core';
import { patchState, signalStore, withMethods, withState } from '@ngrx/signals';
import { firstValueFrom } from 'rxjs';

import { PortalApi, toProblem } from '../../../core/api/portal-api.service';
import { CardType, DataScopeGroup, Problem } from '../../../core/api/portal.models';

interface SettingsState {
  cardTypes: CardType[];
  dataScope: DataScopeGroup[];
  loading: boolean;
  problem: Problem | null;
}

/** Card-type registry and data-scope mapping (GET /v1/card-types, GET /v1/settings/data-scope). */
export const SettingsStore = signalStore(
  withState<SettingsState>({ cardTypes: [], dataScope: [], loading: false, problem: null }),
  withMethods((store, api = inject(PortalApi)) => ({
    async load(): Promise<void> {
      patchState(store, { loading: true, problem: null });
      try {
        const [types, scope] = await Promise.all([
          firstValueFrom(api.cardTypes()),
          firstValueFrom(api.dataScope()),
        ]);
        patchState(store, { cardTypes: types.items, dataScope: scope.items, loading: false });
      } catch (e) {
        patchState(store, { loading: false, problem: toProblem(e) });
      }
    },
  })),
);
