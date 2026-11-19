import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { CurrentUserStore } from './current-user.store';
import { AppRole } from './roles';

/** Allows the route when the user holds any of the given app roles; otherwise /forbidden. */
export function roleGuard(...roles: AppRole[]): CanActivateFn {
  return async () => {
    const store = inject(CurrentUserStore);
    const router = inject(Router);
    await store.load();
    return store.hasAnyRole(roles) ? true : router.parseUrl('/forbidden');
  };
}
