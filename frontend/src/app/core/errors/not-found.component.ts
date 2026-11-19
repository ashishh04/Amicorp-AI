import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { MatButtonModule } from '@angular/material/button';

import { EmptyStateComponent } from '../../shared/ui/layout.components';

@Component({
  selector: 'amc-not-found',
  imports: [RouterLink, MatButtonModule, EmptyStateComponent],
  template: `
    <div class="amc-page">
      <amc-empty-state
        icon="travel_explore"
        title="Page not found"
        message="The link may be out of date, or the card may have moved. Search for the card ID in the top bar."
      >
        <a mat-flat-button routerLink="/home">Go to the overview</a>
      </amc-empty-state>
    </div>
  `,
})
export default class NotFoundComponent {}
