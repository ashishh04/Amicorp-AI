import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService, safeReturnUrl } from './auth.service';

/**
 * Signed-in users pass. Signed-out visitors to the portal's own address see the UDAP landing page
 * first; anyone heading for a particular page signs in and then comes back to it.
 */
export const authGuard: CanActivateFn = async (_route, state) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  if (await auth.isSignedIn()) return true;
  const returnUrl = safeReturnUrl(state.url);
  if (returnUrl === '/' || returnUrl === '/home') {
    auth.openLanding();
    return false;
  }
  return router.createUrlTree(['/login'], { queryParams: { returnUrl } });
};

/** The sign-in page is for signed-out users; anyone else goes on to where they were heading. */
export const signedOutGuard: CanActivateFn = async (route) => {
  const auth = inject(AuthService);
  const router = inject(Router);
  return (await auth.isSignedIn())
    ? router.parseUrl(safeReturnUrl(route.queryParamMap.get('returnUrl')))
    : true;
};
