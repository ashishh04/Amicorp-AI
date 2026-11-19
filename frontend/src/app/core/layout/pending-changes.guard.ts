import { inject } from '@angular/core';
import { CanDeactivateFn } from '@angular/router';

import { AuthService } from '../auth/auth.service';

/** A page with work that would be lost; it asks the user (with its own dialog) before leaving. */
export interface PendingChanges {
  canDeactivate(): boolean | Promise<boolean>;
}

/**
 * Lets a page keep the user when they navigate away with unsaved changes. When the portal ends
 * the session itself (idle timeout, expired token), nothing can keep the user.
 */
export const pendingChangesGuard: CanDeactivateFn<Partial<PendingChanges>> = (page) =>
  inject(AuthService).forced || !page?.canDeactivate ? true : page.canDeactivate();
