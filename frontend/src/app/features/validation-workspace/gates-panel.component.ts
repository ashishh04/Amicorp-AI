import { Component, computed, inject } from '@angular/core';
import { MatIconModule } from '@angular/material/icon';

import { CheckFailure } from '../../core/api/portal.models';
import { StatementStore } from './statement.store';
import { APPROVAL_GATE } from './workspace.util';

/** The requirements-before-save gates (S1-S6); a failure jumps to its line. */
@Component({
  selector: 'amc-ws-gates',
  imports: [MatIconModule],
  template: `
    <section class="amc-panel" aria-labelledby="ws-gates-title">
      <header class="amc-panel-head">
        <h2 id="ws-gates-title">Submit gates</h2>
        <span class="amc-spacer"></span>
        <span
          class="amc-chip"
          [class.amc-chip--green]="!store.failingGates().length"
          [class.amc-chip--red]="store.failingGates().length"
        >
          {{ passing() }} of {{ total() }} pass
        </span>
      </header>
      <ul class="gates">
        @for (c of store.header()?.checks ?? []; track c.id) {
          <li [class.fail]="c.status === 'fail'">
            <mat-icon
              [class]="c.status === 'pass' ? 'amc-text-success' : 'amc-text-danger'"
              [attr.aria-label]="c.status === 'pass' ? 'Passes' : 'Fails'"
              >{{ c.status === 'pass' ? 'check_circle' : 'cancel' }}</mat-icon
            >
            <div class="body">
              <div>
                <b>{{ c.id }}</b> {{ c.desc }}
              </div>
              @if (c.id === approvalGate && c.failures.length) {
                <button type="button" class="amc-link-btn failure" (click)="showUnapproved()">
                  {{ c.failures.length }} line{{ c.failures.length === 1 ? '' : 's' }} not approved:
                  show them
                </button>
              } @else {
                @for (f of c.failures.slice(0, limit); track $index) {
                  @if (f.lineNo) {
                    <button type="button" class="amc-link-btn failure" (click)="jump(f)">
                      {{ f.message }}
                    </button>
                  } @else {
                    <div class="failure">{{ f.message }}</div>
                  }
                }
                @if (c.failures.length > limit) {
                  <div class="failure more">and {{ c.failures.length - limit }} more</div>
                }
              }
            </div>
          </li>
        }
      </ul>
    </section>
  `,
  styles: `
    .gates {
      margin: 0;
      padding: 6px 0;
      list-style: none;
    }
    li {
      display: flex;
      gap: 10px;
      padding: 7px 16px;
      font-size: 13px;
    }
    li.fail {
      background: var(--amc-surface-2);
    }
    mat-icon {
      flex: none;
      width: 18px;
      height: 18px;
      font-size: 18px;
    }
    .body {
      min-width: 0;
    }
    .failure {
      display: block;
      margin-top: 3px;
      font-size: 12px;
    }
    div.failure {
      color: var(--amc-danger);
    }
    div.more {
      color: var(--amc-muted);
    }
  `,
})
export class GatesPanelComponent {
  protected readonly store = inject(StatementStore);
  protected readonly approvalGate = APPROVAL_GATE;
  protected readonly limit = 4;
  protected readonly total = computed(() => this.store.header()?.checks.length ?? 0);
  protected readonly passing = computed(() => this.total() - this.store.failingGates().length);

  protected showUnapproved(): void {
    this.store.setFilter('unapproved');
  }

  /** The store reveals the line if the filter hides it; the grid pages to it. */
  protected jump(f: CheckFailure): void {
    this.store.select(f.lineNo ?? null, f.field ?? null);
  }
}
