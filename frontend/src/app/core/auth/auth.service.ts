import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { MsalService } from '@azure/msal-angular';
import { AccountInfo } from '@azure/msal-browser';
import { firstValueFrom } from 'rxjs';

import { APP_CONFIG, SignInMode, signInMode } from '../config/app-config';
import { MockSession } from '../mock/mock-personas';
import { NotificationsStore } from '../notifications/notifications.store';
import { EventStreamService } from '../sse/event-stream.service';
import { WorkCountsStore } from '../work/work-counts.store';
import { CurrentUserStore } from './current-user.store';
import { LocalAccount, LocalSession } from './local-sign-in';

export type { SignInMode } from '../config/app-config';

/** Why the last session ended; the signed-out page says so. */
export type SignOutReason = 'user' | 'idle';

export interface SignedOut {
  reason: SignOutReason;
  /** Where to go after signing in again (idle sign-out only). */
  returnUrl?: string;
}

export interface SignInProblem {
  message: string;
  /** Entra (AADSTS…) or MSAL error code, for the service desk. */
  code?: string;
}

const SIGNED_OUT_KEY = 'amc.auth.signed-out';
const LANDING_PAGE = 'udap/';
const AUTH_PAGE = /^\/(login|logout|auth|_reload)(?=[/?#]|$)/;

/** Same-origin paths only, and never a sign-in page; anything else goes to the overview. */
export function safeReturnUrl(url: string | null | undefined): string {
  if (!url || !url.startsWith('/') || url.startsWith('//') || url.startsWith('/\\')) return '/home';
  return AUTH_PAGE.test(url) ? '/home' : url;
}

/**
 * Sign-in and sign-out in every mode. With Entra ID, MSAL runs the redirect flow (auth code +
 * PKCE, tokens in session storage; LLD, Key building blocks) and this service decides when.
 * The pages are /login, /logout and /auth/callback; the shell's route guard asks isSignedIn().
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly config = inject(APP_CONFIG);
  private readonly router = inject(Router);
  private readonly msal = inject(MsalService);
  private readonly mock = inject(MockSession);
  private readonly local = inject(LocalSession);
  private readonly user = inject(CurrentUserStore);
  private readonly counts = inject(WorkCountsStore);
  private readonly notifications = inject(NotificationsStore);
  private readonly events = inject(EventStreamService);
  private redirect: Promise<void> | null = null;

  readonly mode: SignInMode = signInMode(this.config);

  /** Why the last sign-in failed; the sign-in page shows it. */
  readonly problem = signal<SignInProblem | null>(null);

  /** True while the portal ends a session itself; unsaved-changes prompts step aside. */
  forced = false;

  /**
   * Completes an Entra redirect (a sign-in, or a token renewal MsalInterceptor started) and
   * picks the active account. MSAL needs this on every page load; later calls share the first.
   */
  ready(): Promise<void> {
    if (this.mode !== 'entra') return Promise.resolve();
    this.redirect ??= firstValueFrom(this.msal.handleRedirectObservable())
      .then((result) => {
        const account = result?.account ?? this.account();
        if (account) this.msal.instance.setActiveAccount(account);
      })
      .catch((err: unknown) => this.problem.set(signInProblem(err)));
    return this.redirect;
  }

  async isSignedIn(): Promise<boolean> {
    if (this.mode === 'mock') return this.mock.personaId() !== null;
    if (this.mode === 'local') return this.local.token() !== null;
    await this.ready();
    return this.account() !== null;
  }

  /** The sample officers platform-api can sign in (mode 'local'); the sign-in page lists them. */
  async localAccounts(): Promise<LocalAccount[]> {
    this.problem.set(null);
    try {
      return await this.local.accounts();
    } catch (err) {
      this.problem.set(localProblem(err));
      throw err;
    }
  }

  /**
   * Entra: off to Microsoft and back to returnUrl. Otherwise signs in as the chosen user, or
   * opens the sign-in page to choose one.
   */
  async signIn(returnUrl: string | null | undefined, personaId?: string): Promise<void> {
    const target = safeReturnUrl(returnUrl);
    this.problem.set(null);
    forget(SIGNED_OUT_KEY);
    if (this.mode !== 'entra') {
      if (!personaId) {
        await this.router.navigate(['/login'], { queryParams: { returnUrl: target } });
        return;
      }
      if (this.mode === 'mock') {
        this.mock.use(personaId);
      } else {
        try {
          await this.local.signIn(personaId);
        } catch (err) {
          this.problem.set(localProblem(err));
          return;
        }
      }
      await this.router.navigateByUrl(target);
      return;
    }
    try {
      await this.ready();
      await firstValueFrom(
        this.msal.loginRedirect({
          scopes: [this.config.auth.apiScope],
          redirectStartPage: new URL(target, window.location.origin).href,
        }),
      );
    } catch (err) {
      this.problem.set(signInProblem(err));
    }
  }

  /**
   * The UDAP landing page (public/udap/, plain HTML outside Angular): where signed-out visitors
   * to the portal's own address go. Its "Sign in" opens /login. Replaces the history entry, so
   * Back does not bounce through the portal again.
   */
  openLanding(): void {
    window.location.replace(new URL(LANDING_PAGE, document.baseURI).href);
  }

  /** Opens /logout, which ends the session. The idle sign-out skips unsaved-changes prompts. */
  async leave(reason: SignOutReason = 'user'): Promise<void> {
    remember(SIGNED_OUT_KEY, {
      reason,
      returnUrl: reason === 'idle' ? this.router.url : undefined,
    } satisfies SignedOut);
    this.forced = reason === 'idle';
    try {
      await this.router.navigateByUrl('/logout');
    } finally {
      this.forced = false;
    }
  }

  /**
   * Ends the session; /logout calls it. Entra also signs out of Microsoft and comes back to
   * /logout (auth.postLogoutRedirectUri in msal.config.ts).
   */
  async signOut(): Promise<void> {
    this.clearState();
    if (this.mode !== 'entra') {
      this.forgetSession();
      return;
    }
    await this.ready();
    const account = this.account();
    if (account) await firstValueFrom(this.msal.logoutRedirect({ account }));
  }

  /** How the last session in this tab ended, for the signed-out page. */
  lastSignOut(): SignedOut {
    return recall<SignedOut>(SIGNED_OUT_KEY) ?? { reason: 'user' };
  }

  /** The API refused the session (401): end it here and ask the user to sign in again. */
  sessionExpired(): void {
    const returnUrl = this.router.url;
    if (this.forced || AUTH_PAGE.test(returnUrl)) return;
    this.clearState();
    if (this.mode === 'entra') void this.msal.instance.clearCache();
    else this.forgetSession();
    this.forced = true;
    void this.router
      .navigate(['/login'], { queryParams: { reason: 'expired', returnUrl } })
      .finally(() => (this.forced = false));
  }

  private forgetSession(): void {
    if (this.mode === 'mock') this.mock.clear();
    else this.local.clear();
  }

  /** Forgets what the root stores hold about the user; pages go with the shell. */
  private clearState(): void {
    this.events.stop();
    this.user.reset();
    this.counts.reset();
    this.notifications.clear();
  }

  private account(): AccountInfo | null {
    const msal = this.msal.instance;
    return msal.getActiveAccount() ?? msal.getAllAccounts()[0] ?? null;
  }
}

/** platform-api's local sign-in failed: usually the API is not running. */
function localProblem(err: unknown): SignInProblem {
  const status = (err as { status?: number } | null)?.status;
  if (!status || status >= 500) {
    return { message: 'The local Platform API did not answer. Start it with: python -m app' };
  }
  return { message: `The local Platform API refused the sign-in (HTTP ${status}).` };
}

/** Entra puts the reason on the first line, then trace and correlation IDs. */
function signInProblem(err: unknown): SignInProblem {
  const e = (err ?? {}) as { errorCode?: string; errorMessage?: string; message?: string };
  const text = e.errorMessage || e.message || '';
  const code = /AADSTS\d+/.exec(text)?.[0] ?? e.errorCode;
  const message = text
    .split(/\r?\n/)[0]
    .replace(/^AADSTS\d+:\s*/, '')
    .trim();
  return { message: message || 'Microsoft sign-in did not finish.', code: code || undefined };
}

function remember(key: string, value: unknown): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Private mode: the signed-out page shows the default text.
  }
}

function recall<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function forget(key: string): void {
  try {
    sessionStorage.removeItem(key);
  } catch {
    // Private mode: nothing was stored.
  }
}
