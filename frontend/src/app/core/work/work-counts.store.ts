import { DestroyRef, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { patchState, signalStore, withHooks, withMethods, withState } from '@ngrx/signals';
import { debounceTime, filter, firstValueFrom } from 'rxjs';

import { PortalApi } from '../api/portal-api.service';
import { CardCounts } from '../api/portal.models';
import { CurrentUserStore } from '../auth/current-user.store';
import { EventStreamService } from '../sse/event-stream.service';

/**
 * Inbox view counts for the sidebar badges and the overview (GET /v1/cards/counts).
 * Re-read after every card event, so the numbers follow the queue live.
 */
export const WorkCountsStore = signalStore(
  { providedIn: 'root' },
  withState<{ counts: CardCounts | null }>({ counts: null }),
  withMethods((store, api = inject(PortalApi), user = inject(CurrentUserStore)) => ({
    async load(): Promise<void> {
      await user.load();
      if (!user.hasAnyRole(['Maker', 'Checker', 'MLRO', 'Auditor'])) {
        patchState(store, { counts: null });
        return;
      }
      try {
        patchState(store, { counts: await firstValueFrom(api.cardCounts()) });
      } catch {
        // Badges are a convenience; the inbox shows the error if the API is down.
      }
    },
    reset(): void {
      patchState(store, { counts: null });
    },
  })),
  withHooks((store) => {
    const events = inject(EventStreamService);
    const destroyRef = inject(DestroyRef);
    return {
      onInit() {
        events.events
          .pipe(
            filter((e) => e.type.startsWith('card.') || e.type === 'statement.updated'),
            debounceTime(300),
            takeUntilDestroyed(destroyRef),
          )
          .subscribe(() => void store.load());
      },
    };
  }),
);
