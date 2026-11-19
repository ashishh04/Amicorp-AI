import { Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';

import { EmptyStateComponent } from '../../shared/ui/layout.components';
import { AuthService } from '../auth/auth.service';
import { CurrentUserStore } from '../auth/current-user.store';

/** No access: to this page, to the portal at all (no role yet), or roles that did not load. */
@Component({
  selector: 'amc-forbidden',
  imports: [RouterLink, MatButtonModule, EmptyStateComponent],
  template: `
    <div class="amc-page">
      @switch (state()) {
        @case ('no-role') {
          <amc-empty-state
            icon="lock"
            title="Your account has no access to the Work Card Portal"
            message="Ask your team lead to request a portal role in Entra ID, then sign in again."
          >
            <button mat-stroked-button (click)="auth.leave()">Sign out</button>
          </amc-empty-state>
        }
        @case ('unknown') {
          <amc-empty-state
            icon="cloud_off"
            title="Your roles could not be loaded"
            message="The portal could not reach the Platform API. Try again in a moment."
          >
            <a mat-flat-button routerLink="/home">Try again</a>
          </amc-empty-state>
        }
        @default {
          <amc-empty-state
            icon="lock"
            title="You don't have access to this page"
            message="Your roles don't include this page. If you need it for your work, ask your team lead to request the role in Entra ID."
          >
            <a mat-flat-button routerLink="/home">Go to the overview</a>
          </amc-empty-state>
        }
      }
    </div>
  `,
})
export default class ForbiddenComponent {
  protected readonly auth = inject(AuthService);
  private readonly user = inject(CurrentUserStore);

  protected readonly state = computed(() => {
    const status = this.user.status();
    if (status === 'error') return 'unknown';
    return status === 'loaded' && !this.user.roles().length ? 'no-role' : 'page';
  });
}
