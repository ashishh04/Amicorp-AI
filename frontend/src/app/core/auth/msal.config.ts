import { Provider } from '@angular/core';
import { HTTP_INTERCEPTORS } from '@angular/common/http';
import {
  MSAL_INSTANCE,
  MSAL_INTERCEPTOR_CONFIG,
  MsalBroadcastService,
  MsalInterceptor,
  MsalService,
} from '@azure/msal-angular';
import {
  BrowserCacheLocation,
  InteractionType,
  LogLevel,
  PublicClientApplication,
} from '@azure/msal-browser';

import { AppConfig, isAuthEnabled } from '../config/app-config';

/**
 * Entra ID sign-in for the amc-portal-spa registration: authorisation code + PKCE,
 * redirect flow, tokens in session storage, silent renewal (LLD, Key building blocks).
 * AuthService decides when to sign in and out; Entra returns to /auth/callback after sign-in
 * and to /logout after sign-out, so both must be redirect URIs of the registration.
 */
export function provideMsal(config: AppConfig): Provider[] {
  const { tenantId, clientId, apiScope, redirectPath } = config.auth;
  const origin = window.location.origin;

  const instance = new PublicClientApplication({
    auth: {
      clientId,
      authority: `https://login.microsoftonline.com/${tenantId}`,
      redirectUri: origin + redirectPath,
      postLogoutRedirectUri: `${origin}/logout`,
    },
    cache: { cacheLocation: BrowserCacheLocation.SessionStorage },
    system: {
      loggerOptions: {
        logLevel: config.environment === 'prd' ? LogLevel.Error : LogLevel.Warning,
        piiLoggingEnabled: false,
        loggerCallback: (level, message) =>
          level === LogLevel.Error ? console.error(message) : console.warn(message),
      },
    },
  });

  // Absolute key so strict matching attaches the token to every Platform API call and nothing else.
  const apiBase = new URL(config.apiBaseUrl, origin).href.replace(/\/$/, '');
  const protectedResourceMap = new Map<string, string[]>([[`${apiBase}/*`, [apiScope]]]);

  // With sign-in off the services still exist (AuthService injects them), but no interceptor
  // attaches tokens and AuthService keeps the session itself.
  const interceptor = isAuthEnabled(config)
    ? [{ provide: HTTP_INTERCEPTORS, useClass: MsalInterceptor, multi: true }]
    : [];

  return [
    { provide: MSAL_INSTANCE, useValue: instance },
    {
      provide: MSAL_INTERCEPTOR_CONFIG,
      useValue: { interactionType: InteractionType.Redirect, protectedResourceMap },
    },
    ...interceptor,
    MsalService,
    MsalBroadcastService,
  ];
}
