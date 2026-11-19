import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  CanActivateFn,
  Router,
  RouterStateSnapshot,
  UrlTree,
  convertToParamMap,
  provideRouter,
} from '@angular/router';
import { vi } from 'vitest';

import { authGuard, signedOutGuard } from './auth.guard';
import { AuthService } from './auth.service';

const openLanding = vi.fn();

async function run(
  guard: CanActivateFn,
  signedIn: boolean,
  url: string,
  returnUrl?: string,
): Promise<string | boolean> {
  openLanding.mockClear();
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      {
        provide: AuthService,
        useValue: { isSignedIn: () => Promise.resolve(signedIn), openLanding },
      },
    ],
  });
  const route = {
    queryParamMap: convertToParamMap(returnUrl ? { returnUrl } : {}),
  } as ActivatedRouteSnapshot;
  const result = await (TestBed.runInInjectionContext(() =>
    guard(route, { url } as RouterStateSnapshot),
  ) as Promise<boolean | UrlTree>);
  return typeof result === 'boolean' ? result : TestBed.inject(Router).serializeUrl(result);
}

describe('authGuard', () => {
  it('lets a signed-in user through', async () => {
    expect(await run(authGuard, true, '/inbox')).toBe(true);
    expect(await run(authGuard, true, '/home')).toBe(true);
    expect(openLanding).not.toHaveBeenCalled();
  });

  it('shows signed-out visitors to the portal address the UDAP landing page', async () => {
    expect(await run(authGuard, false, '/home')).toBe(false);
    expect(openLanding).toHaveBeenCalledOnce();
    expect(await run(authGuard, false, '/')).toBe(false);
    expect(openLanding).toHaveBeenCalledOnce();
  });

  it('sends anyone heading for a page to sign in, then back to the same page', async () => {
    expect(await run(authGuard, false, '/inbox?view=team')).toBe(
      '/login?returnUrl=%2Finbox%3Fview%3Dteam',
    );
    expect(await run(authGuard, false, '/home?tab=team')).toBe(
      '/login?returnUrl=%2Fhome%3Ftab%3Dteam',
    );
    expect(openLanding).not.toHaveBeenCalled();
  });
});

describe('signedOutGuard', () => {
  it('shows the sign-in page to signed-out users', async () => {
    expect(await run(signedOutGuard, false, '/login')).toBe(true);
  });

  it('sends a signed-in user on to the page they asked for, within the portal', async () => {
    expect(await run(signedOutGuard, true, '/login', '/cards/WC-24-1041')).toBe(
      '/cards/WC-24-1041',
    );
    expect(await run(signedOutGuard, true, '/login', 'https://evil.example/')).toBe('/home');
  });
});
