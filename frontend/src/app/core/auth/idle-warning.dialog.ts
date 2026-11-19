import { Component, Injector, computed, effect, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog, MatDialogModule, MatDialogRef } from '@angular/material/dialog';

import { AuthService } from './auth.service';
import { IdleService } from './idle.service';

/** The one-minute warning before the idle sign-out (IdleService). */
@Component({
  selector: 'amc-idle-warning',
  imports: [MatButtonModule, MatDialogModule],
  template: `
    <h2 mat-dialog-title>Your session is about to end</h2>
    <mat-dialog-content>
      <p class="text">
        You will be signed out in <b class="time">{{ time() }}</b> because there has been no
        activity.
      </p>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button (click)="signOut()">Sign out</button>
      <button mat-flat-button cdkFocusInitial (click)="idle.stay()">Stay signed in</button>
    </mat-dialog-actions>
  `,
  styles: `
    .text {
      margin: 0;
    }
    .time {
      font-variant-numeric: tabular-nums;
    }
  `,
})
export class IdleWarningDialog {
  protected readonly idle = inject(IdleService);
  private readonly auth = inject(AuthService);
  private readonly ref = inject<MatDialogRef<IdleWarningDialog>>(MatDialogRef);

  protected readonly time = computed(() => {
    const s = this.idle.secondsLeft() ?? 0;
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  });

  constructor() {
    // Closes itself once the session goes on (here or in another tab) or has ended.
    effect(() => {
      if (this.idle.secondsLeft() === null) this.ref.close();
    });
  }

  protected signOut(): void {
    this.ref.close();
    void this.auth.leave();
  }
}

/** Opens the warning; it lives here so the dialog code loads only when it is needed. */
export function openIdleWarning(injector: Injector): MatDialogRef<IdleWarningDialog> {
  return injector.get(MatDialog).open(IdleWarningDialog, {
    width: '440px',
    role: 'alertdialog',
    disableClose: true,
  });
}
