import {
  HttpErrorResponse,
  HttpEvent,
  HttpInterceptorFn,
  HttpResponse,
} from '@angular/common/http';
import { Injector, inject } from '@angular/core';
import { Observable, from, mergeMap, of, throwError, timer } from 'rxjs';

import { APP_CONFIG } from '../config/app-config';

const LATENCY_MS = 250;

/**
 * Answers Platform API calls from MockBackend when config.mockApi is true. Every other
 * request, and every request when the flag is off, goes to the network unchanged. The
 * backend and its sample data load on first use, so they stay out of the initial bundle.
 */
export const mockApiInterceptor: HttpInterceptorFn = (req, next) => {
  const config = inject(APP_CONFIG);
  if (!config.mockApi || !req.url.startsWith(config.apiBaseUrl)) return next(req);

  const injector = inject(Injector);
  const url = new URL(req.urlWithParams, window.location.origin);
  const base = new URL(config.apiBaseUrl, window.location.origin).pathname;
  const path = url.pathname.slice(base.length).replace(/\/$/, '');

  return from(import('./mock-backend')).pipe(
    mergeMap(({ MockBackend, MockProblem }): Observable<HttpEvent<unknown>> => {
      try {
        const res = injector.get(MockBackend).handle({
          method: req.method,
          path,
          query: url.searchParams,
          body: req.body,
          headers: req.headers,
        });
        // Copies, so callers can never mutate the mock's state by accident.
        const body = structuredClone(res.body);
        return timer(LATENCY_MS).pipe(
          mergeMap(() => of(new HttpResponse({ status: res.status, body, url: req.url }))),
        );
      } catch (e) {
        const problem = (
          e instanceof MockProblem ? e : new MockProblem(500, 'Mock error', (e as Error).message)
        ).toProblem(path);
        return timer(LATENCY_MS).pipe(
          mergeMap(() =>
            throwError(
              () =>
                new HttpErrorResponse({
                  status: problem.status,
                  statusText: problem.title,
                  error: problem,
                  url: req.url,
                }),
            ),
          ),
        );
      }
    }),
  );
};
