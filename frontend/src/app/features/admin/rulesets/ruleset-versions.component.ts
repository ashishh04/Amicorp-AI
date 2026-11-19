import { Component, computed, effect, inject, output, untracked } from '@angular/core';

import { RulesetVersion } from '../../../core/api/portal.models';
import { PaginatorComponent, paged } from '../../../shared/ui/paginator';
import { AmcLabelPipe, AmcTimePipe } from '../../../shared/ui/pipes';
import { RulesetsStore } from './rulesets.store';

const STATUS_TONE: Record<RulesetVersion['status'], string> = {
  draft: 'amber',
  approved: 'green',
  superseded: 'gray',
};

/** Version history: who drafted, who approved, from when it applied. */
@Component({
  selector: 'amc-ruleset-versions',
  imports: [PaginatorComponent, AmcLabelPipe, AmcTimePipe],
  template: `
    <div class="frame">
      <div class="scroll">
        <table class="amc-table">
          <thead>
            <tr>
              <th scope="col">Version</th>
              <th scope="col">Status</th>
              <th scope="col">Drafted by</th>
              <th scope="col">Drafted</th>
              <th scope="col">Approved by</th>
              <th scope="col">Effective from</th>
              <th scope="col">Note</th>
            </tr>
          </thead>
          <tbody>
            @for (v of page.rows(); track v.version) {
              <tr>
                <th scope="row">
                  <button
                    type="button"
                    class="amc-link-btn"
                    [attr.aria-label]="'View the rules of v' + v.version"
                    (click)="view.emit(v.version)"
                  >
                    v{{ v.version }}
                  </button>
                </th>
                <td>
                  <span [class]="'amc-chip amc-chip--' + tone[v.status]">{{
                    v.status | amcLabel
                  }}</span>
                </td>
                <td class="nowrap">{{ v.draftedBy.name }}</td>
                <td class="nowrap">{{ v.draftedAt | amcTime: 'short' }}</td>
                <td class="nowrap">{{ v.approvedBy?.name ?? '—' }}</td>
                <td class="nowrap">
                  {{ v.effectiveFrom ? (v.effectiveFrom | amcTime: 'date') : '—' }}
                </td>
                <td class="note">{{ v.note }}</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
      <amc-paginator [paged]="page" label="Version pages" />
    </div>
  `,
  styles: `
    .frame {
      border: 1px solid var(--amc-border);
      border-radius: var(--amc-radius);
    }
    .scroll {
      overflow-x: auto;
    }
    .nowrap {
      white-space: nowrap;
    }
    .note {
      min-width: 180px;
      color: var(--amc-text-2);
    }
  `,
})
export class RulesetVersionsComponent {
  protected readonly store = inject(RulesetsStore);
  protected readonly tone = STATUS_TONE;
  readonly view = output<number>();

  private readonly versions = computed(() => this.store.selected()?.versions ?? []);
  protected readonly page = paged(this.versions, 10);

  constructor() {
    let last: string | undefined;
    effect(() => {
      const key = this.store.selected()?.key;
      if (key === last) return;
      last = key;
      untracked(() => this.page.reset());
    });
  }
}
