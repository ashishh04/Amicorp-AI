import { HttpClient } from '@angular/common/http';
import { computed, inject } from '@angular/core';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { firstValueFrom } from 'rxjs';

import { APP_CONFIG } from '../config/app-config';
import { AppRole, isAppRole } from './roles';

/** Response of GET /v1/me (LLD, Platform API: portal endpoints). */
export interface CurrentUser {
  id: string;
  displayName: string;
  email: string;
  roles: string[];
  /** Entities and clients the user may see (ref.user_scope), as display labels. */
  dataScope: string[];
  /** Owning teams (Entra groups AMC-IPA-<role>-<team>) the user works in. */
  teams?: string[];
  /** Business-hours calendar; times render in its time zone (store UTC, render HK/EU). */
  calendar?: 'HK' | 'EU';
}

interface CurrentUserState {
  user: CurrentUser | null;
  status: 'idle' | 'loading' | 'loaded' | 'error';
}

/**
 * Who is signed in and which app roles they hold. Route guards and the navigation read
 * this; the API enforces every rule again, so this only shapes the UI.
 */
export const CurrentUserStore = signalStore(
  { providedIn: 'root' },
  withState<CurrentUserState>({ user: null, status: 'idle' }),
  withComputed(({ user }) => ({
    roles: computed<AppRole[]>(() => (user()?.roles ?? []).filter(isAppRole)),
    calendar: computed(() => user()?.calendar ?? 'HK'),
  })),
  withMethods((store, http = inject(HttpClient), config = inject(APP_CONFIG)) => {
    let pending: Promise<void> | null = null;
    return {
      hasAnyRole(roles: readonly AppRole[]): boolean {
        return roles.length === 0 || store.roles().some((r) => roles.includes(r));
      },
      /** Forgets the user so the next load() reads /v1/me again (mock persona switch). */
      reset(): void {
        patchState(store, { user: null, status: 'idle' });
      },
      /**
       * Loads once; concurrent callers share the request. In every sign-in mode /v1/me answers for
       * the caller: the Entra account, the mock's demo user or the locally signed-in officer.
       */
      load(): Promise<void> {
        if (store.status() === 'loaded') return Promise.resolve();
        pending ??= (async () => {
          patchState(store, { status: 'loading' });
          try {
            // Moves to the generated client once platform-api exposes /v1/me.
            const user = await firstValueFrom(http.get<CurrentUser>(`${config.apiBaseUrl}/v1/me`));
            patchState(store, { user, status: 'loaded' });
          } catch {
            patchState(store, { user: null, status: 'error' });
          } finally {
            pending = null;
          }
        })();
        return pending;
      },
    };
  }),
);
