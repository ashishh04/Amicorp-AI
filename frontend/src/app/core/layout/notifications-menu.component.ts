import { Component, effect, inject, untracked } from '@angular/core';
import { Router } from '@angular/router';
import { MatBadgeModule } from '@angular/material/badge';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';
import { MatTooltipModule } from '@angular/material/tooltip';

import { AmcTimePipe } from '../../shared/ui/pipes';
import { NotificationsStore, PortalNotification } from '../notifications/notifications.store';

const ICON: Record<PortalNotification['kind'], string> = {
  new: 'add_task',
  assigned: 'assignment_ind',
  update: 'update',
  alert: 'warning',
};

/** Bell with the unread count; new and reassigned cards also pop up as a toast. */
@Component({
  selector: 'amc-notifications-menu',
  imports: [
    MatBadgeModule,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatSnackBarModule,
    MatTooltipModule,
    AmcTimePipe,
  ],
  template: `
    <button
      mat-icon-button
      class="bell"
      [matMenuTriggerFor]="menu"
      [matBadge]="store.unread()"
      [matBadgeHidden]="!store.unread()"
      matBadgeSize="small"
      [attr.aria-label]="
        store.unread() ? store.unread() + ' unread notifications' : 'Notifications'
      "
      matTooltip="Notifications"
    >
      <mat-icon aria-hidden="true">notifications</mat-icon>
    </button>
    <mat-menu #menu="matMenu" xPosition="before" class="amc-notif-menu">
      <div
        tabindex="-1"
        class="head"
        (click)="$event.stopPropagation()"
        (keydown)="$event.stopPropagation()"
      >
        <b>Notifications</b>
        @if (store.unread()) {
          <button mat-button (click)="store.markAllRead()">Mark all read</button>
        }
      </div>
      @for (n of store.items(); track n.id) {
        <button mat-menu-item class="note" [class.unread]="!n.read" (click)="open(n)">
          <mat-icon [class]="'kind-' + n.kind">{{ icon[n.kind] }}</mat-icon>
          <span class="txt">
            <span class="msg">{{ n.message }}</span>
            <span class="sub">{{ n.title }} · {{ n.at | amcTime: 'relative' }}</span>
          </span>
        </button>
      } @empty {
        <p class="empty">
          You are up to date. New cards, assignments and escalations appear here as they happen.
        </p>
      }
    </mat-menu>
  `,
  styles: `
    .bell {
      color: #fff;
    }
    .head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      padding: 6px 8px 6px 16px;
      border-bottom: 1px solid var(--amc-border);
    }
    .note {
      height: auto;
      min-height: 56px;
      padding-top: 8px;
      padding-bottom: 8px;
    }
    .note.unread {
      background: #f5f8fc;
    }
    .note.unread .msg {
      font-weight: 700;
    }
    .txt {
      display: flex;
      flex-direction: column;
      min-width: 0;
      line-height: 1.3;
    }
    .msg {
      font-size: 13px;
    }
    .sub {
      overflow: hidden;
      color: var(--amc-muted);
      font-size: 12px;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .kind-alert {
      color: var(--amc-danger);
    }
    .kind-new,
    .kind-assigned {
      color: var(--amc-blue);
    }
    .empty {
      max-width: 300px;
      margin: 0;
      padding: 16px;
      color: var(--amc-muted);
      font-size: 13px;
    }
  `,
})
export class NotificationsMenuComponent {
  protected readonly store = inject(NotificationsStore);
  private readonly router = inject(Router);
  private readonly snackBar = inject(MatSnackBar);
  protected readonly icon = ICON;
  private lastToasted: string | null = null;

  constructor() {
    // Toast the newest card that is new to the queue or newly assigned.
    effect(() => {
      const latest = this.store.items()[0];
      if (!latest || latest.read || latest.id === this.lastToasted) return;
      if (latest.kind !== 'new' && latest.kind !== 'assigned') return;
      this.lastToasted = latest.id;
      untracked(() => {
        this.snackBar
          .open(`${latest.message}: ${latest.title}`, 'Open', { duration: 7000 })
          .onAction()
          .subscribe(() => this.open(latest));
      });
    });
  }

  protected open(n: PortalNotification): void {
    this.store.markRead(n.id);
    void this.router.navigate(['/cards', n.cardId]);
  }
}
