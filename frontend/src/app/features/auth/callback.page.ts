import { Component, OnInit, inject } from '@angular/core';
import { Router } from '@angular/router';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { AuthService } from '../../core/auth/auth.service';
import { AuthFrameComponent } from './auth-frame.component';

/** Where Entra returns after sign-in (LLD: amc-portal-spa redirect URI /auth/callback). */
@Component({
  selector: 'amc-auth-callback',
  imports: [AuthFrameComponent, MatProgressSpinnerModule],
  template: `
    <amc-auth-frame heading="Signing you in">
      <mat-spinner class="wait" diameter="28" aria-label="Signing you in" />
    </amc-auth-frame>
  `,
  styles: `
    .wait {
      margin: 20px auto 4px;
    }
  `,
})
export default class CallbackPage implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  async ngOnInit(): Promise<void> {
    // MSAL normally moves on to the page the sign-in started from; this covers a direct visit.
    const signedIn = await this.auth.isSignedIn();
    void this.router.navigateByUrl(signedIn ? '/home' : '/login', { replaceUrl: true });
  }
}
