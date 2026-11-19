import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  Router,
  RouterStateSnapshot,
  UrlTree,
  provideRouter,
} from '@angular/router';

import { CurrentUserStore } from './current-user.store';
import { roleGuard } from './role.guard';
import { AppRole } from './roles';

function run(userRoles: AppRole[], required: AppRole[]) {
  TestBed.configureTestingModule({
    providers: [
      provideRouter([]),
      {
        provide: CurrentUserStore,
        useValue: {
          load: () => Promise.resolve(),
          hasAnyRole: (roles: readonly AppRole[]) => userRoles.some((r) => roles.includes(r)),
        },
      },
    ],
  });
  return TestBed.runInInjectionContext(() =>
    roleGuard(...required)({} as ActivatedRouteSnapshot, {} as RouterStateSnapshot),
  ) as Promise<boolean | UrlTree>;
}

describe('roleGuard', () => {
  it('allows a user holding one of the roles', async () => {
    expect(await run(['Checker'], ['Maker', 'Checker'])).toBe(true);
  });

  it('sends anyone else to /forbidden', async () => {
    const result = await run(['Maker'], ['Admin']);
    expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toBe('/forbidden');
  });
});
