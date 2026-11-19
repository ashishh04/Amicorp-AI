import { BreakpointObserver } from '@angular/cdk/layout';
import {
  Component,
  DestroyRef,
  Injector,
  OnInit,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { map } from 'rxjs';

import { CurrentUserStore } from '../auth/current-user.store';
import { IdleService } from '../auth/idle.service';
import { NotificationsStore } from '../notifications/notifications.store';
import { EventStreamService } from '../sse/event-stream.service';
import { WorkCountsStore } from '../work/work-counts.store';
import { GlobalSearchComponent } from './global-search.component';
import { NAV_GROUPS, NavItem } from './nav-items';
import { NotificationsMenuComponent } from './notifications-menu.component';
import { UserMenuComponent } from './user-menu.component';

const RAIL_KEY = 'amc.nav.rail';

function storedRail(): boolean {
  try {
    return localStorage.getItem(RAIL_KEY) === '1';
  } catch {
    return false;
  }
}

/**
 * The portal frame: top bar (search, notifications, account), grouped side
 * navigation filtered by role, and the routed page. Below 1100 px the navigation becomes an
 * overlay drawer; above it, it can collapse to an icon rail.
 */
@Component({
  selector: 'amc-shell',
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatButtonModule,
    MatIconModule,
    MatTooltipModule,
    GlobalSearchComponent,
    NotificationsMenuComponent,
    UserMenuComponent,
  ],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
})
export class ShellComponent implements OnInit {
  protected readonly user = inject(CurrentUserStore);
  private readonly events = inject(EventStreamService);
  private readonly counts = inject(WorkCountsStore);
  private readonly idle = inject(IdleService);
  private readonly injector = inject(Injector);

  /** Narrow screens get an overlay drawer instead of a fixed sidebar. */
  protected readonly overlay = toSignal(
    inject(BreakpointObserver)
      .observe('(max-width: 1099.98px)')
      .pipe(map((s) => s.matches)),
    { initialValue: false },
  );
  protected readonly navOpen = signal(false);
  protected readonly rail = signal(storedRail());
  protected readonly collapsed = computed(() => !this.overlay() && this.rail());

  protected readonly groups = computed(() =>
    NAV_GROUPS.map((g) => ({
      label: g.label,
      items: g.items.filter((item) => this.user.hasAnyRole(item.roles)),
    })).filter((g) => g.items.length),
  );

  private idleWarningOpen = false;

  constructor() {
    // Created now so it collects events from the first one on.
    inject(NotificationsStore);

    // A minute before the idle sign-out the warning opens over any page; it closes itself.
    effect(() => {
      if (this.idle.secondsLeft() === null || this.idleWarningOpen) return;
      this.idleWarningOpen = true;
      void import('../auth/idle-warning.dialog').then(({ openIdleWarning }) =>
        openIdleWarning(this.injector)
          .afterClosed()
          .subscribe(() => (this.idleWarningOpen = false)),
      );
    });
    inject(DestroyRef).onDestroy(() => this.idle.stop());
  }

  ngOnInit(): void {
    void this.user.load();
    void this.counts.load();
    // Every sign-in mode has a stream now: Entra and local sign-in exchange their token for an SSE ticket
    // (platform-api), the mock streams in the browser.
    this.events.start();
    this.idle.start();
  }

  protected badge(item: NavItem): number | null {
    const counts = this.counts.counts();
    if (!item.badge || !counts) return null;
    return counts[item.badge] || null;
  }

  protected toggleNav(): void {
    if (this.overlay()) {
      this.navOpen.update((open) => !open);
      return;
    }
    this.rail.update((r) => !r);
    try {
      localStorage.setItem(RAIL_KEY, this.rail() ? '1' : '0');
    } catch {
      // Private mode: the choice lasts until reload.
    }
  }

  protected onNavigate(): void {
    if (this.overlay()) this.navOpen.set(false);
  }

  protected skipToMain(event: Event): void {
    event.preventDefault();
    document.getElementById('main-content')?.focus();
  }
}
