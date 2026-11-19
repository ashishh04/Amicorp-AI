import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { Injector, inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { APP_CONFIG } from '../config/app-config';
import { AuthService } from './auth.service';

/**
 * A 401 from the Platform API means the session is no longer valid (token expired or revoked):
 * the user signs in again and returns to the same page. MsalInterceptor renews tokens before
 * that happens, so this is the backstop.
 */
export const sessionExpiryInterceptor: HttpInterceptorFn = (req, next) => {
  const injector = inject(Injector);
  const api = inject(APP_CONFIG).apiBaseUrl;
  return next(req).pipe(
    catchError((err: unknown) => {
      if (err instanceof HttpErrorResponse && err.status === 401 && req.url.startsWith(api)) {
        injector.get(AuthService).sessionExpired();
      }
      return throwError(() => err);
    }),
  );
};
