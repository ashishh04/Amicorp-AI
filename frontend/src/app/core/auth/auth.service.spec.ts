import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { MsalService } from '@azure/msal-angular';
import { vi } from 'vitest';

import { APP_CONFIG, AppConfig } from '../config/app-config';
import { MockSession } from '../mock/mock-personas';
import { AuthService, safeReturnUrl } from './auth.service';
import { LocalSession } from './local-sign-in';

const config = {
  environment: 'local',
  apiBaseUrl: '/api',
  auth: { enabled: false },
  mockApi: true,
} as AppConfig;

describe('safeReturnUrl', () => {
  it('keeps portal paths', () => {
    expect(safeReturnUrl('/inbox?view=team')).toBe('/inbox?view=team');
    expect(safeReturnUrl('/cards/WC-24-1041')).toBe('/cards/WC-24-1041');
  });

  it('never leaves the portal or returns to a sign-in page', () => {
    for (const url of ['https://evil.example/', '//evil.example', '/\\evil.example', '', null]) {
      expect(safeReturnUrl(url)).toBe('/home');
    }
    for (const url of ['/login?returnUrl=%2Finbox', '/logout', '/auth/callback', '/_reload']) {
      expect(safeReturnUrl(url)).toBe('/home');
    }
  });
});

describe('AuthService with the mock API', () => {
  let auth: AuthService;
  let session: MockSession;
  let router: Router;
  let navigateByUrl: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(),
        { provide: APP_CONFIG, useValue: config },
        { provide: MsalService, useValue: {} },
      ],
    });
    auth = TestBed.inject(AuthService);
    session = TestBed.inject(MockSession);
    router = TestBed.inject(Router);
    navigateByUrl = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
  });

  it('signs in as the chosen sample user and returns to the page asked for', async () => {
    expect(auth.mode).toBe('mock');
    expect(await auth.isSignedIn()).toBe(false);

    await auth.signIn('/inbox?view=team', 'u-chan');

    expect(session.personaId()).toBe('u-chan');
    expect(await auth.isSignedIn()).toBe(true);
    expect(navigateByUrl).toHaveBeenCalledWith('/inbox?view=team');
  });

  it('does not follow a return URL to another site', async () => {
    await auth.signIn('https://evil.example/', 'u-chan');
    expect(navigateByUrl).toHaveBeenCalledWith('/home');
  });

  it('ends the session on /logout and remembers why', async () => {
    session.use('u-chan');
    let forced: boolean | null = null;
    navigateByUrl.mockImplementation(async () => {
      forced = auth.forced;
      return true;
    });

    await auth.leave('idle');
    expect(navigateByUrl).toHaveBeenCalledWith('/logout');
    expect(forced).toBe(true);
    expect(auth.forced).toBe(false);

    await auth.signOut();
    expect(session.personaId()).toBeNull();
    expect(auth.lastSignOut()).toEqual({ reason: 'idle', returnUrl: '/' });

    // A user's own sign-out keeps unsaved-changes prompts; signing in forgets the reason.
    await auth.leave();
    expect(forced).toBe(false);
    await auth.signIn('/home', 'u-chan');
    expect(auth.lastSignOut()).toEqual({ reason: 'user' });
  });

  it('sends the user to sign in again when the API answers 401', () => {
    session.use('u-chan');
    vi.spyOn(router, 'url', 'get').mockReturnValue('/inbox?view=team');
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    auth.sessionExpired();

    expect(session.personaId()).toBeNull();
    expect(navigate).toHaveBeenCalledWith(['/login'], {
      queryParams: { reason: 'expired', returnUrl: '/inbox?view=team' },
    });
  });

  it('ignores a 401 on the sign-in pages', () => {
    session.use('u-chan');
    vi.spyOn(router, 'url', 'get').mockReturnValue('/logout');
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);

    auth.sessionExpired();

    expect(navigate).not.toHaveBeenCalled();
    expect(session.personaId()).toBe('u-chan');
  });
});

describe('AuthService with the local Platform API', () => {
  let auth: AuthService;
  let http: HttpTestingController;
  let router: Router;
  let navigateByUrl: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    sessionStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: APP_CONFIG, useValue: { ...config, mockApi: false } },
        { provide: MsalService, useValue: {} },
      ],
    });
    auth = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    navigateByUrl = vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
  });

  afterEach(() => http.verify());

  it('signs in through platform-api and keeps the token until sign-out', async () => {
    expect(auth.mode).toBe('local');
    const done = auth.signIn('/inbox?view=team', 'officer-1');
    const req = http.expectOne('/api/v1/dev/sign-in');
    expect(req.request.body).toEqual({ userId: 'officer-1' });
    req.flush({ accessToken: 'token-1', tokenType: 'Bearer', expiresIn: 3600, user: {} });
    await done;

    expect(await auth.isSignedIn()).toBe(true);
    expect(TestBed.inject(LocalSession).token()).toBe('token-1');
    expect(navigateByUrl).toHaveBeenCalledWith('/inbox?view=team');

    await auth.signOut();
    expect(await auth.isSignedIn()).toBe(false);
  });

  it('says so when platform-api is not running', async () => {
    const done = auth.signIn('/inbox', 'officer-1');
    http
      .expectOne('/api/v1/dev/sign-in')
      .flush('down', { status: 504, statusText: 'Gateway Timeout' });
    await done;

    expect(auth.problem()?.message).toContain('did not answer');
    expect(await auth.isSignedIn()).toBe(false);
    expect(navigateByUrl).not.toHaveBeenCalled();
  });

  it('opens the sign-in page when no officer was chosen', async () => {
    const navigate = vi.spyOn(router, 'navigate').mockResolvedValue(true);
    await auth.signIn('/inbox');
    expect(navigate).toHaveBeenCalledWith(['/login'], { queryParams: { returnUrl: '/inbox' } });
  });
});
