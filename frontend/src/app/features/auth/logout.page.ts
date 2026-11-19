import { Component, OnInit, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { AuthService } from '../../core/auth/auth.service';
import { APP_CONFIG, idleTimeoutMinutes } from '../../core/config/app-config';
import { AuthFrameComponent } from './auth-frame.component';

/**
 * Signed-out page. Opening it ends the session; with Entra ID it signs out of Microsoft as
 * well, and Entra brings the user back here.
 */
@Component({
  selector: 'amc-logout',
  imports: [AuthFrameComponent, MatButtonModule, MatProgressSpinnerModule],
  template: `
    @if (done()) {
      <amc-auth-frame [heading]="view.heading" [lead]="view.lead">
        <button mat-flat-button class="action" [disabled]="busy()" (click)="signInAgain()">
          Sign in again
        </button>
      </amc-auth-frame>
    } @else {
      <amc-auth-frame heading="Signing you out">
        <mat-spinner class="wait" diameter="28" aria-label="Signing you out" />
      </amc-auth-frame>
    }
  `,
  styles: `
    .action {
      width: 100%;
      height: 44px;
      margin-top: 24px;
      font-size: 15px;
    }
    .wait {
      margin: 20px auto 4px;
    }
  `,
})
export default class LogoutPage implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly last = this.auth.lastSignOut();
  private readonly minutes = idleTimeoutMinutes(inject(APP_CONFIG));

  protected readonly done = signal(false);
  protected readonly busy = signal(false);
  protected readonly view =
    this.last.reason === 'idle'
      ? {
          heading: 'You were signed out',
          lead: `Your session ended after ${this.minutes} minutes without activity.`,
        }
      : {
          heading: 'You have signed out',
          lead: 'If others use this computer, close the browser.',
        };

  async ngOnInit(): Promise<void> {
    // With Entra this leaves the page while someone is still signed in.
    await this.auth.signOut();
    this.done.set(true);
  }

  protected signInAgain(): void {
    const returnUrl = this.last.returnUrl;
    // Without Entra the sign-in page lists the sample users to choose from.
    if (this.auth.mode !== 'entra') {
      void this.router.navigate(['/login'], { queryParams: returnUrl ? { returnUrl } : {} });
      return;
    }
    this.busy.set(true);
    void this.auth.signIn(returnUrl).finally(() => this.busy.set(false));
  }
}
