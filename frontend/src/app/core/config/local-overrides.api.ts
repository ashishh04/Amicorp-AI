import type { AppConfig } from './app-config';

/**
 * `npm run start:api`: the portal talks to the platform-api running on this laptop instead of the
 * in-browser mock, and people sign in through platform-api's local sign-in.
 */
export const LOCAL_OVERRIDES: Partial<AppConfig> = { mockApi: false };
