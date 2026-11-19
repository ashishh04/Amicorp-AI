import { Component, computed, input } from '@angular/core';

import { HistoryEntry } from '../../core/api/portal.models';
import { PaginatorComponent, paged } from '../../shared/ui/paginator';
import { AmcTimePipe } from '../../shared/ui/pipes';
import { StateChipComponent } from '../../shared/ui/status.components';

/** History tab: every transition and action, newest first, as kept in the audit trail. */
@Component({
  selector: 'amc-card-history',
  imports: [AmcTimePipe, StateChipComponent, PaginatorComponent],
  template: `
    <section class="amc-panel">
      <table class="amc-table">
        <caption class="amc-sr-only">
          Card history, newest first
        </caption>
        <thead>
          <tr>
            <th scope="col">Time</th>
            <th scope="col">Actor</th>
            <th scope="col">Action</th>
            <th scope="col">State change</th>
            <th scope="col">Note</th>
          </tr>
        </thead>
        <tbody>
          @for (h of page.rows(); track $index) {
            <tr>
              <td class="amc-nowrap">
                <time [attr.datetime]="h.at">{{ h.at | amcTime }}</time>
              </td>
              <td class="amc-nowrap">{{ h.actor }}</td>
              <td>{{ h.action }}</td>
              <td>
                @if (h.to) {
                  <span class="change">
                    @if (h.from) {
                      <amc-state-chip [state]="h.from" />
                      <span class="arrow" aria-label="to">→</span>
                    }
                    <amc-state-chip [state]="h.to" />
                  </span>
                }
              </td>
              <td class="note">{{ h.note ?? '' }}</td>
            </tr>
          }
        </tbody>
      </table>
      <amc-paginator [paged]="page" label="History pages" />
    </section>
  `,
  styles: `
    .change {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }
    .arrow {
      color: var(--amc-faint);
    }
    .note {
      color: var(--amc-text-2);
    }
  `,
})
export class CardHistoryComponent {
  readonly history = input.required<HistoryEntry[]>();
  protected readonly entries = computed(() => [...this.history()].reverse());
  protected readonly page = paged(this.entries, 10);
}
