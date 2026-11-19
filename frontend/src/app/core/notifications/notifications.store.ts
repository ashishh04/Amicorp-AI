import { DestroyRef, computed, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import {
  patchState,
  signalStore,
  withComputed,
  withHooks,
  withMethods,
  withState,
} from '@ngrx/signals';

import { CardEventData, CardState } from '../api/portal.models';
import { CurrentUserStore } from '../auth/current-user.store';
import { EventStreamService, PlatformEvent } from '../sse/event-stream.service';

export interface PortalNotification {
  id: string;
  kind: 'new' | 'assigned' | 'update' | 'alert';
  cardId: string;
  title: string;
  message: string;
  at: string;
  read: boolean;
}

const MAX_ITEMS = 30;

/** States worth telling people about; the rest of the card's life shows on the card itself. */
const NOTABLE: Partial<Record<CardState, { kind: PortalNotification['kind']; text: string }>> = {
  AWAITING_DECISION: { kind: 'update', text: 'is ready for a decision' },
  ESCALATED: { kind: 'alert', text: 'was escalated' },
  CLOSED: { kind: 'update', text: 'was closed' },
  WRITEBACK_FAILED: { kind: 'alert', text: 'failed to write back' },
};

/**
 * In-portal notifications built from the live event stream (card.created, card.updated,
 * card.assigned). Teams carries the same alerts outside the portal (D-07); decisions are only
 * taken in the portal.
 */
export const NotificationsStore = signalStore(
  { providedIn: 'root' },
  withState<{ items: PortalNotification[] }>({ items: [] }),
  withComputed(({ items }) => ({
    unread: computed(() => items().filter((n) => !n.read).length),
  })),
  withMethods((store, user = inject(CurrentUserStore)) => ({
    receive(event: PlatformEvent): PortalNotification | null {
      const data = event.data as CardEventData;
      if (!data?.cardId) return null;
      const title = data.title ?? data.cardId;
      let item: Omit<PortalNotification, 'id' | 'at' | 'read' | 'cardId' | 'title'> | null = null;
      if (event.type === 'card.created') {
        item = { kind: 'new', message: `New card ${data.cardId} in the queue` };
      } else if (event.type === 'card.assigned') {
        const toMe = data.assignee === user.user()?.id;
        item = {
          kind: 'assigned',
          message: toMe ? `${data.cardId} was assigned to you` : `${data.cardId} was reassigned`,
        };
      } else if (event.type === 'card.updated' && data.state && NOTABLE[data.state]) {
        const n = NOTABLE[data.state]!;
        item = { kind: n.kind, message: `${data.cardId} ${n.text}` };
      }
      if (!item) return null;
      const full: PortalNotification = {
        ...item,
        id: event.id,
        cardId: data.cardId,
        title,
        at: new Date().toISOString(),
        read: false,
      };
      patchState(store, { items: [full, ...store.items()].slice(0, MAX_ITEMS) });
      return full;
    },
    markRead(id: string): void {
      patchState(store, {
        items: store.items().map((n) => (n.id === id ? { ...n, read: true } : n)),
      });
    },
    markAllRead(): void {
      patchState(store, { items: store.items().map((n) => ({ ...n, read: true })) });
    },
    clear(): void {
      patchState(store, { items: [] });
    },
  })),
  withHooks((store) => {
    const events = inject(EventStreamService);
    const destroyRef = inject(DestroyRef);
    return {
      onInit() {
        events.events
          .pipe(takeUntilDestroyed(destroyRef))
          .subscribe((event) => store.receive(event));
      },
    };
  }),
);
