import type { AppConfig } from './app-config';

/**
 * Changes a build makes to /assets/config.json. Empty in every real build: the ConfigMap decides.
 * `npm run start:api` swaps in local-overrides.api.ts (angular.json, configuration "api").
 */
export const LOCAL_OVERRIDES: Partial<AppConfig> = {};
