import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient, withInterceptors, withInterceptorsFromDi } from '@angular/common/http';
import { TitleStrategy, provideRouter, withComponentInputBinding } from '@angular/router';

import { routes } from './app.routes';
import { provideApiConfiguration } from './core/api/generated/api-configuration';
import { localTokenInterceptor } from './core/auth/local-sign-in';
import { provideMsal } from './core/auth/msal.config';
import { sessionExpiryInterceptor } from './core/auth/session-expiry.interceptor';
import { APP_CONFIG, AppConfig } from './core/config/app-config';
import { AmcTitleStrategy } from './core/layout/title.strategy';
import { mockApiInterceptor } from './core/mock/mock-api.interceptor';

export function createAppConfig(config: AppConfig): ApplicationConfig {
  return {
    providers: [
      provideBrowserGlobalErrorListeners(),
      provideRouter(routes, withComponentInputBinding()),
      { provide: TitleStrategy, useClass: AmcTitleStrategy },
      // MsalInterceptor is a class interceptor, so DI interceptors must stay enabled. A 401 sends
      // the user to sign in again. The mock interceptor passes everything through unless
      // config.mockApi is true; the local one adds a token only in sign-in mode 'local'.
      provideHttpClient(
        withInterceptorsFromDi(),
        withInterceptors([sessionExpiryInterceptor, mockApiInterceptor, localTokenInterceptor]),
      ),
      { provide: APP_CONFIG, useValue: config },
      provideApiConfiguration(config.apiBaseUrl),
      ...provideMsal(config),
    ],
  };
}
