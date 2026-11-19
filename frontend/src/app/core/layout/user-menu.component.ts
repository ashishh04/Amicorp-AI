import { Component, computed, inject } from '@angular/core';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';

import { AvatarComponent } from '../../shared/ui/layout.components';
import { CALENDAR_ZONE } from '../../shared/ui/format';
import { AuthService } from '../auth/auth.service';
import { CurrentUserStore } from '../auth/current-user.store';
import { APP_ROLES } from '../auth/roles';
import { APP_CONFIG } from '../config/app-config';
import { MockSession, PERSONAS } from '../mock/mock-personas';
import { NotificationsStore } from '../notifications/notifications.store';
import { WorkCountsStore } from '../work/work-counts.store';

const ENVIRONMENTS: Record<string, string> = {
  local: 'Local',
  dev: 'Development',
  npr: 'Test (NPR)',
  prd: 'Production',
};

/** Account menu: who you are, your roles, teams and time zone; demo-user switch; sign out. */
@Component({
  selector: 'amc-user-menu',
  imports: [AvatarComponent, MatButtonModule, MatDividerModule, MatIconModule, MatMenuModule],
  template: `
    @if (user.user(); as u) {
      <button class="who" [matMenuTriggerFor]="menu" aria-label="Your account">
        <amc-avatar [name]="u.displayName" [size]="28" />
        <span class="who-name">{{ u.displayName }}</span>
        <mat-icon aria-hidden="true">expand_more</mat-icon>
      </button>

      <mat-menu #menu="matMenu" xPosition="before" class="amc-user-menu">
        <div
          tabindex="-1"
          class="profile"
          (click)="$event.stopPropagation()"
          (keydown)="$event.stopPropagation()"
        >
          <div class="profile-top">
            <amc-avatar [name]="u.displayName" [size]="40" />
            <div>
              <div class="profile-name">{{ u.displayName }}</div>
              <div class="amc-muted amc-small">{{ u.email }}</div>
            </div>
          </div>
          <dl class="amc-dl">
            <dt>Roles</dt>
            <dd>{{ u.roles.join(', ') || 'None' }}</dd>
            @if (u.teams?.length) {
              <dt>Teams</dt>
              <dd>{{ u.teams!.join(', ') }}</dd>
            }
            <dt>Data scope</dt>
            <dd>{{ u.dataScope.join(', ') || 'Configuration only' }}</dd>
            <dt>Times shown in</dt>
            <dd>{{ zone() }}</dd>
            <dt>Environment</dt>
            <dd>{{ environment }}</dd>
          </dl>
        </div>
        <mat-divider />
        @if (mockApi) {
          <button mat-menu-item [matMenuTriggerFor]="people">
            <mat-icon>switch_account</mat-icon>Switch user (demo)
          </button>
        }
        <button mat-menu-item (click)="signOut()"><mat-icon>logout</mat-icon>Sign out</button>
      </mat-menu>

      <mat-menu #people="matMenu" class="amc-persona-menu">
        @for (group of personaGroups; track group.role) {
          <div class="persona-group" aria-hidden="true">{{ group.role }}</div>
          @for (p of group.people; track p.id) {
            <button mat-menu-item (click)="switchTo(p.id)" [attr.aria-current]="p.id === u.id">
              <span class="persona">
                <amc-avatar [name]="p.displayName" [size]="24" />
                <span class="persona-name">{{ p.displayName }}</span>
                <span class="persona-team"
                  >{{ p.teams.join(', ')
                  }}{{ p.roles.length > 1 ? ' · ' + p.roles.join(' + ') : '' }}</span
                >
                @if (p.id === u.id) {
                  <mat-icon class="current" aria-label="Current user">check</mat-icon>
                }
              </span>
            </button>
          }
        }
      </mat-menu>
    }
  `,
  styles: `
    .who {
      display: flex;
      align-items: center;
      gap: 8px;
      height: 40px;
      padding: 0 4px 0 6px;
      border: 0;
      border-radius: 8px;
      background: transparent;
      color: #fff;
      font: inherit;
      cursor: pointer;
    }
    .who:hover {
      background: rgba(255, 255, 255, 0.08);
    }
    .who-name {
      font-size: 13px;
      font-weight: 600;
      white-space: nowrap;
    }
    .profile {
      width: 300px;
      padding: 14px 16px 12px;
      cursor: default;
    }
    .profile-top {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
    }
    .profile-name {
      font-size: 15px;
      font-weight: 700;
    }
    .persona-group {
      padding: 10px 16px 4px;
      color: var(--amc-muted);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .persona {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 280px;
    }
    .persona-name {
      font-weight: 600;
    }
    .persona-team {
      flex: 1;
      color: var(--amc-muted);
      font-size: 12px;
    }
    .current {
      margin: 0;
      color: var(--amc-blue);
    }
    @media (max-width: 1199.98px) {
      .who-name {
        display: none;
      }
    }
  `,
})
export class UserMenuComponent {
  protected readonly user = inject(CurrentUserStore);
  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);
  private readonly counts = inject(WorkCountsStore);
  private readonly notifications = inject(NotificationsStore);
  private readonly mock = inject(MockSession);
  private readonly config = inject(APP_CONFIG);

  protected readonly mockApi = !!this.config.mockApi;
  protected readonly environment = `${ENVIRONMENTS[this.config.environment] ?? this.config.environment}${
    this.config.mockApi ? ', demo data' : ''
  }`;
  protected readonly zone = computed(() => {
    const cal = this.user.calendar();
    return `${cal === 'HK' ? 'Hong Kong time' : 'Central European time'} (${CALENDAR_ZONE[cal]})`;
  });

  /** Demo users grouped by their main role, in the order of the LLD roles table. */
  protected readonly personaGroups = APP_ROLES.map((role) => ({
    role,
    people: PERSONAS.filter((p) => p.roles[p.roles.length - 1] === role),
  })).filter((g) => g.people.length);

  protected async switchTo(id: string): Promise<void> {
    if (id === this.user.user()?.id) return;
    this.mock.use(id);
    this.user.reset();
    this.counts.reset();
    this.notifications.clear();
    await this.user.load();
    void this.counts.load();
    // Re-create the page so every store reloads for the new user; guards run again.
    await this.router.navigateByUrl('/_reload', { skipLocationChange: true });
    await this.router.navigateByUrl('/home');
  }

  /** The signed-out page ends the session (and Entra's, when sign-in is on). */
  protected signOut(): void {
    void this.auth.leave();
  }
}
