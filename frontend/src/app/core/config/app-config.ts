import { InjectionToken } from '@angular/core';

import { LOCAL_OVERRIDES } from './local-overrides';

/**
 * Runtime configuration, read from /assets/config.json before bootstrap. The file is
 * mounted from a ConfigMap, so one image serves DEV, NPR and PRD (LLD, Runtime container).
 */
export interface AppConfig {
  environment: 'local' | 'dev' | 'npr' | 'prd';
  /** Platform API base, e.g. "/api". Every call under it gets an Entra access token. */
  apiBaseUrl: string;
  auth: {
    /**
     * false skips Entra sign-in. With mockApi you pick a sample user of the in-browser mock;
     * without it, a sample officer through platform-api's local sign-in (/v1/dev/*, which
     * platform-api serves only when it runs locally). Refused in NPR and PRD. Default true.
     */
    enabled?: boolean;
    tenantId: string;
    /** Client ID of the amc-portal-spa app registration. */
    clientId: string;
    /** api://amc-platform-api/.default */
    apiScope: string;
    redirectPath: string;
    /**
     * Minutes without activity in any portal tab before the session ends, after a one-minute
     * warning. Default 30; 0 turns the timeout off.
     */
    idleTimeoutMinutes?: number;
  };
  agGridLicenseKey: string;
  /**
   * true answers every Platform API call from the in-browser mock (core/mock) so the portal
   * can be reviewed with sample data before platform-api has the endpoints. Refused in NPR and PRD.
   */
  mockApi?: boolean;
}

export const APP_CONFIG = new InjectionToken<AppConfig>('APP_CONFIG');

export async function loadAppConfig(url = '/assets/config.json'): Promise<AppConfig> {
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) {
    throw new Error(`Cannot load ${url}: HTTP ${res.status}`);
  }
  const config = { ...((await res.json()) as AppConfig), ...LOCAL_OVERRIDES };
  if (!isAuthEnabled(config) && (config.environment === 'npr' || config.environment === 'prd')) {
    throw new Error(`Sign-in cannot be disabled in ${config.environment}`);
  }
  if (config.mockApi && (config.environment === 'npr' || config.environment === 'prd')) {
    throw new Error(`The mock API cannot be used in ${config.environment}`);
  }
  return config;
}

export function isAuthEnabled(config: AppConfig): boolean {
  return config.auth.enabled !== false;
}

/**
 * How people sign in: 'entra' (Microsoft Entra ID; the only mode allowed in NPR and PRD), 'mock'
 * (pick a sample user; with the mock API) or 'local' (pick a sample officer through
 * platform-api's local sign-in, for a laptop running the real backend).
 */
export type SignInMode = 'entra' | 'mock' | 'local';

export function signInMode(config: AppConfig): SignInMode {
  if (isAuthEnabled(config)) return 'entra';
  return config.mockApi ? 'mock' : 'local';
}

export function idleTimeoutMinutes(config: AppConfig): number {
  return config.auth.idleTimeoutMinutes ?? 30;
}
