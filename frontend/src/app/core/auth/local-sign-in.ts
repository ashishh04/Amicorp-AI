import { HttpClient, HttpInterceptorFn } from '@angular/common/http';
import { Injectable, Injector, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { APP_CONFIG, signInMode } from '../config/app-config';

/** A sample officer platform-api can sign in locally (GET /v1/dev/users). */
export interface LocalAccount {
  id: string;
  displayName: string;
  roles: string[];
  teams: string[];
}

interface SignInResponse {
  accessToken: string;
  expiresIn: number;
}

interface StoredSession {
  token: string;
  expiresAt: number;
}

const KEY = 'amc.local.session';

/**
 * Sign-in mode 'local': the portal talks to platform-api on this laptop, which has no Entra
 * tenant. platform-api lists its sample officers and signs a short-lived token for the one picked
 * (/v1/dev/*, served only when platform-api runs locally). The token stays in this tab's session
 * storage, like MSAL's, and a restart of platform-api ends every local session.
 */
@Injectable({ providedIn: 'root' })
export class LocalSession {
  private readonly http = inject(HttpClient);
  private readonly base = `${inject(APP_CONFIG).apiBaseUrl}/v1/dev`;
  private readonly session = signal<StoredSession | null>(stored());

  /** The bearer token, or null when nobody is signed in or the token has expired. */
  token(): string | null {
    const session = this.session();
    return session && session.expiresAt > Date.now() ? session.token : null;
  }

  async accounts(): Promise<LocalAccount[]> {
    const page = await firstValueFrom(
      this.http.get<{ items: LocalAccount[] }>(`${this.base}/users`),
    );
    return page.items;
  }

  async signIn(userId: string): Promise<void> {
    const res = await firstValueFrom(
      this.http.post<SignInResponse>(`${this.base}/sign-in`, { userId }),
    );
    const session = { token: res.accessToken, expiresAt: Date.now() + res.expiresIn * 1000 };
    try {
      sessionStorage.setItem(KEY, JSON.stringify(session));
    } catch {
      // Private mode: the session lasts until reload.
    }
    this.session.set(session);
  }

  clear(): void {
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      // Private mode: nothing was stored.
    }
    this.session.set(null);
  }
}

function stored(): StoredSession | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as StoredSession) : null;
  } catch {
    return null;
  }
}

/**
 * Adds the local session's token to Platform API calls, as MsalInterceptor does with Entra.
 * Only in sign-in mode 'local', and never on the sign-in calls themselves.
 */
export const localTokenInterceptor: HttpInterceptorFn = (req, next) => {
  const config = inject(APP_CONFIG);
  const api = config.apiBaseUrl;
  if (
    signInMode(config) !== 'local' ||
    !req.url.startsWith(`${api}/`) ||
    req.url.startsWith(`${api}/v1/dev/`)
  ) {
    return next(req);
  }
  const token = inject(Injector).get(LocalSession).token();
  return next(token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req);
};
