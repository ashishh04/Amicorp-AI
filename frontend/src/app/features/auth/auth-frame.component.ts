import { Component, inject, input } from '@angular/core';

import { APP_CONFIG } from '../../core/config/app-config';

/** Named on the sign-in pages outside production, so no one mistakes a test system for PRD. */
const ENVIRONMENT: Partial<Record<string, string>> = { dev: 'Development', npr: 'Test' };

/**
 * Frame of the sign-in pages: one card in the middle of a light page, with the Amicorp logo, the
 * platform name (UDAP, as on the landing page) and the portal's name at its top, then the heading, one lead line, the page's content and an optional note.
 * The use notice sits under the card.
 */
@Component({
  selector: 'amc-auth-frame',
  template: `
    <main class="main">
      <section class="card" aria-labelledby="amc-auth-heading">
        <div class="body">
          <div class="brand">
            <img src="assets/amicorp-logo.png" alt="Amicorp" width="44" height="44" />
            <span class="names">
              <span class="product">UDAP</span>
              <span class="org">Work Card Portal</span>
            </span>
            @if (environment) {
              <span class="env">{{ environment }}</span>
            }
          </div>
          <h1 id="amc-auth-heading">{{ heading() }}</h1>
          @if (lead()) {
            <p class="lead">{{ lead() }}</p>
          }
          <ng-content />
        </div>
        @if (note()) {
          <p class="note">{{ note() }}</p>
        }
      </section>
      <p class="legal">© {{ year }} Amicorp. For authorised users only.</p>
    </main>
  `,
  styleUrl: './auth-frame.component.scss',
})
export class AuthFrameComponent {
  readonly heading = input.required<string>();
  readonly lead = input<string>();
  readonly note = input<string>();

  protected readonly environment = ENVIRONMENT[inject(APP_CONFIG).environment];
  protected readonly year = new Date().getFullYear();
}
